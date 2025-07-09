from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date, timedelta

from .models import User, Member, MembershipApplication, MemberBankAccount
from .utils import ProfileUtils, ValidationUtils
from stokvel.utils import ValidationUtils as StokvelValidationUtils


class UserRegistrationForm(UserCreationForm):
    """Enhanced user registration form"""

    first_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your first name'
        })
    )

    last_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your last name'
        })
    )

    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email address'
        })
    )

    phone_number = forms.CharField(
        max_length=15,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g., +27 82 123 4567'
        }),
        help_text="South African phone number format"
    )

    date_of_birth = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )

    preferred_language = forms.ChoiceField(
        choices=User._meta.get_field('preferred_language').choices,
        initial='en',
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    terms_accepted = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        error_messages={'required': 'You must accept the terms and conditions'}
    )

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'phone_number',
                  'date_of_birth', 'preferred_language', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Choose a username'
            })
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Update password field widgets
        self.fields['password1'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Enter password'
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Confirm password'
        })

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email=email).exists():
            raise ValidationError("This email address is already registered.")
        return email

    def clean_phone_number(self):
        phone_number = self.cleaned_data.get('phone_number')
        if phone_number:
            is_valid, formatted_number = ProfileUtils.validate_south_african_phone(phone_number)
            if not is_valid:
                raise ValidationError(formatted_number)  # Error message
            return formatted_number
        return phone_number

    def clean_date_of_birth(self):
        dob = self.cleaned_data.get('date_of_birth')
        if dob:
            # Check minimum age (18 years)
            min_age_date = timezone.now().date() - timedelta(days=18 * 365)
            if dob > min_age_date:
                raise ValidationError("You must be at least 18 years old to register.")

            # Check maximum age (reasonable limit)
            max_age_date = timezone.now().date() - timedelta(days=100 * 365)
            if dob < max_age_date:
                raise ValidationError("Please enter a valid date of birth.")

        return dob


