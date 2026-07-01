import json
import logging
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse

from .models import BotKey, BotTemplate, BotSession
from .tasks import run_bot_session
from apps.dashboard.models import TradingPair, Wallet

logger = logging.getLogger(__name__)


@login_required
def bot_page(request):
    pairs = TradingPair.objects.filter(is_active=True)
    return render(request, "bot/editor.html", {"pairs": pairs})


@login_required
def laod_bot_template(request):
    """
    AJAX — validate a bot key AND that it matches the bot type
    the user selected on the key-entry screen.
    """
    key = request.GET.get("key", "").strip().upper()
    bot_type = request.GET.get("type", "").strip().upper()

    try:
        bot_key = BotKey.objects.get(key=key, is_active=True)
    except BotKey.DoesNotExist:
        return JsonResponse({"valid": False, "error": "Invalid or inactive bot key."})

    return JsonResponse(
        {
            "valid": True,
            "bot_type": bot_key.bot_type,
            "bot_type_display": bot_key.get_bot_type_display(),
            "profit_pct": str(bot_key.profit_pct),
            "bot_key": bot_key.key,
        }
    )


@login_required
def validate_bot_key(request):
    """
    AJAX — validate a bot key AND that it matches the bot type
    the user selected on the key-entry screen.
    """
    key = request.GET.get("key", "").strip().upper()
    bot_type = request.GET.get("type", "").strip().upper()

    try:
        bot_key = BotKey.objects.get(key=key, is_active=True)
    except BotKey.DoesNotExist:
        return JsonResponse({"valid": False, "error": "Invalid or inactive bot key."})

    if bot_key.bot_type != bot_type:
        return JsonResponse(
            {
                "valid": False,
                "error": f"This key unlocks a {bot_key.get_bot_type_display()} bot, not {bot_type.replace('_', '/').title()}.",
            }
        )

    return JsonResponse(
        {
            "valid": True,
            "bot_type": bot_key.bot_type,
            "bot_type_display": bot_key.get_bot_type_display(),
            "profit_pct": str(bot_key.profit_pct),
            "bot_key": bot_key.key,
        }
    )


@login_required
def list_templates(request):
    """AJAX — list the current user's saved templates"""
    # bot_key_str = request.GET.get("bot_key", "").strip().upper()

    # try:
    #     bot_key = BotKey.objects.get(key=bot_key_str, is_active=True)
    # except BotKey.DoesNotExist:
    #     return JsonResponse({"templates": []})

    templates = BotTemplate.objects.filter(user=request.user)
    return JsonResponse(
        {
            "templates": [
                {
                    "id": t.id,
                    "name": t.name,
                    "trades_per_5min": t.trade_per_5min,
                    "session_duration": t.timeframe,
                    "bot_type": t.key.bot_type,
                    "bot_key": t.key.key,
                }
                for t in templates
            ]
        }
    )


@login_required
@require_POST
def save_template(request):
    """
    AJAX — create or update a user's saved bot template.
    If template_id is provided, update that template (must belong to the user).
    Otherwise create a new one.
    """
    try:
        data = json.loads(request.body)
        template_id = data.get("template_id")
        bot_key_str = data.get("bot_key", "").strip().upper()
        name = data.get("name", "").strip()
        trades_per_5min = int(data.get("trades_per_5min", 2))
        session_duration = int(data.get("session_duration", 5))

        if not name:
            return JsonResponse({"error": "Give your bot a name."}, status=400)

        if not (1 <= trades_per_5min <= 4):
            return JsonResponse(
                {"error": "Trade frequency must be between 1 and 4."}, status=400
            )

        if session_duration not in [5, 10, 20, 30]:
            return JsonResponse({"error": "Invalid session duration."}, status=400)

        try:
            bot_key = BotKey.objects.get(key=bot_key_str, is_active=True)
        except BotKey.DoesNotExist:
            return JsonResponse({"error": "Bot key is no longer active."}, status=400)

        if template_id:
            # update existing — must belong to this user
            try:
                template = BotTemplate.objects.get(id=template_id, user=request.user)
            except BotTemplate.DoesNotExist:
                return JsonResponse({"error": "Template not found."}, status=404)

            template.name = name
            template.key = bot_key
            template.trade_per_5min = trades_per_5min
            template.timeframe = session_duration
            template.save()
        else:
            # create new — check name uniqueness per user
            if BotTemplate.objects.filter(user=request.user, name=name).exists():
                return JsonResponse(
                    {
                        "error": f'You already have a bot saved as "{name}". Choose a different name.'
                    },
                    status=400,
                )
            template = BotTemplate.objects.create(
                user=request.user,
                key=bot_key,
                name=name,
                trade_per_5min=trades_per_5min,
                timeframe=session_duration,
            )

        return JsonResponse({"success": True, "template_id": template.id})

    except Exception as e:
        logger.error(f"Save template error: {e}")
        return JsonResponse(
            {"error": "Something went wrong saving your bot."}, status=500
        )


@login_required
@require_POST
def start_bot(request):
    """Start a bot session, using the key's house config + the chosen run settings."""
    try:
        data = json.loads(request.body)
        key = data.get("key", "").strip().upper()
        pair_symbol = data.get("pair")
        stake = data.get("stake")
        timeframe = int(data.get("timeframe", 5))
        trades_per_5min = int(data.get("trades_per_5min", 2))
        template_id = data.get("template_id")
        is_demo = data.get("is_demo", True)

        if timeframe not in [5, 10, 20, 30]:
            return JsonResponse({"error": "Invalid timeframe."}, status=400)
        if not (1 <= trades_per_5min <= 4):
            return JsonResponse(
                {"error": "Trade frequency must be between 1 and 4."}, status=400
            )

        bot_key = BotKey.objects.get(key=key, is_active=True)
        pair = TradingPair.objects.get(symbol=pair_symbol, is_active=True)

        bot_template = None
        if template_id:
            bot_template = BotTemplate.objects.filter(
                id=template_id, user=request.user
            ).first()
            # if it doesn't exist or doesn't belong to this user, just proceed without it
            # rather than blocking the run — it's only a snapshot reference

        active = BotSession.objects.filter(user=request.user, status="RUNNING").exists()
        if active:
            return JsonResponse(
                {"error": "You already have a bot running."}, status=400
            )

        wallet = Wallet.objects.get(user=request.user)
        total_trades = int((timeframe / 5) * trades_per_5min)
        total_needed = float(stake) * total_trades

        balance = float(wallet.demo_balance if is_demo else wallet.balance)
        if balance < total_needed:
            return JsonResponse(
                {
                    "error": f"Insufficient balance. You need ${total_needed:.2f} for this run."
                },
                status=400,
            )

        # snapshot house settings from the key at this exact moment
        house_settings = bot_key.get_settings(is_demo)

        session = BotSession.objects.create(
            user=request.user,
            bot_key=bot_key,
            bot_template=bot_template,
            pair=pair,
            stake_per_trade=stake,
            timeframe=timeframe,
            trade_per_5min=trades_per_5min,
            is_demo=is_demo,
            total_trades=total_trades,
            house_outcome=house_settings["house_outcome"],
            base_win_rate=house_settings["base_win_rate"],
            breakeven_min_pct=house_settings["breakeven_min_pct"],
            breakeven_max_pct=house_settings["breakeven_max_pct"],
            profit_pct=bot_key.profit_pct,
            status="RUNNING",
        )

        run_bot_session.delay(str(session.id))

        return JsonResponse(
            {
                "success": True,
                "session_id": str(session.id),
                "total_trades": total_trades,
                "total_needed": total_needed,
                "balance": balance,
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
