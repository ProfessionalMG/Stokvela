from django.db import models
from django.utils import timezone
from datetime import date
from typing import Optional


class StokvelManager(models.Manager):
    """Custom manager for Stokvel model"""

    def active(self):
        """Returns only active stokvels"""
        return self.filter(is_active=True)

    def accepting_members(self):
        """Returns stokvels that are accepting new members"""
        return self.filter(is_active=True, is_accepting_members=True)

    def with_constitution(self):
        """Returns stokvels that have a constitution configured"""
        return self.filter(constitution__isnull=False)

    def by_establishment_year(self, year: int):
        """Returns stokvels established in a specific year"""
        return self.filter(date_established__year=year)

    def search(self, query: str):
        """Search stokvels by name or description"""
        return self.filter(
            models.Q(name__icontains=query) |
            models.Q(description__icontains=query)
        )


class ContributionRuleManager(models.Manager):
    """Custom manager for ContributionRule model"""

    def active(self):
        """Returns only active contribution rules"""
        return self.filter(is_active=True)

    def for_date(self, target_date: date = None):
        """Returns rules active for a specific date"""
        if not target_date:
            target_date = timezone.now().date()

        return self.filter(
            is_active=True,
            effective_from__lte=target_date
        ).filter(
            models.Q(effective_until__gte=target_date) |
            models.Q(effective_until__isnull=True)
        )

    def by_type(self, contribution_type: str):
        """Returns rules by contribution type"""
        return self.filter(contribution_type=contribution_type)

    def regular_contributions(self):
        """Returns only regular contribution rules"""
        return self.filter(contribution_type='regular', is_active=True)

    def mandatory(self):
        """Returns only mandatory contribution rules"""
        return self.filter(is_mandatory=True, is_active=True)

    def by_frequency(self, frequency: str):
        """Returns rules by frequency"""
        return self.filter(frequency=frequency)

    def expiring_soon(self, days: int = 30):
        """Returns rules expiring within specified days"""
        future_date = timezone.now().date() + timezone.timedelta(days=days)
        return self.filter(
            is_active=True,
            effective_until__lte=future_date,
            effective_until__gte=timezone.now().date()
        )


class PenaltyRuleManager(models.Manager):
    """Custom manager for PenaltyRule model"""

    def active(self):
        """Returns only active penalty rules"""
        return self.filter(is_active=True)

    def for_date(self, target_date: date = None):
        """Returns rules active for a specific date"""
        if not target_date:
            target_date = timezone.now().date()

        return self.filter(
            is_active=True,
            effective_from__lte=target_date
        ).filter(
            models.Q(effective_until__gte=target_date) |
            models.Q(effective_until__isnull=True)
        )

    def by_type(self, penalty_type: str):
        """Returns rules by penalty type"""
        return self.filter(penalty_type=penalty_type)

    def late_payment_rules(self):
        """Returns late payment penalty rules"""
        return self.filter(penalty_type='late_payment', is_active=True)

    def by_calculation_method(self, method: str):
        """Returns rules by calculation method"""
        return self.filter(calculation_method=method)

    def with_grace_period(self):
        """Returns rules that have a grace period"""
        return self.filter(grace_period_days__gt=0)


class StokvelCycleManager(models.Manager):
    """Custom manager for StokvelCycle model"""

    def active(self):
        """Returns only active cycles"""
        return self.filter(status='active')

    def current(self, target_date: date = None):
        """Returns cycles that are current for a specific date"""
        if not target_date:
            target_date = timezone.now().date()

        return self.filter(
            status='active',
            start_date__lte=target_date,
            end_date__gte=target_date
        )

    def upcoming(self, days: int = 30):
        """Returns cycles starting within specified days"""
        future_date = timezone.now().date() + timezone.timedelta(days=days)
        return self.filter(
            status='planned',
            start_date__lte=future_date,
            start_date__gte=timezone.now().date()
        )

    def completed(self):
        """Returns completed cycles"""
        return self.filter(status='completed')

    def by_status(self, status: str):
        """Returns cycles by status"""
        return self.filter(status=status)

    def for_year(self, year: int):
        """Returns cycles that overlap with a specific year"""
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)

        return self.filter(
            start_date__lte=year_end,
            end_date__gte=year_start
        )


class StokvelBankAccountManager(models.Manager):
    """Custom manager for StokvelBankAccount model"""

    def active(self):
        """Returns only active bank accounts"""
        return self.filter(is_active=True)

    def primary(self):
        """Returns primary bank accounts"""
        return self.filter(is_primary=True, is_active=True)

    def by_bank(self, bank_name: str):
        """Returns accounts by bank name"""
        return self.filter(bank_name__icontains=bank_name)

    def by_account_type(self, account_type: str):
        """Returns accounts by account type"""
        return self.filter(account_type=account_type)


class StokvelConstitutionManager(models.Manager):
    """Custom manager for StokvelConstitution model"""

    def with_meeting_frequency(self, frequency: str):
        """Returns constitutions with specific meeting frequency"""
        return self.filter(meeting_frequency=frequency)

    def with_payout_method(self, method: str):
        """Returns constitutions with specific payout order method"""
        return self.filter(payout_order_method=method)

    def requiring_minimum_members(self, min_count: int):
        """Returns constitutions requiring at least min_count members"""
        return self.filter(minimum_members__gte=min_count)

    def with_probation_period(self):
        """Returns constitutions that have probation periods"""
        return self.filter(probation_period_months__gt=0)