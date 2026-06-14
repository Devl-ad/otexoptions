import time
import random
from django.core.management.base import BaseCommand
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.dashboard.models import TradingPair, PriceTick


class Command(BaseCommand):
    help = "Run the live price engine"

    def handle(self, *args, **kwargs):
        channel_layer = get_channel_layer()

        pairs = list(TradingPair.objects.filter(is_active=True))
        prices = {p.symbol: random.uniform(40, 60) for p in pairs}
        last_update = {p.symbol: 0 for p in pairs}

        cycle = 0

        self.stdout.write(self.style.SUCCESS("Price engine started..."))

        try:
            while True:
                cycle += 1
                now = time.time()

                ticks_to_create = []

                # refresh pairs every 10 seconds
                if cycle % 10 == 0:
                    pairs = list(TradingPair.objects.filter(is_active=True))

                for pair in pairs:
                    if now - last_update.get(pair.symbol, 0) < float(pair.tick_speed):
                        continue

                    current = prices[pair.symbol]

                    change = random.gauss(0, float(pair.volatility) * 0.1)

                    new_price = round(max(1.00, min(100.00, current + change)), 2)

                    prices[pair.symbol] = new_price
                    last_update[pair.symbol] = now

                    ticks_to_create.append(PriceTick(pair=pair, price=new_price))

                    async_to_sync(channel_layer.group_send)(
                        f"price_{pair.symbol}",
                        {
                            "type": "price_update",
                            "symbol": pair.symbol,
                            "price": str(new_price),
                            "time": timezone.now().strftime("%H:%M:%S"),
                        },
                    )

                    self.stdout.write(f"{pair.symbol}: {new_price}")

                # bulk insert
                if ticks_to_create:
                    PriceTick.objects.bulk_create(ticks_to_create)

                # cleanup every 60 cycles (~1 min)
                if cycle % 60 == 0:
                    PriceTick.cleanup_old(keep_minutes=60)

                time.sleep(1)

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Price engine stopped"))
