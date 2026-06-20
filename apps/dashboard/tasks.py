import random
from celery import shared_task
from django.utils import timezone
import logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from datetime import timedelta
from decimal import Decimal
from .models import TradingPair, PriceTick, Wallet, Trade, BotSession, BotTrade

logger = logging.getLogger(__name__)


# Define price ranges per symbol — each lives in its own world
PAIR_PRICE_RANGES = {
    "OTV19": (10.0, 99.0),  # low range, tight
    "OTV22": (100.0, 499.0),  # mid range
    "OTV59": (500.0, 999.0),  # high range
    "OTV90": (1000.0, 4999.0),  # very high
    "OTV115": (5000.0, 9999.0),  # extreme
}

DEFAULT_PRICE_RANGE = (10.0, 99.0)


@shared_task
def update_prices():
    channel_layer = get_channel_layer()
    pairs = list(TradingPair.objects.filter(is_active=True))
    ticks = []

    for pair in pairs:
        price_range = PAIR_PRICE_RANGES.get(pair.symbol, DEFAULT_PRICE_RANGE)
        low, high = price_range

        last_tick = pair.ticks.first()
        if last_tick:
            last_price = float(last_tick.price)
        else:
            # each pair seeds its own starting price within its range
            rng = random.Random(pair.symbol)
            last_price = rng.uniform(low, high)

        volatility = float(pair.volatility)

        # scale change to the price range so high-value pairs move proportionally
        change = random.gauss(0, (high - low) * volatility * 0.005)

        # clamp within the pair's own range
        new_price = round(max(low, min(high, last_price + change)), 4)

        ticks.append(PriceTick(pair=pair, price=new_price))

        async_to_sync(channel_layer.group_send)(
            f"price_{pair.symbol}",
            {
                "type": "price_update",
                "symbol": pair.symbol,
                "price": str(new_price),
                "time": timezone.now().strftime("%H:%M:%S"),
            },
        )

    PriceTick.objects.bulk_create(ticks)


@shared_task
def cleanup_old_ticks():
    """Keep only the last 100 ticks per pair — runs every 10 seconds."""
    pairs = TradingPair.objects.filter(is_active=True)

    for pair in pairs:
        keep_ids = (
            PriceTick.objects.filter(pair=pair)
            .order_by("-timestamp")
            .values_list("id", flat=True)[:100]
        )
        PriceTick.objects.filter(pair=pair).exclude(id__in=list(keep_ids)).delete()


@shared_task
def resolve_trades():
    channel_layer = get_channel_layer()

    open_trades = Trade.objects.filter(status="OPEN").select_related(
        "pair", "user", "user__wallet"
    )

    for trade in open_trades:
        try:
            latest_tick = PriceTick.objects.filter(pair=trade.pair).first()
            if not latest_tick:
                continue

            current_price = float(latest_tick.price)
            return_balance = 0
            resolved = False

            if trade.duration_unit == "ticks":
                trade.ticks_elapsed += 1
                trade.save(update_fields=["ticks_elapsed"])
                if trade.ticks_elapsed < trade.duration:
                    continue
                resolved = True

            elif trade.duration_unit == "seconds":
                if trade.expires_at and timezone.now() < trade.expires_at:
                    continue
                resolved = True

            if not resolved:
                continue

            # --- natural result from price movement ---
            entry = float(trade.entry_price)
            natural_result = determine_result(trade, entry, current_price)

            # --- favourability: house edge control ---
            # favourability = how often the house OVERRIDES to benefit itself
            # e.g. favourability=30 means 30% of the time the house forces a loss
            # regardless of natural outcome — giving the house its edge
            house = trade.pair.house_settings
            house_edge = (
                house.favourability
            )  # rename this field to house_edge in your model
            # 0 = pure natural result, 100 = house always wins
            rng = random.randint(1, 100)

            if rng <= house_edge:
                # house overrides — user loses regardless of natural result
                final_result = "LOST"
            else:
                # natural market result applies
                final_result = natural_result

            # --- update trade ---
            trade.exit_price = current_price
            trade.status = final_result
            trade.save(update_fields=["exit_price", "status"])

            # --- update wallet ---

            wallet = Wallet.objects.get(user=trade.user)

            return_balance = wallet.get_balance(
                mode="demo" if trade.is_demo else "live"
            )

            if final_result == "WON":
                payout = round(
                    float(trade.stake) * (1 + float(trade.payout_pct) / 100), 2
                )
                return_balance = wallet.credit(
                    payout, mode="demo" if trade.is_demo else "live"
                )

            # --- notify user ---
            async_to_sync(channel_layer.group_send)(
                f"trade_{trade.user.id}",
                {
                    "type": "trade_result",
                    "trade_id": trade.id,
                    "status": final_result,
                    "exit_price": str(current_price),
                    "entry_price": str(trade.entry_price),
                    "stake": str(trade.stake),
                    "payout": str(trade.payout) if final_result == "WON" else "0",
                    "profit": str(trade.profit),
                    "balance": str(return_balance),
                    "pair": trade.pair.symbol,
                    "direction": trade.direction,
                },
            )

        except Exception as e:
            logger.error(f"Error resolving trade {trade.id}: {e}")
            continue


