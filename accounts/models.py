from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import RegexValidator
from django.utils import timezone
import uuid


class User(AbstractUser):
    """Extended user model for the platform"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Additional profile fields
    phone_number = models.CharField(
        max_length=15,
        blank=True,
        validators=[RegexValidator(r'^\+?1?\d{9,15}$', 'Enter a valid phone number.')]
    )
    date_of_birth = models.DateField(null=True, blank=True)
    id_number = models.CharField(
        max_length=20,
        blank=True,
        help_text="National ID or passport number"
    )

    # Address
    address_line_1 = models.CharField(max_length=200, blank=True)
    address_line_2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    province = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=10, blank=True)
    country = models.CharField(max_length=100, default='South Africa')

    # Profile settings
    preferred_language = models.CharField(max_length=10, choices=[
        ('en', 'English'),
        ('af', 'Afrikaans'),
        ('zu', 'Zulu'),
        ('xh', 'Xhosa'),
        ('st', 'Sotho'),
        ('tn', 'Tswana'),
        ('ts', 'Tsonga'),
        ('ss', 'Swati'),
        ('ve', 'Venda'),
        ('nr', 'Ndebele'),
    ], default='en')

    # Notifications preferences
    email_notifications = models.BooleanField(default=True)
    sms_notifications = models.BooleanField(default=False)
    whatsapp_notifications = models.BooleanField(default=False)

    # Account status
    is_verified = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False)

    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"

    def get_full_address(self):
        """Returns formatted full address"""
        address_parts = [
            self.address_line_1,
            self.address_line_2,
            self.city,
            self.province,
            self.postal_code,
            self.country
        ]
        return ', '.join([part for part in address_parts if part])


class Member(models.Model):
    """Links users to stokvels with member-specific information"""
    MEMBER_STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('probation', 'Probation Period'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('inactive', 'Inactive'),
        ('exited', 'Exited'),
    ]

    MEMBER_ROLE_CHOICES = [
        ('member', 'Member'),
        ('secretary', 'Secretary'),
        ('treasurer', 'Treasurer'),
        ('chairperson', 'Chairperson'),
        ('admin', 'Administrator'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='memberships')
    stokvel = models.ForeignKey('stokvel.Stokvel', on_delete=models.CASCADE, related_name='members')

    # Member details
    member_number = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=20, choices=MEMBER_ROLE_CHOICES, default='member')
    status = models.CharField(max_length=20, choices=MEMBER_STATUS_CHOICES, default='pending')

    # Important dates
    application_date = models.DateField(auto_now_add=True)
    approval_date = models.DateField(null=True, blank=True)
    probation_end_date = models.DateField(null=True, blank=True)
    exit_date = models.DateField(null=True, blank=True)

    # Bank reference information for payment matching
    bank_reference_names = models.TextField(
        help_text="Comma-separated list of names as they appear on bank statements",
        blank=True
    )

    # Emergency contact
    emergency_contact_name = models.CharField(max_length=200, blank=True)
    emergency_contact_phone = models.CharField(max_length=15, blank=True)
    emergency_contact_relationship = models.CharField(max_length=50, blank=True)

    # Additional information
    occupation = models.CharField(max_length=100, blank=True)
    employer = models.CharField(max_length=200, blank=True)
    monthly_income_range = models.CharField(max_length=20, choices=[
        ('0-5000', 'R0 - R5,000'),
        ('5001-10000', 'R5,001 - R10,000'),
        ('10001-20000', 'R10,001 - R20,000'),
        ('20001-30000', 'R20,001 - R30,000'),
        ('30001-50000', 'R30,001 - R50,000'),
        ('50000+', 'R50,000+'),
    ], blank=True)

    # Stokvel-specific settings
    payout_preference = models.CharField(max_length=20, choices=[
        ('bank_transfer', 'Bank Transfer'),
        ('cash', 'Cash'),
        ('cheque', 'Cheque'),
    ], default='bank_transfer')

    # Notes and comments
    application_notes = models.TextField(blank=True)
    admin_notes = models.TextField(blank=True)

    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.stokvel.name} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        # Auto-generate member number if not provided
        if not self.member_number:
            # Get the last member number for this stokvel
            last_member = Member.objects.filter(
                stokvel=self.stokvel
            ).exclude(member_number='').order_by('-member_number').first()

            if last_member and last_member.member_number.isdigit():
                next_number = int(last_member.member_number) + 1
            else:
                next_number = 1

            self.member_number = str(next_number).zfill(3)  # Pad with zeros: 001, 002, etc.

        super().save(*args, **kwargs)

    @property
    def is_active_member(self):
        return self.status == 'active'

    @property
    def is_in_probation(self):
        return self.status == 'probation'

    @property
    def days_since_joining(self):
        if self.approval_date:
            return (timezone.now().date() - self.approval_date).days
        return 0

    def get_bank_reference_list(self):
        """Returns list of bank reference names"""
        if self.bank_reference_names:
            return [name.strip() for name in self.bank_reference_names.split(',')]
        return []

    class Meta:
        verbose_name = "Member"
        verbose_name_plural = "Members"
        unique_together = ['user', 'stokvel']
        ordering = ['stokvel', 'member_number']


class MemberBankAccount(models.Model):
    """Member's bank account details for payouts"""
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='bank_accounts')

    bank_name = models.CharField(max_length=100)
    account_holder_name = models.CharField(max_length=200)
    account_number = models.CharField(max_length=50)
    account_type = models.CharField(max_length=50, choices=[
        ('savings', 'Savings'),
        ('cheque', 'Cheque'),
        ('current', 'Current'),
        ('transmission', 'Transmission'),
    ])
    branch_code = models.CharField(max_length=10)

    is_primary = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)

    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.member.user.get_full_name()} - {self.bank_name} ({self.account_number})"

    def save(self, *args, **kwargs):
        # Ensure only one primary account per member
        if self.is_primary:
            MemberBankAccount.objects.filter(
                member=self.member,
                is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Member Bank Account"
        verbose_name_plural = "Member Bank Accounts"
        unique_together = ['member', 'account_number']


class MembershipApplication(models.Model):
    """Tracks membership applications and approval process"""
    APPLICATION_STATUS_CHOICES = [
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('withdrawn', 'Withdrawn'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='applications')
    stokvel = models.ForeignKey('stokvel.Stokvel', on_delete=models.CASCADE, related_name='applications')

    status = models.CharField(max_length=20, choices=APPLICATION_STATUS_CHOICES, default='submitted')

    # Application details
    motivation = models.TextField(help_text="Why do you want to join this stokvel?")
    referral_source = models.CharField(max_length=100, blank=True, help_text="How did you hear about us?")
    referred_by = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='referrals',
        help_text="Existing member who referred you"
    )

    # Review process
    reviewed_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_applications'
    )
    review_date = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)

    # Important dates
    submitted_date = models.DateTimeField(auto_now_add=True)
    decision_date = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.get_full_name()} -> {self.stokvel.name} ({self.get_status_display()})"

    def approve(self, reviewed_by_user, notes=""):
        """Approve the application and create member record"""
        self.status = 'approved'
        self.reviewed_by = reviewed_by_user
        self.review_date = timezone.now()
        self.decision_date = timezone.now()
        self.review_notes = notes
        self.save()

        # Create member record
        member = Member.objects.create(
            user=self.user,
            stokvel=self.stokvel,
            status='probation',  # Start in probation
            approval_date=timezone.now().date(),
            application_notes=self.motivation
        )

        return member

    def reject(self, reviewed_by_user, notes=""):
        """Reject the application"""
        self.status = 'rejected'
        self.reviewed_by = reviewed_by_user
        self.review_date = timezone.now()
        self.decision_date = timezone.now()
        self.review_notes = notes
        self.save()

    class Meta:
        verbose_name = "Membership Application"
        verbose_name_plural = "Membership Applications"
        unique_together = ['user', 'stokvel']
        ordering = ['-submitted_date']


class MemberActivity(models.Model):
    """Tracks member activities and engagement"""
    ACTIVITY_TYPES = [
        ('login', 'Login'),
        ('payment_made', 'Payment Made'),
        ('meeting_attended', 'Meeting Attended'),
        ('profile_updated', 'Profile Updated'),
        ('status_changed', 'Status Changed'),
        ('penalty_applied', 'Penalty Applied'),
        ('penalty_waived', 'Penalty Waived'),
    ]

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPES)
    description = models.TextField()

    # Additional context
    related_object_type = models.CharField(max_length=50, blank=True)
    related_object_id = models.CharField(max_length=50, blank=True)

    created_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.member.user.get_full_name()} - {self.get_activity_type_display()}"

    class Meta:
        verbose_name = "Member Activity"
        verbose_name_plural = "Member Activities"
        ordering = ['-created_date']