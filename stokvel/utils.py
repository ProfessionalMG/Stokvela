from datetime import date, timedelta
from decimal import Decimal
from typing import List, Dict, Tuple, Optional
import calendar
from django.utils import timezone

from .models import Stokvel, ContributionRule, PenaltyRule


class DateUtils:
    """Utility functions for date calculations"""

    @staticmethod
    def get_month_end_date(year: int, month: int) -> date:
        """Returns the last day of a given month"""
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, last_day)

    @staticmethod
    def get_due_date_for_month(year: int, month: int, due_day: int) -> date:
        """
        Returns the due date for a given month, handling edge cases
        """
        if due_day == 31:
            # Last day of month
            return DateUtils.get_month_end_date(year, month)
        else:
            last_day = calendar.monthrange(year, month)[1]
            actual_day = min(due_day, last_day)
            return date(year, month, actual_day)

    @staticmethod
    def get_quarter_dates(year: int, quarter: int) -> Tuple[date, date]:
        """Returns start and end dates for a quarter"""
        if quarter == 1:
            return date(year, 1, 1), date(year, 3, 31)
        elif quarter == 2:
            return date(year, 4, 1), date(year, 6, 30)
        elif quarter == 3:
            return date(year, 7, 1), date(year, 9, 30)
        elif quarter == 4:
            return date(year, 10, 1), date(year, 12, 31)
        else:
            raise ValueError("Quarter must be 1, 2, 3, or 4")

    @staticmethod
    def get_business_days_between(start_date: date, end_date: date) -> int:
        """Returns number of business days between two dates"""
        days = 0
        current_date = start_date

        while current_date <= end_date:
            # Monday is 0, Sunday is 6
            if current_date.weekday() < 5:  # Monday to Friday
                days += 1
            current_date += timedelta(days=1)

        return days

    @staticmethod
    def is_weekend(target_date: date) -> bool:
        """Checks if a date falls on a weekend"""
        return target_date.weekday() >= 5  # Saturday or Sunday


class ContributionCalculator:
    """Utility functions for contribution calculations"""

    @staticmethod
    def calculate_monthly_periods(
            start_date: date,
            end_date: date,
            due_day: int = 31
    ) -> List[Dict]:
        """
        Generates monthly payment periods between two dates
        """
        periods = []
        current_date = start_date

        while current_date <= end_date:
            year = current_date.year
            month = current_date.month

            # Calculate period dates
            period_start = date(year, month, 1)
            period_end = DateUtils.get_month_end_date(year, month)
            due_date = DateUtils.get_due_date_for_month(year, month, due_day)

            # Only include if period overlaps with our date range
            if period_end >= start_date and period_start <= end_date:
                periods.append({
                    'year': year,
                    'month': month,
                    'period_start': max(period_start, start_date),
                    'period_end': min(period_end, end_date),
                    'due_date': due_date,
                    'name': f"{calendar.month_name[month]} {year}"
                })

            # Move to next month
            if month == 12:
                current_date = date(year + 1, 1, 1)
            else:
                current_date = date(year, month + 1, 1)

        return periods

    @staticmethod
    def calculate_quarterly_periods(
            start_date: date,
            end_date: date
    ) -> List[Dict]:
        """
        Generates quarterly payment periods between two dates
        """
        periods = []
        current_year = start_date.year
        end_year = end_date.year

        while current_year <= end_year:
            for quarter in range(1, 5):
                quarter_start, quarter_end = DateUtils.get_quarter_dates(current_year, quarter)

                # Only include if quarter overlaps with our date range
                if quarter_end >= start_date and quarter_start <= end_date:
                    periods.append({
                        'year': current_year,
                        'quarter': quarter,
                        'period_start': max(quarter_start, start_date),
                        'period_end': min(quarter_end, end_date),
                        'due_date': quarter_end,
                        'name': f"Q{quarter} {current_year}"
                    })

            current_year += 1

        return periods

    @staticmethod
    def calculate_expected_contribution(
            stokvel: Stokvel,
            period_start: date,
            period_end: date,
            contribution_type: str = 'regular'
    ) -> Decimal:
        """
        Calculates expected contribution amount for a period
        """
        total = Decimal('0.00')

        # Get active contribution rules for the period
        rules = ContributionRule.objects.filter(
            stokvel=stokvel,
            contribution_type=contribution_type,
            is_active=True,
            effective_from__lte=period_end
        ).filter(
            models.Q(effective_until__gte=period_start) |
            models.Q(effective_until__isnull=True)
        )

        for rule in rules:
            total += rule.amount

        return total


