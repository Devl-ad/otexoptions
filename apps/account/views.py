import qrcode
import qrcode.image.svg
import io
from django.db import transaction
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.http import require_POST
from django.db.models import Sum, Count, Q
import logging
from .forms import AccountDetailsForm, PersonalInfoForm, AddressForm
from .models import Details, Referral, ReferralDeposit
from .emails import send_activation_email, send_password_reset_email
from .forms import (
    LoginForm,
    PasswordResetConfirmForm,
    PasswordResetRequestForm,
    RegisterForm,
    TOTPEnableForm,
    TOTPVerifyForm,
)
from .tokens import account_activation_token, password_reset_token
from .decorator import affiliate_required

import json
from django.core.serializers.json import DjangoJSONEncoder

User = get_user_model()
logger = logging.getLogger(__name__)


# ── Session key used to hold the pre-2FA authenticated user pk ──────────────
TOTP_SESSION_KEY = "_totp_user_pk"
TOTP_REMEMBER_KEY = "_totp_remember"


@login_required
def complete_profile(request):

    if request.user.is_completed:
        messages.info(request, "Your profile is already complete.")
        return redirect("dashboard")

    details, _ = Details.objects.get_or_create(user=request.user)

    step = int(request.POST.get("step", request.session.get("profile_step", 1)))

    forms_classes = {
        1: PersonalInfoForm,
        2: AddressForm,
        3: AccountDetailsForm,
    }

    if request.method == "POST":
        form = forms_classes[step](request.POST)

        if form.is_valid():
            # save step data to session
            request.session[f"profile_step_{step}"] = form.cleaned_data
            request.session["profile_step"] = step + 1

            if step == 3:
                # all steps done, merge and save
                data = {}
                for s in [1, 2, 3]:
                    data.update(request.session.get(f"profile_step_{s}", {}))

                for field, value in data.items():
                    setattr(details, field, value)
                details.save()

                # clear session
                for s in [1, 2, 3]:
                    request.session.pop(f"profile_step_{s}", None)
                request.session.pop("profile_step", None)

                request.user.is_active = True
                request.user.is_completed = True
                request.user.save(update_fields=["is_active", "is_completed"])

                messages.success(
                    request, "Your account has been activated successfully."
                )
                return redirect("dashboard")

            return redirect("account:complete_profile")
        # form invalid, stay on same step
    else:
        step = request.session.get("profile_step", 1)
        back = request.GET.get("back")
        if back and step > 1:
            step -= 1
            request.session["profile_step"] = step
        initial = request.session.get(f"profile_step_{step}", {})
        form = forms_classes[step](initial=initial)

    return render(
        request,
        "account/complete_profile.html",
        {
            "form": form,
            "step": step,
        },
    )


# ────────────────────────────────────────────────────────────────────────────
# Registration & Activation
# ────────────────────────────────────────────────────────────────────────────


def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    form = RegisterForm(request.POST or None)

    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save(commit=False)

                    # User must verify email first
                    user.is_active = False
                    user.email_verified = False

                    user.save()

                    # Create empty profile record
                    Details.objects.create(user=user)

                    # handle referral
                    ref_code = request.session.get("ref_code")

                    if ref_code:
                        try:
                            referrer = User.objects.get(username=ref_code)

                            user.referred_by = referrer
                            user.save(update_fields=["referred_by"])

                            # increment referrer's count
                            referrer.total_referrals += 1
                            referrer.save(update_fields=["total_referrals"])

                            # create referral record
                            Referral.objects.create(referrer=referrer, referred=user)

                            # clear from session
                            del request.session["ref_code"]
                            request.session.modified = True

                        except User.DoesNotExist:
                            pass  # invalid ref code — just ignore silently

                    # Send activation email
                    send_activation_email(request, user)

                messages.success(
                    request,
                    (
                        " Please check your email and click the activation link to verify your account."
                    ),
                )

                return redirect("account:register")

            except Exception as e:
                logger.error(f"Error during registration: {e}")
                messages.error(
                    request,
                    (
                        "An error occurred while creating your account. "
                        "Please try again."
                    ),
                )

    return render(
        request,
        "account/register.html",
        {"form": form},
    )