def determine_result(trade, entry, exit_price):
    """
    Pure result based on price movement — before favourability is applied.
    """
    direction = trade.direction

    if direction == "RISE":
        return "WON" if exit_price > entry else "LOST"

    elif direction == "FALL":
        return "WON" if exit_price < entry else "LOST"

    elif direction == "OVER":
        barrier = float(trade.barrier) if trade.barrier else entry
        return "WON" if exit_price > barrier else "LOST"

    elif direction == "UNDER":
        barrier = float(trade.barrier) if trade.barrier else entry
        return "WON" if exit_price < barrier else "LOST"

    elif direction == "ACCUM":
        # accumulator wins as long as price stays within range
        lower = entry * 0.97
        upper = entry * 1.03
        return "WON" if lower <= exit_price <= upper else "LOST"

    return "LOST"


# BOT TRADING


def decide_trade_result(session, trade_number, total_trades, current_pnl):
    template = session.bot_key.template
    settings_ = template.get_settings(session.is_demo)  # ← key change

    house_outcome = settings_["house_outcome"]
    base_win_rate = settings_["base_win_rate"]
    breakeven_min = float(settings_["breakeven_min_pct"]) / 100
    breakeven_max = float(settings_["breakeven_max_pct"]) / 100

    stake = float(session.stake_per_trade)
    profit_pct = float(template.profit_pct) / 100
    total_staked = stake * total_trades
    progress = trade_number / total_trades
    pnl_pct = current_pnl / total_staked if total_staked > 0 else 0

    win_rate = base_win_rate

    if progress >= 0.7:
        if house_outcome == "PROFIT":
            win_rate = min(85, base_win_rate + 25) if pnl_pct < 0.05 else base_win_rate
        elif house_outcome == "LOSS":
            win_rate = max(20, base_win_rate - 30) if pnl_pct > -0.05 else base_win_rate
        elif house_outcome == "BREAKEVEN":
            if pnl_pct > breakeven_max:
                win_rate = max(20, base_win_rate - 25)
            elif pnl_pct < breakeven_min:
                win_rate = min(85, base_win_rate + 25)

    return "WON" if random.randint(1, 100) <= win_rate else "LOST"


def get_trade_direction(bot_type):
    if bot_type == "RISE_FALL":
        return random.choice(["RISE", "FALL"])
    elif bot_type == "OVER_UNDER":
        return random.choice(["OVER", "UNDER"])
    elif bot_type == "ACCUMULATOR":
        return "ACCUM"
    return "RISE"


