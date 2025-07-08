# stokvel/models.py
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from decimal import Decimal
import uuid

from .managers import (
    StokvelManager, ContributionRuleManager, PenaltyRuleManager,
    StokvelCycleManager, StokvelBankAccountManager, StokvelConstitutionManager
)


class Stokvel(models.Model):
    """Core stokvel entity"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    # Registration details
    registration_number = models.CharField(max_length=50, blank=True, null=True)
    date_established = models.DateField()

    # Status
    is_active = models.BooleanField(default=True)
    is_accepting_members = models.BooleanField(default=True)

    # Metadata
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    # Custom manager
    objects = StokvelManager()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Stokvel"
        verbose_name_plural = "Stokvels"
        ordering = ['name']


class StokvelConstitution(models.Model):
    """Stokvel rules and constitution"""
    stokvel = models.OneToOneField(Stokvel, on_delete=models.CASCADE, related_name='constitution')

    # Meeting requirements
    meeting_frequency = models.CharField(max_length=20, choices=[
        ('weekly', 'Weekly'),
        ('bi_weekly', 'Bi-weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('annually', 'Annually'),
    ], default='monthly')

    minimum_attendance_percentage = models.IntegerField(
        default=60,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Minimum attendance percentage for valid meetings"
    )

    # Member requirements
    minimum_members = models.IntegerField(default=5)
    maximum_members = models.IntegerField(null=True, blank=True)
    probation_period_months = models.IntegerField(
        default=3,
        help_text="Months a new member must complete before full membership"
    )

    # Financial rules
    contribution_start_day = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text="Day of month when contribution period starts"
    )
    contribution_due_day = models.IntegerField(
        default=31,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text="Day of month when contributions are due (31 = last day)"
    )

    # Exit and suspension rules
    notice_period_days = models.IntegerField(
        default=30,
        help_text="Days notice required before leaving stokvel"
    )
    suspension_rules = models.TextField(
        blank=True,
        help_text="Rules for member suspension"
    )

    # Payout rules
    payout_frequency = models.CharField(max_length=20, choices=[
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('bi_annually', 'Bi-annually'),
        ('annually', 'Annually'),
        ('end_of_cycle', 'End of Cycle'),
    ], default='monthly')

    payout_order_method = models.CharField(max_length=20, choices=[
        ('rotation', 'Rotation'),
        ('draw', 'Lucky Draw'),
        ('seniority', 'Seniority'),
        ('contribution_based', 'Contribution Based'),
    ], default='rotation')

    constitution_text = models.TextField(
        blank=True,
        help_text="Full constitution document"
    )

    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    # Custom manager
    objects = StokvelConstitutionManager()

    def __str__(self):
        return f"{self.stokvel.name} Constitution"

    class Meta:
        verbose_name = "Stokvel Constitution"
        verbose_name_plural = "Stokvel Constitutions"


class ContributionRule(models.Model):
    """Defines contribution amounts and schedules"""
    stokvel = models.ForeignKey(Stokvel, on_delete=models.CASCADE, related_name='contribution_rules')

    # Basic contribution info
    name = models.CharField(max_length=100, help_text="e.g., 'Monthly Contribution', 'Registration Fee'")
    contribution_type = models.CharField(max_length=20, choices=[
        ('regular', 'Regular Contribution'),
        ('registration', 'Registration Fee'),
        ('special', 'Special Contribution'),
        ('emergency', 'Emergency Contribution'),
    ])

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )

    # Schedule
    frequency = models.CharField(max_length=20, choices=[
        ('once_off', 'Once Off'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('annually', 'Annually'),
    ], default='monthly')

    # Effective dates
    effective_from = models.DateField()
    effective_until = models.DateField(null=True, blank=True)

    # Status
    is_active = models.BooleanField(default=True)
    is_mandatory = models.BooleanField(default=True)

    description = models.TextField(blank=True)
    created_date = models.DateTimeField(auto_now_add=True)

    # Custom manager
    objects = ContributionRuleManager()

    def __str__(self):
        return f"{self.stokvel.name} - {self.name} (R{self.amount})"

    def is_active_for_date(self, target_date):
        """Check if rule is active for a specific date"""
        if not self.is_active:
            return False
        if self.effective_from > target_date:
            return False
        if self.effective_until and self.effective_until < target_date:
            return False
        return True

    class Meta:
        verbose_name = "Contribution Rule"
        verbose_name_plural = "Contribution Rules"
        ordering = ['stokvel', '-effective_from']


class PenaltyRule(models.Model):
    """Defines penalty rules and amounts"""
    stokvel = models.ForeignKey(Stokvel, on_delete=models.CASCADE, related_name='penalty_rules')

    name = models.CharField(max_length=100)
    penalty_type = models.CharField(max_length=30, choices=[
        ('late_payment', 'Late Payment'),
        ('insufficient_payment', 'Insufficient Payment'),
        ('no_payment', 'No Payment'),
        ('missed_meeting', 'Missed Meeting'),
        ('early_exit', 'Early Exit'),
        ('breach_of_rules', 'Breach of Rules'),
    ])

    # Penalty calculation
    calculation_method = models.CharField(max_length=20, choices=[
        ('fixed', 'Fixed Amount'),
        ('percentage', 'Percentage of Contribution'),
        ('daily', 'Daily Accumulation'),
        ('tiered', 'Tiered Based on Days Late'),
    ], default='fixed')

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Fixed amount or percentage (for percentage method)"
    )

    # Grace period
    grace_period_days = models.IntegerField(
        default=0,
        help_text="Days before penalty is applied"
    )

    # Maximum penalties
    maximum_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum penalty amount (optional)"
    )

    # Effective dates
    effective_from = models.DateField()
    effective_until = models.DateField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    created_date = models.DateTimeField(auto_now_add=True)

    # Custom manager
    objects = PenaltyRuleManager()

    def __str__(self):
        return f"{self.stokvel.name} - {self.name}"

    def calculate_penalty(self, base_amount, days_late=0):
        """Calculate penalty based on the rule configuration"""
        if days_late <= self.grace_period_days:
            return Decimal('0.00')

        if self.calculation_method == 'fixed':
            penalty = self.amount
        elif self.calculation_method == 'percentage':
            penalty = base_amount * (self.amount / 100)
        elif self.calculation_method == 'daily':
            penalty = self.amount * (days_late - self.grace_period_days)
        else:  # tiered - would need additional configuration
            penalty = self.amount

        # Apply maximum if set
        if self.maximum_amount and penalty > self.maximum_amount:
            penalty = self.maximum_amount

        return penalty

    def is_active_for_date(self, target_date):
        """Check if rule is active for a specific date"""
        if not self.is_active:
            return False
        if self.effective_from > target_date:
            return False
        if self.effective_until and self.effective_until < target_date:
            return False
        return True

    class Meta:
        verbose_name = "Penalty Rule"
        verbose_name_plural = "Penalty Rules"
        ordering = ['stokvel', 'penalty_type']


class StokvelCycle(models.Model):
    """Represents a stokvel cycle/period"""
    stokvel = models.ForeignKey(Stokvel, on_delete=models.CASCADE, related_name='cycles')

    name = models.CharField(max_length=100, help_text="e.g., '2025 Cycle', 'Year 1'")
    start_date = models.DateField()
    end_date = models.DateField()

    # Expected totals
    expected_total_contributions = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )

    # Status
    status = models.CharField(max_length=20, choices=[
        ('planned', 'Planned'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], default='planned')

    description = models.TextField(blank=True)
    created_date = models.DateTimeField(auto_now_add=True)

    # Custom manager
    objects = StokvelCycleManager()

    def __str__(self):
        return f"{self.stokvel.name} - {self.name}"

    @property
    def is_current(self):
        today = timezone.now().date()
        return self.start_date <= today <= self.end_date

    @property
    def duration_months(self):
        """Calculate cycle duration in months"""
        return (self.end_date.year - self.start_date.year) * 12 + (self.end_date.month - self.start_date.month)

    def get_progress_percentage(self):
        """Calculate cycle progress as percentage"""
        if self.status != 'active':
            return 0 if self.status == 'planned' else 100

        today = timezone.now().date()
        if today < self.start_date:
            return 0
        elif today > self.end_date:
            return 100
        else:
            total_days = (self.end_date - self.start_date).days
            elapsed_days = (today - self.start_date).days
            return round((elapsed_days / total_days) * 100, 1) if total_days > 0 else 0

    class Meta:
        verbose_name = "Stokvel Cycle"
        verbose_name_plural = "Stokvel Cycles"
        ordering = ['stokvel', '-start_date']


class StokvelBankAccount(models.Model):
    """Bank account details for the stokvel"""
    stokvel = models.ForeignKey(Stokvel, on_delete=models.CASCADE, related_name='bank_accounts')

    bank_name = models.CharField(max_length=100)
    account_name = models.CharField(max_length=200)
    account_number = models.CharField(max_length=50)
    branch_code = models.CharField(max_length=10)
    account_type = models.CharField(max_length=50)

    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    created_date = models.DateTimeField(auto_now_add=True)

    # Custom manager
    objects = StokvelBankAccountManager()

    def __str__(self):
        return f"{self.stokvel.name} - {self.bank_name} ({self.account_number})"

    def save(self, *args, **kwargs):
        # Ensure only one primary account per stokvel
        if self.is_primary:
            StokvelBankAccount.objects.filter(
                stokvel=self.stokvel,
                is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)

    @property
    def masked_account_number(self):
        """Returns masked account number for display"""
        if len(self.account_number) <= 4:
            return self.account_number
        return f"****{self.account_number[-4:]}"

    class Meta:
        verbose_name = "Stokvel Bank Account"
        verbose_name_plural = "Stokvel Bank Accounts"
        unique_together = ['bank_name', 'account_number']