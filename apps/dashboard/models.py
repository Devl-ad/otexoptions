import uuid
import random
import string
from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal


from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator


class TradingPair(models.Model):
    symbol = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)
    min_trade = models.DecimalField(max_digits=10, decimal_places=4, default=1.00)
    max_trade = models.DecimalField(max_digits=10, decimal_places=4, default=1000.00)
    volatility = models.DecimalField(
        max_digits=5, decimal_places=2, default=0.19
    )  # ← add this
    pip_size = models.DecimalField(max_digits=6, decimal_places=4, default=0.01)
    tick_speed = models.DecimalField(max_digits=4, decimal_places=2, default=1.00)

    def __str__(self):
        return self.symbol


class PriceTick(models.Model):
    pair = models.ForeignKey(
        TradingPair, on_delete=models.CASCADE, related_name="ticks"
    )
    price = models.DecimalField(max_digits=8, decimal_places=4)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        get_latest_by = "timestamp"
        indexes = [
            models.Index(fields=["pair", "-timestamp"]),
        ]

    def __str__(self):
        return f"{self.pair.symbol} — {self.price} @ {self.timestamp:%Y-%m-%d %H:%M:%S}"

    @classmethod
    def cleanup_old(cls, keep_minutes=60):

        cutoff = timezone.now() - timedelta(minutes=keep_minutes)
        cls.objects.filter(timestamp__lt=cutoff).delete()


class Trade(models.Model):

    DIRECTION_CHOICES = [
        ("RISE", "Rise"),
        ("FALL", "Fall"),
        ("OVER", "Over"),
        ("UNDER", "Under"),
        ("ACCUM", "Accumulator"),
    ]

    TYPE_CHOICES = [
        ("RISE_FALL", "Rise / Fall"),
        ("OVER_UNDER", "Over / Under"),
        ("ACCUMULATOR", "Accumulator"),
    ]

    STATUS_CHOICES = [
        ("OPEN", "Open"),
        ("WON", "Won"),
        ("LOST", "Lost"),
        ("EXPIRED", "Expired"),
    ]

    DURATION_CHOICES = [
        (1, "1 tick"),
        (5, "5 ticks"),
        (10, "10 ticks"),
        (60, "1 min"),
        (300, "5 min"),
        (900, "15 min"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="trades"
    )
    pair = models.ForeignKey("TradingPair", on_delete=models.CASCADE)
    trade_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    stake = models.DecimalField(max_digits=10, decimal_places=2)
    payout_pct = models.DecimalField(max_digits=5, decimal_places=2, default=43.00)
    entry_price = models.DecimalField(max_digits=10, decimal_places=2)
    exit_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    barrier = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )  # for over/under
    duration = models.IntegerField(choices=DURATION_CHOICES)  # in ticks or seconds
    duration_unit = models.CharField(
        max_length=10, default="ticks"
    )  # 'ticks' or 'seconds'
    ticks_elapsed = models.IntegerField(default=0)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="OPEN")
    opened_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_demo = models.BooleanField(default=True)

    # house edge / favourability (tweakable from admin)
    house_edge = models.DecimalField(max_digits=5, decimal_places=2, default=15.00)  # %

    @property
    def payout(self):
        if self.status == "WON":
            return round(float(self.stake) * (1 + float(self.payout_pct) / 100), 2)
        return 0

    @property
    def profit(self):
        if self.status == "WON":
            return round(float(self.stake) * float(self.payout_pct) / 100, 2)
        elif self.status == "LOST":
            return -float(self.stake)
        return 0

    def __str__(self):
        return f"{self.user} | {self.pair.symbol} | {self.direction} | ${self.stake} | {self.status}"


class Wallet(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wallet"
    )
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    demo_balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=10000.00
    )
    is_demo = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_balance(self, mode):
        if mode == "demo":
            return self.demo_balance
        return self.balance

    def credit(self, amount, mode="demo"):
        current_balance = self.demo_balance if mode == "demo" else self.balance
        if mode == "demo":
            self.demo_balance += Decimal(str(amount))
            current_balance = self.demo_balance
        else:
            self.balance += Decimal(str(amount))
            current_balance = self.balance
        self.save(update_fields=["balance", "demo_balance", "updated_at"])
        return current_balance

    def debit(self, amount, mode="demo"):
        current_balance = self.demo_balance if mode == "demo" else self.balance
        if mode == "demo":
            if self.demo_balance < Decimal(str(amount)):
                raise ValueError("Insufficient demo balance.")
            self.demo_balance -= Decimal(str(amount))
            current_balance = self.demo_balance
        else:
            if self.balance < Decimal(str(amount)):
                raise ValueError("Insufficient live balance.")
            self.balance -= Decimal(str(amount))
            current_balance = self.balance
        self.save(update_fields=["balance", "demo_balance", "updated_at"])
        return current_balance

    @property
    def current_balance(self):
        # use session mode — handled at view level
        return self.demo_balance

    def __str__(self):
        return f"{self.user} — ${self.current_balance}"