@shared_task
def execute_bot_trade(session_id, trade_number):
    """
    Executes a single trade for the session.
    Schedules the next trade after the interval.
    This way each trade fires independently — no sleep(), no blocking.
    """
    channel_layer = get_channel_layer()

    try:
        session = BotSession.objects.select_related(
            "bot_key__template", "pair", "user", "user__wallet"
        ).get(id=session_id)
    except BotSession.DoesNotExist:
        logger.error(f"BotSession {session_id} not found")
        return

    # cancelled mid-run
    if session.status == "CANCELLED":
        return

    template = session.bot_key.template
    total_trades = session.total_trades
    stake = Decimal(str(session.stake_per_trade))
    profit_pct = Decimal(str(template.profit_pct)) / 100

    # get current P&L from existing trades
    from django.db.models import Sum

    existing = session.bot_trades.aggregate(total=Sum("profit"))
    current_pnl = float(existing["total"] or 0)

    # get latest price
    latest_tick = PriceTick.objects.filter(pair=session.pair).first()
    entry_price = latest_tick.price if latest_tick else Decimal("50.00")

    direction = get_trade_direction(template.bot_type)
    wallet = Wallet.objects.get(user=session.user)
    mode = "demo" if session.is_demo else "live"
    wallet.debit(float(stake), mode=mode)

    # notify: trade OPENING (shows as "Running..." in feed)
    async_to_sync(channel_layer.group_send)(
        f"bot_{session.user.id}",
        {
            "type": "bot_trade_open",
            "trade_number": trade_number,
            "total_trades": total_trades,
            "direction": direction,
            "entry_price": str(entry_price),
            "stake": str(stake),
            "pair": session.pair.symbol,
            "price": str(entry_price),
        },
    )

    # simulate trade duration (3 seconds per trade feels natural)
    TRADE_DURATION = 3  # seconds — trade shows as "running" for this long

    # schedule trade resolution after TRADE_DURATION seconds
    resolve_bot_trade.apply_async(
        args=[session_id, trade_number, direction, str(entry_price), current_pnl],
        countdown=TRADE_DURATION,
    )

    # schedule next trade after the interval
    interval = (session.timeframe * 60) / total_trades
    if trade_number < total_trades:
        execute_bot_trade.apply_async(
            args=[session_id, trade_number + 1],
            countdown=interval,
        )


@shared_task
def resolve_bot_trade(
    session_id, trade_number, direction, entry_price_str, current_pnl
):
    """
    Resolves a single trade — determines win/loss, updates wallet,
    saves to DB, notifies via WebSocket.
    """
    channel_layer = get_channel_layer()

    try:
        session = BotSession.objects.select_related(
            "bot_key__template", "pair", "user", "user__wallet"
        ).get(id=session_id)
    except BotSession.DoesNotExist:
        return

    if session.status == "CANCELLED":
        return

    template = session.bot_key.template
    total_trades = session.total_trades
    stake = Decimal(str(session.stake_per_trade))
    profit_pct = Decimal(str(template.profit_pct)) / 100
    entry_price = Decimal(entry_price_str)

    # get latest price as exit
    latest_tick = PriceTick.objects.filter(pair=session.pair).first()
    exit_price = latest_tick.price if latest_tick else entry_price

    result = decide_trade_result(session, trade_number, total_trades, current_pnl)

    if result == "WON":
        trade_profit = round(stake * profit_pct, 2)
    else:
        trade_profit = -stake

    # save trade
    BotTrade.objects.create(
        session=session,
        trade_number=trade_number,
        direction=direction,
        entry_price=entry_price,
        exit_price=exit_price,
        stake=stake,
        profit=trade_profit,
        result=result,
    )

    # update wallet
    wallet = Wallet.objects.get(user=session.user)
    mode = "demo" if session.is_demo else "live"
    if result == "WON":
        wallet.credit(float(stake + trade_profit), mode=mode)
    else:
        # wallet.debit(float(stake), mode=mode) already debited at trade open, so no action needed here
        pass

    # update session running totals
    from django.db.models import Sum, Count

    agg = session.bot_trades.aggregate(
        total=Count("id"),
        won=Count(
            "id", filter=__import__("django.db.models", fromlist=["Q"]).Q(result="WON")
        ),
        pnl=Sum("profit"),
    )
    new_pnl = float(agg["pnl"] or 0)

    # notify: trade RESOLVED
    async_to_sync(channel_layer.group_send)(
        f"bot_{session.user.id}",
        {
            "type": "bot_trade_result",
            "trade_number": trade_number,
            "total_trades": total_trades,
            "direction": direction,
            "result": result,
            "entry_price": str(entry_price),
            "exit_price": str(exit_price),
            "stake": str(stake),
            "profit": str(trade_profit),
            "current_pnl": str(new_pnl),
            "balance": str(wallet.get_balance(mode=mode)),
            "pair": session.pair.symbol,
        },
    )

    # check if this was the last trade
    if trade_number == total_trades:
        finalize_bot_session.apply_async(
            args=[session_id],
            countdown=2,  # short delay so last trade result renders first
        )


