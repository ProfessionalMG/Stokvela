from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from datetime import date, timedelta

from .models import (
    Stokvel, StokvelConstitution, ContributionRule,
    PenaltyRule, StokvelCycle, StokvelBankAccount
)
from .utils import ValidationUtils


class StokvelCreateForm(forms.ModelForm):
    """Form for creating a new stokvel with basic constitution data"""

    # Constitution fields included in stokvel creation
    meeting_frequency = forms.ChoiceField(
        choices=StokvelConstitution._meta.get_field('meeting_frequency').choices,
        initial='monthly',
        help_text="How often will the stokvel hold meetings?"
    )

    minimum_members = forms.IntegerField(
        initial=5,
        min_value=3,
        max_value=100,
        help_text="Minimum number of members required"
    )

    maximum_members = forms.IntegerField(
        required=False,
        min_value=5,
        max_value=1000,
        help_text="Maximum number of members allowed (optional)"
    )

    contribution_due_day = forms.IntegerField(
        initial=31,
        min_value=1,
        max_value=31,
        help_text="Day of month when contributions are due (31 = last day)"
    )

    payout_frequency = forms.ChoiceField(
        choices=StokvelConstitution._meta.get_field('payout_frequency').choices,
        initial='monthly',
        help_text="How often will payouts be made?"
    )

    class Meta:
        model = Stokvel
        fields = ['name', 'description', 'registration_number', 'date_established']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter stokvel name'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Describe the purpose and goals of your stokvel'
            }),
            'registration_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Optional registration number'
            }),
            'date_established': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            })
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date_established'].initial = timezone.now().date()

        # Add CSS classes to constitution fields
        constitution_fields = [
            'meeting_frequency', 'minimum_members', 'maximum_members',
            'contribution_due_day', 'payout_frequency'
        ]

        for field_name in constitution_fields:
            self.fields[field_name].widget.attrs.update({'class': 'form-control'})

    def clean_maximum_members(self):
        minimum = self.cleaned_data.get('minimum_members')
        maximum = self.cleaned_data.get('maximum_members')

        if maximum and minimum and maximum < minimum:
            raise ValidationError("Maximum members cannot be less than minimum members")

        return maximum

    def clean_date_established(self):
        date_established = self.cleaned_data.get('date_established')

        if date_established and date_established > timezone.now().date():
            raise ValidationError("Establishment date cannot be in the future")

        return date_established


class StokvelUpdateForm(forms.ModelForm):
    """Form for updating basic stokvel information"""

    class Meta:
        model = Stokvel
        fields = ['name', 'description', 'registration_number', 'is_active', 'is_accepting_members']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'registration_number': forms.TextInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_accepting_members': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }


class ConstitutionForm(forms.ModelForm):
    """Form for updating stokvel constitution"""

    class Meta:
        model = StokvelConstitution
        exclude = ['stokvel', 'created_date', 'updated_date']
        widgets = {
            'meeting_frequency': forms.Select(attrs={'class': 'form-control'}),
            'minimum_attendance_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'max': 100
            }),
            'minimum_members': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 3
            }),
            'maximum_members': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 3
            }),
            'probation_period_months': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0
            }),
            'contribution_start_day': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 31
            }),
            'contribution_due_day': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 31
            }),
            'notice_period_days': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0
            }),
            'suspension_rules': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
            'payout_frequency': forms.Select(attrs={'class': 'form-control'}),
            'payout_order_method': forms.Select(attrs={'class': 'form-control'}),
            'constitution_text': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 10
            })
        }

    def clean(self):
        cleaned_data = super().clean()
        minimum_members = cleaned_data.get('minimum_members')
        maximum_members = cleaned_data.get('maximum_members')

        if maximum_members and minimum_members and maximum_members < minimum_members:
            raise ValidationError("Maximum members cannot be less than minimum members")

        return cleaned_data