class HouseSettings(models.Model):
    pair = models.OneToOneField(
        "TradingPair", on_delete=models.CASCADE, related_name="house_settings"
    )
    payout_pct = models.DecimalField(max_digits=5, decimal_places=2, default=43.00)
    house_edge = models.DecimalField(max_digits=5, decimal_places=2, default=15.00)

    # favourability — 50 = fair, >50 = users win more, <50 = house wins more
    favourability = models.IntegerField(
        default=50, help_text="0-100. 50=fair, >50=user favoured, <50=house favoured"
    )

    max_stake = models.DecimalField(max_digits=10, decimal_places=2, default=1000.00)
    min_stake = models.DecimalField(max_digits=10, decimal_places=2, default=1.00)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.pair.symbol} — edge:{self.house_edge}% fav:{self.favourability}"


User = get_user_model()


class Agent(models.Model):
    """
    Represents a P2P deposit agent users can contact via WhatsApp.
    """

    class Status(models.TextChoices):
        ONLINE = "online", "Online"
        OFFLINE = "offline", "Offline"
        BUSY = "busy", "Busy"

    # Identity
    name = models.CharField(max_length=100)
    initials = models.CharField(
        max_length=3, help_text="2–3 letter avatar initials e.g. 'AK'"
    )
    whatsapp_number = models.CharField(
        max_length=20,
        help_text="International format without '+', e.g. 233200000001",
    )

    # Location
    city = models.CharField(max_length=100)
    country = models.CharField(max_length=100)

    # Deposit limits
    min_deposit = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("10.00")
    )
    max_deposit = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("5000.00")
    )
    fee_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("1.50"),
        help_text="Agent fee as a percentage e.g. 1.50 means 1.5%",
    )

    # Stats (can be updated by signals or a management command)
    total_trades = models.PositiveIntegerField(default=0)
    rating = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        default=Decimal("5.0"),
        validators=[MinValueValidator(Decimal("0.0"))],
    )
    avg_speed_minutes = models.PositiveSmallIntegerField(
        default=10,
        help_text="Average confirmation time in minutes",
    )

    # Status
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ONLINE
    )
    avatar_color = models.CharField(
        max_length=7,
        default="#fef0ec",
        help_text="CSS hex background colour for the avatar",
    )
    avatar_text_color = models.CharField(max_length=7, default="#e85d35")

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="agent_profile",
        null=True,
        blank=True,
        help_text="The Django user account this agent logs in with",
    )

    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Agent's current spendable balance",
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-status", "-total_trades"]
        verbose_name = "Agent"
        verbose_name_plural = "Agents"

    def __str__(self):
        return f"{self.name} ({self.city}, {self.country})"

    @property
    def whatsapp_url(self):
        """Pre-filled WhatsApp deep link."""
        msg = f"Hi {self.name}, I would like to make a deposit on OTEX."
        from urllib.parse import quote

        return f"https://wa.me/{self.whatsapp_number}?text={quote(msg)}"

    @property
    def location(self):
        return f"{self.city}, {self.country}"

    @property
    def speed_display(self):
        m = self.avg_speed_minutes
        return f"~{m} min" if m < 60 else f"~{m // 60}h {m % 60}m"


