import random
import logging
from decimal import Decimal
from celery import shared_task
from django.utils import timezone
from django.db.models import Sum, Count, Q
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import BotSession, BotTrade
from apps.dashboard.models import PriceTick, Wallet

logger = logging.getLogger(__name__)

TRADE_DURATION = 3  # seconds a trade shows as "running" before resolving


def decide_trade_result(session, trade_number, total_trades, current_pnl):
    house_outcome = session.house_outcome
    base_win_rate = session.base_win_rate
    breakeven_min = float(session.breakeven_min_pct) / 100
    breakeven_max = float(session.breakeven_max_pct) / 100

    stake = float(session.stake_per_trade)
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
def run_bot_session(session_id):
    """Entry point — session is already fully configured at creation."""
    try:
        session = BotSession.objects.get(id=session_id)
    except BotSession.DoesNotExist:
        logger.error(f"BotSession {session_id} not found")
        return

    execute_bot_trade.apply_async(args=[session_id, 1], countdown=1)


@shared_task
def execute_bot_trade(session_id, trade_number):
    channel_layer = get_channel_layer()

    try:
        session = BotSession.objects.select_related(
            "bot_key", "pair", "user", "user__wallet"
        ).get(id=session_id)
    except BotSession.DoesNotExist:
        logger.error(f"BotSession {session_id} not found")
        return

    if session.status == "CANCELLED":
        return

    total_trades = session.total_trades
    stake = Decimal(str(session.stake_per_trade))

    latest_tick = PriceTick.objects.filter(pair=session.pair).first()
    entry_price = latest_tick.price if latest_tick else Decimal("50.00")

    direction = get_trade_direction(session.bot_key.bot_type)

    wallet = Wallet.objects.get(user=session.user)
    mode = "demo" if session.is_demo else "live"
    wallet.debit(float(stake), mode=mode)

    try:
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
            },
        )
    except Exception as e:
        logger.error(
            f"[BOT] Failed to send trade_open WS for trade {trade_number}: {e}"
        )

    resolve_bot_trade.apply_async(
        args=[session_id, trade_number, direction, str(entry_price)],
        countdown=TRADE_DURATION,
    )

    interval = (session.timeframe * 60) / total_trades
    if trade_number < total_trades:
        execute_bot_trade.apply_async(
            args=[session_id, trade_number + 1],
            countdown=interval,
        )


@shared_task
def resolve_bot_trade(session_id, trade_number, direction, entry_price_str):
    channel_layer = get_channel_layer()

    try:
        session = BotSession.objects.select_related(
            "bot_key", "pair", "user", "user__wallet"
        ).get(id=session_id)
    except BotSession.DoesNotExist:
        return

    if session.status == "CANCELLED":
        return

    total_trades = session.total_trades
    stake = Decimal(str(session.stake_per_trade))
    profit_pct = Decimal(str(session.profit_pct)) / 100
    entry_price = Decimal(entry_price_str)

    latest_tick = PriceTick.objects.filter(pair=session.pair).first()
    exit_price = latest_tick.price if latest_tick else entry_price

    existing = session.bot_trades.aggregate(total=Sum("profit"))
    current_pnl = float(existing["total"] or 0)

    result = decide_trade_result(session, trade_number, total_trades, current_pnl)

    if result == "WON":
        trade_profit = round(stake * profit_pct, 2)
    else:
        trade_profit = -stake

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

    wallet = Wallet.objects.get(user=session.user)
    mode = "demo" if session.is_demo else "live"
    if result == "WON":
        wallet.credit(float(stake + trade_profit), mode=mode)

    agg = session.bot_trades.aggregate(pnl=Sum("profit"))
    new_pnl = float(agg["pnl"] or 0)

    try:
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
                "balance": str(wallet.get_balance(mode)),
                "pair": session.pair.symbol,
            },
        )
    except Exception as e:
        logger.error(
            f"[BOT] Failed to send trade_result WS for trade {trade_number}: {e}"
        )

    if trade_number == total_trades:
        finalize_bot_session.apply_async(args=[session_id], countdown=2)


@shared_task
def finalize_bot_session(session_id):
    channel_layer = get_channel_layer()

    try:
        session = BotSession.objects.select_related(
            "bot_key", "user", "user__wallet"
        ).get(id=session_id)
    except BotSession.DoesNotExist:
        return

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

    breakeven_min = float(session.breakeven_min_pct) / 100
    breakeven_max = float(session.breakeven_max_pct) / 100

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

    session.bot_key.total_uses += 1
    session.bot_key.save(update_fields=["total_uses"])

    wallet = Wallet.objects.get(user=session.user)
    mode = "demo" if session.is_demo else "live"

    try:
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
                "win_rate": str(
                    round(((agg["won"] or 0) / (agg["total"] or 1)) * 100, 1)
                ),
                "balance": str(wallet.get_balance(mode)),
            },
        )
    except Exception as e:
        logger.error(f"[BOT] Failed to send session_complete WS: {e}")
