from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import date, timedelta
import calendar
from typing import Optional, Dict, List, Tuple

from .models import (
    Stokvel, StokvelConstitution, ContributionRule,
    PenaltyRule, StokvelCycle, StokvelBankAccount
)


class StokvelService:
    """Core business logic for stokvel management"""

    @staticmethod
    @transaction.atomic
    def create_stokvel_with_constitution(
            name: str,
            description: str,
            date_established: date,
            constitution_data: Dict,
            created_by_user=None
    ) -> Stokvel:
        """
        Creates a new stokvel with its constitution in a single transaction
        """
        # Validate required fields
        if not name or not date_established:
            raise ValidationError("Name and establishment date are required")

        # Check if stokvel name already exists
        if Stokvel.objects.filter(name=name).exists():
            raise ValidationError(f"Stokvel with name '{name}' already exists")

        # Create the stokvel
        stokvel = Stokvel.objects.create(
            name=name,
            description=description,
            date_established=date_established,
            is_active=True,
            is_accepting_members=True
        )

        # Create constitution with defaults
        constitution_defaults = {
            'meeting_frequency': 'monthly',
            'minimum_attendance_percentage': 60,
            'minimum_members': 5,
            'maximum_members': None,
            'probation_period_months': 3,
            'contribution_start_day': 1,
            'contribution_due_day': 31,
            'notice_period_days': 30,
            'payout_frequency': 'monthly',
            'payout_order_method': 'rotation',
        }

        # Update defaults with provided data
        constitution_defaults.update(constitution_data)

        constitution = StokvelConstitution.objects.create(
            stokvel=stokvel,
            **constitution_defaults
        )

        return stokvel

    @staticmethod
    def update_stokvel_status(stokvel: Stokvel, is_active: bool, reason: str = "") -> bool:
        """
        Updates stokvel active status with validation
        """
        if not is_active:
            # Check if there are active members
            active_members_count = stokvel.members.filter(status='active').count()
            if active_members_count > 0:
                raise ValidationError(
                    f"Cannot deactivate stokvel with {active_members_count} active members. "
                    "Please handle member status first."
                )

        stokvel.is_active = is_active
        stokvel.save()
        return True

    @staticmethod
    def get_stokvel_summary(stokvel: Stokvel) -> Dict:
        """
        Returns comprehensive stokvel summary information
        """
        members = stokvel.members.all()

        return {
            'stokvel': stokvel,
            'total_members': members.count(),
            'active_members': members.filter(status='active').count(),
            'pending_members': members.filter(status='pending').count(),
            'probation_members': members.filter(status='probation').count(),
            'current_cycle': stokvel.cycles.filter(status='active').first(),
            'total_cycles': stokvel.cycles.count(),
            'contribution_rules_count': stokvel.contribution_rules.filter(is_active=True).count(),
            'penalty_rules_count': stokvel.penalty_rules.filter(is_active=True).count(),
            'has_constitution': hasattr(stokvel, 'constitution'),
            'bank_accounts_count': stokvel.bank_accounts.filter(is_active=True).count(),
        }


class ConstitutionService:
    """Business logic for stokvel constitution management"""

    @staticmethod
    def update_constitution(stokvel: Stokvel, updates: Dict) -> StokvelConstitution:
        """
        Updates stokvel constitution with validation
        """
        constitution = stokvel.constitution

        # Validate critical changes
        if 'minimum_members' in updates:
            current_active_members = stokvel.members.filter(status='active').count()
            if updates['minimum_members'] > current_active_members:
                raise ValidationError(
                    f"Cannot set minimum members to {updates['minimum_members']}. "
                    f"Current active members: {current_active_members}"
                )

        if 'maximum_members' in updates and updates['maximum_members']:
            current_total_members = stokvel.members.count()
            if updates['maximum_members'] < current_total_members:
                raise ValidationError(
                    f"Cannot set maximum members to {updates['maximum_members']}. "
                    f"Current total members: {current_total_members}"
                )

        # Apply updates
        for field, value in updates.items():
            if hasattr(constitution, field):
                setattr(constitution, field, value)

        constitution.save()
        return constitution

    @staticmethod
    def validate_constitution_compliance(stokvel: Stokvel) -> List[str]:
        """
        Checks if stokvel is compliant with its constitution
        Returns list of compliance issues
        """
        issues = []
        constitution = stokvel.constitution

        # Check member count compliance
        active_members = stokvel.members.filter(status='active').count()
        if active_members < constitution.minimum_members:
            issues.append(
                f"Below minimum members requirement: {active_members}/{constitution.minimum_members}"
            )

        if constitution.maximum_members and active_members > constitution.maximum_members:
            issues.append(
                f"Exceeds maximum members limit: {active_members}/{constitution.maximum_members}"
            )

        return issues


