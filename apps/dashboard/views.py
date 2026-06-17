import json
import logging
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.utils import timezone
from django.db import transaction
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from apps.account.models import KYCSubmission
from apps.account.forms import KYCForm
from apps.account.referrals import record_referral_deposit

from .tasks import run_bot_session
from apps.dashboard.utils import get_account_mode
from .models import (
    BotTrade,
    Trade,
    Wallet,
    HouseSettings,
    TradingPair,
    PriceTick,
    Transaction,
    Agent,
    BotSession,
    BotKey,
)
from decimal import Decimal
from apps.account.models import User

from django.db.models import Count, Sum, Avg, F, ExpressionWrapper, DecimalField, Q

logger = logging.getLogger(__name__)


@login_required
def dashboard(request):
    user = request.user
    mode = get_account_mode(request)

    trades = Trade.objects.filter(user=user, is_demo=(mode == "demo"))

    recent_trades = trades.select_related("pair").order_by("-opened_at")[:5]

    total_won = trades.filter(status="WON").count()
    total_lost = trades.filter(status="LOST").count()
    open_trades = trades.filter(status="OPEN").count()

    settled_trades = trades.filter(status__in=["WON", "LOST"]).count()

    win_rate = round((total_won / settled_trades) * 100, 1) if settled_trades > 0 else 0

    context = {
        "recent_trades": recent_trades,
        "total_won": total_won,
        "total_lost": total_lost,
        "open_trades": open_trades,
        "win_rate": win_rate,
    }

    return render(request, "dashboard/index.html", context)


@login_required
@require_POST
def switch_account_mode(request):
    mode = request.POST.get("mode")  # 'demo' or 'live'

    if mode not in ["demo", "live"]:
        return JsonResponse({"error": "Invalid mode."}, status=400)

    # check if user is verified before allowing live
    # if mode == "live":
    #     wallet = request.user.wallet
    #     # if not request.user.is_verified:  # add this field to your user model
    #     #     return JsonResponse({
    #     #         'error': 'Complete KYC verification to access live trading.'
    #     #     }, status=403)

    #     if float(wallet.balance) <= 0:
    #         return JsonResponse(
    #             {"error": "Please deposit funds to trade live."}, status=403
    #         )

    request.session["account_mode"] = mode
    request.session.modified = True

    wallet = request.user.wallet
    balance = str(wallet.demo_balance if mode == "demo" else wallet.balance)

    return JsonResponse(
        {
            "success": True,
            "mode": mode,
            "balance": balance,
        }
    )


@login_required
def trade_page(request):
    user = request.user
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    context = {"wallet": wallet}
    return render(request, "dashboard/trade.html", context)


