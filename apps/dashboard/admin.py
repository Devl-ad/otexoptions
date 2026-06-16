# dashboard/admin.py
from django.db import models
from django.contrib import admin
from .models import (
    Trade,
    Wallet,
    HouseSettings,
    TradingPair,
    Agent,
    Transaction,
    PriceTick,
    BotKey,
    BotTrade,
    BotSession,
    BotTemplate,
)
from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from django.db.models import Sum, Count

admin.site.register(PriceTick)
admin.site.register(BotKey)
admin.site.register(BotTrade)
admin.site.register(BotSession)
admin.site.register(BotTemplate)


@admin.register(HouseSettings)
class HouseSettingsAdmin(admin.ModelAdmin):
    list_display = [
        "pair",
        "payout_pct",
        "house_edge",
        "favourability",
        "min_stake",
        "max_stake",
        "is_active",
    ]
    list_editable = ["payout_pct", "house_edge", "favourability", "is_active"]


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "pair",
        "trade_type",
        "direction",
        "stake",
        "entry_price",
        "exit_price",
        "status",
        "opened_at",
    ]
    list_filter = ["status", "trade_type", "pair"]
    search_fields = ["user__username"]


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ["user", "balance", "demo_balance", "is_demo", "updated_at"]
    list_editable = ["demo_balance", "is_demo"]


@admin.register(TradingPair)
class TradingPairAdmin(admin.ModelAdmin):
    list_display = ["symbol", "name", "volatility", "is_active"]
    list_editable = ["is_active"]