@shared_task
def finalize_bot_session(session_id):
    """Wraps up the session, computes final outcome, notifies user."""
    channel_layer = get_channel_layer()

    try:
        session = BotSession.objects.select_related(
            "bot_key__template", "user", "user__wallet"
        ).get(id=session_id)
    except BotSession.DoesNotExist:
        return

    from django.db.models import Sum, Count, Q

    agg = session.bot_trades.aggregate(
        total=Count("id"),
        won=Count("id", filter=Q(result="WON")),
        lost=Count("id", filter=Q(result="LOST")),
        gross_profit=Sum("profit", filter=Q(result="WON")),
        gross_loss=Sum("profit", filter=Q(result="LOST")),
        net_pnl=Sum("profit"),
    )

    net_pnl = float(agg["net_pnl"] or 0)
    total_staked = float(session.stake_per_trade) * (agg["total"] or 0)
    pnl_pct = net_pnl / total_staked if total_staked > 0 else 0

    template = session.bot_key.template
    breakeven_min = float(template.breakeven_min_pct) / 100
    breakeven_max = float(template.breakeven_max_pct) / 100

    if breakeven_min <= pnl_pct <= breakeven_max:
        final_outcome = "BREAKEVEN"
    elif net_pnl > 0:
        final_outcome = "PROFIT"
    else:
        final_outcome = "LOSS"

    session.trades_won = agg["won"] or 0
    session.trades_lost = agg["lost"] or 0
    session.gross_profit = agg["gross_profit"] or 0
    session.gross_loss = abs(agg["gross_loss"] or 0)
    session.net_pnl = net_pnl
    session.outcome = final_outcome
    session.status = "COMPLETED"
    session.completed_at = timezone.now()
    session.save()

    wallet = Wallet.objects.get(user=session.user)

    session.bot_key.total_uses += 1
    session.bot_key.save(update_fields=["total_uses"])

    async_to_sync(channel_layer.group_send)(
        f"bot_{session.user.id}",
        {
            "type": "bot_session_complete",
            "outcome": final_outcome,
            "total_trades": agg["total"],
            "trades_won": agg["won"],
            "trades_lost": agg["lost"],
            "net_pnl": str(net_pnl),
            "total_staked": str(total_staked),
            "win_rate": str(round(((agg["won"] or 0) / (agg["total"] or 1)) * 100, 1)),
            "balance": str(
                wallet.get_balance(mode="demo" if session.is_demo else "live")
            ),
        },
    )


@shared_task
def run_bot_session(session_id):
    try:
        session = BotSession.objects.select_related("bot_key__template").get(
            id=session_id
        )
    except BotSession.DoesNotExist:
        logger.error(f"BotSession {session_id} not found")
        return

    template = session.bot_key.template
    settings_ = template.get_settings(session.is_demo)  # ← key change

    total_trades = int((session.timeframe / 5) * template.trades_per_5min)

    session.total_trades = total_trades
    session.status = "RUNNING"
    session.house_outcome = settings_["house_outcome"]
    session.save(update_fields=["total_trades", "status", "house_outcome"])

    execute_bot_trade.apply_async(args=[session_id, 1], countdown=1)