@login_required
@require_POST
def place_trade(request):

    try:
        data = json.loads(request.body)

        pair_symbol = data.get("pair")
        trade_type = data.get("trade_type")  # RISE_FALL, OVER_UNDER, ACCUMULATOR
        direction = data.get("direction")  # RISE, FALL, OVER, UNDER, ACCUM
        stake = float(data.get("stake", 0))
        duration = int(data.get("duration", 5))
        duration_unit = data.get("duration_unit", "ticks")
        barrier = data.get("barrier", None)

        # --- validate ---
        if not all([pair_symbol, trade_type, direction]):
            return JsonResponse({"error": "Missing required fields."}, status=400)

        if stake <= 0:
            return JsonResponse({"error": "Stake must be greater than 0."}, status=400)

        # --- get pair ---
        try:
            pair = TradingPair.objects.get(symbol=pair_symbol, is_active=True)
        except TradingPair.DoesNotExist:
            return JsonResponse({"error": "Invalid or inactive pair."}, status=400)

        # --- get house settings ---
        house = HouseSettings.objects.get_or_create(pair=pair)[0]

        # --- validate stake limits ---
        if stake < float(house.min_stake):
            return JsonResponse(
                {"error": f"Minimum stake is ${house.min_stake}."}, status=400
            )
        if stake > float(house.max_stake):
            return JsonResponse(
                {"error": f"Maximum stake is ${house.max_stake}."}, status=400
            )

        # --- get wallet ---
        # wallet, _ = Wallet.objects.get_or_create(user=request.user)
        mode = get_account_mode(request)
        wallet = request.user.wallet
        current_balance = 0
        if mode == "live":
            current_balance = wallet.balance
        elif mode == "demo":
            current_balance = wallet.demo_balance

        if float(current_balance) < stake:
            return JsonResponse({"error": "Insufficient balance."}, status=400)

        # --- get current price ---
        latest_tick = PriceTick.objects.filter(pair=pair).latest()
        entry_price = latest_tick.price

        # --- calculate expiry ---
        if duration_unit == "ticks":
            # expiry by tick count — store ticks needed, no time expiry
            expires_at = None
        else:
            expires_at = timezone.now() + timedelta(seconds=duration)

        # --- atomic: debit stake + create trade ---
        with transaction.atomic():
            current_balance = wallet.debit(stake, mode=mode)

            trade = Trade.objects.create(
                user=request.user,
                pair=pair,
                trade_type=trade_type,
                direction=direction,
                stake=stake,
                payout_pct=house.payout_pct,
                entry_price=entry_price,
                barrier=barrier,
                duration=duration,
                duration_unit=duration_unit,
                expires_at=expires_at,
                house_edge=house.house_edge,
                status="OPEN",
                is_demo=(mode == "demo"),
            )

        return JsonResponse(
            {
                "success": True,
                "trade_id": trade.id,
                "entry_price": str(entry_price),
                "stake": str(stake),
                "payout_pct": str(house.payout_pct),
                "est_payout": str(
                    round(stake * (1 + float(house.payout_pct) / 100), 2)
                ),
                "balance": str(current_balance),
                "expires_at": expires_at.isoformat() if expires_at else None,
            }
        )

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def trade_status(request, trade_id):
    try:
        trade = Trade.objects.get(id=trade_id, user=request.user)
        wallet = Wallet.objects.get(user=request.user)
        return JsonResponse(
            {
                "status": trade.status,
                "payout": trade.payout,
                "stake": str(trade.stake),
                "profit": trade.profit,
                "balance": str(wallet.current_balance),
            }
        )
    except Trade.DoesNotExist:
        return JsonResponse({"error": "Trade not found."}, status=404)


@login_required
def transactions_logs(request):
    transactions = Transaction.objects.filter(user=request.user).order_by("-created_at")

    return render(
        request, "dashboard/transaction_logs.html", {"transactions": transactions}
    )


