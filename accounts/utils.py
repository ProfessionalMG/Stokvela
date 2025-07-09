from datetime import date, timedelta
from decimal import Decimal
from typing import List, Dict, Tuple, Optional
import re
import random
import string
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string

from .models import User, Member, MembershipApplication, MemberActivity


class ProfileUtils:
    """Utility functions for user profile management"""

    @staticmethod
    def calculate_profile_completion(user: User) -> Dict:
        """
        Calculates profile completion percentage and missing fields
        """
        required_fields = {
            'first_name': 'First Name',
            'last_name': 'Last Name',
            'email': 'Email Address',
            'phone_number': 'Phone Number',
            'date_of_birth': 'Date of Birth',
            'address_line_1': 'Address',
            'city': 'City',
            'province': 'Province',
            'postal_code': 'Postal Code',
        }

        verification_fields = {
            'email_verified': 'Email Verification',
            'phone_verified': 'Phone Verification',
        }

        completed_fields = 0
        total_fields = len(required_fields) + len(verification_fields)
        missing_fields = []

        # Check required fields
        for field, display_name in required_fields.items():
            value = getattr(user, field, None)
            if value and str(value).strip():
                completed_fields += 1
            else:
                missing_fields.append(display_name)

        # Check verification fields
        for field, display_name in verification_fields.items():
            if getattr(user, field, False):
                completed_fields += 1
            else:
                missing_fields.append(display_name)

        completion_percentage = int((completed_fields / total_fields) * 100)

        return {
            'completion_percentage': completion_percentage,
            'completed_fields': completed_fields,
            'total_fields': total_fields,
            'missing_fields': missing_fields,
            'is_complete': completion_percentage == 100
        }

    @staticmethod
    def generate_username(first_name: str, last_name: str, email: str = None) -> str:
        """
        Generates a unique username based on name or email
        """
        base_username = ""

        if first_name and last_name:
            # Use first name + last name
            base_username = f"{first_name.lower()}.{last_name.lower()}"
        elif email:
            # Use email prefix
            base_username = email.split('@')[0].lower()
        else:
            # Fallback to random string
            base_username = f"user{random.randint(1000, 9999)}"

        # Clean username (remove special characters except dots and underscores)
        base_username = re.sub(r'[^a-z0-9._]', '', base_username)

        # Ensure uniqueness
        username = base_username
        counter = 1

        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        return username

    @staticmethod
    def validate_south_african_phone(phone_number: str) -> Tuple[bool, str]:
        """
        Validates and formats South African phone numbers
        """
        if not phone_number:
            return False, "Phone number is required"

        # Remove all non-digit characters
        cleaned = re.sub(r'\D', '', phone_number)

        # South African phone patterns
        patterns = [
            r'^27[0-9]{9}$',  # +27 format (without +)
            r'^0[0-9]{9}$',  # 0 format (local)
            r'^[0-9]{9}$',  # 9 digits (without leading 0)
        ]

        # Try to match patterns
        for pattern in patterns:
            if re.match(pattern, cleaned):
                # Format to international format
                if cleaned.startswith('27'):
                    formatted = f"+{cleaned}"
                elif cleaned.startswith('0'):
                    formatted = f"+27{cleaned[1:]}"
                else:
                    formatted = f"+27{cleaned}"

                return True, formatted

        return False, "Invalid South African phone number format"

    @staticmethod
    def generate_verification_code(length: int = 6) -> str:
        """
        Generates a random verification code
        """
        return ''.join(random.choices(string.digits, k=length))


