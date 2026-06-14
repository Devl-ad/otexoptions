from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from .models import Details, KYCSubmission

User = get_user_model()


class RegisterForm(forms.ModelForm):
    password1 = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "placeholder": "Password",
            }
        ),
        min_length=8,
    )
    password2 = forms.CharField(
        label=_("Confirm password"),
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "placeholder": "Confirm password",
            }
        ),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "placeholder": "Email address",
            }
        )
    )
    username = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "placeholder": "Username",
            }
        )
    )
    first_name = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "placeholder": "First name",
            }
        )
    )
    last_name = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "placeholder": "Last name",
            }
        )
    )

    class Meta:
        model = User
        fields = ("email", "username", "first_name", "last_name")
        widgets = {
            "email": forms.EmailInput(attrs={"placeholder": "Email address"}),
            "username": forms.TextInput(attrs={"placeholder": "Username"}),
            "first_name": forms.TextInput(attrs={"placeholder": "First name"}),
            "last_name": forms.TextInput(attrs={"placeholder": "Last name"}),
        }

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            raise ValidationError(_("An account with this email already exists."))
        return email

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError(_("This username is already taken."))
        return username

    def clean_password2(self):
        p1 = self.cleaned_data.get("password1")
        p2 = self.cleaned_data.get("password2")
        if p1 and p2 and p1 != p2:
            raise ValidationError(_("Passwords do not match."))
        return p2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        user.is_active = False  # requires email verification
        if commit:
            user.save()
        return user


class PersonalInfoForm(forms.ModelForm):
    class Meta:
        model = Details
        fields = [
            "title",
            "gender",
            "date_of_birth",
            "citizenship",
            "country_of_residence",
            "place_of_birth",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
        }


class AddressForm(forms.ModelForm):
    class Meta:
        model = Details
        fields = [
            "first_address",
            "second_address",
            "city",
            "state",
            "zipcode",
        ]


class AccountDetailsForm(forms.ModelForm):
    class Meta:
        model = Details
        fields = [
            "local_currency",
            "account_opening_reason",
            "employment_status",
            "annual_income",
        ]


class LoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={"placeholder": "Email address", "autofocus": True}
        )
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"placeholder": "Password"})
    )
    remember_me = forms.BooleanField(required=False)


class TOTPVerifyForm(forms.Form):
    code = forms.CharField(
        max_length=6,
        min_length=6,
        widget=forms.TextInput(
            attrs={
                "placeholder": "6-digit code",
                "autocomplete": "one-time-code",
                "inputmode": "numeric",
                "autofocus": True,
            }
        ),
        label=_("Authenticator code"),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_code(self):
        code = self.cleaned_data["code"].strip()
        if self.user and not self.user.verify_totp(code):
            raise ValidationError(_("Invalid or expired code. Please try again."))
        return code


class TOTPEnableForm(forms.Form):
    """Confirms the user has successfully scanned and can produce a valid code."""

    code = forms.CharField(
        max_length=6,
        min_length=6,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Enter the 6-digit code",
                "inputmode": "numeric",
                "autofocus": True,
            }
        ),
        label=_("Verify authenticator code"),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_code(self):
        code = self.cleaned_data["code"].strip()
        if self.user and not self.user.verify_totp(code):
            raise ValidationError(
                _(
                    "Code not recognised. Make sure your authenticator app is set up correctly."
                )
            )
        return code


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"placeholder": "Enter your email address"})
    )


class PasswordResetConfirmForm(SetPasswordForm):
    new_password1 = forms.CharField(
        label=_("New password"),
        widget=forms.PasswordInput(
            attrs={"placeholder": "New password", "autocomplete": "new-password"}
        ),
        min_length=8,
    )
    new_password2 = forms.CharField(
        label=_("Confirm new password"),
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Confirm new password",
                "autocomplete": "new-password",
            }
        ),
    )


