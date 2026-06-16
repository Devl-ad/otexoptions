from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from .models import User, Details, KYCSubmission, Referral, ReferralDeposit

# ── Actions ───────────────────────────────────────────────────────────────────


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


# ── Actions (bulk — list page dropdown) ───────────────────────────────────────


@admin.action(description="✅ Approve selected submissions")
def approve_kyc(modeladmin, request, queryset):
    for submission in queryset.select_related("user"):
        submission.status = KYCSubmission.Status.APPROVED
        submission.reviewed_at = timezone.now()
        submission.reviewed_by = request.user
        submission.save()

        user = submission.user
        user.is_verified = True
        user.save(update_fields=["is_verified"])

        try:
            send_mail(
                subject="Your OTEX account has been verified ✅",
                message=f"Hi {user.get_full_name() or user.username}, your KYC has been approved.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=_approval_email(user),
            )
        except Exception as e:
            modeladmin.message_user(
                request,
                f"Approved {user.email} but email failed: {e}",
                level="warning",
            )


@admin.action(description="❌ Reject selected submissions")
def reject_kyc(modeladmin, request, queryset):
    for submission in queryset.select_related("user"):
        submission.status = KYCSubmission.Status.REJECTED
        submission.reviewed_at = timezone.now()
        submission.reviewed_by = request.user
        submission.save()

        user = submission.user
        user.is_verified = False
        user.save(update_fields=["is_verified"])

        try:
            send_mail(
                subject="OTEX KYC Verification Update",
                message=f"Hi {user.get_full_name() or user.username}, your KYC was not approved.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=_rejection_email(user, submission.admin_note),
            )
        except Exception as e:
            modeladmin.message_user(
                request,
                f"Rejected {user.email} but email failed: {e}",
                level="warning",
            )


# ── Email helpers ─────────────────────────────────────────────────────────────


def _logo():
    return """
        <div style="text-align:center;margin-bottom:28px">
            <svg width="40" height="40" viewBox="0 0 32 32" fill="none">
                <rect x="2" y="18" width="6" height="12" rx="2" fill="#E85D35"/>
                <rect x="11" y="10" width="6" height="20" rx="2" fill="#E85D35" opacity="0.75"/>
                <rect x="20" y="4" width="6" height="26" rx="2" fill="#E85D35" opacity="0.45"/>
            </svg>
            <h1 style="font-size:22px;font-weight:800;color:#111;margin:12px 0 4px">OTEX</h1>
        </div>
    """


def _footer():
    return """
        <p style="font-size:12px;color:#aaa;margin-top:32px;
                  border-top:1px solid #f0f0f0;padding-top:16px">
            OTEX Options · otexoption.com
        </p>
    """


def _approval_email(user):
    name = user.get_full_name() or user.username
    return f"""
    <div style="font-family:Inter,sans-serif;max-width:560px;margin:0 auto;
                padding:32px 24px;background:#fff;">
        {_logo()}
        <div style="background:#f0fdf4;border-radius:12px;padding:24px;
                    text-align:center;margin-bottom:24px">
            <div style="font-size:40px;margin-bottom:8px">✅</div>
            <h2 style="font-size:18px;font-weight:700;color:#166534;margin:0">
                KYC Approved!
            </h2>
        </div>
        <p style="font-size:14px;color:#444;line-height:1.7">
            Hi <strong>{name}</strong>,
        </p>
        <p style="font-size:14px;color:#444;line-height:1.7">
            Your identity verification has been approved. You now have full
            access to live trading on OTEX.
        </p>
        <div style="margin:24px 0">
            <a href="https://otexoption.com/dashboard"
               style="display:inline-block;background:#E85D35;color:#fff;
                      padding:13px 28px;border-radius:10px;font-size:14px;
                      font-weight:700;text-decoration:none">
                Start Trading →
            </a>
        </div>
        {_footer()}
    </div>
    """


