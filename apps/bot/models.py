import uuid
import random
import string
from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from django.core.exceptions import ValidationError
from apps.account.forms import User
from apps.dashboard.models import TradingPair


def generate_bot_key():
    """Generate a unique 16-character alphanumeric key."""
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=16))


class BotKey(models.Model):

    BOT_TYPES = [
        ("RISE_FALL", "Rise / Fall"),
        ("OVER_UNDER", "Over / Under"),
        ("ACCUMULATOR", "Accumulator"),
    ]

    OUTCOME_CHOICES = [
        ("PROFIT", "Profit"),
        ("BREAKEVEN", "Breakeven"),
        ("LOSS", "Loss"),
    ]

    key = models.CharField(max_length=16, unique=True, default=generate_bot_key)

    label = models.CharField(max_length=100, blank=True)  # e.g. "Mentor A Key"
    is_active = models.BooleanField(default=True)
    total_uses = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    bot_type = models.CharField(max_length=20, choices=BOT_TYPES)

    # base win rate per trade (0-100) — nudged by house toward outcome
    base_win_rate = models.PositiveIntegerField(default=55)

    # profit per winning trade as percentage of stake
    profit_pct = models.DecimalField(max_digits=5, decimal_places=2, default=15.63)

    # house controls the session outcome
    house_outcome = models.CharField(
        max_length=10, choices=OUTCOME_CHOICES, default="PROFIT"
    )

    # breakeven range — session P&L within this % of total staked = breakeven
    breakeven_min_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=-2.00
    )
    breakeven_max_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=5.00
    )

    # ── Demo settings  ──────────────────────
    demo_base_win_rate = models.PositiveIntegerField(default=65)
    demo_house_outcome = models.CharField(
        max_length=10, choices=OUTCOME_CHOICES, default="PROFIT"
    )
    demo_breakeven_min_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=0.00
    )
    demo_breakeven_max_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=8.00
    )

    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def clean(self):
        if self.demo_breakeven_min_pct >= self.demo_breakeven_max_pct:
            raise ValidationError(
                "Demo breakeven min must be less than demo breakeven max."
            )
        if self.breakeven_min_pct >= self.breakeven_max_pct:
            raise ValidationError(
                "Live breakeven min must be less than live breakeven max."
            )

    # ── Helper — get the right settings based on mode ──────────────────────
    def get_settings(self, is_demo):
        if is_demo:
            return {
                "base_win_rate": self.demo_base_win_rate,
                "house_outcome": self.demo_house_outcome,
                "breakeven_min_pct": self.demo_breakeven_min_pct,
                "breakeven_max_pct": self.demo_breakeven_max_pct,
            }
        return {
            "base_win_rate": self.base_win_rate,
            "house_outcome": self.house_outcome,
            "breakeven_min_pct": self.breakeven_min_pct,
            "breakeven_max_pct": self.breakeven_max_pct,
        }

    def __str__(self):
        return f"{self.key} → {self.label}"

    class Meta:
        verbose_name = "Bot Key"
        verbose_name_plural = "Bot Keys"


class BotTemplate(models.Model):
    TIMEFRAME_CHOICES = [
        (10, "10 Minutes"),
        (20, "20 Minutes"),
        (30, "30 Minutes"),
    ]
    RISK_LEVELS = [
        ("LOW", "Low Risk"),
        ("MEDIUM", "Medium Risk"),
        ("HIGH", "High Risk"),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="botemplate")
    key = models.ForeignKey(BotKey, on_delete=models.CASCADE, related_name="botkey")

    name = models.CharField(max_length=100)

    created_at = models.DateTimeField(auto_now_add=True)

    timeframe = models.PositiveIntegerField(choices=TIMEFRAME_CHOICES, default=5)
    trade_per_5min = models.PositiveIntegerField(default=1)
    risk_level = models.CharField(max_length=10, choices=RISK_LEVELS)

    def __str__(self):
        return f"{self.name} — {self.user.first_name} ({self.risk_level})"

    class Meta:
        verbose_name = "Bot Template"
        verbose_name_plural = "Bot Templates"


class BotSession(models.Model):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("RUNNING", "Running"),
        ("COMPLETED", "Completed"),
        ("CANCELLED", "Cancelled"),
    ]

    OUTCOME_CHOICES = [
        ("PROFIT", "Profit"),
        ("BREAKEVEN", "Breakeven"),
        ("LOSS", "Loss"),
        ("PENDING", "Pending"),
    ]
    TIMEFRAME_CHOICES = [
        (10, "10 Minutes"),
        (20, "20 Minutes"),
        (30, "30 Minutes"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bot_sessions"
    )
    bot_key = models.ForeignKey(
        BotKey, on_delete=models.CASCADE, related_name="sessions"
    )
    bot_template = models.ForeignKey(
        BotTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
    )
    pair = models.ForeignKey(
        TradingPair, on_delete=models.CASCADE, related_name="bot_pair"
    )

    stake_per_trade = models.DecimalField(max_digits=10, decimal_places=2)

    is_demo = models.BooleanField(default=True)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="PENDING")
    outcome = models.CharField(
        max_length=10, choices=OUTCOME_CHOICES, default="PENDING"
    )

    # house decision made at session start
    house_outcome = models.CharField(max_length=10, default="PROFIT")
    base_win_rate = models.PositiveIntegerField(default=50)
    breakeven_min_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("-2.00")
    )
    breakeven_max_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("5.00")
    )
    profit_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("15.63")
    )

    total_trades = models.PositiveIntegerField(default=0)
    trades_won = models.PositiveIntegerField(default=0)
    trades_lost = models.PositiveIntegerField(default=0)

    gross_profit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gross_loss = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_pnl = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    timeframe = models.PositiveIntegerField(choices=TIMEFRAME_CHOICES, default=5)
    trade_per_5min = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.user} — {self.bot_key} — {self.status}"

    @property
    def total_staked(self):
        return self.stake_per_trade * self.total_trades

    @property
    def win_rate(self):
        if self.total_trades == 0:
            return 0
        return round((self.trades_won / self.total_trades) * 100, 1)

    class Meta:
        verbose_name = "Bot Session"
        verbose_name_plural = "Bot Sessions"


class BotTrade(models.Model):
    RESULT_CHOICES = [
        ("WON", "Won"),
        ("LOST", "Lost"),
        ("PENDING", "Pending"),
    ]

    session = models.ForeignKey(
        BotSession, on_delete=models.CASCADE, related_name="bot_trades"
    )
    trade_number = models.PositiveIntegerField()  # 1, 2, 3... within the session
    direction = models.CharField(max_length=10)  # RISE, FALL, OVER, UNDER, ACCUM
    entry_price = models.DecimalField(max_digits=12, decimal_places=4)
    exit_price = models.DecimalField(max_digits=12, decimal_places=4, null=True)
    stake = models.DecimalField(max_digits=10, decimal_places=2)
    profit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    result = models.CharField(max_length=10, choices=RESULT_CHOICES, default="PENDING")
    executed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Trade #{self.trade_number} — {self.result}"

    class Meta:
        ordering = ["trade_number"]
        verbose_name = "Bot Trade"
        verbose_name_plural = "Bot Trades"