class MemberUtils:
    """Utility functions for member management"""

    @staticmethod
    def calculate_member_statistics(stokvel) -> Dict:
        """
        Calculates comprehensive member statistics for a stokvel
        """
        members = stokvel.members.all()

        # Basic counts
        stats = {
            'total_members': members.count(),
            'active_members': members.filter(status='active').count(),
            'pending_members': members.filter(status='pending').count(),
            'probation_members': members.filter(status='probation').count(),
            'suspended_members': members.filter(status='suspended').count(),
            'inactive_members': members.filter(status='inactive').count(),
            'exited_members': members.filter(status='exited').count(),
        }

        # Leadership
        stats['leadership_count'] = members.filter(
            role__in=['chairperson', 'treasurer', 'secretary', 'admin'],
            status='active'
        ).count()

        # Recent activity
        thirty_days_ago = timezone.now().date() - timedelta(days=30)
        stats['recent_joiners'] = members.filter(
            approval_date__gte=thirty_days_ago
        ).count()

        # Profile completion
        complete_profiles = 0
        for member in members:
            profile_info = ProfileUtils.calculate_profile_completion(member.user)
            if profile_info['is_complete']:
                complete_profiles += 1

        stats['complete_profiles'] = complete_profiles
        stats['profile_completion_rate'] = (
            (complete_profiles / stats['total_members'] * 100)
            if stats['total_members'] > 0 else 0
        )

        # Verification status
        stats['email_verified'] = members.filter(
            user__email_verified=True
        ).count()
        stats['phone_verified'] = members.filter(
            user__phone_verified=True
        ).count()

        # Bank accounts
        stats['members_with_bank_accounts'] = members.filter(
            bank_accounts__isnull=False
        ).distinct().count()
        stats['verified_bank_accounts'] = members.filter(
            bank_accounts__is_verified=True
        ).distinct().count()

        return stats

    @staticmethod
    def get_member_engagement_score(member: Member, days: int = 30) -> Dict:
        """
        Calculates member engagement score based on recent activity
        """
        start_date = timezone.now() - timedelta(days=days)
        activities = member.activities.filter(created_date__gte=start_date)

        # Scoring weights
        activity_weights = {
            'login': 1,
            'payment_made': 3,
            'meeting_attended': 2,
            'profile_updated': 1,
            'status_changed': 0,  # System activities don't count
            'penalty_applied': -1,
            'penalty_waived': 0,
        }

        # Calculate score
        total_score = 0
        activity_breakdown = {}

        for activity in activities:
            weight = activity_weights.get(activity.activity_type, 0)
            total_score += weight

            activity_type = activity.activity_type
            if activity_type not in activity_breakdown:
                activity_breakdown[activity_type] = 0
            activity_breakdown[activity_type] += 1

        # Normalize score (0-100)
        max_possible_score = days * 2  # Rough estimate
        normalized_score = min(100, max(0, (total_score / max_possible_score) * 100))

        # Determine engagement level
        if normalized_score >= 80:
            engagement_level = 'Very High'
        elif normalized_score >= 60:
            engagement_level = 'High'
        elif normalized_score >= 40:
            engagement_level = 'Medium'
        elif normalized_score >= 20:
            engagement_level = 'Low'
        else:
            engagement_level = 'Very Low'

        return {
            'score': round(normalized_score, 1),
            'level': engagement_level,
            'total_activities': activities.count(),
            'activity_breakdown': activity_breakdown,
            'period_days': days
        }

    @staticmethod
    def check_probation_eligibility(member: Member) -> Dict:
        """
        Checks if member is eligible to complete probation
        """
        if member.status != 'probation':
            return {
                'eligible': False,
                'reason': f"Member status is {member.status}, not in probation"
            }

        if not member.approval_date:
            return {
                'eligible': False,
                'reason': "No approval date recorded"
            }

        constitution = member.stokvel.constitution
        probation_months = constitution.probation_period_months

        # Calculate probation end date
        probation_end = member.approval_date + timedelta(days=probation_months * 30)
        days_remaining = (probation_end - timezone.now().date()).days

        if days_remaining > 0:
            return {
                'eligible': False,
                'reason': f"Probation period ends in {days_remaining} days",
                'probation_end_date': probation_end,
                'days_remaining': days_remaining
            }

        # Check if member has any outstanding issues
        issues = []

        # Profile completion
        profile_info = ProfileUtils.calculate_profile_completion(member.user)
        if not profile_info['is_complete']:
            issues.append("Profile not complete")

        # Bank account verification
        if not member.bank_accounts.filter(is_verified=True).exists():
            issues.append("No verified bank account")

        # Outstanding penalties
        outstanding_penalties = member.penalties.filter(
            status__in=['applied', 'outstanding']
        ).count()
        if outstanding_penalties > 0:
            issues.append(f"{outstanding_penalties} outstanding penalties")

        return {
            'eligible': len(issues) == 0,
            'reason': "Eligible for promotion" if len(issues) == 0 else "Issues need resolution",
            'issues': issues,
            'probation_end_date': probation_end,
            'days_since_eligible': abs(days_remaining) if days_remaining <= 0 else 0
        }

    @staticmethod
    def generate_member_report(member: Member) -> Dict:
        """
        Generates comprehensive member report
        """
        profile_info = ProfileUtils.calculate_profile_completion(member.user)
        engagement_info = MemberUtils.get_member_engagement_score(member)

        # Financial summary (would be enhanced with finances app)
        financial_summary = {
            'total_contributions': member.contributions.filter(
                verification_status='verified'
            ).count() if hasattr(member, 'contributions') else 0,
            'total_penalties': member.penalties.filter(
                status__in=['applied', 'outstanding']
            ).count() if hasattr(member, 'penalties') else 0,
        }

        # Recent activities
        recent_activities = member.activities.order_by('-created_date')[:10]

        return {
            'member': member,
            'profile_completion': profile_info,
            'engagement': engagement_info,
            'financial_summary': financial_summary,
            'recent_activities': recent_activities,
            'membership_duration': member.days_since_joining,
            'bank_accounts': member.bank_accounts.all(),
            'verified_bank_accounts': member.bank_accounts.filter(is_verified=True),
        }