# ─────────────────────────────────────────────
# Agent Admin
# ─────────────────────────────────────────────


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = (
        "avatar_preview",
        "name",
        "location",
        "status_badge",
        "total_trades",
        "rating_display",
        "speed_display",
        "fee_percent",
        "deposit_range",
        "is_active",
    )
    list_display_links = ("name",)
    list_filter = ("status", "is_active", "country")
    search_fields = ("name", "city", "country", "whatsapp_number")
    list_editable = ("is_active",)
    ordering = ("-status", "-total_trades")
    readonly_fields = ("created_at", "updated_at", "whatsapp_url_display")

    fieldsets = (
        (
            "Identity",
            {
                "fields": (
                    "name",
                    "initials",
                    "whatsapp_number",
                    "whatsapp_url_display",
                ),
            },
        ),
        (
            "Account",
            {
                "fields": (
                    "user",
                    "balance",
                ),
            },
        ),
        (
            "Location",
            {
                "fields": ("city", "country"),
            },
        ),
        (
            "Avatar",
            {
                "fields": ("avatar_color", "avatar_text_color"),
                "classes": ("collapse",),
            },
        ),
        (
            "Deposit Limits & Fee",
            {
                "fields": ("min_deposit", "max_deposit", "fee_percent"),
            },
        ),
        (
            "Stats",
            {
                "fields": ("total_trades", "rating", "avg_speed_minutes"),
            },
        ),
        (
            "Status",
            {
                "fields": ("status", "is_active"),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    # ── Custom display columns ──────────────────

    @admin.display(description="")
    def avatar_preview(self, obj):
        return format_html(
            '<div style="width:34px;height:34px;border-radius:8px;background:{};'
            "color:{};display:flex;align-items:center;justify-content:center;"
            'font-size:12px;font-weight:700;">{}</div>',
            obj.avatar_color,
            obj.avatar_text_color,
            obj.initials,
        )

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {
            "online": ("#e6f8f2", "#00a878"),
            "offline": ("#f3f4f6", "#6b7280"),
            "busy": ("#fffbeb", "#f59e0b"),
        }
        bg, fg = colors.get(obj.status, ("#f3f4f6", "#6b7280"))
        return format_html(
            '<span style="background:{};color:{};padding:3px 10px;'
            'border-radius:12px;font-size:11px;font-weight:700;">{}</span>',
            bg,
            fg,
            obj.get_status_display(),
        )

    @admin.display(description="Rating")
    def rating_display(self, obj):
        return format_html(
            '<span style="color:#f59e0b;font-weight:700;">★ {}</span>', obj.rating
        )

    @admin.display(description="Limits")
    def deposit_range(self, obj):
        return f"${obj.min_deposit} – ${obj.max_deposit}"

    @admin.display(description="Speed")
    def speed_display(self, obj):
        return obj.speed_display

    @admin.display(description="WhatsApp Link")
    def whatsapp_url_display(self, obj):
        if obj.pk:
            return format_html(
                '<a href="{}" target="_blank">{}</a>',
                obj.whatsapp_url,
                obj.whatsapp_url,
            )
        return "—"


# ─────────────────────────────────────────────
# Transaction Admin
# ─────────────────────────────────────────────


@admin.action(description="✅ Mark selected as Completed")
def mark_completed(modeladmin, request, queryset):
    queryset.update(status=Transaction.Status.COMPLETED, confirmed_at=timezone.now())


@admin.action(description="❌ Mark selected as Failed")
def mark_failed(modeladmin, request, queryset):
    queryset.update(status=Transaction.Status.FAILED)


@admin.action(description="🔄 Mark selected as Pending")
def mark_pending(modeladmin, request, queryset):
    queryset.update(status=Transaction.Status.PENDING)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "user_link",
        "method_badge",
        "amount_display",
        "fee",
        "net_display",
        "status_badge",
        "agent",
        "tx_hash_short",
        "created_at",
    )
    list_display_links = ("reference",)
    list_filter = ("status", "method", "transaction_type", "created_at")
    search_fields = (
        "reference",
        "user__username",
        "user__email",
        "tx_hash",
        "agent__name",
    )
    readonly_fields = (
        "reference",
        "net_amount",
        "created_at",
        "updated_at",
        "proof_preview",
        "whatsapp_link",
    )
    actions = [mark_completed, mark_failed, mark_pending]
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    fieldsets = (
        (
            "Reference",
            {
                "fields": ("reference", "transaction_type"),
            },
        ),
        (
            "User & Agent",
            {
                "fields": ("user", "agent", "whatsapp_link"),
            },
        ),
        (
            "Amount",
            {
                "fields": ("method", "amount", "fee", "net_amount"),
            },
        ),
        (
            "Crypto Details",
            {
                "fields": (
                    "crypto_address",
                    "tx_hash",
                    "proof_screenshot",
                    "proof_preview",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Status",
            {
                "fields": ("status", "confirmed_at", "admin_note"),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    # ── Custom display columns ──────────────────

    @admin.display(description="User")
    def user_link(self, obj):
        from django.urls import reverse

        url = reverse("admin:auth_user_change", args=[obj.user.pk])
        return format_html('<a href="{}">{}</a>', url, obj.user.username)

    @admin.display(description="Method")
    def method_badge(self, obj):
        colors = {
            "agent": ("#fef0ec", "#e85d35"),
            "crypto_btc": ("#fff7ed", "#f7931a"),
            "crypto_usdt": ("#e6f8f2", "#26a17b"),
            "crypto_eth": ("#eef2ff", "#6366f1"),
            "bank": ("#f3f4f6", "#6b7280"),
        }
        bg, fg = colors.get(obj.method, ("#f3f4f6", "#6b7280"))
        return format_html(
            '<span style="background:{};color:{};padding:3px 10px;'
            'border-radius:12px;font-size:11px;font-weight:700;">{}</span>',
            bg,
            fg,
            obj.get_method_display(),
        )

    @admin.display(description="Amount")
    def amount_display(self, obj):
        return format_html("<strong>${}</strong>", obj.amount)

    @admin.display(description="Net")
    def net_display(self, obj):
        return format_html(
            '<span style="color:#00a878;font-weight:700;">${}</span>', obj.net_amount
        )

    @admin.display(description="Status")
    def status_badge(self, obj):
        return format_html(
            '<span style="background:{};color:#fff;padding:3px 10px;'
            'border-radius:12px;font-size:11px;font-weight:700;">{}</span>',
            obj.status_color,
            obj.get_status_display(),
        )

    @admin.display(description="TxID")
    def tx_hash_short(self, obj):
        if obj.tx_hash:
            short = obj.tx_hash[:12] + "…"
            return format_html(
                '<span title="{}" style="font-family:monospace;font-size:11px;">{}</span>',
                obj.tx_hash,
                short,
            )
        return "—"

    @admin.display(description="Proof")
    def proof_preview(self, obj):
        if obj.proof_screenshot:
            return format_html(
                '<img src="{}" style="max-height:120px;border-radius:6px;" />',
                obj.proof_screenshot.url,
            )
        return "No screenshot uploaded"

    @admin.display(description="WhatsApp")
    def whatsapp_link(self, obj):
        if obj.agent:
            return format_html(
                '<a href="{}" target="_blank">Chat with {}</a>',
                obj.agent.whatsapp_url,
                obj.agent.name,
            )
        return "—"

    # ── Changelist summary ──────────────────────

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        qs = self.get_queryset(request)
        totals = qs.aggregate(
            total_volume=Sum("amount"),
            total_count=Count("id"),
            pending_count=Count(
                "id", filter=models.Q(status=Transaction.Status.PENDING)
            ),
            completed_count=Count(
                "id", filter=models.Q(status=Transaction.Status.COMPLETED)
            ),
        )
        extra_context["summary"] = totals
        return super().changelist_view(request, extra_context=extra_context)


# BOT TRADING