@login_required
def trade_logs(request):
    mode = get_account_mode(request)
    qs = Trade.objects.filter(
        user=request.user, is_demo=(mode == "demo")
    ).select_related("pair")

    total_trades = qs.count()
    won_count = qs.filter(status="WON").count()
    win_rate = round(won_count / total_trades * 100, 1) if total_trades else 0

    # Profit from WON trades: stake * payout_pct / 100
    won_profit = (
        qs.filter(status="WON")
        .annotate(
            trade_profit=ExpressionWrapper(
                F("stake") * F("payout_pct") / 100, output_field=DecimalField()
            )
        )
        .aggregate(total=Sum("trade_profit"))["total"]
        or 0
    )

    # Loss from LOST trades: sum of stakes
    lost_stakes = qs.filter(status="LOST").aggregate(total=Sum("stake"))["total"] or 0

    total_pnl = round(float(won_profit) - float(lost_stakes), 2)
    avg_stake = qs.aggregate(avg=Avg("stake"))["avg"] or 0
    avg_stake = round(float(avg_stake), 2)

    # Best single trade profit
    best_trade = (
        qs.filter(status="WON")
        .annotate(
            trade_profit=ExpressionWrapper(
                F("stake") * F("payout_pct") / 100, output_field=DecimalField()
            )
        )
        .order_by("-trade_profit")
        .values_list("trade_profit", flat=True)
        .first()
        or 0
    )

    # ── Trade list for the table
    trades_list = [
        {
            "id": t.id,
            "asset": t.pair.symbol,
            "trade_type": t.trade_type,
            "direction": t.direction,
            "stake": float(t.stake),
            "payout_pct": float(t.payout_pct),
            "pnl": t.profit,
            "payout": t.payout,
            "duration": t.get_duration_display(),
            "entry_price": float(t.entry_price),
            "exit_price": float(t.exit_price) if t.exit_price is not None else None,
            "barrier": float(t.barrier) if t.barrier is not None else None,
            "status": t.status,
            "is_demo": t.is_demo,
            "opened_at": t.opened_at,
        }
        for t in qs.order_by("-opened_at")
    ]
    bot_trades = BotTrade.objects.filter(
        session__user=request.user, session__is_demo=(mode == "demo")
    ).select_related("session")
    for bt in bot_trades:
        trades_list.append(
            {
                "id": bt.id,
                "source": "bot",
                "asset": "BOT",  # or actual asset if available
                "trade_type": "BOT",
                "direction": bt.direction,
                "stake": float(bt.stake),
                "payout_pct": None,
                "pnl": float(bt.profit),
                "payout": (
                    float(bt.stake) + float(bt.profit) if bt.result == "WON" else 0
                ),
                "duration": None,
                "entry_price": float(bt.entry_price),
                "exit_price": float(bt.exit_price) if bt.exit_price else None,
                "status": bt.result,
                "opened_at": bt.executed_at,
            }
        )

    # Sort everything together
    trades_list.sort(key=lambda x: x["opened_at"], reverse=True)

    # Format dates after sorting
    for trade in trades_list:
        trade["opened_at"] = trade["opened_at"].strftime("%d %b %Y, %I:%M %p")

    # ── Combined Statistics

    # Manual trades
    manual_total = qs.count()
    manual_won = qs.filter(status="WON").count()

    manual_profit = sum(t.profit for t in qs if t.status in ["WON", "LOST"])

    manual_stakes = [float(t.stake) for t in qs]

    manual_best = max(
        [float(t.profit) for t in qs if t.status == "WON"],
        default=0,
    )

    # Bot trades
    bot_total = bot_trades.count()
    bot_won = bot_trades.filter(result="WON").count()

    bot_profit = sum(
        float(bt.profit) for bt in bot_trades if bt.result in ["WON", "LOST"]
    )

    bot_stakes = [float(bt.stake) for bt in bot_trades]

    bot_best = max(
        [float(bt.profit) for bt in bot_trades if bt.result == "WON"],
        default=0,
    )

    # Combined values
    total_trades = manual_total + bot_total
    won_count = manual_won + bot_won

    win_rate = round((won_count / total_trades) * 100, 1) if total_trades else 0

    total_pnl = round(manual_profit + bot_profit, 2)

    all_stakes = manual_stakes + bot_stakes

    avg_stake = round(sum(all_stakes) / len(all_stakes), 2) if all_stakes else 0

    best_trade = round(max(manual_best, bot_best), 2)

    context = {
        "trades_json": json.dumps(trades_list),
        "total_trades": total_trades,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "avg_stake": avg_stake,
        "best_trade": round(float(best_trade), 2),
        "won_count": won_count,
    }
    return render(request, "dashboard/trade_logs.html", context)


@login_required
def deposit_page(request):
    agents = Agent.objects.all()
    return render(request, "dashboard/deposit.html", {"agents": agents})


@login_required
def deposit_withcrypto_page(request):

    if request.method == "POST":
        coin = request.POST.get("coin")
        amount = request.POST.get("amount")
        tx_hash = request.POST.get("tx_hash")

        try:
            amount = Decimal(amount)
        except:
            messages.error(request, "Invalid deposit amount.")
            return redirect("deposit_withcrypto_page")

        if amount < Decimal("20"):
            messages.error(request, "Minimum deposit is $20.")
            return redirect("deposit_withcrypto_page")

        method_map = {
            "btc": Transaction.Method.CRYPTO_BTC,
            "usdt": Transaction.Method.CRYPTO_USDT,
            "eth": Transaction.Method.CRYPTO_ETH,
        }

        Transaction.objects.create(
            user=request.user,
            transaction_type=Transaction.TransactionType.DEPOSIT,
            method=method_map.get(
                coin,
                Transaction.Method.CRYPTO_USDT,
            ),
            amount=amount,
            fee=Decimal("0.00"),
            net_amount=amount,
            tx_hash=tx_hash,
            status=Transaction.Status.PENDING,
        )

        messages.success(
            request,
            "Deposit request submitted! Your balance will be updated in 2–4 hours after confirmation.",
        )

        return redirect("deposit_withcrypto_page")
    return render(request, "dashboard/deposit-crypto.html")