class ApplicationUtils:
    """Utility functions for membership applications"""

    @staticmethod
    def calculate_application_statistics(stokvel) -> Dict:
        """
        Calculates application statistics for a stokvel
        """
        applications = stokvel.applications.all()

        stats = {
            'total_applications': applications.count(),
            'submitted': applications.filter(status='submitted').count(),
            'under_review': applications.filter(status='under_review').count(),
            'approved': applications.filter(status='approved').count(),
            'rejected': applications.filter(status='rejected').count(),
            'withdrawn': applications.filter(status='withdrawn').count(),
        }

        # Approval rate
        total_decided = stats['approved'] + stats['rejected']
        stats['approval_rate'] = (
            (stats['approved'] / total_decided * 100)
            if total_decided > 0 else 0
        )

        # Average processing time
        processed_apps = applications.filter(
            decision_date__isnull=False
        )

        if processed_apps.exists():
            total_days = 0
            for app in processed_apps:
                days_diff = (app.decision_date.date() - app.submitted_date.date()).days
                total_days += days_diff

            stats['avg_processing_days'] = total_days / processed_apps.count()
        else:
            stats['avg_processing_days'] = 0

        # Recent applications (last 30 days)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        stats['recent_applications'] = applications.filter(
            submitted_date__gte=thirty_days_ago
        ).count()

        return stats

    @staticmethod
    def get_pending_applications_summary(stokvel) -> List[Dict]:
        """
        Gets summary of pending applications with priority scoring
        """
        pending_apps = stokvel.applications.filter(
            status__in=['submitted', 'under_review']
        ).order_by('submitted_date')

        summary = []

        for app in pending_apps:
            # Calculate waiting time
            waiting_days = (timezone.now().date() - app.submitted_date.date()).days

            # Priority score based on waiting time and other factors
            priority_score = waiting_days

            # Boost priority if referred by existing member
            if app.referred_by:
                priority_score += 5

            # Boost priority for users with complete profiles
            profile_info = ProfileUtils.calculate_profile_completion(app.user)
            if profile_info['completion_percentage'] > 80:
                priority_score += 3

            # Determine priority level
            if priority_score >= 10:
                priority_level = 'High'
            elif priority_score >= 5:
                priority_level = 'Medium'
            else:
                priority_level = 'Low'

            summary.append({
                'application': app,
                'waiting_days': waiting_days,
                'priority_score': priority_score,
                'priority_level': priority_level,
                'profile_completion': profile_info['completion_percentage'],
                'has_referral': bool(app.referred_by),
            })

        # Sort by priority score (highest first)
        summary.sort(key=lambda x: x['priority_score'], reverse=True)

        return summary