class PenaltyCalculator:
    """Utility functions for penalty calculations"""

    @staticmethod
    def calculate_late_payment_penalty(
            stokvel: Stokvel,
            contribution_amount: Decimal,
            payment_date: date,
            due_date: date
    ) -> Tuple[Decimal, Optional[PenaltyRule]]:
        """
        Calculates late payment penalty amount
        Returns (penalty_amount, penalty_rule_used)
        """
        if payment_date <= due_date:
            return Decimal('0.00'), None

        days_late = (payment_date - due_date).days

        # Get applicable penalty rule
        penalty_rule = PenaltyRule.objects.filter(
            stokvel=stokvel,
            penalty_type='late_payment',
            is_active=True,
            effective_from__lte=payment_date
        ).filter(
            models.Q(effective_until__gte=payment_date) |
            models.Q(effective_until__isnull=True)
        ).first()

        if not penalty_rule:
            return Decimal('0.00'), None

        penalty_amount = penalty_rule.calculate_penalty(contribution_amount, days_late)
        return penalty_amount, penalty_rule

    @staticmethod
    def calculate_insufficient_payment_penalty(
            stokvel: Stokvel,
            paid_amount: Decimal,
            expected_amount: Decimal,
            payment_date: date
    ) -> Tuple[Decimal, Optional[PenaltyRule]]:
        """
        Calculates penalty for insufficient payment
        """
        if paid_amount >= expected_amount:
            return Decimal('0.00'), None

        shortage = expected_amount - paid_amount

        # Get applicable penalty rule
        penalty_rule = PenaltyRule.objects.filter(
            stokvel=stokvel,
            penalty_type='insufficient_payment',
            is_active=True,
            effective_from__lte=payment_date
        ).filter(
            models.Q(effective_until__gte=payment_date) |
            models.Q(effective_until__isnull=True)
        ).first()

        if not penalty_rule:
            return Decimal('0.00'), None

        penalty_amount = penalty_rule.calculate_penalty(shortage, 0)
        return penalty_amount, penalty_rule