class ContributionRuleService:
    """Business logic for contribution rule management"""

    @staticmethod
    @transaction.atomic
    def create_contribution_rule(
            stokvel: Stokvel,
            name: str,
            contribution_type: str,
            amount: Decimal,
            frequency: str = 'monthly',
            effective_from: date = None,
            effective_until: date = None,
            is_mandatory: bool = True,
            description: str = ""
    ) -> ContributionRule:
        """
        Creates a new contribution rule with validation
        """
        if not effective_from:
            effective_from = timezone.now().date()

        # Validate amount
        if amount <= 0:
            raise ValidationError("Contribution amount must be greater than 0")

        # Check for overlapping rules of same type
        overlapping_rules = ContributionRule.objects.filter(
            stokvel=stokvel,
            contribution_type=contribution_type,
            is_active=True,
            effective_from__lte=effective_until or date.max,
            effective_until__gte=effective_from if effective_until else None
        )

        if overlapping_rules.exists():
            raise ValidationError(
                f"Overlapping {contribution_type} rule already exists for this period"
            )

        rule = ContributionRule.objects.create(
            stokvel=stokvel,
            name=name,
            contribution_type=contribution_type,
            amount=amount,
            frequency=frequency,
            effective_from=effective_from,
            effective_until=effective_until,
            is_mandatory=is_mandatory,
            description=description
        )

        return rule

    @staticmethod
    def get_active_contribution_rules(stokvel: Stokvel, as_of_date: date = None) -> List[ContributionRule]:
        """
        Returns active contribution rules for a specific date
        """
        if not as_of_date:
            as_of_date = timezone.now().date()

        return ContributionRule.objects.filter(
            stokvel=stokvel,
            is_active=True,
            effective_from__lte=as_of_date,
            effective_until__gte=as_of_date
        ) | ContributionRule.objects.filter(
            stokvel=stokvel,
            is_active=True,
            effective_from__lte=as_of_date,
            effective_until__isnull=True
        )

    @staticmethod
    def deactivate_rule(rule: ContributionRule, end_date: date = None) -> ContributionRule:
        """
        Deactivates a contribution rule
        """
        if not end_date:
            end_date = timezone.now().date()

        rule.effective_until = end_date
        rule.is_active = False
        rule.save()

        return rule


