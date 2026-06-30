import random
from celery import shared_task
from django.utils import timezone
import logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from datetime import timedelta
from decimal import Decimal
from .models import TradingPair, PriceTick, Wallet, Trade
from apps.bot.models import BotSession, BotTrade

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
