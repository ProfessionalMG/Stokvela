from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from datetime import date, timedelta
from typing import Optional, Dict, List, Tuple
import uuid

from .models import Member, MemberBankAccount, MembershipApplication, MemberActivity
from stokvel.models import Stokvel

User = get_user_model()


class UserService:
    """Core business logic for user management"""

    @staticmethod
    @transaction.atomic
    def create_user_account(
            username: str,
            email: str,
            password: str,
            first_name: str,
            last_name: str,
            phone_number: str = "",
            **additional_fields
    ) -> User:
        """
        Creates a new user account with profile information
        """
        # Validate required fields
        if not username or not email or not password:
            raise ValidationError("Username, email, and password are required")

        # Check if username or email already exists
        if User.objects.filter(username=username).exists():
            raise ValidationError(f"Username '{username}' already exists")

        if User.objects.filter(email=email).exists():
            raise ValidationError(f"Email '{email}' already registered")

        # Create user
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
            **additional_fields
        )

        return user

    @staticmethod
    def update_user_profile(user: User, updates: Dict) -> User:
        """
        Updates user profile information with validation
        """
        # Fields that can be updated
        allowed_fields = [
            'first_name', 'last_name', 'email', 'phone_number',
            'date_of_birth', 'id_number', 'address_line_1', 'address_line_2',
            'city', 'province', 'postal_code', 'country', 'preferred_language',
            'email_notifications', 'sms_notifications', 'whatsapp_notifications'
        ]

        # Validate email uniqueness if being updated
        if 'email' in updates and updates['email'] != user.email:
            if User.objects.filter(email=updates['email']).exists():
                raise ValidationError(f"Email '{updates['email']}' already registered")

        # Apply updates
        for field, value in updates.items():
            if field in allowed_fields and hasattr(user, field):
                setattr(user, field, value)

        user.save()
        return user

    @staticmethod
    def verify_user_email(user: User) -> User:
        """
        Marks user email as verified
        """
        user.email_verified = True
        user.save()
        return user

    @staticmethod
    def verify_user_phone(user: User) -> User:
        """
        Marks user phone as verified
        """
        user.phone_verified = True
        user.save()
        return user

    @staticmethod
    def get_user_verification_status(user: User) -> Dict:
        """
        Returns comprehensive verification status
        """
        return {
            'email_verified': user.email_verified,
            'phone_verified': user.phone_verified,
            'is_verified': user.is_verified,
            'verification_percentage': UserService.calculate_verification_percentage(user),
            'missing_verifications': UserService.get_missing_verifications(user)
        }

    @staticmethod
    def calculate_verification_percentage(user: User) -> int:
        """
        Calculates verification completion percentage
        """
        total_checks = 2  # email, phone
        completed = 0

        if user.email_verified:
            completed += 1
        if user.phone_verified:
            completed += 1

        return int((completed / total_checks) * 100)

    @staticmethod
    def get_missing_verifications(user: User) -> List[str]:
        """
        Returns list of missing verifications
        """
        missing = []

        if not user.email_verified:
            missing.append('email')
        if not user.phone_verified:
            missing.append('phone')

        return missing


class MembershipApplicationService:
    """Business logic for membership applications"""

    @staticmethod
    @transaction.atomic
    def submit_application(
            user: User,
            stokvel: Stokvel,
            motivation: str,
            referral_source: str = "",
            referred_by: Optional[Member] = None
    ) -> MembershipApplication:
        """
        Submits a membership application
        """
        # Check if user is already a member or has pending application
        existing_membership = Member.objects.filter(user=user, stokvel=stokvel).first()
        if existing_membership:
            raise ValidationError(f"You are already a member of {stokvel.name}")

        existing_application = MembershipApplication.objects.filter(
            user=user,
            stokvel=stokvel,
            status__in=['submitted', 'under_review']
        ).first()
        if existing_application:
            raise ValidationError(f"You already have a pending application for {stokvel.name}")

        # Check if stokvel is accepting members
        if not stokvel.is_accepting_members or not stokvel.is_active:
            raise ValidationError(f"{stokvel.name} is not currently accepting new members")

        # Check maximum members limit
        if hasattr(stokvel, 'constitution') and stokvel.constitution.maximum_members:
            current_members = stokvel.members.count()
            if current_members >= stokvel.constitution.maximum_members:
                raise ValidationError(f"{stokvel.name} has reached its maximum member limit")

        # Create application
        application = MembershipApplication.objects.create(
            user=user,
            stokvel=stokvel,
            motivation=motivation,
            referral_source=referral_source,
            referred_by=referred_by,
            status='submitted'
        )

        return application

    @staticmethod
    @transaction.atomic
    def approve_application(
            application: MembershipApplication,
            reviewed_by: User,
            notes: str = ""
    ) -> Member:
        """
        Approves a membership application and creates member record
        """
        if application.status != 'submitted':
            raise ValidationError("Only submitted applications can be approved")

        # Create member using the application's approve method
        member = application.approve(reviewed_by, notes)

        # Log activity
        MemberActivityService.log_activity(
            member=member,
            activity_type='status_changed',
            description=f"Membership application approved by {reviewed_by.get_full_name()}"
        )

        return member

    @staticmethod
    def reject_application(
            application: MembershipApplication,
            reviewed_by: User,
            notes: str = ""
    ) -> MembershipApplication:
        """
        Rejects a membership application
        """
        if application.status != 'submitted':
            raise ValidationError("Only submitted applications can be rejected")

        application.reject(reviewed_by, notes)
        return application

    @staticmethod
    def get_pending_applications(stokvel: Stokvel) -> List[MembershipApplication]:
        """
        Returns all pending applications for a stokvel
        """
        return MembershipApplication.objects.filter(
            stokvel=stokvel,
            status='submitted'
        ).order_by('submitted_date')


