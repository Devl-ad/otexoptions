from decimal import Decimal
from django.db.models import Sum, Count, Q, Avg
from django.utils import timezone
from datetime import timedelta

from apps.dashboard.models import Wallet, Agent, Transaction
from apps.bot.models import BotSession
from .models import PlatformSettings


def get_platform_analytics():
    """
    Returns a full snapshot of platform liquidity, broken down by
    users, agents, and risk indicators — measured against the
    admin-configured target market cap.
    """
    settings_obj = PlatformSettings.load()
    target_cap = settings_obj.target_market_cap

    # ── User-side liquidity (LIVE only — demo never counts) ──────────────
    user_agg = Wallet.objects.exclude(user__is_affiliate=True).aggregate(
        total_live_balance=Sum("balance"),
        total_demo_balance=Sum("demo_balance"),
        active_live_users=Count("id", filter=Q(balance__gt=0)),
        total_wallets=Count("id"),
    )
    total_live_balance = user_agg["total_live_balance"] or Decimal("0.00")
    total_demo_balance = user_agg["total_demo_balance"] or Decimal("0.00")
    active_live_users = user_agg["active_live_users"] or 0
    total_wallets = user_agg["total_wallets"] or 0

    avg_live_balance = (
        round(total_live_balance / active_live_users, 2)
        if active_live_users > 0
        else Decimal("0.00")
    )

    top_holders = (
        Wallet.objects.filter(balance__gt=0)
        .exclude(user__is_affiliate=True)
        .select_related("user")
        .order_by("-balance")[:10]
    )

    # ── Agent-side liquidity ───────────────────────────────────────────────
    agent_agg = Agent.objects.aggregate(
        total_float=Sum("balance"),
        agent_count=Count("id"),
        avg_float=Avg("balance"),
    )
    total_agent_float = agent_agg["total_float"] or Decimal("0.00")
    agent_count = agent_agg["agent_count"] or 0
    avg_agent_float = agent_agg["avg_float"] or Decimal("0.00")

    # flag agents below the safety threshold relative to the average
    threshold_pct = settings_obj.safety_threshold_pct / 100
    safety_floor = (
        avg_agent_float * threshold_pct if avg_agent_float else Decimal("0.00")
    )

    low_float_agents = Agent.objects.filter(balance__lt=safety_floor).order_by(
        "balance"
    )

    agent_breakdown = Agent.objects.annotate(
        tx_count=Count("transactions"),
        completed_count=Count(
            "transactions", filter=Q(transactions__status="completed")
        ),
    ).order_by("-balance")

    # ── Current total liquidity vs target ───────────────────────────────────
    current_liquidity = total_live_balance + total_agent_float
    health_pct = (
        round((current_liquidity / target_cap) * 100, 1)
        if target_cap > 0
        else Decimal("0.00")
    )
    gap_to_target = target_cap - current_liquidity

    if health_pct >= 100:
        health_status = "healthy"
    elif health_pct >= 70:
        health_status = "warning"
    else:
        health_status = "critical"

    # ── All-time platform flow ──────────────────────────────────────────────
    flow_agg = (
        Transaction.objects.filter(status="completed")
        .exclude(user__is_affiliate=True)
        .aggregate(
            total_deposits=Sum("amount", filter=Q(transaction_type="deposit")),
            total_withdrawals=Sum("amount", filter=Q(transaction_type="withdrawal")),
        )
    )
    total_deposits = flow_agg["total_deposits"] or Decimal("0.00")
    total_withdrawals = flow_agg["total_withdrawals"] or Decimal("0.00")
    net_flow_all_time = total_deposits - total_withdrawals

    # ── Time-windowed flow (today / week / month) ───────────────────────────
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)

    def flow_since(start_time):
        agg = (
            Transaction.objects.filter(status="completed", created_at__gte=start_time)
            .exclude(user__is_affiliate=True)
            .aggregate(
                deposits=Sum("amount", filter=Q(transaction_type="deposit")),
                withdrawals=Sum("amount", filter=Q(transaction_type="withdrawal")),
            )
        )
        deposits = agg["deposits"] or Decimal("0.00")
        withdrawals = agg["withdrawals"] or Decimal("0.00")
        return {
            "deposits": deposits,
            "withdrawals": withdrawals,
            "net": deposits - withdrawals,
        }

    flow_today = flow_since(today_start)
    flow_week = flow_since(week_start)
    flow_month = flow_since(month_start)

    # ── Pending liability — money claimed but not yet confirmed ────────────
    pending_agg = (
        Transaction.objects.filter(status="pending")
        .exclude(user__is_affiliate=True)
        .aggregate(
            pending_deposits=Sum("amount", filter=Q(transaction_type="deposit")),
            pending_withdrawals=Sum("amount", filter=Q(transaction_type="withdrawal")),
        )
    )
    pending_deposits = pending_agg["pending_deposits"] or Decimal("0.00")
    pending_withdrawals = pending_agg["pending_withdrawals"] or Decimal("0.00")

    # ── Withdrawal coverage ratio — can we pay everyone right now? ──────────
    coverage_ratio = (
        round(total_agent_float / pending_withdrawals, 2)
        if pending_withdrawals > 0
        else None  # None = no pending withdrawals to worry about
    )

    # ── Bot exposure — money currently staked in running sessions ──────────
    try:

        bot_exposure_agg = BotSession.objects.filter(status="RUNNING").aggregate(
            exposure=Sum(
                "stake_per_trade"
            )  # rough — multiply by remaining trades for precision
        )
        bot_exposure = bot_exposure_agg["exposure"] or Decimal("0.00")
        running_bot_sessions = BotSession.objects.filter(status="RUNNING").count()
    except Exception:
        bot_exposure = Decimal("0.00")
        running_bot_sessions = 0

    return {
        "target_cap": target_cap,
        "current_liquidity": current_liquidity,
        "health_pct": health_pct,
        "health_status": health_status,
        "gap_to_target": gap_to_target,
        "users": {
            "total_live_balance": total_live_balance,
            "total_demo_balance": total_demo_balance,
            "active_live_users": active_live_users,
            "total_wallets": total_wallets,
            "avg_live_balance": avg_live_balance,
            "top_holders": top_holders,
        },
        "agents": {
            "total_float": total_agent_float,
            "agent_count": agent_count,
            "avg_float": (
                round(avg_agent_float, 2) if avg_agent_float else Decimal("0.00")
            ),
            "low_float_agents": low_float_agents,
            "breakdown": agent_breakdown,
        },
        "flow": {
            "all_time_deposits": total_deposits,
            "all_time_withdrawals": total_withdrawals,
            "net_all_time": net_flow_all_time,
            "today": flow_today,
            "week": flow_week,
            "month": flow_month,
        },
        "pending": {
            "deposits": pending_deposits,
            "withdrawals": pending_withdrawals,
        },
        "risk": {
            "coverage_ratio": coverage_ratio,
            "bot_exposure": bot_exposure,
            "running_bot_sessions": running_bot_sessions,
        },
    }