def _rejection_email(user, admin_note=""):
    name = user.get_full_name() or user.username
    note_block = (
        (
            f'<div style="background:#fff7ed;border-radius:8px;padding:14px 16px;'
            f'margin:16px 0;font-size:13px;color:#92400e">'
            f"<strong>Note:</strong> {admin_note}</div>"
        )
        if admin_note
        else ""
    )

    return f"""
    <div style="font-family:Inter,sans-serif;max-width:560px;margin:0 auto;
                padding:32px 24px;background:#fff;">
        {_logo()}
        <div style="background:#fef2f2;border-radius:12px;padding:24px;
                    text-align:center;margin-bottom:24px">
            <div style="font-size:40px;margin-bottom:8px">❌</div>
            <h2 style="font-size:18px;font-weight:700;color:#991b1b;margin:0">
                Verification Unsuccessful
            </h2>
        </div>
        <p style="font-size:14px;color:#444;line-height:1.7">
            Hi <strong>{name}</strong>,
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
        {note_block}
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
        {_footer()}
    </div>
    """


# ── Admin class ───────────────────────────────────────────────────────────────


@admin.register(KYCSubmission)
class KYCSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "full_name",
        "nationality",
        "document_type_display",
        "status_badge",
        "submitted_at",
        "reviewed_at",
        "reviewed_by",
    )
    list_filter = ("status", "document_type", "nationality")
    search_fields = (
        "user__username",
        "user__email",
        "first_name",
        "last_name",
        "document_number",
    )
    readonly_fields = (
        "user",
        "submitted_at",
        "reviewed_at",
        "created_at",
        "updated_at",
        "doc_front_preview",
        "doc_back_preview",
        "selfie_preview",
        "action_buttons",
    )
    actions = [approve_kyc, reject_kyc]
    ordering = ["-submitted_at"]

    fieldsets = (
        (
            "User",
            {
                "fields": ("user", "action_buttons", "status", "admin_note"),
            },
        ),
        (
            "Personal Information",
            {
                "fields": (
                    ("first_name", "last_name"),
                    ("date_of_birth", "gender"),
                    ("nationality", "phone"),
                    ("address", "city", "postal_code"),
                ),
            },
        ),
        (
            "Identity Document",
            {
                "fields": (
                    "document_type",
                    "document_number",
                    "doc_front_preview",
                    "document_front",
                    "doc_back_preview",
                    "document_back",
                ),
            },
        ),
        (
            "Selfie",
            {
                "fields": ("selfie_preview", "selfie"),
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "submitted_at",
                    "reviewed_at",
                    "reviewed_by",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    # ── Approve / Reject buttons on detail page ───────────────────────────────

    def get_urls(self):
        from django.urls import path

        urls = super().get_urls()
        custom = [
            path(
                "<int:pk>/approve/",
                self.admin_site.admin_view(self.approve_view),
                name="kyc_approve",
            ),
            path(
                "<int:pk>/reject/",
                self.admin_site.admin_view(self.reject_view),
                name="kyc_reject",
            ),
        ]
        return custom + urls

    def approve_view(self, request, pk):
        submission = KYCSubmission.objects.select_related("user").get(pk=pk)
        submission.status = KYCSubmission.Status.APPROVED
        submission.reviewed_at = timezone.now()
        submission.reviewed_by = request.user
        submission.save()

        user = submission.user
        user.is_verified = True
        user.save(update_fields=["is_verified"])

        try:
            send_mail(
                subject="Your OTEX account has been verified ✅",
                message=f"Hi {user.get_full_name() or user.username}, your KYC has been approved.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=_approval_email(user),
            )
        except Exception as e:
            self.message_user(
                request,
                f"Approved but email failed: {e}",
                level="warning",
            )

        self.message_user(request, f"✅ {user.username} KYC approved successfully.")

        return redirect(
            reverse(
                "admin:account_kycsubmission_change",
                args=[pk],
            )
        )

    def reject_view(self, request, pk):
        submission = KYCSubmission.objects.select_related("user").get(pk=pk)
        submission.status = KYCSubmission.Status.REJECTED
        submission.reviewed_at = timezone.now()
        submission.reviewed_by = request.user
        submission.save()

        user = submission.user
        user.is_verified = False
        user.save(update_fields=["is_verified"])

        try:
            send_mail(
                subject="OTEX KYC Verification Update",
                message=f"Hi {user.get_full_name() or user.username}, your KYC was not approved.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=_rejection_email(user, submission.admin_note),
            )
        except Exception as e:
            self.message_user(
                request,
                f"Rejected but email failed: {e}",
                level="warning",
            )

        self.message_user(request, f"❌ {user.username} KYC rejected.")
        return redirect(
            reverse(
                "admin:account_kycsubmission_change",
                args=[pk],
            )
        )

    @admin.display(description="Quick Actions")
    def action_buttons(self, obj):
        if not obj.pk:
            return "—"

        approve_url = reverse("admin:kyc_approve", args=[obj.pk])
        reject_url = reverse("admin:kyc_reject", args=[obj.pk])

        approve_btn = (
            f'<a href="{approve_url}" style="display:inline-block;background:#166534;color:#fff;'
            f"padding:8px 20px;border-radius:8px;font-size:13px;font-weight:700;"
            f'text-decoration:none;margin-right:8px">✅ Approve</a>'
        )
        reject_btn = (
            f'<a href="{reject_url}" style="display:inline-block;background:#991b1b;color:#fff;'
            f"padding:8px 20px;border-radius:8px;font-size:13px;font-weight:700;"
            f'text-decoration:none">❌ Reject</a>'
        )
        approved_label = (
            '<span style="color:#166534;font-weight:700;font-size:13px;margin-right:12px">'
            "✅ Already Approved</span>"
        )
        rejected_label = (
            '<span style="color:#991b1b;font-weight:700;font-size:13px;margin-right:12px">'
            "❌ Already Rejected</span>"
        )

        if obj.status == KYCSubmission.Status.APPROVED:
            return format_html(approved_label + reject_btn)
        elif obj.status == KYCSubmission.Status.REJECTED:
            return format_html(rejected_label + approve_btn)
        elif obj.status == KYCSubmission.Status.PENDING:
            return format_html(approve_btn + reject_btn)
        else:
            return format_html(
                '<span style="color:#aaa;font-size:13px">No submission yet.</span>'
            )

    # ── Custom columns ────────────────────────────────────────────────────────

    @admin.display(description="Name")
    def full_name(self, obj):
        return obj.full_name

    @admin.display(description="Document")
    def document_type_display(self, obj):
        return obj.get_document_type_display()

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {
            "unverified": ("#fffbeb", "#92400e"),
            "pending": ("#eff6ff", "#1e40af"),
            "approved": ("#f0fdf4", "#166534"),
            "rejected": ("#fef2f2", "#991b1b"),
        }
        bg, fg = colors.get(obj.status, ("#f3f4f6", "#374151"))
        return format_html(
            '<span style="background:{};color:{};padding:3px 10px;'
            'border-radius:12px;font-size:11px;font-weight:700;">{}</span>',
            bg,
            fg,
            obj.get_status_display(),
        )

    @admin.display(description="Front")
    def doc_front_preview(self, obj):
        if obj.document_front:
            return format_html(
                '<img src="{}" style="max-height:160px;border-radius:8px;'
                'border:1px solid #e5e7eb" />',
                obj.document_front.url,
            )
        return "—"

    @admin.display(description="Back")
    def doc_back_preview(self, obj):
        if obj.document_back:
            return format_html(
                '<img src="{}" style="max-height:160px;border-radius:8px;'
                'border:1px solid #e5e7eb" />',
                obj.document_back.url,
            )
        return "—"

    @admin.display(description="Selfie")
    def selfie_preview(self, obj):
        if obj.selfie:
            return format_html(
                '<img src="{}" style="max-height:200px;border-radius:8px;'
                'border:1px solid #e5e7eb" />',
                obj.selfie.url,
            )
        return "—"

    # ── Save hook — status change from detail page ────────────────────────────

    def save_model(self, request, obj, form, change):
        if change:
            original = KYCSubmission.objects.get(pk=obj.pk)
            if original.status != obj.status:
                obj.reviewed_by = request.user
                obj.reviewed_at = timezone.now()

                if obj.status == KYCSubmission.Status.APPROVED:
                    obj.user.is_verified = True
                    obj.user.save(update_fields=["is_verified"])

                elif obj.status == KYCSubmission.Status.REJECTED:
                    obj.user.is_verified = False
                    obj.user.save(update_fields=["is_verified"])

        super().save_model(request, obj, form, change)