class PenaltyRuleService:
    """Business logic for penalty rule management"""

    @staticmethod
    @transaction.atomic
    def create_penalty_rule(
            stokvel: Stokvel,
            name: str,
            penalty_type: str,
            calculation_method: str,
            amount: Decimal,
            grace_period_days: int = 0,
            maximum_amount: Optional[Decimal] = None,
            effective_from: date = None,
            description: str = ""
    ) -> PenaltyRule:
        """
        Creates a new penalty rule with validation
        """
        if not effective_from:
            effective_from = timezone.now().date()

        # Validate amount based on calculation method
        if calculation_method == 'percentage' and amount > 100:
            raise ValidationError("Percentage penalty cannot exceed 100%")

        if amount < 0:
            raise ValidationError("Penalty amount cannot be negative")

        # Check for existing active rule of same type
        existing_rule = PenaltyRule.objects.filter(
            stokvel=stokvel,
            penalty_type=penalty_type,
            is_active=True,
            effective_from__lte=timezone.now().date(),
            effective_until__gte=timezone.now().date()
        ).first()

        if existing_rule:
            raise ValidationError(
                f"Active {penalty_type} rule already exists. "
                "Deactivate existing rule before creating new one."
            )

        rule = PenaltyRule.objects.create(
            stokvel=stokvel,
            name=name,
            penalty_type=penalty_type,
            calculation_method=calculation_method,
            amount=amount,
            grace_period_days=grace_period_days,
            maximum_amount=maximum_amount,
            effective_from=effective_from,
            description=description
        )

        return rule

    @staticmethod
    def calculate_penalty_amount(
            penalty_rule: PenaltyRule,
            base_amount: Decimal,
            days_late: int = 0
    ) -> Decimal:
        """
        Calculates penalty amount based on rule configuration
        """
        return penalty_rule.calculate_penalty(base_amount, days_late)

    @staticmethod
    def get_applicable_penalty_rules(
            stokvel: Stokvel,
            penalty_type: str,
            as_of_date: date = None
    ) -> Optional[PenaltyRule]:
        """
        Gets the applicable penalty rule for a specific type and date
        """
        if not as_of_date:
            as_of_date = timezone.now().date()

        return PenaltyRule.objects.filter(
            stokvel=stokvel,
            penalty_type=penalty_type,
            is_active=True,
            effective_from__lte=as_of_date,
            effective_until__gte=as_of_date
        ).first() or PenaltyRule.objects.filter(
            stokvel=stokvel,
            penalty_type=penalty_type,
            is_active=True,
            effective_from__lte=as_of_date,
            effective_until__isnull=True
        ).first()


class CycleService:
    """Business logic for stokvel cycle management"""

    @staticmethod
    @transaction.atomic
    def create_cycle(
            stokvel: Stokvel,
            name: str,
            start_date: date,
            end_date: date,
            description: str = ""
    ) -> StokvelCycle:
        """
        Creates a new stokvel cycle with validation
        """
        # Validate dates
        if start_date >= end_date:
            raise ValidationError("Start date must be before end date")

        if start_date < timezone.now().date():
            raise ValidationError("Start date cannot be in the past")

        # Check for overlapping cycles
        overlapping = StokvelCycle.objects.filter(
            stokvel=stokvel,
            start_date__lt=end_date,
            end_date__gt=start_date
        )

        if overlapping.exists():
            raise ValidationError("Cycle dates overlap with existing cycle")

        # Calculate expected contributions
        active_rules = ContributionRuleService.get_active_contribution_rules(
            stokvel, start_date
        )
        regular_rules = active_rules.filter(contribution_type='regular')

        expected_total = Decimal('0.00')
        if regular_rules.exists():
            # Simple calculation - can be enhanced based on frequency
            monthly_contribution = sum(rule.amount for rule in regular_rules)
            months_in_cycle = (end_date.year - start_date.year) * 12 + end_date.month - start_date.month
            active_members = stokvel.members.filter(status='active').count()
            expected_total = monthly_contribution * months_in_cycle * active_members

        cycle = StokvelCycle.objects.create(
            stokvel=stokvel,
            name=name,
            start_date=start_date,
            end_date=end_date,
            expected_total_contributions=expected_total,
            description=description
        )

        return cycle

    @staticmethod
    def activate_cycle(cycle: StokvelCycle) -> StokvelCycle:
        """
        Activates a cycle and deactivates others
        """
        # Deactivate other active cycles
        StokvelCycle.objects.filter(
            stokvel=cycle.stokvel,
            status='active'
        ).update(status='completed')

        cycle.status = 'active'
        cycle.save()

        return cycle

    @staticmethod
    def get_current_cycle(stokvel: Stokvel) -> Optional[StokvelCycle]:
        """
        Gets the current active cycle for a stokvel
        """
        today = timezone.now().date()
        return StokvelCycle.objects.filter(
            stokvel=stokvel,
            status='active',
            start_date__lte=today,
            end_date__gte=today
        ).first()