def activate(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user and account_activation_token.check_token(user, token):

        user.is_active = True
        user.email_verified = True
        user.save(update_fields=["is_active", "email_verified"])

        login(request, user)

        messages.success(
            request, "Email verified successfully. Please complete your profile."
        )

        return redirect("account:complete_profile")
    else:
        messages.error(request, "Invalid activation link.")
        return redirect("account:register")


# ────────────────────────────────────────────────────────────────────────────
# Login / Logout
# ────────────────────────────────────────────────────────────────────────────


def user_login(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = authenticate(
            request,
            username=form.cleaned_data["email"],
            password=form.cleaned_data["password"],
        )

        if user is None:
            messages.error(request, "Invalid email or password.")
            return render(request, "account/login.html", {"form": form})

        if not user.is_active or not user.email_verified:
            messages.warning(request, "Please verify your email before logging in.")
            return render(request, "account/login.html", {"form": form})

        remember_me = form.cleaned_data.get("remember_me", False)

        if user.totp_enabled:
            # Park the user in the session and send them to 2FA step
            request.session[TOTP_SESSION_KEY] = user.pk
            request.session[TOTP_REMEMBER_KEY] = remember_me
            return redirect("account:totp_verify")

        _complete_login(request, user, remember_me)
        return redirect("dashboard")

    return render(request, "account/login.html", {"form": form})


def user_logout(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("account:login")


def _complete_login(request, user, remember_me=False):
    login(request, user)
    if not remember_me:
        request.session.set_expiry(0)  # browser-session only


# ────────────────────────────────────────────────────────────────────────────
# TOTP – verification at login
# ────────────────────────────────────────────────────────────────────────────


def totp_verify(request):
    user_pk = request.session.get(TOTP_SESSION_KEY)
    if not user_pk:
        return redirect("account:login")

    user = get_object_or_404(User, pk=user_pk)
    form = TOTPVerifyForm(request.POST or None, user=user)

    if request.method == "POST" and form.is_valid():
        remember_me = request.session.pop(TOTP_REMEMBER_KEY, False)
        request.session.pop(TOTP_SESSION_KEY, None)
        _complete_login(request, user, remember_me)
        return redirect("dashboard")

    return render(request, "account/totp_verify.html", {"form": form})


# ────────────────────────────────────────────────────────────────────────────
# TOTP – enable / disable from settings
# ────────────────────────────────────────────────────────────────────────────


@login_required
def totp_setup(request):
    user = request.user

    # Generate a fresh secret if none yet
    if not user.totp_secret:

        user.generate_totp_secret()

    # Build QR code as inline SVG
    qr = qrcode.make(
        user.get_totp_uri(),
        image_factory=qrcode.image.svg.SvgPathImage,
    )
    svg_buf = io.BytesIO()
    qr.save(svg_buf)
    qr_svg = svg_buf.getvalue().decode("utf-8")

    form = TOTPEnableForm(request.POST or None, user=user)
    if request.method == "POST":

        if form.is_valid():
            user.totp_enabled = True
            user.save(update_fields=["totp_enabled"])
            logger.info(f"TOTP enabled for user: {user.email}")
            messages.success(request, "Two-factor authentication is now enabled.")
            return redirect("dashboard")

    return render(
        request,
        "account/totp_setup.html",
        {"form": form, "qr_svg": qr_svg, "secret": user.totp_secret},
    )


@login_required
@require_POST
def totp_disable(request):
    user = request.user
    user.totp_enabled = False
    user.totp_secret = ""
    user.save(update_fields=["totp_enabled", "totp_secret"])
    messages.success(request, "Two-factor authentication has been disabled.")
    return redirect("dashboard")


# ────────────────────────────────────────────────────────────────────────────
# Password Reset
# ────────────────────────────────────────────────────────────────────────────


def password_reset_request(request):
    form = PasswordResetRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].lower()
        try:
            user = User.objects.get(email=email, is_active=True)
            send_password_reset_email(request, user)
        except User.DoesNotExist:
            pass  # Don't reveal whether the address exists
        messages.info(
            request,
            "If that email is registered, you'll receive a reset link shortly.",
        )
        return redirect("account:password_reset_request")

    return render(request, "account/password_reset_request.html", {"form": form})


def password_reset_confirm(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist) as e:
        logger.error(f"Password reset confirm error: {e}")
        user = None

    valid = user is not None and password_reset_token.check_token(user, token)

    if not valid:
        return render(request, "account/password_reset_invalid.html", status=400)

    form = PasswordResetConfirmForm(user=user, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Password updated. You can now log in.")
        return redirect("account:login")

    return render(request, "account/password_reset_confirm.html", {"form": form})


@login_required
@affiliate_required
def affiliate_dashboard(request):
    referrals = (
        Referral.objects.filter(referrer=request.user)
        .select_related("referred")
        .prefetch_related("deposits")
        .order_by("-created_at")
    )

    stats = referrals.aggregate(
        total_referred=Count("id"),
        total_active=Count("id", filter=Q(status="ACTIVE")),
        total_deposited=Sum("total_deposited"),
        total_commission=Sum("total_commission"),
    )

    # build JSON for frontend table
    referrals_json = json.dumps(
        [
            {
                "initials": (
                    referred := r.referred,
                    (
                        (referred.first_name[0] + referred.last_name[0]).upper()
                        if referred.first_name and referred.last_name
                        else referred.username[:2].upper()
                    ),
                )[-1],
                "name": referred.get_full_name() or referred.username,
                "username": "@" + referred.username,
                "joined": r.created_at.strftime("%d %b %Y"),
                "status": r.status,
                "total_deposited": float(r.total_deposited),
                "commission": float(r.total_commission),
                "last_deposit": (
                    r.last_deposit_at.strftime("%d %b %Y") if r.last_deposit_at else "—"
                ),
            }
            for r in referrals
        ],
        cls=DjangoJSONEncoder,
    )

    return render(
        request,
        "affiliate/dashboard.html",
        {
            "referrals": referrals,
            "referrals_json": referrals_json,
            "stats": stats,
            "referral_link": f"https://otexoption.com/?ref={request.user.username}",
            "commission_rate": (
                referrals.first().commission_rate if referrals.exists() else 5
            ),
        },
    )