class Transaction(models.Model):
    """
    Records every deposit (and in future: withdrawal) attempt by a user.
    """

    class TransactionType(models.TextChoices):
        DEPOSIT = "deposit", "Deposit"
        WITHDRAWAL = "withdrawal", "Withdrawal"

    class Method(models.TextChoices):
        AGENT = "agent", "Agent (P2P)"
        CRYPTO_BTC = "crypto_btc", "Bitcoin (BTC)"
        CRYPTO_USDT = "crypto_usdt", "USDT TRC20"
        CRYPTO_ETH = "crypto_eth", "Ethereum (ETH)"
        BANK = "bank", "Bank Transfer"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    # Relations
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="transactions"
    )
    agent = models.ForeignKey(
        Agent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
        help_text="Populated only for agent-based deposits",
    )

    # Core fields
    transaction_type = models.CharField(
        max_length=20, choices=TransactionType.choices, default=TransactionType.DEPOSIT
    )
    method = models.CharField(max_length=20, choices=Method.choices)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("1.00"))],
    )
    fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    net_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="amount minus fee — what is credited to the user",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )

    # Crypto-specific
    crypto_address = models.CharField(max_length=200, blank=True, default="")
    tx_hash = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="Transaction Hash / TxID",
    )
    proof_screenshot = models.ImageField(
        upload_to="deposits/proofs/%Y/%m/", blank=True, null=True
    )

    # Admin / internal
    reference = models.CharField(max_length=60, unique=True, editable=False)
    admin_note = models.TextField(blank=True, default="")
    confirmed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now, editable=True)
    updated_at = models.DateTimeField(default=timezone.now, editable=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["tx_hash"]),
        ]

    def __str__(self):
        return f"[{self.reference}] {self.user} — {self.get_method_display()} ${self.amount} ({self.status})"

    def save(self, *args, **kwargs):
        # Auto-generate reference on first save
        if not self.reference:
            self.reference = self._generate_reference()
        # Auto-calculate net amount
        self.net_amount = self.amount - self.fee
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_reference():
        import uuid

        return "OTX-" + uuid.uuid4().hex[:10].upper()

    @property
    def is_crypto(self):
        return self.method in (
            self.Method.CRYPTO_BTC,
            self.Method.CRYPTO_USDT,
            self.Method.CRYPTO_ETH,
        )

    @property
    def status_color(self):
        """Returns a CSS colour string matching the OTEX design system."""
        return {
            self.Status.PENDING: "#f59e0b",
            self.Status.CONFIRMED: "#6366f1",
            self.Status.COMPLETED: "#00a878",
            self.Status.FAILED: "#e85d35",
            self.Status.CANCELLED: "#9ca3af",
        }.get(self.status, "#9ca3af")

    @property
    def whatsapp_withdrawal_url(self):
        """Pre-filled WhatsApp deep link."""
        msg = f"Hi {self.agent.name}, I just placed a withdrawal request of ${self.amount} on OTEX."
        from urllib.parse import quote

        return f"https://wa.me/{self.agent.whatsapp_number}?text={quote(msg)}"


def generate_bot_key():
    """Generate a unique 16-character alphanumeric key."""
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=16))


class BotTemplate(models.Model):
    BOT_TYPES = [
        ("RISE_FALL", "Rise / Fall"),
        ("OVER_UNDER", "Over / Under"),
        ("ACCUMULATOR", "Accumulator"),
    ]

    RISK_LEVELS = [
        ("LOW", "Low Risk"),
        ("MEDIUM", "Medium Risk"),
        ("HIGH", "High Risk"),
    ]

    OUTCOME_CHOICES = [
        ("PROFIT", "Profit"),
        ("BREAKEVEN", "Breakeven"),
        ("LOSS", "Loss"),
    ]

    name = models.CharField(max_length=100)
    bot_type = models.CharField(max_length=20, choices=BOT_TYPES)
    risk_level = models.CharField(max_length=10, choices=RISK_LEVELS)

    # trades per 5 minutes — scales with timeframe
    trades_per_5min = models.PositiveIntegerField(default=5)

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
    created_at = models.DateTimeField(auto_now_add=True)

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
        return f"{self.name} — {self.bot_type} ({self.risk_level})"

    class Meta:
        verbose_name = "Bot Template"
        verbose_name_plural = "Bot Templates"


class BotKey(models.Model):
    key = models.CharField(max_length=16, unique=True, default=generate_bot_key)
    template = models.ForeignKey(
        BotTemplate, on_delete=models.CASCADE, related_name="keys"
    )
    label = models.CharField(max_length=100, blank=True)  # e.g. "Mentor A Key"
    is_active = models.BooleanField(default=True)
    total_uses = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.key} → {self.template.name}"

    class Meta:
        verbose_name = "Bot Key"
        verbose_name_plural = "Bot Keys"


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
        (5, "5 Minutes"),
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
    pair = models.ForeignKey(
        "dashboard.TradingPair", on_delete=models.CASCADE, related_name="bot_sessions"
    )

    stake_per_trade = models.DecimalField(max_digits=10, decimal_places=2)
    timeframe = models.PositiveIntegerField(choices=TIMEFRAME_CHOICES, default=5)
    is_demo = models.BooleanField(default=True)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="PENDING")
    outcome = models.CharField(
        max_length=10, choices=OUTCOME_CHOICES, default="PENDING"
    )

    # house decision made at session start
    house_outcome = models.CharField(max_length=10, default="PROFIT")

    total_trades = models.PositiveIntegerField(default=0)
    trades_won = models.PositiveIntegerField(default=0)
    trades_lost = models.PositiveIntegerField(default=0)

    gross_profit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gross_loss = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_pnl = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user} — {self.bot_key.template.name} — {self.status}"

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


class TodayRate(models.Model):
    currency = models.CharField(max_length=10, unique=True)
    rate = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.currency}"