class MemberService:
    """Core business logic for member management"""

    @staticmethod
    def update_member_status(
            member: Member,
            new_status: str,
            reason: str = "",
            updated_by: Optional[User] = None
    ) -> Member:
        """
        Updates member status with validation and logging
        """
        old_status = member.status

        # Validate status transition
        valid_transitions = {
            'pending': ['probation', 'active', 'rejected'],
            'probation': ['active', 'suspended', 'inactive'],
            'active': ['suspended', 'inactive', 'exited'],
            'suspended': ['active', 'inactive', 'exited'],
            'inactive': ['active', 'exited'],
            'exited': [],  # Final state
        }

        if new_status not in valid_transitions.get(old_status, []):
            raise ValidationError(
                f"Invalid status transition from {old_status} to {new_status}"
            )

        # Handle special status changes
        if new_status == 'active' and old_status == 'probation':
            # Set probation end date
            member.probation_end_date = timezone.now().date()

        if new_status == 'exited':
            # Set exit date
            member.exit_date = timezone.now().date()

        # Update status
        member.status = new_status
        member.save()

        # Log activity
        description = f"Status changed from {old_status} to {new_status}"
        if reason:
            description += f". Reason: {reason}"
        if updated_by:
            description += f" by {updated_by.get_full_name()}"

        MemberActivityService.log_activity(
            member=member,
            activity_type='status_changed',
            description=description
        )

        return member

    @staticmethod
    def update_member_role(
            member: Member,
            new_role: str,
            updated_by: Optional[User] = None
    ) -> Member:
        """
        Updates member role with validation
        """
        old_role = member.role

        # Validate role
        valid_roles = [choice[0] for choice in Member.MEMBER_ROLE_CHOICES]
        if new_role not in valid_roles:
            raise ValidationError(f"Invalid role: {new_role}")

        # Check if changing to admin/leadership role
        leadership_roles = ['chairperson', 'treasurer', 'secretary', 'admin']
        if new_role in leadership_roles:
            # Ensure only active members can have leadership roles
            if member.status != 'active':
                raise ValidationError("Only active members can have leadership roles")

        # For certain roles, ensure only one person has that role
        unique_roles = ['chairperson', 'treasurer', 'secretary']
        if new_role in unique_roles:
            existing = Member.objects.filter(
                stokvel=member.stokvel,
                role=new_role,
                status='active'
            ).exclude(pk=member.pk)

            if existing.exists():
                raise ValidationError(
                    f"Another member already has the {new_role} role"
                )

        # Update role
        member.role = new_role
        member.save()

        # Log activity
        description = f"Role changed from {old_role} to {new_role}"
        if updated_by:
            description += f" by {updated_by.get_full_name()}"

        MemberActivityService.log_activity(
            member=member,
            activity_type='status_changed',
            description=description
        )

        return member

    @staticmethod
    def get_member_summary(member: Member) -> Dict:
        """
        Returns comprehensive member summary
        """
        return {
            'member': member,
            'days_since_joining': member.days_since_joining,
            'is_in_probation': member.is_in_probation,
            'is_active_member': member.is_active_member,
            'bank_accounts_count': member.bank_accounts.filter(is_verified=True).count(),
            'total_contributions': member.contributions.filter(verification_status='verified').count(),
            'total_penalties': member.penalties.filter(status__in=['applied', 'outstanding']).count(),
            'recent_activities': member.activities.order_by('-created_date')[:5],
        }

    @staticmethod
    def get_stokvel_members_summary(stokvel: Stokvel) -> Dict:
        """
        Returns comprehensive summary of all stokvel members
        """
        members = stokvel.members.all()

        summary = {
            'total_members': members.count(),
            'by_status': {},
            'by_role': {},
            'leadership_team': [],
            'probation_members': [],
            'recent_joiners': [],
        }

        # Count by status
        for status, _ in Member.MEMBER_STATUS_CHOICES:
            summary['by_status'][status] = members.filter(status=status).count()

        # Count by role
        for role, _ in Member.MEMBER_ROLE_CHOICES:
            summary['by_role'][role] = members.filter(role=role).count()

        # Leadership team
        leadership_roles = ['chairperson', 'treasurer', 'secretary', 'admin']
        summary['leadership_team'] = members.filter(
            role__in=leadership_roles,
            status='active'
        ).order_by('role')

        # Members in probation
        summary['probation_members'] = members.filter(
            status='probation'
        ).order_by('application_date')

        # Recent joiners (last 30 days)
        thirty_days_ago = timezone.now().date() - timedelta(days=30)
        summary['recent_joiners'] = members.filter(
            approval_date__gte=thirty_days_ago
        ).order_by('-approval_date')

        return summary

    @staticmethod
    def check_probation_completion(member: Member) -> bool:
        """
        Checks if member has completed probation period
        """
        if member.status != 'probation':
            return False

        if not member.approval_date:
            return False

        constitution = member.stokvel.constitution
        probation_months = constitution.probation_period_months

        probation_end = member.approval_date + timedelta(days=probation_months * 30)
        return timezone.now().date() >= probation_end

    @staticmethod
    def promote_from_probation(member: Member, promoted_by: Optional[User] = None) -> Member:
        """
        Promotes member from probation to active status
        """
        if member.status != 'probation':
            raise ValidationError("Member is not in probation")

        if not MemberService.check_probation_completion(member):
            raise ValidationError("Probation period not yet completed")

        return MemberService.update_member_status(
            member=member,
            new_status='active',
            reason="Probation period completed",
            updated_by=promoted_by
        )


