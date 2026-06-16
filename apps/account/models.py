import pyotp
import uuid
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from django.utils import timezone
from django.conf import settings

from django.utils.translation import gettext_lazy as _


def generate_username():
    """Generate a unique username like CR-A3F9B2."""
    return f"OT-{uuid.uuid4().hex[:6].upper()}"


class UserManager(BaseUserManager):
    def create_user(self, email, username, password=None, **extra_fields):
        if not email:
            raise ValueError(_("Email is required."))
        if not username:
            raise ValueError(_("Username is required."))
        email = self.normalize_email(email)
        user = self.model(email=email, username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        return self.create_user(email, username, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(_("email address"), unique=True)
    username = models.CharField(_("username"), max_length=40, unique=True)
    first_name = models.CharField(_("first name"), max_length=50, blank=True)
    last_name = models.CharField(_("last name"), max_length=50, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)

    balance = models.FloatField(default=0)

    is_active = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    email_verified = models.BooleanField(default=False)

    totp_secret = models.CharField(max_length=64, blank=True)
    totp_enabled = models.BooleanField(default=False)
    is_completed = models.BooleanField(default=False)

    is_verified = models.BooleanField(default=False)

    is_affiliate = models.BooleanField(default=False)

    referred_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="referrals",
    )
    total_referrals = models.PositiveIntegerField(default=0)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    objects = UserManager()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")

    def __str__(self):
        return f"{self.username} <{self.email}>"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username

    def get_totp_uri(self):
        return pyotp.totp.TOTP(self.totp_secret).provisioning_uri(
            name=self.email,
            issuer_name="OptionsBroker",
        )

    def get_initials(self):
        return self.first_name[0].upper() + self.last_name[0].upper()

    def generate_totp_secret(self):
        self.totp_secret = pyotp.random_base32()
        self.save(update_fields=["totp_secret"])

    def verify_totp(self, code: str) -> bool:
        if not self.totp_secret:
            return False
        totp = pyotp.TOTP(self.totp_secret)
        return totp.verify(code, valid_window=1)

    def save(self, *args, **kwargs):
        if not self.username or self.username == "OT":
            # Keep generating until unique (collision is astronomically unlikely
            # but we guard anyway)
            username = generate_username()
            while User.objects.filter(username=username).exists():
                username = generate_username()
            self.username = username
        super().save(*args, **kwargs)


class Details(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="details")
    total_deposit = models.FloatField(default=0, blank=True, null=True)
    total_withdraw = models.FloatField(default=0, blank=True, null=True)

    zipcode = models.CharField(max_length=20, blank=True, null=True)
    country_of_residence = models.CharField(max_length=100, blank=True, null=True)
    citizenship = models.CharField(max_length=100, blank=True, null=True)
    place_of_birth = models.CharField(max_length=100, blank=True, null=True)

    title = models.CharField(max_length=100, blank=True, null=True)

    first_address = models.CharField(max_length=1000, blank=True, null=True)
    second_address = models.CharField(max_length=1000, blank=True, null=True)
    gender = models.CharField(max_length=50, blank=True, null=True)

    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)

    date_of_birth = models.CharField(max_length=100, blank=True, null=True)

    phone = models.CharField(max_length=30, blank=True, null=True, unique=True)

    local_currency = models.CharField(max_length=30, blank=True, null=True)

    account_opening_reason = models.CharField(max_length=100, blank=True, null=True)

    is_agent = models.BooleanField(default=False)
    employment_status = models.CharField(max_length=100, blank=True, null=True)
    annual_income = models.FloatField(blank=True, null=True)

    def __str__(self):
        return self.user.email


class KYCSubmission(models.Model):

    class Status(models.TextChoices):
        UNVERIFIED = "unverified", "Unverified"
        PENDING = "pending", "Pending Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    class DocumentType(models.TextChoices):
        PASSPORT = "passport", "Passport"
        NATIONAL_ID = "national_id", "National ID"
        DRIVERS_LICENSE = "drivers_license", "Driver's License"

    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        PREFER_NOT = "prefer_not_say", "Prefer not to say"

    # ── Relation ──────────────────────────────────
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="kyc",
    )

    # ── Personal info ─────────────────────────────
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=20, choices=Gender.choices)
    nationality = models.CharField(max_length=100)
    phone = models.CharField(max_length=30)

    # ── Address ───────────────────────────────────
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20, blank=True, default="")

    # ── Identity document ─────────────────────────
    document_type = models.CharField(max_length=20, choices=DocumentType.choices)
    document_number = models.CharField(max_length=100)
    document_front = models.ImageField(upload_to="kyc/documents/%Y/%m/")
    document_back = models.ImageField(
        upload_to="kyc/documents/%Y/%m/", blank=True, null=True
    )

    # ── Selfie ────────────────────────────────────
    selfie = models.ImageField(upload_to="kyc/selfies/%Y/%m/")

    # ── Status & admin ────────────────────────────
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.UNVERIFIED
    )
    admin_note = models.TextField(
        blank=True, default="", help_text="Internal note shown to the user on rejection"
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kyc_reviews",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "KYC Submission"
        verbose_name_plural = "KYC Submissions"
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.user.username} — {self.get_status_display()}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def is_verified(self):
        return self.status == self.Status.APPROVED

    @property
    def can_resubmit(self):
        return self.status in (self.Status.UNVERIFIED, self.Status.REJECTED)

    @property
    def banner_class(self):
        """Maps status to the CSS class used in the template."""
        return {
            self.Status.UNVERIFIED: "unverified",
            self.Status.PENDING: "pending",
            self.Status.APPROVED: "verified",
            self.Status.REJECTED: "rejected",
        }.get(self.status, "unverified")

    @property
    def banner_message(self):
        return {
            self.Status.UNVERIFIED: (
                "Identity Not Verified",
                "Complete the form below to unlock full trading access and higher limits.",
            ),
            self.Status.PENDING: (
                "Verification Under Review",
                "Your documents have been submitted and are being reviewed. This usually takes 1–3 business days.",
            ),
            self.Status.APPROVED: (
                "Identity Verified ✓",
                "Your account is fully verified. You now have access to higher deposit limits and full trading features.",
            ),
            self.Status.REJECTED: (
                "Verification Rejected",
                self.admin_note
                or "Your submission was rejected. Please correct the issue and resubmit.",
            ),
        }.get(self.status, ("Not Verified", ""))


class Referral(models.Model):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),  # signed up, not deposited yet
        ("ACTIVE", "Active"),  # has made at least one deposit
        ("PAID", "Paid"),
    ]

    referrer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="referral_records",
    )
    referred = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="referral_record",
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="PENDING")

    total_deposited = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_commission = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    commission_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=10.00
    )  # 10%

    first_deposit_at = models.DateTimeField(null=True, blank=True)
    last_deposit_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.referrer.username} → {self.referred.username} | ${self.total_commission}"


class ReferralDeposit(models.Model):
    """Every deposit the referred user makes — tracked individually."""

    referral = models.ForeignKey(
        Referral, on_delete=models.CASCADE, related_name="deposits"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    commission_earned = models.DecimalField(max_digits=10, decimal_places=2)
    deposited_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"${self.amount} deposit → ${self.commission_earned} commission"
