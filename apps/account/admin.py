from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.utils import timezone
from .models import User, Details, KYCSubmission


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
        (_("2FA"), {"fields": ("totp_enabled", "totp_secret")}),
        (_("Permissions"), {"fields": ("groups", "user_permissions")}),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
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


@admin.action(description="✅ Approve selected submissions")
def approve_kyc(modeladmin, request, queryset):
    queryset.update(
        status=KYCSubmission.Status.APPROVED,
        reviewed_at=timezone.now(),
        reviewed_by=request.user,
    )


@admin.action(description="❌ Reject selected submissions")
def reject_kyc(modeladmin, request, queryset):
    queryset.update(
        status=KYCSubmission.Status.REJECTED,
        reviewed_at=timezone.now(),
        reviewed_by=request.user,
    )


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
    )
    actions = [approve_kyc, reject_kyc]
    ordering = ["-submitted_at"]

    fieldsets = (
        (
            "User",
            {
                "fields": ("user", "status", "admin_note"),
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

    # ── Custom columns ──────────────────────────────────

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
                '<img src="{}" style="max-height:160px;border-radius:8px;border:1px solid #e5e7eb" />',
                obj.document_front.url,
            )
        return "—"

    @admin.display(description="Back")
    def doc_back_preview(self, obj):
        if obj.document_back:
            return format_html(
                '<img src="{}" style="max-height:160px;border-radius:8px;border:1px solid #e5e7eb" />',
                obj.document_back.url,
            )
        return "—"

    @admin.display(description="Selfie")
    def selfie_preview(self, obj):
        if obj.selfie:
            return format_html(
                '<img src="{}" style="max-height:200px;border-radius:8px;border:1px solid #e5e7eb" />',
                obj.selfie.url,
            )
        return "—"

    def save_model(self, request, obj, form, change):
        """Auto-set reviewed_by and reviewed_at when admin changes status."""
        if change:
            original = KYCSubmission.objects.get(pk=obj.pk)
            if original.status != obj.status and obj.status in (
                KYCSubmission.Status.APPROVED,
                KYCSubmission.Status.REJECTED,
            ):
                obj.reviewed_by = request.user
                obj.reviewed_at = timezone.now()
        super().save_model(request, obj, form, change)