class StokvelReportUtils:
    """Utility functions for generating stokvel reports and statistics"""

    @staticmethod
    def calculate_member_statistics(stokvel: Stokvel) -> Dict:
        """
        Calculates comprehensive member statistics
        """
        members = stokvel.members.all()

        stats = {
            'total_members': members.count(),
            'active_members': members.filter(status='active').count(),
            'pending_members': members.filter(status='pending').count(),
            'probation_members': members.filter(status='probation').count(),
            'suspended_members': members.filter(status='suspended').count(),
            'inactive_members': members.filter(status='inactive').count(),
            'exited_members': members.filter(status='exited').count(),
        }

        # Calculate percentages
        if stats['total_members'] > 0:
            for key, value in stats.items():
                if key != 'total_members':
                    percentage_key = f"{key}_percentage"
                    stats[percentage_key] = round((value / stats['total_members']) * 100, 2)

        return stats

    @staticmethod
    def calculate_contribution_statistics(
            stokvel: Stokvel,
            start_date: date = None,
            end_date: date = None
    ) -> Dict:
        """
        Calculates contribution statistics for a period
        """
        from finances.models import PaymentPeriod, Contribution

        if not start_date:
            start_date = timezone.now().date().replace(day=1)  # First day of current month
        if not end_date:
            end_date = timezone.now().date()

        # Get payment periods in range
        periods = PaymentPeriod.objects.filter(
            stokvel=stokvel,
            due_date__gte=start_date,
            due_date__lte=end_date
        )

        total_expected = sum(period.total_expected_amount for period in periods)
        total_received = sum(period.total_received_amount for period in periods)

        stats = {
            'total_expected': total_expected,
            'total_received': total_received,
            'total_outstanding': total_expected - total_received,
            'collection_rate': round((total_received / total_expected * 100), 2) if total_expected > 0 else 0,
            'periods_count': periods.count(),
        }

        return stats

    @staticmethod
    def get_payment_compliance_report(stokvel: Stokvel, year: int = None) -> Dict:
        """
        Generates payment compliance report for members
        """
        from finances.models import PaymentPeriod, Contribution

        if not year:
            year = timezone.now().year

        periods = PaymentPeriod.objects.filter(
            stokvel=stokvel,
            year=year
        )

        members = stokvel.members.filter(status='active')
        compliance_data = []

        for member in members:
            member_data = {
                'member': member,
                'total_periods': periods.count(),
                'paid_periods': 0,
                'late_payments': 0,
                'total_contributed': Decimal('0.00'),
                'total_penalties': Decimal('0.00'),
                'compliance_rate': 0,
            }

            for period in periods:
                contribution = Contribution.objects.filter(
                    member=member,
                    payment_period=period,
                    verification_status='verified'
                ).first()

                if contribution:
                    member_data['paid_periods'] += 1
                    member_data['total_contributed'] += contribution.amount

                    if contribution.is_late_payment:
                        member_data['late_payments'] += 1

            # Calculate compliance rate
            if member_data['total_periods'] > 0:
                member_data['compliance_rate'] = round(
                    (member_data['paid_periods'] / member_data['total_periods']) * 100, 2
                )

            compliance_data.append(member_data)

        return {
            'year': year,
            'stokvel': stokvel,
            'members_data': compliance_data,
            'summary': {
                'total_members': len(compliance_data),
                'avg_compliance_rate': round(
                    sum(m['compliance_rate'] for m in compliance_data) / len(compliance_data), 2
                ) if compliance_data else 0,
            }
        }


class ValidationUtils:
    """Utility functions for validation"""

    @staticmethod
    def validate_south_african_id(id_number: str) -> bool:
        """
        Validates South African ID number using Luhn algorithm
        """
        if not id_number or len(id_number) != 13:
            return False

        if not id_number.isdigit():
            return False

        # Check date validity (first 6 digits)
        try:
            year_digits = id_number[:2]
            year = int(year_digits)
            # Assume years 00-30 are 2000s, 31-99 are 1900s
            full_year = 2000 + year if year <= 30 else 1900 + year

            month = int(id_number[2:4])
            day = int(id_number[4:6])

            if month < 1 or month > 12:
                return False

            if day < 1 or day > 31:
                return False

            # Basic date validation
            date(full_year, month, day)
        except (ValueError, TypeError):
            return False

        # Luhn algorithm for checksum
        digits = [int(d) for d in id_number]
        checksum = 0

        for i in range(12):
            if i % 2 == 0:
                checksum += digits[i]
            else:
                doubled = digits[i] * 2
                checksum += doubled if doubled < 10 else doubled - 9

        check_digit = (10 - (checksum % 10)) % 10
        return check_digit == digits[12]

    @staticmethod
    def validate_bank_account_number(account_number: str, bank_name: str = None) -> bool:
        """
        Basic validation for South African bank account numbers
        """
        if not account_number:
            return False

        # Remove spaces and check if numeric
        clean_number = account_number.replace(' ', '')
        if not clean_number.isdigit():
            return False

        # Check length (most SA bank accounts are 9-11 digits)
        if len(clean_number) < 8 or len(clean_number) > 12:
            return False

        return True

    @staticmethod
    def validate_contribution_amount(amount: Decimal, min_amount: Decimal = None) -> Tuple[bool, str]:
        """
        Validates contribution amount
        """
        if amount <= 0:
            return False, "Amount must be greater than zero"

        if min_amount and amount < min_amount:
            return False, f"Amount must be at least R{min_amount}"

        # Check if amount is reasonable (not too large)
        if amount > Decimal('1000000'):  # 1 million
            return False, "Amount seems unreasonably large"

        return True, "Valid amount"