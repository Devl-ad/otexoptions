from django.core.management.base import BaseCommand
from apps.bot.models import BotKey


class Command(BaseCommand):
    help = "Seed BotKeys for the redesigned bot system"

    def handle(self, *args, **kwargs):
        self.stdout.write("Seeding bot keys...")

        keys_to_create = [
            # ── Rise / Fall ───────────────────────────────────────────────
            {
                "bot_type": "RISE_FALL",
                "label": "Rise/Fall — Low Risk — Mentor A",
                "demo_house_outcome": "PROFIT",
                "demo_base_win_rate": 68,
                "demo_breakeven_min_pct": 0.00,
                "demo_breakeven_max_pct": 8.00,
                "house_outcome": "BREAKEVEN",
                "base_win_rate": 50,
                "breakeven_min_pct": -2.00,
                "breakeven_max_pct": 5.00,
                "profit_pct": 15.63,
            },
            {
                "bot_type": "RISE_FALL",
                "label": "Rise/Fall — Medium Risk — Mentor A",
                "demo_house_outcome": "PROFIT",
                "demo_base_win_rate": 65,
                "demo_breakeven_min_pct": 0.00,
                "demo_breakeven_max_pct": 8.00,
                "house_outcome": "BREAKEVEN",
                "base_win_rate": 48,
                "breakeven_min_pct": -2.00,
                "breakeven_max_pct": 5.00,
                "profit_pct": 15.63,
            },
            {
                "bot_type": "RISE_FALL",
                "label": "Rise/Fall — High Risk — Mentor B",
                "demo_house_outcome": "PROFIT",
                "demo_base_win_rate": 62,
                "demo_breakeven_min_pct": 0.00,
                "demo_breakeven_max_pct": 8.00,
                "house_outcome": "LOSS",
                "base_win_rate": 42,
                "breakeven_min_pct": -2.00,
                "breakeven_max_pct": 5.00,
                "profit_pct": 15.63,
            },
            # ── Over / Under ──────────────────────────────────────────────
            {
                "bot_type": "OVER_UNDER",
                "label": "Over/Under — Low Risk — Mentor A",
                "demo_house_outcome": "PROFIT",
                "demo_base_win_rate": 70,
                "demo_breakeven_min_pct": 0.00,
                "demo_breakeven_max_pct": 8.00,
                "house_outcome": "BREAKEVEN",
                "base_win_rate": 52,
                "breakeven_min_pct": -2.00,
                "breakeven_max_pct": 5.00,
                "profit_pct": 15.63,
            },
            {
                "bot_type": "OVER_UNDER",
                "label": "Over/Under — Medium Risk — Mentor B",
                "demo_house_outcome": "PROFIT",
                "demo_base_win_rate": 65,
                "demo_breakeven_min_pct": 0.00,
                "demo_breakeven_max_pct": 8.00,
                "house_outcome": "BREAKEVEN",
                "base_win_rate": 49,
                "breakeven_min_pct": -2.00,
                "breakeven_max_pct": 5.00,
                "profit_pct": 15.63,
            },
            {
                "bot_type": "OVER_UNDER",
                "label": "Over/Under — High Risk — Mentor C",
                "demo_house_outcome": "PROFIT",
                "demo_base_win_rate": 60,
                "demo_breakeven_min_pct": 0.00,
                "demo_breakeven_max_pct": 8.00,
                "house_outcome": "LOSS",
                "base_win_rate": 40,
                "breakeven_min_pct": -2.00,
                "breakeven_max_pct": 5.00,
                "profit_pct": 15.63,
            },
            # ── Accumulator ───────────────────────────────────────────────
            {
                "bot_type": "ACCUMULATOR",
                "label": "Accumulator — Low Risk — Mentor B",
                "demo_house_outcome": "PROFIT",
                "demo_base_win_rate": 72,
                "demo_breakeven_min_pct": 0.00,
                "demo_breakeven_max_pct": 8.00,
                "house_outcome": "BREAKEVEN",
                "base_win_rate": 53,
                "breakeven_min_pct": -2.00,
                "breakeven_max_pct": 5.00,
                "profit_pct": 15.63,
            },
            {
                "bot_type": "ACCUMULATOR",
                "label": "Accumulator — Medium Risk — Mentor C",
                "demo_house_outcome": "PROFIT",
                "demo_base_win_rate": 66,
                "demo_breakeven_min_pct": 0.00,
                "demo_breakeven_max_pct": 8.00,
                "house_outcome": "BREAKEVEN",
                "base_win_rate": 48,
                "breakeven_min_pct": -2.00,
                "breakeven_max_pct": 5.00,
                "profit_pct": 15.63,
            },
            {
                "bot_type": "ACCUMULATOR",
                "label": "Accumulator — High Risk — Mentor A",
                "demo_house_outcome": "PROFIT",
                "demo_base_win_rate": 58,
                "demo_breakeven_min_pct": 0.00,
                "demo_breakeven_max_pct": 8.00,
                "house_outcome": "LOSS",
                "base_win_rate": 38,
                "breakeven_min_pct": -2.00,
                "breakeven_max_pct": 5.00,
                "profit_pct": 15.63,
            },
        ]

        created_count = 0
        for key_data in keys_to_create:
            bot_key = BotKey.objects.create(**key_data)
            created_count += 1
            self.stdout.write(
                f"  Key [{bot_key.key}]  →  {bot_key.label}  "
                f"(type={bot_key.bot_type})"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"\n✅ Done — {created_count} bot keys created.\n"
                f"Distribute these 16-character keys to your mentors/users."
            )
        )
