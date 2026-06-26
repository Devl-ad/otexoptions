# dashboard/admin.py
from django.db import models
from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline


from django.utils import timezone

from django.core.mail import send_mail
from django.shortcuts import redirect
from django.conf import settings
from django.db.models import Sum, Count
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe


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
    TodayRate,
    RecivingCryptoWallet,
)
from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone


@admin.register(PriceTick)
class PriceTickAdmin(ModelAdmin):
    list_display = ["pair"]


@admin.register(BotKey)
class BotKeyAdmin(ModelAdmin):
    list_display = ["key", "template", "label"]
    list_editable = ["label"]
    search_fields = ("key", "label", "template__name")


@admin.register(BotTrade)
class BotTradeAdmin(ModelAdmin):
    list_display = ["session", "result"]


@admin.register(BotSession)
class BotSessionAdmin(ModelAdmin):
    list_display = ["id", "user", "pair"]
    search_fields = ("user__username", "bot_key__key", "pair__symbol")


@admin.register(RecivingCryptoWallet)
class RecivingCryptoWalletAdmin(ModelAdmin):
    list_display = ["coin"]


@admin.register(TodayRate)
class TodayRateAdmin(ModelAdmin):
    list_display = ["currency", "rate"]
    list_editable = ["rate"]


@admin.register(BotTemplate)
class BotTemplateAdmin(ModelAdmin):
    list_display = [
        "name",
        "bot_type",
        "demo_house_outcome",
        "demo_base_win_rate",
        "house_outcome",
        "base_win_rate",
        "is_active",
        "users_sets",
    ]
    list_editable = [
        "demo_house_outcome",
        "demo_base_win_rate",
        "house_outcome",
        "base_win_rate",
        "is_active",
    ]
    list_filter = ["bot_type", "risk_level"]

    fieldsets = (
        (
            "Bot Info",
            {
                "fields": (
                    "name",
                    "bot_type",
                    "risk_level",
                    "trades_per_5min",
                    "profit_pct",
                    "description",
                    "is_active",
                    "users_sets",
                )
            },
        ),
        (
            "Demo Mode Settings",
            {
                "fields": (
                    "demo_base_win_rate",
                    "demo_house_outcome",
                    "demo_breakeven_min_pct",
                    "demo_breakeven_max_pct",
                ),
                "description": "More generous settings to encourage users to go live.",
            },
        ),
        (
            "Live Mode Settings",
            {
                "fields": (
                    "base_win_rate",
                    "house_outcome",
                    "breakeven_min_pct",
                    "breakeven_max_pct",
                ),
                "description": "Real house edge — controls actual revenue.",
            },
        ),
    )


@admin.register(HouseSettings)
class HouseSettingsAdmin(ModelAdmin):
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
class TradeAdmin(ModelAdmin):
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
class WalletAdmin(ModelAdmin):
    list_display = ["user", "balance", "demo_balance", "is_demo", "updated_at"]
    list_editable = ["demo_balance", "is_demo"]
    search_fields = ("user__username", "balance")


@admin.register(TradingPair)
class TradingPairAdmin(ModelAdmin):
    list_display = ["symbol", "name", "volatility", "is_active"]
    list_editable = ["is_active"]


# ─────────────────────────────────────────────
# Agent Admin
# ─────────────────────────────────────────────