@login_required
def withdrawal(request):

    wallet = request.user.wallet
    # if request.user.is_verified == False:
    #     messages.info(request, "Verify your account!")
    #     return redirect("kyc_verify")
    if request.method == "POST":
        coin = request.POST.get("coin")
        amount = request.POST.get("amount")
        address = request.POST.get("address")
        fee = request.POST.get("fee")

        try:
            amount = Decimal(amount)
        except:
            messages.error(request, "Invalid withdrawal amount.")
            return redirect("withdrawal")

        if amount < Decimal("30"):
            messages.error(request, "Minimum withdrawal is $30.")
            return redirect("withdrawal")

        if amount > wallet.balance:
            messages.error(request, "Insufficient balance.")
            return redirect("withdrawal")

        method_map = {
            "btc": Transaction.Method.CRYPTO_BTC,
            "usdt": Transaction.Method.CRYPTO_USDT,
            "eth": Transaction.Method.CRYPTO_ETH,
        }

        Transaction.objects.create(
            user=request.user,
            transaction_type=Transaction.TransactionType.WITHDRAWAL,
            method=method_map.get(
                coin,
                Transaction.Method.CRYPTO_USDT,
            ),
            amount=amount,
            fee=Decimal(fee),
            net_amount=amount,
            crypto_address=address,
            status=Transaction.Status.PENDING,
        )

        wallet.debit(float(amount), mode="live")

        messages.success(
            request,
            "Your withdrawal request has been received and is under review.",
        )

        return redirect("withdrawal")
    return render(request, "dashboard/withdrawal.html")


@login_required
def settings(request):
    return render(request, "dashboard/settings.html")


@login_required
def notification_page(request):
    return render(request, "dashboard/notification.html")


@login_required
def kyc_page(request):

    try:
        kyc = request.user.kyc
    except KYCSubmission.DoesNotExist:
        kyc = None

    if kyc is None:
        current_step = 2
    elif kyc.status in (KYCSubmission.Status.PENDING, KYCSubmission.Status.APPROVED):
        current_step = 5
    else:
        current_step = 2  # rejected — allow resubmission

    # ── POST ────────────────────────────────────────────
    if request.method == "POST":

        # Block if already pending or approved
        if kyc and not kyc.can_resubmit:
            messages.warning(
                request, "Your KYC is already under review or has been approved."
            )
            return redirect("dashboard")

        form = KYCForm(request.POST, request.FILES, instance=kyc)

        if form.is_valid():
            submission = form.save(commit=False)
            submission.user = request.user
            submission.status = KYCSubmission.Status.PENDING
            submission.submitted_at = timezone.now()
            submission.admin_note = ""
            submission.save()

            messages.success(
                request,
                "Your KYC documents have been submitted. "
                "We will review them within 1–3 business days.",
            )
            return redirect("kyc_verify")

        # Invalid — re-render with errors, re-open at step 2
        current_step = 2

    # ── GET (or invalid POST falls through here) ────────
    else:
        form = KYCForm(instance=kyc) if kyc else KYCForm()

    # ── Banner ──────────────────────────────────────────
    if kyc:
        banner_class = kyc.banner_class
        banner_title, banner_body = kyc.banner_message
    else:
        banner_class = "unverified"
        banner_title = "Identity Not Verified"
        banner_body = (
            "Complete the form below to unlock full trading access and higher limits."
        )

    # ── Pending summary (read-only table) ───────────────
    pending_summary = []
    if kyc and kyc.status == KYCSubmission.Status.PENDING:
        pending_summary = [
            ("Full Name", kyc.full_name),
            ("Date of Birth", kyc.date_of_birth.strftime("%d %b %Y")),
            ("Nationality", kyc.nationality),
            ("Document Type", kyc.get_document_type_display()),
            ("Document Number", kyc.document_number),
            ("Phone", kyc.phone),
            ("City", kyc.city),
            ("Submitted", kyc.submitted_at.strftime("%d %b %Y, %I:%M %p")),
        ]

    context = {
        "form": form,
        "kyc": kyc,
        "banner_class": banner_class,
        "banner_title": banner_title,
        "banner_body": banner_body,
        "current_step": current_step,
        "pending_summary": pending_summary,
        "can_edit": kyc is None or (kyc and kyc.can_resubmit),
    }
    return render(request, "dashboard/kyc_verify.html", context)


@login_required
def bot_page(request):
    pairs = TradingPair.objects.filter(is_active=True)
    return render(request, "dashboard/bot.html", {"pairs": pairs})


