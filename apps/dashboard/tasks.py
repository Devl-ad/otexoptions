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

            result_balance = wallet.get_balance(
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
    """
    Decide win/loss per trade — random but nudged toward house outcome
    as the session approaches its end.
    """
    template = session.bot_key.template
    house_outcome = session.house_outcome
    base_win_rate = template.base_win_rate  # e.g. 55

    stake = float(session.stake_per_trade)
    profit_pct = float(template.profit_pct) / 100  # 0.1563
    breakeven_min = float(template.breakeven_min_pct) / 100
    breakeven_max = float(template.breakeven_max_pct) / 100
    total_staked = stake * total_trades

    # how far through the session are we (0.0 → 1.0)
    progress = trade_number / total_trades

    # remaining trades
    remaining = total_trades - trade_number

    # current P&L as % of total staked
    pnl_pct = current_pnl / total_staked if total_staked > 0 else 0

    win_rate = base_win_rate  # start with base

    # in the last 30% of trades start nudging toward house outcome
    if progress >= 0.7:
        if house_outcome == "PROFIT":
            # need to be in profit — boost win rate if behind
            if pnl_pct < 0.05:
                win_rate = min(85, base_win_rate + 25)
            else:
                win_rate = base_win_rate  # already profitable, stay natural

        elif house_outcome == "LOSS":
            # need to be in loss — reduce win rate
            if pnl_pct > -0.05:
                win_rate = max(20, base_win_rate - 30)
            else:
                win_rate = base_win_rate  # already losing, stay natural

        elif house_outcome == "BREAKEVEN":
            # steer toward breakeven range
            if pnl_pct > breakeven_max:
                win_rate = max(20, base_win_rate - 25)  # too profitable, lose more
            elif pnl_pct < breakeven_min:
                win_rate = min(85, base_win_rate + 25)  # too low, win more
            else:
                win_rate = base_win_rate  # in range, stay natural

    return "WON" if random.randint(1, 100) <= win_rate else "LOST"


def get_trade_direction(bot_type):
    """Pick a direction based on bot type."""
    if bot_type == "RISE_FALL":
        return random.choice(["RISE", "FALL"])
    elif bot_type == "OVER_UNDER":
        return random.choice(["OVER", "UNDER"])
    elif bot_type == "ACCUMULATOR":
        return "ACCUM"
    return "RISE"


@shared_task(bind=True)
def run_bot_session(self, session_id):
    """
    Main bot task — executes all trades for a session sequentially.
    Each trade fires, waits, resolves, then notifies via WebSocket.
    """
    channel_layer = get_channel_layer()

    try:
        session = BotSession.objects.select_related(
            "bot_key__template", "pair", "user", "user__wallet"
        ).get(id=session_id)
    except BotSession.DoesNotExist:
        logger.error(f"BotSession {session_id} not found")
        return

    template = session.bot_key.template
    total_trades = int((session.timeframe / 5) * template.trades_per_5min)
    session.total_trades = total_trades
    session.status = "RUNNING"
    session.house_outcome = template.house_outcome
    session.save(update_fields=["total_trades", "status", "house_outcome"])

    # interval between trades in seconds
    trade_interval = (session.timeframe * 60) / total_trades

    stake = Decimal(str(session.stake_per_trade))
    profit_pct = Decimal(str(template.profit_pct)) / 100
    current_pnl = Decimal("0")
    trades_won = 0
    trades_lost = 0

    wallet = Wallet.objects.get(user=session.user)

    for trade_number in range(1, total_trades + 1):
        try:
            # get latest price
            latest_tick = PriceTick.objects.filter(pair=session.pair).first()
            entry_price = latest_tick.price if latest_tick else Decimal("50.00")

            direction = get_trade_direction(template.bot_type)

            result = decide_trade_result(
                session, trade_number, total_trades, float(current_pnl)
            )

            # calculate profit/loss
            if result == "WON":
                trade_profit = round(stake * profit_pct, 2)
                trades_won += 1
                current_pnl += trade_profit
                wallet.credit(
                    float(stake + trade_profit),
                    mode="demo" if session.is_demo else "live",
                )
            else:
                trade_profit = -stake
                trades_lost += 1
                current_pnl -= stake
                wallet.debit(float(stake), mode="demo" if session.is_demo else "live")

            # save trade
            bot_trade = BotTrade.objects.create(
                session=session,
                trade_number=trade_number,
                direction=direction,
                entry_price=entry_price,
                exit_price=entry_price,  # for bots exit = entry (tick based)
                stake=stake,
                profit=trade_profit,
                result=result,
            )

            # notify user via WebSocket
            async_to_sync(channel_layer.group_send)(
                f"bot_{session.user.id}",
                {
                    "type": "bot_trade_update",
                    "trade_number": trade_number,
                    "total_trades": total_trades,
                    "direction": direction,
                    "result": result,
                    "stake": str(stake),
                    "profit": str(trade_profit),
                    "current_pnl": str(current_pnl),
                    "balance": str(
                        wallet.get_balance(
                            float(stake), mode="demo" if session.is_demo else "live"
                        )
                    ),
                    "pair": session.pair.symbol,
                    "entry_price": str(entry_price),
                },
            )

            # wait before next trade
            import time

            time.sleep(trade_interval)

        except Exception as e:
            logger.error(f"Bot trade {trade_number} error: {e}")
            continue

    # --- session complete ---
    total_staked = stake * total_trades
    pnl_pct = float(current_pnl / total_staked) if total_staked > 0 else 0

    breakeven_min = float(template.breakeven_min_pct) / 100
    breakeven_max = float(template.breakeven_max_pct) / 100

    if breakeven_min <= pnl_pct <= breakeven_max:
        final_outcome = "BREAKEVEN"
    elif current_pnl > 0:
        final_outcome = "PROFIT"
    else:
        final_outcome = "LOSS"

    session.trades_won = trades_won
    session.trades_lost = trades_lost
    session.gross_profit = sum(
        t.profit for t in session.bot_trades.filter(result="WON")
    )
    session.gross_loss = abs(
        sum(t.profit for t in session.bot_trades.filter(result="LOST"))
    )
    session.net_pnl = current_pnl
    session.outcome = final_outcome
    session.status = "COMPLETED"
    session.completed_at = timezone.now()
    session.save()

    # notify session complete
    async_to_sync(channel_layer.group_send)(
        f"bot_{session.user.id}",
        {
            "type": "bot_session_complete",
            "outcome": final_outcome,
            "total_trades": total_trades,
            "trades_won": trades_won,
            "trades_lost": trades_lost,
            "net_pnl": str(current_pnl),
            "total_staked": str(total_staked),
            "win_rate": str(round((trades_won / total_trades) * 100, 1)),
            "balance": str(wallet.current_balance),
        },
    )

    # increment key usage
    session.bot_key.total_uses += 1
    session.bot_key.save(update_fields=["total_uses"])