class CustomLoginForm(AuthenticationForm):
    """Custom login form with enhanced styling"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['username'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Username or Email'
        })

        self.fields['password'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Password'
        })


class UserProfileForm(forms.ModelForm):
    """Comprehensive user profile form"""

    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'email', 'phone_number', 'date_of_birth',
            'id_number', 'address_line_1', 'address_line_2', 'city', 'province',
            'postal_code', 'country', 'preferred_language', 'email_notifications',
            'sms_notifications', 'whatsapp_notifications'
        ]

        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+27 82 123 4567'
            }),
            'date_of_birth': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'id_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'South African ID number'
            }),
            'address_line_1': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Street address'
            }),
            'address_line_2': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Apartment, suite, etc. (optional)'
            }),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'province': forms.TextInput(attrs={'class': 'form-control'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control'}),
            'country': forms.TextInput(attrs={'class': 'form-control'}),
            'preferred_language': forms.Select(attrs={'class': 'form-control'}),
            'email_notifications': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'sms_notifications': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'whatsapp_notifications': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and email != self.instance.email:
            if User.objects.filter(email=email).exists():
                raise ValidationError("This email address is already in use.")
        return email

    def clean_phone_number(self):
        phone_number = self.cleaned_data.get('phone_number')
        if phone_number:
            is_valid, formatted_number = ProfileUtils.validate_south_african_phone(phone_number)
            if not is_valid:
                raise ValidationError(formatted_number)
            return formatted_number
        return phone_number

    def clean_id_number(self):
        id_number = self.cleaned_data.get('id_number')
        if id_number:
            if not StokvelValidationUtils.validate_south_african_id(id_number):
                raise ValidationError("Invalid South African ID number.")
        return id_number


class MembershipApplicationForm(forms.ModelForm):
    """Form for submitting membership applications"""

    motivation = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 5,
            'placeholder': 'Tell us why you want to join this stokvel and what you hope to achieve...'
        }),
        help_text="Please provide a detailed motivation (minimum 100 characters)"
    )

    referral_source = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'How did you hear about us? (optional)'
        })
    )

    class Meta:
        model = MembershipApplication
        fields = ['motivation', 'referral_source', 'referred_by']
        widgets = {
            'referred_by': forms.Select(attrs={
                'class': 'form-control',
                'empty_label': 'Select a referring member (optional)'
            })
        }

    def __init__(self, *args, **kwargs):
        self.stokvel = kwargs.pop('stokvel', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Populate referring members dropdown
        if self.stokvel:
            self.fields['referred_by'].queryset = Member.objects.filter(
                stokvel=self.stokvel,
                status='active'
            ).select_related('user')

            self.fields['referred_by'].empty_label = "No referral"

    def clean_motivation(self):
        motivation = self.cleaned_data.get('motivation')
        if motivation and len(motivation.strip()) < 100:
            raise ValidationError("Motivation must be at least 100 characters long.")
        return motivation

    def clean(self):
        cleaned_data = super().clean()

        # Additional validation would be handled by the service
        # but we can add basic checks here

        return cleaned_data


class ApplicationReviewForm(forms.Form):
    """Form for reviewing membership applications"""

    DECISION_CHOICES = [
        ('', 'Select Decision'),
        ('approve', 'Approve Application'),
        ('reject', 'Reject Application'),
    ]

    decision = forms.ChoiceField(
        choices=DECISION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    review_notes = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Add your review notes here...'
        }),
        help_text="Provide reasons for your decision"
    )

    def clean_decision(self):
        decision = self.cleaned_data.get('decision')
        if not decision:
            raise ValidationError("Please select a decision.")
        return decision


class MemberUpdateForm(forms.ModelForm):
    """Form for updating member information"""

    status_change_reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Reason for status change (if applicable)'
        })
    )

    class Meta:
        model = Member
        fields = [
            'status', 'role', 'bank_reference_names', 'emergency_contact_name',
            'emergency_contact_phone', 'emergency_contact_relationship',
            'occupation', 'employer', 'monthly_income_range', 'payout_preference',
            'admin_notes'
        ]

        widgets = {
            'status': forms.Select(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-control'}),
            'bank_reference_names': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Comma-separated names as they appear on bank statements'
            }),
            'emergency_contact_name': forms.TextInput(attrs={'class': 'form-control'}),
            'emergency_contact_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'emergency_contact_relationship': forms.TextInput(attrs={'class': 'form-control'}),
            'occupation': forms.TextInput(attrs={'class': 'form-control'}),
            'employer': forms.TextInput(attrs={'class': 'form-control'}),
            'monthly_income_range': forms.Select(attrs={'class': 'form-control'}),
            'payout_preference': forms.Select(attrs={'class': 'form-control'}),
            'admin_notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4
            })
        }

    def clean_emergency_contact_phone(self):
        phone = self.cleaned_data.get('emergency_contact_phone')
        if phone:
            is_valid, formatted_number = ProfileUtils.validate_south_african_phone(phone)
            if not is_valid:
                raise ValidationError(formatted_number)
            return formatted_number
        return phone


class MemberBankAccountForm(forms.ModelForm):
    """Form for adding/updating member bank accounts"""

    class Meta:
        model = MemberBankAccount
        fields = [
            'bank_name', 'account_holder_name', 'account_number',
            'account_type', 'branch_code', 'is_primary'
        ]

        widgets = {
            'bank_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., African Bank, Capitec, FNB'
            }),
            'account_holder_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Full name as per bank records'
            }),
            'account_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Account number'
            }),
            'account_type': forms.Select(attrs={'class': 'form-control'}),
            'branch_code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '6-digit branch code'
            }),
            'is_primary': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }

    def clean_account_number(self):
        account_number = self.cleaned_data.get('account_number')
        bank_name = self.cleaned_data.get('bank_name', '')

        if account_number:
            if not StokvelValidationUtils.validate_bank_account_number(account_number, bank_name):
                raise ValidationError("Invalid account number format.")

        return account_number

    def clean_branch_code(self):
        branch_code = self.cleaned_data.get('branch_code')

        if branch_code:
            # Remove spaces and validate
            branch_code = branch_code.replace(' ', '')

            if not branch_code.isdigit():
                raise ValidationError("Branch code must contain only numbers.")

            if len(branch_code) != 6:
                raise ValidationError("Branch code must be exactly 6 digits.")

        return branch_code


class MemberSearchForm(forms.Form):
    """Form for searching and filtering members"""

    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by name, email, or member number...'
        })
    )

    status = forms.ChoiceField(
        required=False,
        choices=[('', 'All Status')] + Member.MEMBER_STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    role = forms.ChoiceField(
        required=False,
        choices=[('', 'All Roles')] + Member.MEMBER_ROLE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )


class ApplicationFilterForm(forms.Form):
    """Form for filtering membership applications"""

    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by name, email, or motivation...'
        })
    )

    status = forms.ChoiceField(
        required=False,
        choices=[('', 'All Status')] + MembershipApplication.APPLICATION_STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )


class BulkMemberActionForm(forms.Form):
    """Form for bulk actions on members"""

    ACTION_CHOICES = [
        ('', 'Select Action'),
        ('activate', 'Activate Members'),
        ('suspend', 'Suspend Members'),
        ('send_notification', 'Send Notification'),
        ('export_data', 'Export Member Data'),
    ]

    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Reason for action (if applicable)'
        })
    )

    selected_members = forms.CharField(
        widget=forms.HiddenInput()
    )

    def clean_action(self):
        action = self.cleaned_data.get('action')
        if not action:
            raise ValidationError("Please select an action.")
        return action


class EmailVerificationForm(forms.Form):
    """Form for email verification"""

    verification_code = forms.CharField(
        max_length=6,
        widget=forms.TextInput(attrs={
            'class': 'form-control text-center',
            'placeholder': '######',
            'maxlength': 6,
            'style': 'font-size: 1.5rem; letter-spacing: 0.5rem;'
        }),
        help_text="Enter the 6-digit code sent to your email"
    )

    def clean_verification_code(self):
        code = self.cleaned_data.get('verification_code')
        if code and not code.isdigit():
            raise ValidationError("Verification code must contain only numbers.")
        return code


class PhoneVerificationForm(forms.Form):
    """Form for phone verification"""

    verification_code = forms.CharField(
        max_length=6,
        widget=forms.TextInput(attrs={
            'class': 'form-control text-center',
            'placeholder': '######',
            'maxlength': 6,
            'style': 'font-size: 1.5rem; letter-spacing: 0.5rem;'
        }),
        help_text="Enter the 6-digit code sent to your phone"
    )

    def clean_verification_code(self):
        code = self.cleaned_data.get('verification_code')
        if code and not code.isdigit():
            raise ValidationError("Verification code must contain only numbers.")
        return code


class MemberReportFilterForm(forms.Form):
    """Form for filtering member reports"""

    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )

    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )

    status_filter = forms.MultipleChoiceField(
        required=False,
        choices=Member.MEMBER_STATUS_CHOICES,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'})
    )

    include_inactive = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date:
            if end_date < start_date:
                raise ValidationError("End date must be after start date.")

        return cleaned_data