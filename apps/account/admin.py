from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from .models import User, Details, KYCSubmission, Referral, ReferralDeposit


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "email",
        "username",
        "is_active",
        "email_verified",
        "totp_enabled",
        "date_joined",
    )
    list_filter = ("is_active", "is_staff", "email_verified", "totp_enabled")
    search_fields = ("email", "username", "first_name", "last_name")
    ordering = ("-date_joined",)

    fieldsets = (
        (None, {"fields": ("email", "username", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "phone_number")}),
        (
            _("Status"),
            {"fields": ("is_active", "email_verified", "is_staff", "is_superuser")},
        ),
        (
            _("Afiliate"),
            {"fields": ("is_affiliate",)},
        ),
        (_("2FA"), {"fields": ("totp_enabled", "totp_secret")}),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
        (
            _("Referral"),
            {
                "fields": ("referred_by",),
            },
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "username", "password1", "password2"),
            },
        ),
    )


admin.site.register(Details)


def approve_kyc(modeladmin, request, queryset):
    for submission in queryset:
        submission.status = KYCSubmission.Status.APPROVED
        submission.reviewed_at = timezone.now()
        submission.reviewed_by = request.user
        submission.save()

        # update user
        user = submission.user
        user.is_verified = True
        user.save(update_fields=["is_verified"])

        # send approval email
        try:
            send_mail(
                subject="Your OTEX account has been verified ✅",
                message="",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=f"""
                <div style="font-family:Inter,sans-serif;max-width:560px;margin:0 auto;padding:32px 24px;background:#fff;">
                    <div style="text-align:center;margin-bottom:28px">
                        <svg width="40" height="40" viewBox="0 0 32 32" fill="none">
                            <rect x="2" y="18" width="6" height="12" rx="2" fill="#E85D35"/>
                            <rect x="11" y="10" width="6" height="20" rx="2" fill="#E85D35" opacity="0.75"/>
                            <rect x="20" y="4" width="6" height="26" rx="2" fill="#E85D35" opacity="0.45"/>
                        </svg>
                        <h1 style="font-size:22px;font-weight:800;color:#111;margin:12px 0 4px">OTEX</h1>
                    </div>

                    <div style="background:#f0fdf4;border-radius:12px;padding:24px;text-align:center;margin-bottom:24px">
                        <div style="font-size:40px;margin-bottom:8px">✅</div>
                        <h2 style="font-size:18px;font-weight:700;color:#166534;margin:0">
                            KYC Approved!
                        </h2>
                    </div>

                    <p style="font-size:14px;color:#444;line-height:1.7">
                        Hi <strong>{user.get_full_name() or user.username}</strong>,
                    </p>
                    <p style="font-size:14px;color:#444;line-height:1.7">
                        Your identity verification has been approved. You now have full access 
                        to live trading on OTEX.
                    </p>

                    <div style="margin:24px 0">
                        <a href="https://otexoption.com/dashboard"
                           style="display:inline-block;background:#E85D35;color:#fff;
                                  padding:13px 28px;border-radius:10px;font-size:14px;
                                  font-weight:700;text-decoration:none">
                            Start Trading →
                        </a>
                    </div>

                    <p style="font-size:12px;color:#aaa;margin-top:32px;border-top:1px solid #f0f0f0;padding-top:16px">
                        OTEX Options · otexoption.com
                    </p>
                </div>
                """,
            )
        except Exception as e:
            modeladmin.message_user(
                request,
                f"KYC approved for {user.email} but email failed: {e}",
                level="warning",
            )


approve_kyc.short_description = "✅ Approve selected submissions"


def reject_kyc(modeladmin, request, queryset):
    for submission in queryset:
        submission.status = KYCSubmission.Status.REJECTED
        submission.reviewed_at = timezone.now()
        submission.reviewed_by = request.user
        submission.save()

        user = submission.user
        user.is_verified = False
        user.save(update_fields=["is_verified"])

        # send rejection email
        try:
            send_mail(
                subject="OTEX KYC Verification Update",
                message="",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=f"""
                <div style="font-family:Inter,sans-serif;max-width:560px;margin:0 auto;padding:32px 24px;background:#fff;">
                    <div style="text-align:center;margin-bottom:28px">
                        <svg width="40" height="40" viewBox="0 0 32 32" fill="none">
                            <rect x="2" y="18" width="6" height="12" rx="2" fill="#E85D35"/>
                            <rect x="11" y="10" width="6" height="20" rx="2" fill="#E85D35" opacity="0.75"/>
                            <rect x="20" y="4" width="6" height="26" rx="2" fill="#E85D35" opacity="0.45"/>
                        </svg>
                        <h1 style="font-size:22px;font-weight:800;color:#111;margin:12px 0 4px">OTEX</h1>
                    </div>

                    <div style="background:#fef2f2;border-radius:12px;padding:24px;text-align:center;margin-bottom:24px">
                        <div style="font-size:40px;margin-bottom:8px">❌</div>
                        <h2 style="font-size:18px;font-weight:700;color:#991b1b;margin:0">
                            Verification Unsuccessful
                        </h2>
                    </div>

                    <p style="font-size:14px;color:#444;line-height:1.7">
                        Hi <strong>{user.get_full_name() or user.username}</strong>,
                    </p>
                    <p style="font-size:14px;color:#444;line-height:1.7">
                        Unfortunately we were unable to verify your identity with the 
                        documents provided. This may be due to:
                    </p>
                    <ul style="font-size:14px;color:#444;line-height:2;padding-left:20px">
                        <li>Blurry or unclear document images</li>
                        <li>Expired identity document</li>
                        <li>Information mismatch</li>
                        <li>Incomplete submission</li>
                    </ul>

                    {f'<div style="background:#fff7ed;border-radius:8px;padding:14px 16px;margin:16px 0;font-size:13px;color:#92400e"><strong>Admin note:</strong> {submission.admin_note}</div>' if submission.admin_note else ''}

                    <p style="font-size:14px;color:#444;line-height:1.7">
                        You can resubmit your KYC with clearer documents.
                    </p>

                    <div style="margin:24px 0">
                        <a href="https://otexoption.com/kyc"
                           style="display:inline-block;background:#E85D35;color:#fff;
                                  padding:13px 28px;border-radius:10px;font-size:14px;
                                  font-weight:700;text-decoration:none">
                            Resubmit KYC →
                        </a>
                    </div>

                    <p style="font-size:12px;color:#aaa;margin-top:32px;border-top:1px solid #f0f0f0;padding-top:16px">
                        OTEX Options · otexoption.com
                    </p>
                </div>
                """,
            )
        except Exception as e:
            modeladmin.message_user(
                request,
                f"KYC rejected for {user.email} but email failed: {e}",
                level="warning",
            )


reject_kyc.short_description = "❌ Reject selected submissions"


class ReferralDepositInline(admin.TabularInline):
    model = ReferralDeposit
    readonly_fields = ["amount", "commission_earned", "deposited_at"]
    extra = 0


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = [
        "referrer",
        "referred",
        "status",
        "total_deposited",
        "total_commission",
        "commission_rate",
        "created_at",
    ]
    list_filter = ["status"]
    list_editable = ["commission_rate"]  # adjust per affiliate from admin
    readonly_fields = [
        "total_deposited",
        "total_commission",
        "first_deposit_at",
        "last_deposit_at",
    ]
    inlines = [ReferralDepositInline]
    search_fields = ["referrer__username", "referred__username"]
