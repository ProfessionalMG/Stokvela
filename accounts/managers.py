from django.db import models
from django.utils import timezone
from django.contrib.auth.models import BaseUserManager
from datetime import date, timedelta
from typing import Optional


class UserManager(BaseUserManager):
    """Custom manager for User model"""

    def create_user(self, username, email, password=None, **extra_fields):
        """Create and return a regular user"""
        if not email:
            raise ValueError('Users must have an email address')
        if not username:
            raise ValueError('Users must have a username')

        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password=None, **extra_fields):
        """Create and return a superuser"""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_verified', True)
        extra_fields.setdefault('email_verified', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True')

        return self.create_user(username, email, password, **extra_fields)

    def verified_users(self):
        """Returns users with verified accounts"""
        return self.filter(is_verified=True)

    def email_verified(self):
        """Returns users with verified email addresses"""
        return self.filter(email_verified=True)

    def phone_verified(self):
        """Returns users with verified phone numbers"""
        return self.filter(phone_verified=True)

    def incomplete_profiles(self):
        """Returns users with incomplete profiles"""
        return self.filter(
            models.Q(first_name='') |
            models.Q(last_name='') |
            models.Q(phone_number='') |
            models.Q(email_verified=False) |
            models.Q(phone_verified=False)
        )

    def by_language(self, language_code: str):
        """Returns users by preferred language"""
        return self.filter(preferred_language=language_code)

    def with_notifications_enabled(self, notification_type: str = 'email'):
        """Returns users with specific notification type enabled"""
        if notification_type == 'email':
            return self.filter(email_notifications=True, email_verified=True)
        elif notification_type == 'sms':
            return self.filter(sms_notifications=True, phone_verified=True)
        elif notification_type == 'whatsapp':
            return self.filter(whatsapp_notifications=True, phone_verified=True)
        return self.none()

    def search(self, query: str):
        """Search users by name, username, or email"""
        return self.filter(
            models.Q(first_name__icontains=query) |
            models.Q(last_name__icontains=query) |
            models.Q(username__icontains=query) |
            models.Q(email__icontains=query)
        )


class MemberManager(models.Manager):
    """Custom manager for Member model"""

    def active(self):
        """Returns only active members"""
        return self.filter(status='active')

    def pending(self):
        """Returns members pending approval"""
        return self.filter(status='pending')

    def in_probation(self):
        """Returns members in probation period"""
        return self.filter(status='probation')

    def suspended(self):
        """Returns suspended members"""
        return self.filter(status='suspended')

    def inactive(self):
        """Returns inactive members"""
        return self.filter(status='inactive')

    def exited(self):
        """Returns members who have exited"""
        return self.filter(status='exited')

    def by_status(self, status: str):
        """Returns members by specific status"""
        return self.filter(status=status)

    def by_role(self, role: str):
        """Returns members by role"""
        return self.filter(role=role)

    def leadership(self):
        """Returns members with leadership roles"""
        leadership_roles = ['chairperson', 'treasurer', 'secretary', 'admin']
        return self.filter(role__in=leadership_roles, status='active')

    def chairpersons(self):
        """Returns chairpersons"""
        return self.filter(role='chairperson', status='active')

    def treasurers(self):
        """Returns treasurers"""
        return self.filter(role='treasurer', status='active')

    def secretaries(self):
        """Returns secretaries"""
        return self.filter(role='secretary', status='active')

    def joined_in_period(self, start_date: date, end_date: date):
        """Returns members who joined in a specific period"""
        return self.filter(
            approval_date__gte=start_date,
            approval_date__lte=end_date
        )

    def joined_recently(self, days: int = 30):
        """Returns members who joined in the last N days"""
        start_date = timezone.now().date() - timedelta(days=days)
        return self.filter(approval_date__gte=start_date)

    def due_for_probation_completion(self):
        """Returns members who should complete probation"""
        # This would need the constitution's probation period
        # For now, assume 3 months
        three_months_ago = timezone.now().date() - timedelta(days=90)
        return self.filter(
            status='probation',
            approval_date__lte=three_months_ago
        )

    def with_complete_profiles(self):
        """Returns members with complete profiles"""
        return self.filter(
            user__first_name__isnull=False,
            user__last_name__isnull=False,
            user__email_verified=True,
            user__phone_verified=True
        ).exclude(
            user__first_name='',
            user__last_name=''
        )

    def eligible_for_payout(self):
        """Returns members eligible for payouts"""
        return self.active().filter(
            user__email_verified=True,
            user__phone_verified=True,
            bank_accounts__is_verified=True,
            bank_accounts__is_primary=True
        ).distinct()

    def search(self, query: str):
        """Search members by user details or member number"""
        return self.filter(
            models.Q(user__first_name__icontains=query) |
            models.Q(user__last_name__icontains=query) |
            models.Q(user__username__icontains=query) |
            models.Q(user__email__icontains=query) |
            models.Q(member_number__icontains=query)
        )


class MembershipApplicationManager(models.Manager):
    """Custom manager for MembershipApplication model"""

    def submitted(self):
        """Returns submitted applications"""
        return self.filter(status='submitted')

    def under_review(self):
        """Returns applications under review"""
        return self.filter(status='under_review')

    def approved(self):
        """Returns approved applications"""
        return self.filter(status='approved')

    def rejected(self):
        """Returns rejected applications"""
        return self.filter(status='rejected')

    def withdrawn(self):
        """Returns withdrawn applications"""
        return self.filter(status='withdrawn')

    def pending_review(self):
        """Returns applications pending review (submitted + under_review)"""
        return self.filter(status__in=['submitted', 'under_review'])

    def by_status(self, status: str):
        """Returns applications by status"""
        return self.filter(status=status)

    def for_stokvel(self, stokvel):
        """Returns applications for a specific stokvel"""
        return self.filter(stokvel=stokvel)

    def submitted_in_period(self, start_date: date, end_date: date):
        """Returns applications submitted in a period"""
        return self.filter(
            submitted_date__date__gte=start_date,
            submitted_date__date__lte=end_date
        )

    def awaiting_decision(self, days: int = 7):
        """Returns applications awaiting decision for more than N days"""
        cutoff_date = timezone.now() - timedelta(days=days)
        return self.filter(
            status='submitted',
            submitted_date__lte=cutoff_date
        )

    def with_referrals(self):
        """Returns applications that have referrals"""
        return self.filter(referred_by__isnull=False)

    def search(self, query: str):
        """Search applications by user details"""
        return self.filter(
            models.Q(user__first_name__icontains=query) |
            models.Q(user__last_name__icontains=query) |
            models.Q(user__username__icontains=query) |
            models.Q(user__email__icontains=query) |
            models.Q(motivation__icontains=query)
        )


class MemberBankAccountManager(models.Manager):
    """Custom manager for MemberBankAccount model"""

    def verified(self):
        """Returns verified bank accounts"""
        return self.filter(is_verified=True)

    def unverified(self):
        """Returns unverified bank accounts"""
        return self.filter(is_verified=False)

    def primary(self):
        """Returns primary bank accounts"""
        return self.filter(is_primary=True)

    def by_bank(self, bank_name: str):
        """Returns accounts by bank name"""
        return self.filter(bank_name__icontains=bank_name)

    def by_account_type(self, account_type: str):
        """Returns accounts by account type"""
        return self.filter(account_type=account_type)

    def for_member(self, member):
        """Returns accounts for a specific member"""
        return self.filter(member=member)

    def needs_verification(self):
        """Returns accounts that need verification"""
        return self.filter(is_verified=False)

    def without_primary(self):
        """Returns members who don't have a primary account set"""
        member_ids_with_primary = self.filter(is_primary=True).values_list('member_id', flat=True)
        return self.exclude(member_id__in=member_ids_with_primary)


class MemberActivityManager(models.Manager):
    """Custom manager for MemberActivity model"""

    def for_member(self, member):
        """Returns activities for a specific member"""
        return self.filter(member=member)

    def by_type(self, activity_type: str):
        """Returns activities by type"""
        return self.filter(activity_type=activity_type)

    def in_period(self, start_date: date, end_date: date):
        """Returns activities in a specific period"""
        start_datetime = timezone.make_aware(
            timezone.datetime.combine(start_date, timezone.datetime.min.time())
        )
        end_datetime = timezone.make_aware(
            timezone.datetime.combine(end_date, timezone.datetime.max.time())
        )
        return self.filter(
            created_date__gte=start_datetime,
            created_date__lte=end_datetime
        )

    def recent(self, days: int = 30):
        """Returns recent activities"""
        start_date = timezone.now() - timedelta(days=days)
        return self.filter(created_date__gte=start_date)

    def login_activities(self):
        """Returns login activities"""
        return self.filter(activity_type='login')

    def payment_activities(self):
        """Returns payment-related activities"""
        return self.filter(activity_type='payment_made')

    def status_changes(self):
        """Returns status change activities"""
        return self.filter(activity_type='status_changed')

    def profile_updates(self):
        """Returns profile update activities"""
        return self.filter(activity_type='profile_updated')

    def for_stokvel_members(self, stokvel):
        """Returns activities for all members of a stokvel"""
        member_ids = stokvel.members.values_list('id', flat=True)
        return self.filter(member_id__in=member_ids)

    def search(self, query: str):
        """Search activities by description"""
        return self.filter(description__icontains=query)