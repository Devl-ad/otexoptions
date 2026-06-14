# dashboard/management/commands/seed_pairs.py

TRADING_PAIRS = [
    {
        "symbol": "OTV19",
        "name": "OTEX Volatility 19",
        "category": "Synthetic",
        "volatility": 0.19,
        "tick_speed": 1.0,
    },
    {
        "symbol": "OTV22",
        "name": "OTEX Volatility 22",
        "category": "Synthetic",
        "volatility": 0.22,
        "tick_speed": 1.0,
    },
    {
        "symbol": "OTV59",
        "name": "OTEX Volatility 59",
        "category": "Synthetic",
        "volatility": 0.59,
        "tick_speed": 0.8,
    },
    {
        "symbol": "OTV90",
        "name": "OTEX Volatility 90",
        "category": "Synthetic",
        "volatility": 0.90,
        "tick_speed": 0.6,
    },
    {
        "symbol": "OTV115",
        "name": "OTEX Volatility 115",
        "category": "Synthetic",
        "volatility": 1.15,
        "tick_speed": 0.5,
    },
]

from django.core.management.base import BaseCommand
from apps.dashboard.models import TradingPair


class Command(BaseCommand):
    help = "Seed trading pairs"

    def handle(self, *args, **kwargs):
        for pair in TRADING_PAIRS:
            obj, created = TradingPair.objects.update_or_create(
                symbol=pair["symbol"],
                defaults={
                    "name": pair["name"],
                    "category": pair["category"],
                    "volatility": pair["volatility"],
                    "tick_speed": pair["tick_speed"],
                },
            )
            status = "✅ created" if created else "🔄 updated"
            self.stdout.write(f'{status}: {pair["symbol"]}')