class ContributionRuleForm(forms.ModelForm):
    """Form for creating/updating contribution rules"""

    class Meta:
        model = ContributionRule
        exclude = ['stokvel', 'created_date']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Monthly Contribution'
            }),
            'contribution_type': forms.Select(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.01'
            }),
            'frequency': forms.Select(attrs={'class': 'form-control'}),
            'effective_from': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'effective_until': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_mandatory': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional description of this contribution rule'
            })
        }

    def __init__(self, *args, **kwargs):
        self.stokvel = kwargs.pop('stokvel', None)
        super().__init__(*args, **kwargs)

        # Set default effective_from to today
        if not self.instance.pk:
            self.fields['effective_from'].initial = timezone.now().date()

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')

        if amount and amount <= 0:
            raise ValidationError("Amount must be greater than zero")

        if amount and amount > Decimal('1000000'):
            raise ValidationError("Amount seems unreasonably large")

        return amount

    def clean(self):
        cleaned_data = super().clean()
        effective_from = cleaned_data.get('effective_from')
        effective_until = cleaned_data.get('effective_until')

        if effective_from and effective_until:
            if effective_until <= effective_from:
                raise ValidationError("End date must be after start date")

        # Check for overlapping rules if we have a stokvel
        if self.stokvel and effective_from:
            contribution_type = cleaned_data.get('contribution_type')

            overlapping = ContributionRule.objects.filter(
                stokvel=self.stokvel,
                contribution_type=contribution_type,
                is_active=True,
                effective_from__lte=effective_until or date.max,
            )

            if effective_until:
                overlapping = overlapping.filter(
                    models.Q(effective_until__gte=effective_from) |
                    models.Q(effective_until__isnull=True)
                )

            # Exclude current instance if updating
            if self.instance.pk:
                overlapping = overlapping.exclude(pk=self.instance.pk)

            if overlapping.exists():
                raise ValidationError(
                    f"Another {contribution_type} rule already exists for this period"
                )

        return cleaned_data


class PenaltyRuleForm(forms.ModelForm):
    """Form for creating/updating penalty rules"""

    class Meta:
        model = PenaltyRule
        exclude = ['stokvel', 'created_date']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Late Payment Penalty'
            }),
            'penalty_type': forms.Select(attrs={'class': 'form-control'}),
            'calculation_method': forms.Select(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'grace_period_days': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0'
            }),
            'maximum_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'effective_from': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'effective_until': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            })
        }

    def __init__(self, *args, **kwargs):
        self.stokvel = kwargs.pop('stokvel', None)
        super().__init__(*args, **kwargs)

        # Set default effective_from to today
        if not self.instance.pk:
            self.fields['effective_from'].initial = timezone.now().date()

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        calculation_method = self.cleaned_data.get('calculation_method')

        if amount and amount < 0:
            raise ValidationError("Amount cannot be negative")

        if calculation_method == 'percentage' and amount and amount > 100:
            raise ValidationError("Percentage cannot exceed 100%")

        return amount

    def clean(self):
        cleaned_data = super().clean()
        effective_from = cleaned_data.get('effective_from')
        effective_until = cleaned_data.get('effective_until')
        amount = cleaned_data.get('amount')
        maximum_amount = cleaned_data.get('maximum_amount')

        if effective_from and effective_until:
            if effective_until <= effective_from:
                raise ValidationError("End date must be after start date")

        if amount and maximum_amount and maximum_amount < amount:
            raise ValidationError("Maximum amount cannot be less than base amount")

        return cleaned_data


