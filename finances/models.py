from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal
import uuid
import calendar


class PaymentPeriod(models.Model):
    """Defines payment periods for contributions"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stokvel = models.ForeignKey('stokvel.Stokvel', on_delete=models.CASCADE, related_name='payment_periods')
    contribution_rule = models.ForeignKey(
        'stokvel.ContributionRule',
        on_delete=models.CASCADE,
        related_name='payment_periods'
    )

    # Period definition
    name = models.CharField(max_length=100, help_text="e.g., 'March 2025', 'Q1 2025'")
    year = models.IntegerField()
    month = models.IntegerField(null=True, blank=True)  # For monthly periods
    quarter = models.IntegerField(null=True, blank=True)  # For quarterly periods

    # Important dates
    period_start_date = models.DateField()
    period_end_date = models.DateField()
    due_date = models.DateField()

    # Expected amounts
    expected_amount_per_member = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )

    # Status and settings
    is_open = models.BooleanField(default=True)
    is_finalized = models.BooleanField(default=False)
    auto_generate_penalties = models.BooleanField(default=True)

    notes = models.TextField(blank=True)
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.stokvel.name} - {self.name}"

    def save(self, *args, **kwargs):
        # Auto-set expected amount from contribution rule if not provided
        if not self.expected_amount_per_member:
            self.expected_amount_per_member = self.contribution_rule.amount
        super().save(*args, **kwargs)

    @property
    def is_overdue(self):
        return timezone.now().date() > self.due_date

    @property
    def total_expected_amount(self):
        """Total expected from all active members"""
        active_members_count = self.stokvel.members.filter(status='active').count()
        return self.expected_amount_per_member * active_members_count

    @property
    def total_received_amount(self):
        """Total amount received from all payments"""
        return self.contributions.filter(
            verification_status='verified'
        ).aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')

    @property
    def collection_percentage(self):
        """Percentage of expected amount collected"""
        expected = self.total_expected_amount
        if expected > 0:
            return (self.total_received_amount / expected) * 100
        return 0

    class Meta:
        verbose_name = "Payment Period"
        verbose_name_plural = "Payment Periods"
        unique_together = ['stokvel', 'contribution_rule', 'year', 'month', 'quarter']
        ordering = ['-year', '-month', '-quarter']


class Contribution(models.Model):
    """Individual member contributions/payments"""
    VERIFICATION_STATUS_CHOICES = [
        ('pending', 'Pending Verification'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
        ('reversed', 'Reversed'),
    ]

    PAYMENT_METHOD_CHOICES = [
        ('bank_transfer', 'Bank Transfer'),
        ('cash', 'Cash'),
        ('eft', 'EFT'),
        ('debit_order', 'Debit Order'),
        ('mobile_payment', 'Mobile Payment'),
        ('other', 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    member = models.ForeignKey('accounts.Member', on_delete=models.CASCADE, related_name='contributions')
    payment_period = models.ForeignKey(PaymentPeriod, on_delete=models.CASCADE, related_name='contributions')

    # Payment details
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    payment_date = models.DateField()
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)

    # Bank/transaction details
    reference_number = models.CharField(max_length=100, blank=True)
    bank_reference = models.CharField(
        max_length=200,
        blank=True,
        help_text="Transaction description from bank statement"
    )
    bank_transaction_date = models.DateField(null=True, blank=True)

    # Verification
    verification_status = models.CharField(
        max_length=15,
        choices=VERIFICATION_STATUS_CHOICES,
        default='pending'
    )
    verified_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_contributions'
    )
    verification_date = models.DateTimeField(null=True, blank=True)
    verification_notes = models.TextField(blank=True)

    # Additional information
    notes = models.TextField(blank=True)
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.member.user.get_full_name()} - {self.payment_period.name} - R{self.amount}"

    @property
    def is_late_payment(self):
        return self.payment_date > self.payment_period.due_date

    @property
    def is_full_payment(self):
        return self.amount >= self.payment_period.expected_amount_per_member

    @property
    def shortage_amount(self):
        if self.amount < self.payment_period.expected_amount_per_member:
            return self.payment_period.expected_amount_per_member - self.amount
        return Decimal('0.00')

    @property
    def days_late(self):
        if self.is_late_payment:
            return (self.payment_date - self.payment_period.due_date).days
        return 0

    def verify(self, verified_by_user, notes=""):
        """Mark contribution as verified"""
        self.verification_status = 'verified'
        self.verified_by = verified_by_user
        self.verification_date = timezone.now()
        self.verification_notes = notes
        self.save()

    def reject(self, verified_by_user, notes=""):
        """Mark contribution as rejected"""
        self.verification_status = 'rejected'
        self.verified_by = verified_by_user
        self.verification_date = timezone.now()
        self.verification_notes = notes
        self.save()

    class Meta:
        verbose_name = "Contribution"
        verbose_name_plural = "Contributions"
        unique_together = ['member', 'payment_period']
        ordering = ['-payment_date']


class Penalty(models.Model):
    """Penalty fees applied to members"""
    PENALTY_STATUS_CHOICES = [
        ('applied', 'Applied'),
        ('waived', 'Waived'),
        ('paid', 'Paid'),
        ('outstanding', 'Outstanding'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    member = models.ForeignKey('accounts.Member', on_delete=models.CASCADE, related_name='penalties')
    payment_period = models.ForeignKey(
        PaymentPeriod,
        on_delete=models.CASCADE,
        related_name='penalties',
        null=True,
        blank=True
    )
    penalty_rule = models.ForeignKey(
        'stokvel.PenaltyRule',
        on_delete=models.CASCADE,
        related_name='applied_penalties'
    )

    # Penalty details
    penalty_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    reason = models.TextField()
    applied_date = models.DateField()

    # Status tracking
    status = models.CharField(max_length=15, choices=PENALTY_STATUS_CHOICES, default='applied')

    # Waiver information
    waived_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='waived_penalties'
    )
    waived_date = models.DateField(null=True, blank=True)
    waived_reason = models.TextField(blank=True)

    # Payment tracking
    paid_date = models.DateField(null=True, blank=True)
    paid_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )

    notes = models.TextField(blank=True)
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.member.user.get_full_name()} - {self.penalty_rule.name} - R{self.penalty_amount}"

    @property
    def outstanding_amount(self):
        return self.penalty_amount - self.paid_amount

    def waive(self, waived_by_user, reason=""):
        """Waive the penalty"""
        self.status = 'waived'
        self.waived_by = waived_by_user
        self.waived_date = timezone.now().date()
        self.waived_reason = reason
        self.save()

    def mark_as_paid(self, amount=None, payment_date=None):
        """Mark penalty as paid"""
        if amount is None:
            amount = self.penalty_amount
        if payment_date is None:
            payment_date = timezone.now().date()

        self.paid_amount = amount
        self.paid_date = payment_date

        if self.paid_amount >= self.penalty_amount:
            self.status = 'paid'
        else:
            self.status = 'outstanding'

        self.save()

    class Meta:
        verbose_name = "Penalty"
        verbose_name_plural = "Penalties"
        ordering = ['-applied_date']


class Transaction(models.Model):
    """All financial transactions (credits and debits)"""
    TRANSACTION_TYPES = [
        ('contribution', 'Member Contribution'),
        ('penalty_payment', 'Penalty Payment'),
        ('payout', 'Member Payout'),
        ('expense', 'Expense'),
        ('transfer', 'Transfer'),
        ('interest', 'Interest'),
        ('fee', 'Bank Fee'),
        ('adjustment', 'Adjustment'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stokvel = models.ForeignKey('stokvel.Stokvel', on_delete=models.CASCADE, related_name='transactions')

    # Transaction details
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)  # Can be negative for debits
    description = models.CharField(max_length=200)
    transaction_date = models.DateField()

    # Related objects
    related_member = models.ForeignKey(
        'accounts.Member',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions'
    )
    related_contribution = models.ForeignKey(
        Contribution,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions'
    )
    related_penalty = models.ForeignKey(
        Penalty,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions'
    )

    # Bank details
    reference_number = models.CharField(max_length=100, blank=True)
    bank_reference = models.CharField(max_length=200, blank=True)

    # Running balance (calculated field)
    running_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )

    # Metadata
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_transactions'
    )
    notes = models.TextField(blank=True)
    created_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.stokvel.name} - {self.get_transaction_type_display()} - R{self.amount}"

    @property
    def is_credit(self):
        return self.amount > 0

    @property
    def is_debit(self):
        return self.amount < 0

    class Meta:
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"
        ordering = ['-transaction_date', '-created_date']


class BankStatementImport(models.Model):
    """Tracks bank statement imports and processing"""
    IMPORT_STATUS_CHOICES = [
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('partially_matched', 'Partially Matched'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stokvel = models.ForeignKey('stokvel.Stokvel', on_delete=models.CASCADE, related_name='statement_imports')

    # Import details
    file_name = models.CharField(max_length=255)
    statement_period_start = models.DateField()
    statement_period_end = models.DateField()

    # Processing status
    status = models.CharField(max_length=20, choices=IMPORT_STATUS_CHOICES, default='processing')

    # Statistics
    total_transactions_imported = models.IntegerField(default=0)
    matched_contributions = models.IntegerField(default=0)
    unmatched_transactions = models.IntegerField(default=0)
    duplicate_transactions = models.IntegerField(default=0)

    # Processing details
    imported_by = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='imports')
    import_date = models.DateTimeField(auto_now_add=True)
    processing_completed_date = models.DateTimeField(null=True, blank=True)

    error_log = models.TextField(blank=True)
    processing_notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.stokvel.name} - {self.file_name} ({self.import_date.strftime('%Y-%m-%d')})"

    @property
    def match_percentage(self):
        if self.total_transactions_imported > 0:
            return (self.matched_contributions / self.total_transactions_imported) * 100
        return 0

    def mark_completed(self):
        self.status = 'completed'
        self.processing_completed_date = timezone.now()
        self.save()

    def mark_failed(self, error_message=""):
        self.status = 'failed'
        self.error_log = error_message
        self.processing_completed_date = timezone.now()
        self.save()

    class Meta:
        verbose_name = "Bank Statement Import"
        verbose_name_plural = "Bank Statement Imports"
        ordering = ['-import_date']


class Payout(models.Model):
    """Member payouts from the stokvel"""
    PAYOUT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('processed', 'Processed'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    member = models.ForeignKey('accounts.Member', on_delete=models.CASCADE, related_name='payouts')
    stokvel_cycle = models.ForeignKey(
        'stokvel.StokvelCycle',
        on_delete=models.CASCADE,
        related_name='payouts'
    )

    # Payout details
    payout_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    payout_date = models.DateField()
    payout_method = models.CharField(max_length=20, choices=[
        ('bank_transfer', 'Bank Transfer'),
        ('cash', 'Cash'),
        ('cheque', 'Cheque'),
    ])

    # Status tracking
    status = models.CharField(max_length=15, choices=PAYOUT_STATUS_CHOICES, default='pending')

    # Approval workflow
    requested_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='requested_payouts'
    )
    approved_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_payouts'
    )
    processed_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_payouts'
    )

    # Important dates
    request_date = models.DateTimeField(auto_now_add=True)
    approval_date = models.DateTimeField(null=True, blank=True)
    processing_date = models.DateTimeField(null=True, blank=True)
    completion_date = models.DateTimeField(null=True, blank=True)

    # Bank transfer details
    bank_account = models.ForeignKey(
        'accounts.MemberBankAccount',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    reference_number = models.CharField(max_length=100, blank=True)

    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.member.user.get_full_name()} - R{self.payout_amount} ({self.get_status_display()})"

    def approve(self, approved_by_user, notes=""):
        """Approve the payout"""
        self.status = 'approved'
        self.approved_by = approved_by_user
        self.approval_date = timezone.now()
        if notes:
            self.notes = notes
        self.save()

    def process(self, processed_by_user, reference_number=""):
        """Mark payout as processed"""
        self.status = 'processed'
        self.processed_by = processed_by_user
        self.processing_date = timezone.now()
        if reference_number:
            self.reference_number = reference_number
        self.save()

    def complete(self):
        """Mark payout as completed"""
        self.status = 'completed'
        self.completion_date = timezone.now()
        self.save()

    class Meta:
        verbose_name = "Payout"
        verbose_name_plural = "Payouts"
        ordering = ['-request_date']