class MemberBankAccountService:
    """Business logic for member bank account management"""

    @staticmethod
    @transaction.atomic
    def add_bank_account(
            member: Member,
            bank_name: str,
            account_holder_name: str,
            account_number: str,
            account_type: str,
            branch_code: str,
            is_primary: bool = False
    ) -> MemberBankAccount:
        """
        Adds a new bank account for a member
        """
        # Validate account number format
        from stokvel.utils import ValidationUtils

        if not ValidationUtils.validate_bank_account_number(account_number, bank_name):
            raise ValidationError("Invalid account number format")

        # Check for duplicate account
        if MemberBankAccount.objects.filter(
                member=member,
                account_number=account_number
        ).exists():
            raise ValidationError("This account number already exists for this member")

        # If this is the first account, make it primary
        if not member.bank_accounts.exists():
            is_primary = True

        account = MemberBankAccount.objects.create(
            member=member,
            bank_name=bank_name,
            account_holder_name=account_holder_name,
            account_number=account_number,
            account_type=account_type,
            branch_code=branch_code,
            is_primary=is_primary
        )

        # Log activity
        MemberActivityService.log_activity(
            member=member,
            activity_type='profile_updated',
            description=f"Added bank account: {bank_name} {account.masked_account_number}"
        )

        return account

    @staticmethod
    def verify_bank_account(
            account: MemberBankAccount,
            verified_by: Optional[User] = None
    ) -> MemberBankAccount:
        """
        Marks a bank account as verified
        """
        account.is_verified = True
        account.save()

        # Log activity
        description = f"Bank account verified: {account.bank_name} {account.masked_account_number}"
        if verified_by:
            description += f" by {verified_by.get_full_name()}"

        MemberActivityService.log_activity(
            member=account.member,
            activity_type='profile_updated',
            description=description
        )

        return account

    @staticmethod
    def set_primary_account(account: MemberBankAccount) -> MemberBankAccount:
        """
        Sets an account as the primary account for payouts
        """
        # Deactivate other primary accounts
        MemberBankAccount.objects.filter(
            member=account.member,
            is_primary=True
        ).exclude(pk=account.pk).update(is_primary=False)

        account.is_primary = True
        account.save()

        # Log activity
        MemberActivityService.log_activity(
            member=account.member,
            activity_type='profile_updated',
            description=f"Set primary account: {account.bank_name} {account.masked_account_number}"
        )

        return account


