# apps/dashboard/management/commands/seed_bots.py
from django.core.management.base import BaseCommand
from apps.dashboard.models import BotTemplate, BotKey


class Command(BaseCommand):
    help = "Seed bot templates and keys"

    def handle(self, *args, **kwargs):
        self.stdout.write("Seeding bot templates and keys...")

        templates = [
            # ── Rise / Fall ───────────────────────────────────────────────
            {
                "name": "Rise/Fall Low Risk",
                "bot_type": "RISE_FALL",
                "risk_level": "LOW",
                "trades_per_5min": 5,
                "base_win_rate": 55,
                "profit_pct": 15.63,
                "house_outcome": "PROFIT",
                "breakeven_min_pct": -2.00,
                "breakeven_max_pct": 5.00,
                "description": "Conservative rise/fall bot. Fewer trades, steadier results.",
            },
            {
                "name": "Rise/Fall Medium Risk",
                "bot_type": "RISE_FALL",
                "risk_level": "MEDIUM",
                "trades_per_5min": 8,
                "base_win_rate": 50,
                "profit_pct": 15.63,
                "house_outcome": "PROFIT",
                "breakeven_min_pct": -2.00,
                "breakeven_max_pct": 5.00,
                "description": "Balanced rise/fall bot. Moderate frequency and risk.",
            },
            {
                "name": "Rise/Fall High Risk",
                "bot_type": "RISE_FALL",
                "risk_level": "HIGH",
                "trades_per_5min": 12,
                "base_win_rate": 45,
                "profit_pct": 15.63,
                "house_outcome": "PROFIT",
                "breakeven_min_pct": -2.00,
                "breakeven_max_pct": 5.00,
                "description": "Aggressive rise/fall bot. High frequency, higher variance.",
            },
            # ── Over / Under ──────────────────────────────────────────────
            {
                "name": "Over/Under Low Risk",
                "bot_type": "OVER_UNDER",
                "risk_level": "LOW",
                "trades_per_5min": 4,
                "base_win_rate": 57,
                "profit_pct": 15.63,
                "house_outcome": "PROFIT",
                "breakeven_min_pct": -2.00,
                "breakeven_max_pct": 5.00,
                "description": "Conservative over/under bot. Trades barrier levels carefully.",
            },
            {
                "name": "Over/Under Medium Risk",
                "bot_type": "OVER_UNDER",
                "risk_level": "MEDIUM",
                "trades_per_5min": 7,
                "base_win_rate": 50,
                "profit_pct": 15.63,
                "house_outcome": "PROFIT",
                "breakeven_min_pct": -2.00,
                "breakeven_max_pct": 5.00,
                "description": "Balanced over/under bot. Standard barrier trading.",
            },
            {
                "name": "Over/Under High Risk",
                "bot_type": "OVER_UNDER",
                "risk_level": "HIGH",
                "trades_per_5min": 10,
                "base_win_rate": 43,
                "profit_pct": 15.63,
                "house_outcome": "PROFIT",
                "breakeven_min_pct": -2.00,
                "breakeven_max_pct": 5.00,
                "description": "Aggressive over/under bot. Rapid barrier trades.",
            },
            # ── Accumulator ───────────────────────────────────────────────
            {
                "name": "Accumulator Low Risk",
                "bot_type": "ACCUMULATOR",
                "risk_level": "LOW",
                "trades_per_5min": 3,
                "base_win_rate": 60,
                "profit_pct": 15.63,
                "house_outcome": "PROFIT",
                "breakeven_min_pct": -2.00,
                "breakeven_max_pct": 5.00,
                "description": "Conservative accumulator. Stays within tight price ranges.",
            },
            {
                "name": "Accumulator Medium Risk",
                "bot_type": "ACCUMULATOR",
                "risk_level": "MEDIUM",
                "trades_per_5min": 5,
                "base_win_rate": 50,
                "profit_pct": 15.63,
                "house_outcome": "PROFIT",
                "breakeven_min_pct": -2.00,
                "breakeven_max_pct": 5.00,
                "description": "Balanced accumulator. Standard range trading.",
            },
            {
                "name": "Accumulator High Risk",
                "bot_type": "ACCUMULATOR",
                "risk_level": "HIGH",
                "trades_per_5min": 8,
                "base_win_rate": 40,
                "profit_pct": 15.63,
                "house_outcome": "PROFIT",
                "breakeven_min_pct": -2.00,
                "breakeven_max_pct": 5.00,
                "description": "Aggressive accumulator. Wider ranges, more frequent trades.",
            },
        ]

        created_templates = []
        for t in templates:
            obj, created = BotTemplate.objects.get_or_create(
                name=t["name"],
                defaults=t,
            )
            created_templates.append(obj)
            status = "created" if created else "already exists"
            self.stdout.write(f"  Template: {obj.name} — {status}")

        self.stdout.write("\nSeeding bot keys...")

        # 3 keys per template — one for each mentor tier
        key_labels = ["Mentor A", "Mentor B", "Mentor C"]

        for template in created_templates:
            for label in key_labels:
                key, created = BotKey.objects.get_or_create(
                    template=template,
                    label=f"{label} — {template.name}",
                    defaults={"is_active": True},
                )
                status = "created" if created else "already exists"
                self.stdout.write(
                    f"  Key [{key.key}] → {template.name} ({label}) — {status}"
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"\n✅ Done — {len(created_templates)} templates, "
                f"{len(created_templates) * len(key_labels)} keys seeded."
            )
        )