class NotificationUtils:
    """Utility functions for sending notifications to users and members"""

    @staticmethod
    def send_welcome_email(user: User) -> bool:
        """
        Sends welcome email to new user
        """
        try:
            subject = "Welcome to Stokvela!"

            context = {
                'user': user,
                'verification_url': f"{settings.BASE_URL}/accounts/verify-email/{user.pk}/"
            }

            html_message = render_to_string('emails/welcome.html', context)
            text_message = render_to_string('emails/welcome.txt', context)

            send_mail(
                subject=subject,
                message=text_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_message,
                fail_silently=False
            )

            return True

        except Exception as e:
            print(f"Failed to send welcome email: {str(e)}")
            return False

    @staticmethod
    def send_application_confirmation(application: MembershipApplication) -> bool:
        """
        Sends application confirmation email
        """
        try:
            subject = f"Application Received - {application.stokvel.name}"

            context = {
                'application': application,
                'user': application.user,
                'stokvel': application.stokvel,
            }

            html_message = render_to_string('emails/application_confirmation.html', context)
            text_message = render_to_string('emails/application_confirmation.txt', context)

            send_mail(
                subject=subject,
                message=text_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[application.user.email],
                html_message=html_message,
                fail_silently=False
            )

            return True

        except Exception as e:
            print(f"Failed to send application confirmation: {str(e)}")
            return False

    @staticmethod
    def send_application_decision(application: MembershipApplication) -> bool:
        """
        Sends application decision email (approved/rejected)
        """
        try:
            if application.status == 'approved':
                subject = f"Application Approved - Welcome to {application.stokvel.name}!"
                template_prefix = 'application_approved'
            else:
                subject = f"Application Update - {application.stokvel.name}"
                template_prefix = 'application_rejected'

            context = {
                'application': application,
                'user': application.user,
                'stokvel': application.stokvel,
            }

            html_message = render_to_string(f'emails/{template_prefix}.html', context)
            text_message = render_to_string(f'emails/{template_prefix}.txt', context)

            send_mail(
                subject=subject,
                message=text_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[application.user.email],
                html_message=html_message,
                fail_silently=False
            )

            return True

        except Exception as e:
            print(f"Failed to send application decision email: {str(e)}")
            return False

    @staticmethod
    def send_sms_notification(phone_number: str, message: str) -> bool:
        """
        Sends SMS notification (placeholder - integrate with SMS provider)
        """
        # This would integrate with SMS providers like Twilio, Clickatell, etc.
        # For now, just log the message
        print(f"SMS to {phone_number}: {message}")
        return True

    @staticmethod
    def send_verification_code(user: User, code: str, method: str = 'email') -> bool:
        """
        Sends verification code via email or SMS
        """
        if method == 'email':
            try:
                subject = "Your Verification Code"
                message = f"Your verification code is: {code}"

                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False
                )
                return True
            except:
                return False

        elif method == 'sms':
            message = f"Your Stokvela verification code is: {code}"
            return NotificationUtils.send_sms_notification(user.phone_number, message)

        return False


class ReportUtils:
    """Utility functions for generating reports"""

    @staticmethod
    def generate_membership_report(stokvel, start_date: date = None, end_date: date = None) -> Dict:
        """
        Generates comprehensive membership report
        """
        if not start_date:
            start_date = timezone.now().date().replace(day=1)  # First day of current month
        if not end_date:
            end_date = timezone.now().date()

        # Member statistics
        member_stats = MemberUtils.calculate_member_statistics(stokvel)

        # Application statistics
        app_stats = ApplicationUtils.calculate_application_statistics(stokvel)

        # New members in period
        new_members = stokvel.members.filter(
            approval_date__gte=start_date,
            approval_date__lte=end_date
        )

        # Member status changes in period
        status_changes = MemberActivity.objects.filter(
            member__stokvel=stokvel,
            activity_type='status_changed',
            created_date__date__gte=start_date,
            created_date__date__lte=end_date
        )

        return {
            'stokvel': stokvel,
            'report_period': {'start': start_date, 'end': end_date},
            'member_statistics': member_stats,
            'application_statistics': app_stats,
            'new_members': new_members,
            'new_members_count': new_members.count(),
            'status_changes': status_changes,
            'status_changes_count': status_changes.count(),
            'generated_at': timezone.now()
        }