class MemberActivityService:
    """Business logic for member activity tracking"""

    @staticmethod
    def log_activity(
            member: Member,
            activity_type: str,
            description: str,
            related_object_type: str = "",
            related_object_id: str = ""
    ) -> MemberActivity:
        """
        Logs a member activity
        """
        activity = MemberActivity.objects.create(
            member=member,
            activity_type=activity_type,
            description=description,
            related_object_type=related_object_type,
            related_object_id=related_object_id
        )

        return activity

    @staticmethod
    def get_member_activity_summary(
            member: Member,
            days: int = 30
    ) -> Dict:
        """
        Returns activity summary for a member
        """
        start_date = timezone.now() - timedelta(days=days)
        activities = member.activities.filter(created_date__gte=start_date)

        summary = {
            'total_activities': activities.count(),
            'by_type': {},
            'recent_activities': activities.order_by('-created_date')[:10],
        }

        # Count by activity type
        for activity_type, _ in MemberActivity.ACTIVITY_TYPES:
            summary['by_type'][activity_type] = activities.filter(
                activity_type=activity_type
            ).count()

        return summary

    @staticmethod
    def get_stokvel_activity_summary(
            stokvel: Stokvel,
            days: int = 30
    ) -> Dict:
        """
        Returns activity summary for all stokvel members
        """
        start_date = timezone.now() - timedelta(days=days)

        # Get activities for all stokvel members
        member_ids = stokvel.members.values_list('id', flat=True)
        activities = MemberActivity.objects.filter(
            member_id__in=member_ids,
            created_date__gte=start_date
        )

        summary = {
            'total_activities': activities.count(),
            'active_members_count': activities.values('member').distinct().count(),
            'by_type': {},
            'most_active_members': [],
            'recent_activities': activities.order_by('-created_date')[:20],
        }

        # Count by activity type
        for activity_type, _ in MemberActivity.ACTIVITY_TYPES:
            summary['by_type'][activity_type] = activities.filter(
                activity_type=activity_type
            ).count()

        # Most active members
        from django.db.models import Count
        most_active = activities.values('member__user__first_name', 'member__user__last_name', 'member') \
                          .annotate(activity_count=Count('id')) \
                          .order_by('-activity_count')[:5]

        summary['most_active_members'] = most_active

        return summary


class MemberValidationService:
    """Validation services for member operations"""

    @staticmethod
    def validate_member_profile_completion(member: Member) -> Tuple[bool, List[str]]:
        """
        Validates if member profile is complete
        Returns (is_complete, list_of_missing_fields)
        """
        missing = []

        user = member.user

        # Required user fields
        if not user.first_name:
            missing.append("First name")
        if not user.last_name:
            missing.append("Last name")
        if not user.email:
            missing.append("Email address")
        if not user.phone_number:
            missing.append("Phone number")

        # Verification status
        if not user.email_verified:
            missing.append("Email verification")
        if not user.phone_verified:
            missing.append("Phone verification")

        # Bank account for payouts
        if not member.bank_accounts.filter(is_verified=True).exists():
            missing.append("Verified bank account")

        # ID number for South African members
        if user.country == 'South Africa' and not user.id_number:
            missing.append("ID number")

        return len(missing) == 0, missing

    @staticmethod
    def can_receive_payout(member: Member) -> Tuple[bool, str]:
        """
        Checks if member is eligible to receive payouts
        """
        if member.status != 'active':
            return False, f"Member status is {member.status}, must be active"

        # Check profile completion
        is_complete, missing = MemberValidationService.validate_member_profile_completion(member)
        if not is_complete:
            return False, f"Profile incomplete: {', '.join(missing)}"

        # Check for verified bank account
        primary_account = member.bank_accounts.filter(
            is_primary=True,
            is_verified=True
        ).first()

        if not primary_account:
            return False, "No verified primary bank account"

        return True, "Eligible for payout"

    @staticmethod
    def validate_leadership_eligibility(member: Member, role: str) -> Tuple[bool, str]:
        """
        Validates if member is eligible for leadership role
        """
        leadership_roles = ['chairperson', 'treasurer', 'secretary', 'admin']

        if role not in leadership_roles:
            return True, "Role validation not required"

        if member.status != 'active':
            return False, "Only active members can hold leadership roles"

        # Check minimum membership duration (e.g., 6 months)
        if member.approval_date:
            six_months_ago = timezone.now().date() - timedelta(days=180)
            if member.approval_date > six_months_ago:
                return False, "Must be a member for at least 6 months"

        # Check profile completion
        is_complete, missing = MemberValidationService.validate_member_profile_completion(member)
        if not is_complete:
            return False, f"Profile must be complete: {', '.join(missing)}"

        return True, "Eligible for leadership role"