class BankAccountService:
    """Business logic for stokvel bank account management"""

    @staticmethod
    @transaction.atomic
    def add_bank_account(
            stokvel: Stokvel,
            bank_name: str,
            account_name: str,
            account_number: str,
            branch_code: str,
            account_type: str,
            is_primary: bool = False
    ) -> StokvelBankAccount:
        """
        Adds a new bank account for the stokvel
        """
        # Validate account number format (basic validation)
        if not account_number.strip():
            raise ValidationError("Account number is required")

        # Check for duplicate account
        if StokvelBankAccount.objects.filter(
                bank_name=bank_name,
                account_number=account_number
        ).exists():
            raise ValidationError("Bank account already exists")

        # If this is the first account, make it primary
        if not stokvel.bank_accounts.filter(is_active=True).exists():
            is_primary = True

        account = StokvelBankAccount.objects.create(
            stokvel=stokvel,
            bank_name=bank_name,
            account_name=account_name,
            account_number=account_number,
            branch_code=branch_code,
            account_type=account_type,
            is_primary=is_primary,
            is_active=True
        )

        return account

    @staticmethod
    def set_primary_account(account: StokvelBankAccount) -> StokvelBankAccount:
        """
        Sets an account as the primary account
        """
        # Deactivate other primary accounts
        StokvelBankAccount.objects.filter(
            stokvel=account.stokvel,
            is_primary=True
        ).exclude(pk=account.pk).update(is_primary=False)

        account.is_primary = True
        account.save()

        return account

    @staticmethod
    def deactivate_account(account: StokvelBankAccount) -> StokvelBankAccount:
        """
        Deactivates a bank account
        """
        if account.is_primary:
            # Check if there are other active accounts to promote
            other_accounts = StokvelBankAccount.objects.filter(
                stokvel=account.stokvel,
                is_active=True
            ).exclude(pk=account.pk)

            if other_accounts.exists():
                # Promote the first available account to primary
                other_accounts.first().is_primary = True
                other_accounts.first().save()

        account.is_active = False
        account.is_primary = False
        account.save()

        return account


class StokvelValidationService:
    """Validation services for stokvel operations"""

    @staticmethod
    def validate_stokvel_setup(stokvel: Stokvel) -> Tuple[bool, List[str]]:
        """
        Validates if stokvel is properly set up for operations
        Returns (is_valid, list_of_issues)
        """
        issues = []

        # Check constitution
        if not hasattr(stokvel, 'constitution'):
            issues.append("Stokvel constitution not configured")

        # Check contribution rules
        active_rules = ContributionRuleService.get_active_contribution_rules(stokvel)
        if not active_rules.exists():
            issues.append("No active contribution rules defined")

        # Check penalty rules
        penalty_rules = PenaltyRule.objects.filter(stokvel=stokvel, is_active=True)
        if not penalty_rules.exists():
            issues.append("No penalty rules defined")

        # Check bank accounts
        if not stokvel.bank_accounts.filter(is_active=True).exists():
            issues.append("No active bank accounts configured")

        # Check primary bank account
        if not stokvel.bank_accounts.filter(is_primary=True, is_active=True).exists():
            issues.append("No primary bank account set")

        # Check minimum members
        if hasattr(stokvel, 'constitution'):
            active_members = stokvel.members.filter(status='active').count()
            if active_members < stokvel.constitution.minimum_members:
                issues.append(
                    f"Below minimum members requirement: {active_members}/{stokvel.constitution.minimum_members}")

        return len(issues) == 0, issues

    @staticmethod
    def can_accept_new_members(stokvel: Stokvel) -> Tuple[bool, str]:
        """
        Checks if stokvel can accept new members
        """
        if not stokvel.is_accepting_members:
            return False, "Stokvel is not accepting new members"

        if not stokvel.is_active:
            return False, "Stokvel is not active"

        if hasattr(stokvel, 'constitution') and stokvel.constitution.maximum_members:
            current_members = stokvel.members.count()
            if current_members >= stokvel.constitution.maximum_members:
                return False, f"Maximum member limit reached ({current_members}/{stokvel.constitution.maximum_members})"

        return True, "Can accept new members"