@login_required
def validate_bot_key(request):
    """AJAX — validate a bot key and return its parameters."""
    key = request.GET.get("key", "").strip().upper()

    try:
        bot_key = BotKey.objects.select_related("template").get(key=key, is_active=True)
        template = bot_key.template
        return JsonResponse(
            {
                "valid": True,
                "bot_type": template.get_bot_type_display(),
                "risk_level": template.get_risk_level_display(),
                "profit_pct": str(template.profit_pct),
                "trades_per_5min": template.trades_per_5min,
                "description": template.description,
                "name": template.name,
            }
        )
    except BotKey.DoesNotExist:
        return JsonResponse({"valid": False, "error": "Invalid or inactive bot key."})


@login_required
@require_POST
def start_bot(request):
    """Start a bot session."""
    try:
        data = json.loads(request.body)
        key = data.get("key", "").strip().upper()
        pair_symbol = data.get("pair")
        stake = data.get("stake")
        timeframe = int(data.get("timeframe", 5))
        is_demo = data.get("is_demo", True)

        # validate
        if timeframe not in [5, 10, 20, 30]:
            return JsonResponse({"error": "Invalid timeframe."}, status=400)

        bot_key = BotKey.objects.select_related("template").get(
            key=key, is_active=True, template__is_active=True
        )
        pair = TradingPair.objects.get(symbol=pair_symbol, is_active=True)

        # check no active session already running
        active = BotSession.objects.filter(user=request.user, status="RUNNING").exists()
        if active:
            return JsonResponse(
                {"error": "You already have a bot running."}, status=400
            )

        # check wallet balance
        wallet = Wallet.objects.get(user=request.user)
        template = bot_key.template
        total_trades = int((timeframe / 5) * template.trades_per_5min)
        total_needed = float(stake) * total_trades

        balance = float(wallet.demo_balance if is_demo else wallet.balance)
        if balance < total_needed:
            return JsonResponse(
                {
                    "error": f"Insufficient balance. You need ${total_needed:.2f} for this run."
                },
                status=400,
            )

        # create session
        session = BotSession.objects.create(
            user=request.user,
            bot_key=bot_key,
            pair=pair,
            stake_per_trade=stake,
            timeframe=timeframe,
            is_demo=is_demo,
        )

        # fire celery task
        run_bot_session.delay(str(session.id))

        return JsonResponse(
            {
                "success": True,
                "session_id": str(session.id),
                "total_trades": total_trades,
                "total_needed": total_needed,
            }
        )

    except BotKey.DoesNotExist:
        return JsonResponse({"error": "Invalid bot key."}, status=400)
    except TradingPair.DoesNotExist:
        return JsonResponse({"error": "Invalid trading pair."}, status=400)
    except Exception as e:
        logger.error(f"Start bot error: {e}")
        return JsonResponse({"error": "Something went wrong."}, status=500)


@login_required
def session_summary(request, session_id):
    """Return session summary for the modal."""
    try:
        session = BotSession.objects.prefetch_related("bot_trades").get(
            id=session_id, user=request.user
        )
        trades = list(
            session.bot_trades.values(
                "trade_number", "direction", "result", "stake", "profit", "entry_price"
            )
        )
        return JsonResponse(
            {
                "outcome": session.outcome,
                "total_trades": session.total_trades,
                "trades_won": session.trades_won,
                "trades_lost": session.trades_lost,
                "net_pnl": str(session.net_pnl),
                "gross_profit": str(session.gross_profit),
                "gross_loss": str(session.gross_loss),
                "win_rate": str(session.win_rate),
                "total_staked": str(session.total_staked),
                "trades": trades,
            }
        )
    except BotSession.DoesNotExist:
        return JsonResponse({"error": "Session not found."}, status=404)


@login_required
def agent_dashboard(request):
    """
    Only accessible by users who are linked to an Agent record.
    Shows balance, stats, and recent activity.
    """
    agent = get_object_or_404(Agent, user=request.user, is_active=True)

    # Stats
    today = timezone.now().date()

    credits_today = Transaction.objects.filter(
        agent=agent,
        transaction_type=Transaction.TransactionType.DEPOSIT,
        status=Transaction.Status.COMPLETED,
        created_at__date=today,
    )
    credits_today_count = credits_today.count()
    credits_today_amount = credits_today.aggregate(t=Sum("amount"))["t"] or Decimal("0")

    all_time_amount = Transaction.objects.filter(
        agent=agent,
        transaction_type=Transaction.TransactionType.DEPOSIT,
        status=Transaction.Status.COMPLETED,
    ).aggregate(t=Sum("amount"))["t"] or Decimal("0")

    recent_transactions = (
        Transaction.objects.filter(
            agent=agent,
        )
        .select_related("user")
        .order_by("-created_at")[:10]
    )

    context = {
        "agent": agent,
        "credits_today_count": credits_today_count,
        "credits_today_amount": credits_today_amount,
        "all_time_amount": all_time_amount,
        "recent_transactions": recent_transactions,
    }
    return render(request, "dashboard/agent.html", context)