@admin.register(Agent)
class AgentAdmin(ModelAdmin):
    list_display = (
        "avatar_preview",
        "name",
        "location",
        "status_badge",
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


# ── Email helper ──────────────────────────────────────────────────────────────


def _send_transaction_email(user, transaction, status):
    """Render transaction_status.html and send it."""
    try:
        html_message = render_to_string(
            "emails/transaction_status.html",
            {
                "user": user,
                "transaction": transaction,
                "status": status,
                "status_label": transaction.get_status_display(),
            },
        )
        subjects = {
            Transaction.Status.COMPLETED: f"Transaction Completed — OTEX",
            Transaction.Status.FAILED: f"Transaction Declined — OTEX",
        }
        send_mail(
            subject=subjects.get(status, f"Transaction Update — OTEX"),
            message=f"Transaction {transaction.reference} is now {transaction.get_status_display()}.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
        )
    except Exception as e:
        return str(e)
    return None


# ── Bulk actions ──────────────────────────────────────────────────────────────


@admin.action(description="✅ Mark selected as Completed")
def mark_completed(modeladmin, request, queryset):
    for transaction in queryset.select_related("user"):
        transaction.status = Transaction.Status.COMPLETED
        transaction.confirmed_at = timezone.now()
        transaction.save()
        err = _send_transaction_email(
            transaction.user, transaction, Transaction.Status.COMPLETED
        )
        if err:
            modeladmin.message_user(
                request,
                f"Email failed for {transaction.reference}: {err}",
                level="warning",
            )


@admin.action(description="❌ Mark selected as Failed")
def mark_failed(modeladmin, request, queryset):
    for transaction in queryset.select_related("user"):
        transaction.status = Transaction.Status.FAILED
        transaction.save()
        err = _send_transaction_email(
            transaction.user, transaction, Transaction.Status.FAILED
        )
        if err:
            modeladmin.message_user(
                request,
                f"Email failed for {transaction.reference}: {err}",
                level="warning",
            )


@admin.action(description="🔄 Mark selected as Pending")
def mark_pending(modeladmin, request, queryset):
    queryset.update(status=Transaction.Status.PENDING)


# ── Admin ─────────────────────────────────────────────────────────────────────


@admin.register(Transaction)
class TransactionAdmin(ModelAdmin):
    list_display = (
        "reference",
        "user_link",
        "method_badge",
        "amount_display",
        "status_badge",
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
        "proof_preview",
        "whatsapp_link",
        "action_buttons",
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
            "Quick Actions",
            {
                "fields": ("action_buttons",),
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

    # ── Custom URLs for approve / decline buttons ─────────────────────────────

    def get_urls(self):
        from django.urls import path

        urls = super().get_urls()
        custom = [
            path(
                "<int:pk>/complete/",
                self.admin_site.admin_view(self.complete_view),
                name="transaction_complete",
            ),
            path(
                "<int:pk>/fail/",
                self.admin_site.admin_view(self.fail_view),
                name="transaction_fail",
            ),
        ]
        return custom + urls

    def complete_view(self, request, pk):
        from django.urls import reverse

        transaction = Transaction.objects.select_related("user").get(pk=pk)

        if transaction.status != Transaction.Status.PENDING:
            self.message_user(
                request,
                f"Transaction {transaction.reference} is not pending.",
                level="warning",
            )
            return redirect(f"/admin/dashboard/transaction/{pk}/change/")

        transaction.status = Transaction.Status.COMPLETED
        transaction.confirmed_at = timezone.now()
        transaction.save()

        try:
            from apps.dashboard.models import Wallet

            if transaction.transaction_type == Transaction.TransactionType.DEPOSIT:

                wallet = Wallet.objects.get(user=transaction.user)
                wallet.credit(float(transaction.net_amount), mode="live")
        except Exception as e:
            self.message_user(request, f"Wallet credit failed: {e}", level="error")

        err = _send_transaction_email(
            transaction.user, transaction, Transaction.Status.COMPLETED
        )
        if err:
            self.message_user(
                request, f"Approved but email failed: {err}", level="warning"
            )

        try:
            from apps.account.referrals import record_referral_deposit

            record_referral_deposit(transaction.user, transaction.net_amount)
        except Exception:
            pass

        self.message_user(
            request, f"✅ {transaction.reference} approved and wallet credited."
        )
        return redirect(f"/admin/dashboard/transaction/{pk}/change/")

    def fail_view(self, request, pk):
        from django.urls import reverse

        transaction = Transaction.objects.select_related("user").get(pk=pk)

        if transaction.status != Transaction.Status.PENDING:
            self.message_user(
                request,
                f"Transaction {transaction.reference} is not pending.",
                level="warning",
            )
            return redirect(f"/admin/dashboard/transaction/{pk}/change/")

        transaction.status = Transaction.Status.FAILED
        transaction.save()

        err = _send_transaction_email(
            transaction.user, transaction, Transaction.Status.FAILED
        )
        if err:
            self.message_user(
                request, f"Declined but email failed: {err}", level="warning"
            )

        self.message_user(request, f"❌ {transaction.reference} marked as failed.")
        return redirect(f"/admin/dashboard/transaction/{pk}/change/")

    # ── Action buttons field ──────────────────────────────────────────────────

    @admin.display(description="Actions")
    def action_buttons(self, obj):
        if not obj.pk:
            return "—"

        from django.urls import reverse

        complete_url = reverse("admin:transaction_complete", args=[obj.pk])
        fail_url = reverse("admin:transaction_fail", args=[obj.pk])

        is_pending = obj.status == Transaction.Status.PENDING

        approve_style = (
            "display:inline-block;background:#166534;color:#fff;"
            "padding:9px 22px;border-radius:8px;font-size:13px;"
            "font-weight:700;text-decoration:none;margin-right:8px"
        )
        decline_style = (
            "display:inline-block;background:#991b1b;color:#fff;"
            "padding:9px 22px;border-radius:8px;font-size:13px;"
            "font-weight:700;text-decoration:none"
        )
        disabled_style = (
            "display:inline-block;background:#d1d5db;color:#9ca3af;"
            "padding:9px 22px;border-radius:8px;font-size:13px;"
            "font-weight:700;text-decoration:none;cursor:not-allowed;pointer-events:none"
        )

        if is_pending:
            approve_btn = (
                f'<a href="{complete_url}" style="{approve_style}">✅ Approve</a>'
            )
            decline_btn = f'<a href="{fail_url}" style="{decline_style}">❌ Decline</a>'
        else:
            approve_btn = f'<span style="{disabled_style}">✅ Approve</span>'
            decline_btn = f'<span style="{disabled_style}">❌ Decline</span>'

        status_note = ""
        if obj.status == Transaction.Status.COMPLETED:
            status_note = (
                '&nbsp;<span style="color:#166534;font-size:12px;font-weight:600">'
                "— Already completed</span>"
            )
        elif obj.status == Transaction.Status.FAILED:
            status_note = (
                '&nbsp;<span style="color:#991b1b;font-size:12px;font-weight:600">'
                "— Already declined</span>"
            )

        return mark_safe(approve_btn + "&nbsp;" + decline_btn + status_note)

    # ── Custom columns ────────────────────────────────────────────────────────

    @admin.display(description="User")
    def user_link(self, obj):
        from django.urls import reverse

        url = reverse("admin:account_user_change", args=[obj.user.pk])
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
            '<span style="color:#00a878;font-weight:700;">${}</span>',
            obj.net_amount,
        )

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {
            Transaction.Status.PENDING: "#f59e0b",
            Transaction.Status.CONFIRMED: "#3b82f6",
            Transaction.Status.COMPLETED: "#22c55e",
            Transaction.Status.FAILED: "#ef4444",
            Transaction.Status.CANCELLED: "#6b7280",
        }
        color = colors.get(obj.status, "#6b7280")
        return format_html(
            '<span style="background:{};color:#fff;padding:3px 10px;'
            'border-radius:12px;font-size:11px;font-weight:700;">{}</span>',
            color,
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

    # ── Changelist summary ────────────────────────────────────────────────────

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
