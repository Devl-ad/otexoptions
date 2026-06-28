import json
import logging
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.utils import timezone
from django.db import transaction
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from apps.account.referrals import record_referral_deposit
from django.conf import settings as django_setting
import requests
import uuid
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.views.decorators.csrf import csrf_exempt
from baseapp import notify

from apps.dashboard.decorator import withdrawal_confirm_required

from django.core.paginator import Paginator


from dashboard.tasks import run_bot_session

from dashboard.models import (
    Trade,
    Wallet,
    HouseSettings,
    TradingPair,
    PriceTick,
    Transaction,
    Agent,
    TodayRate,
    RecivingCryptoWallet,
)
from bot.models import BotTrade, BotSession, BotKey
from decimal import Decimal
from apps.account.models import User

logger = logging.getLogger(__name__)


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