# ─────────────────────────────────────────────
# Username lookup (AJAX)
# ─────────────────────────────────────────────


@login_required
def lookup_user(request):
    """
    GET /agent/lookup-user/?username=kwame23
    Returns whether the user exists and their display name.
    Called live from the credit modal as the agent types.
    """
    username = request.GET.get("username", "").strip()

    if not username:
        return JsonResponse({"found": False, "error": "No username provided."})

    try:
        user = User.objects.get(username__iexact=username)
        return JsonResponse(
            {
                "found": True,
                "username": user.username,
                "full_name": user.get_full_name(),
            }
        )
    except User.DoesNotExist:
        return JsonResponse({"found": False})


# ─────────────────────────────────────────────
# Credit user (AJAX POST)
# ─────────────────────────────────────────────


@login_required
@require_POST
def credit_user(request):
    """
    POST /agent/credit-user/
    Body: username=kwame23&amount=300.00

    Deducts from agent balance (if you track it on the Agent model),
    creates a completed Transaction, and credits the user's live wallet.
    """
    agent = get_object_or_404(Agent, user=request.user, is_active=True)

    username = request.POST.get("username", "").strip()
    raw_amount = request.POST.get("amount", "").strip()

    # ── Validate ──────────────────────────────────────
    if not username:

        return JsonResponse(
            {"success": False, "error": "Username is required."}, status=400
        )

    logger.warning(
        f"Validation one failed — username was Full. Raw POST data: {request.POST}"
    )

    try:
        target_user = User.objects.get(username__iexact=username)
        logger.info(f"{target_user}")
    except User.DoesNotExist as e:
        logger.warning(f"User naot found {e}")
        return JsonResponse({"success": False, "error": "User not found."}, status=404)

    try:
        amount = Decimal(raw_amount)
        if amount < Decimal("1.00"):
            raise ValueError
    except (ValueError, Exception):
        return JsonResponse({"success": False, "error": "Invalid amount."}, status=400)

    if amount < agent.min_deposit:
        return JsonResponse(
            {
                "success": False,
                "error": f"Minimum credit amount is ${agent.min_deposit}.",
            },
            status=400,
        )

    if amount > agent.max_deposit:
        return JsonResponse(
            {
                "success": False,
                "error": f"Maximum credit amount is ${agent.max_deposit}.",
            },
            status=400,
        )

    # ── Calculate fee ──────────────────────────────────
    fee = (amount * agent.fee_percent / 100).quantize(Decimal("0.01"))
    net_amount = amount - fee

    # ── Create transaction ─────────────────────────────
    transaction = Transaction.objects.create(
        user=target_user,
        agent=agent,
        transaction_type=Transaction.TransactionType.DEPOSIT,
        method=Transaction.Method.AGENT,
        amount=amount,
        fee=fee,
        status=Transaction.Status.COMPLETED,
        confirmed_at=timezone.now(),
    )

    # ── Credit the user's live wallet ─────────────────
    # Adjust this to match your actual wallet / balance model.
    # Example using a Profile with a live_balance field:
    target_user_wallet = Wallet.objects.get(user=target_user)
    target_user_wallet.credit(float(net_amount), mode="live")
    target_user_wallet.save(update_fields=["balance"])

    record_referral_deposit(target_user, amount=net_amount)

    # ── Update agent trade count ───────────────────────
    agent.balance -= amount
    agent.total_trades += 1
    agent.save(update_fields=["balance", "total_trades"])

    return JsonResponse(
        {
            "success": True,
            "reference": transaction.reference,
            "username": target_user.username,
            "amount": str(amount),
            "net": str(net_amount),
            "fee": str(fee),
            "new_balance": str(agent.balance),
        }
    )


def faq(request):
    return render(request, "dashboard/faq.html")