class KYCForm(forms.ModelForm):

    class Meta:
        model = KYCSubmission
        fields = [
            # Personal
            "first_name",
            "last_name",
            "date_of_birth",
            "gender",
            "nationality",
            "phone",
            # Address
            "address",
            "city",
            "postal_code",
            # Document
            "document_type",
            "document_number",
            "document_front",
            "document_back",
            # Selfie
            "selfie",
        ]
        widgets = {
            "first_name": forms.TextInput(
                attrs={
                    "class": "finput",
                    "placeholder": "John",
                    "id": "firstName",
                    "autocomplete": "given-name",
                }
            ),
            "last_name": forms.TextInput(
                attrs={
                    "class": "finput",
                    "placeholder": "Doe",
                    "id": "lastName",
                    "autocomplete": "family-name",
                }
            ),
            "date_of_birth": forms.DateInput(
                attrs={
                    "class": "finput",
                    "type": "date",
                    "id": "dob",
                    "autocomplete": "bday",
                }
            ),
            "gender": forms.Select(
                attrs={
                    "class": "finput",
                    "id": "gender",
                }
            ),
            "nationality": forms.TextInput(
                attrs={
                    "class": "finput",
                    "placeholder": "e.g. Ghanaian",
                    "id": "nationality",
                }
            ),
            "phone": forms.TextInput(
                attrs={
                    "class": "finput",
                    "placeholder": "+233 20 000 0000",
                    "id": "phone",
                    "autocomplete": "tel",
                }
            ),
            "address": forms.TextInput(
                attrs={
                    "class": "finput",
                    "placeholder": "Street address, city, region",
                    "id": "address",
                    "autocomplete": "street-address",
                }
            ),
            "city": forms.TextInput(
                attrs={
                    "class": "finput",
                    "placeholder": "Accra",
                    "id": "city",
                    "autocomplete": "address-level2",
                }
            ),
            "postal_code": forms.TextInput(
                attrs={
                    "class": "finput",
                    "placeholder": "00233",
                    "id": "postalCode",
                    "autocomplete": "postal-code",
                }
            ),
            "document_type": forms.HiddenInput(attrs={"id": "documentType"}),
            "document_number": forms.TextInput(
                attrs={
                    "class": "finput",
                    "placeholder": "e.g. GHA-A12345678",
                    "id": "docNumber",
                    "style": "font-family:monospace",
                }
            ),
            "document_front": forms.FileInput(
                attrs={
                    "id": "docFront",
                    "accept": "image/*",
                }
            ),
            "document_back": forms.FileInput(
                attrs={
                    "id": "docBack",
                    "accept": "image/*",
                }
            ),
            "selfie": forms.FileInput(
                attrs={
                    "id": "selfieInput",
                    "accept": "image/*",
                    "capture": "user",
                }
            ),
        }

    # ── Field-level tweaks ────────────────────────

    document_back = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={"id": "docBack", "accept": "image/*"}),
        label="Back of Document (not required for passport)",
    )

    def clean_date_of_birth(self):
        from datetime import date

        dob = self.cleaned_data.get("date_of_birth")
        if dob:
            today = date.today()
            age = (
                today.year
                - dob.year
                - ((today.month, today.day) < (dob.month, dob.day))
            )
            if age < 18:
                raise forms.ValidationError(
                    "You must be at least 18 years old to verify your account."
                )
            if age > 120:
                raise forms.ValidationError("Please enter a valid date of birth.")
        return dob

    def clean_document_number(self):
        num = self.cleaned_data.get("document_number", "").strip()
        if len(num) < 4:
            raise forms.ValidationError("Please enter a valid document number.")
        return num

    def clean(self):
        cleaned = super().clean()
        doc_type = cleaned.get("document_type")
        doc_back = cleaned.get("document_back")

        # Back side required for non-passport documents
        if doc_type in ("national_id", "drivers_license") and not doc_back:
            # Only enforce on new submissions (not if file already saved)
            if not (self.instance.pk and self.instance.document_back):
                self.add_error(
                    "document_back",
                    "Back side is required for National ID and Driver's License.",
                )
        return cleaned