class CycleForm(forms.ModelForm):
    """Form for creating/updating stokvel cycles"""

    class Meta:
        model = StokvelCycle
        exclude = ['stokvel', 'created_date', 'expected_total_contributions']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., 2025 Annual Cycle'
            }),
            'start_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'end_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Describe the goals and purpose of this cycle'
            })
        }

    def __init__(self, *args, **kwargs):
        self.stokvel = kwargs.pop('stokvel', None)
        super().__init__(*args, **kwargs)

        # Set default dates if creating new cycle
        if not self.instance.pk:
            today = timezone.now().date()
            self.fields['start_date'].initial = today
            self.fields['end_date'].initial = today + timedelta(days=365)

    def clean_start_date(self):
        start_date = self.cleaned_data.get('start_date')

        if start_date and start_date < timezone.now().date():
            raise ValidationError("Start date cannot be in the past")

        return start_date

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date:
            if end_date <= start_date:
                raise ValidationError("End date must be after start date")

            # Check minimum cycle duration (e.g., at least 1 month)
            if (end_date - start_date).days < 30:
                raise ValidationError("Cycle must be at least 30 days long")

        # Check for overlapping cycles if we have a stokvel
        if self.stokvel and start_date and end_date:
            overlapping = StokvelCycle.objects.filter(
                stokvel=self.stokvel,
                start_date__lt=end_date,
                end_date__gt=start_date
            )

            # Exclude current instance if updating
            if self.instance.pk:
                overlapping = overlapping.exclude(pk=self.instance.pk)

            if overlapping.exists():
                raise ValidationError("Cycle dates overlap with existing cycle")

        return cleaned_data


class BankAccountForm(forms.ModelForm):
    """Form for creating/updating bank accounts"""

    class Meta:
        model = StokvelBankAccount
        exclude = ['stokvel', 'created_date']
        widgets = {
            'bank_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., African Bank'
            }),
            'account_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Account holder name'
            }),
            'account_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Account number'
            }),
            'branch_code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Branch code'
            }),
            'account_type': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Savings, Cheque'
            }),
            'is_primary': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }

    def clean_account_number(self):
        account_number = self.cleaned_data.get('account_number')
        bank_name = self.cleaned_data.get('bank_name', '')

        if account_number:
            # Basic validation using utility function
            is_valid = ValidationUtils.validate_bank_account_number(account_number, bank_name)
            if not is_valid:
                raise ValidationError("Invalid account number format")

        return account_number

    def clean_branch_code(self):
        branch_code = self.cleaned_data.get('branch_code')

        if branch_code:
            # Remove spaces and validate format
            branch_code = branch_code.replace(' ', '')

            if not branch_code.isdigit():
                raise ValidationError("Branch code must contain only numbers")

            if len(branch_code) != 6:
                raise ValidationError("Branch code must be 6 digits")

        return branch_code

    def clean(self):
        cleaned_data = super().clean()

        # Check for duplicate account
        bank_name = cleaned_data.get('bank_name')
        account_number = cleaned_data.get('account_number')

        if bank_name and account_number:
            existing = StokvelBankAccount.objects.filter(
                bank_name=bank_name,
                account_number=account_number
            )

            # Exclude current instance if updating
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)

            if existing.exists():
                raise ValidationError("This bank account already exists")

        return cleaned_data


# Search and Filter Forms
class StokvelSearchForm(forms.Form):
    """Form for searching and filtering stokvels"""

    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by name or description...'
        })
    )

    status = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'All Status'),
            ('active', 'Active'),
            ('accepting', 'Accepting Members'),
        ],
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    year = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Populate year choices
        current_year = timezone.now().year
        year_choices = [('', 'All Years')]

        # Get years from existing stokvels
        years = Stokvel.objects.values_list(
            'date_established__year', flat=True
        ).distinct().order_by('-date_established__year')

        for year in years:
            year_choices.append((str(year), str(year)))

        self.fields['year'].choices = year_choices


class ContributionRuleFilterForm(forms.Form):
    """Form for filtering contribution rules"""

    type = forms.ChoiceField(
        required=False,
        choices=[('', 'All Types')] + ContributionRule._meta.get_field('contribution_type').choices,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    active = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'All Rules'),
            ('true', 'Active Only'),
            ('false', 'Inactive Only'),
        ],
        widget=forms.Select(attrs={'class': 'form-control'})
    )


class PenaltyRuleFilterForm(forms.Form):
    """Form for filtering penalty rules"""

    type = forms.ChoiceField(
        required=False,
        choices=[('', 'All Types')] + PenaltyRule._meta.get_field('penalty_type').choices,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    active = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'All Rules'),
            ('true', 'Active Only'),
            ('false', 'Inactive Only'),
        ],
        widget=forms.Select(attrs={'class': 'form-control'})
    )