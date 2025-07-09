# accounts/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from django.contrib import messages

from .models import User, Member, MembershipApplication, MemberBankAccount, MemberActivity
from .services import (
    UserService, MemberService, MembershipApplicationService,
    MemberBankAccountService, MemberValidationService
)
from .utils import ProfileUtils, MemberUtils


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Enhanced admin for User model"""

    list_display = [
        'username', 'email', 'display_name', 'phone_number',
        'verification_status', 'profile_completion', 'date_joined'
    ]
    list_filter = [
        'is_verified', 'email_verified', 'phone_verified',
        'preferred_language', 'is_staff', 'is_active', 'date_joined'
    ]
    search_fields = ['username', 'email', 'first_name', 'last_name', 'phone_number']
    readonly_fields = ['id', 'date_joined', 'last_login', 'verification_summary']

    fieldsets = BaseUserAdmin.fieldsets + (
        ('Profile Information', {
            'fields': ('phone_number', 'date_of_birth', 'id_number')
        }),
        ('Address', {
            'fields': ('address_line_1', 'address_line_2', 'city', 'province', 'postal_code', 'country')
        }),
        ('Preferences', {
            'fields': ('preferred_language', 'email_notifications', 'sms_notifications', 'whatsapp_notifications')
        }),
        ('Verification Status', {
            'fields': ('is_verified', 'email_verified', 'phone_verified', 'verification_summary'),
            'classes': ('collapse',)
        }),
        ('System Information', {
            'fields': ('id', 'date_joined', 'last_login'),
            'classes': ('collapse',)
        })
    )

    def display_name(self, obj):
        return obj.display_name

    display_name.short_description = "Display Name"

    def verification_status(self, obj):
        percentage = obj.get_verification_percentage()
        if percentage == 100:
            color = 'green'
            icon = '✓'
        elif percentage >= 50:
            color = 'orange'
            icon = '◐'
        else:
            color = 'red'
            icon = '✗'

        return format_html(
            '<span style="color: {};">{} {}%</span>',
            color, icon, percentage
        )

    verification_status.short_description = "Verification"

    def profile_completion(self, obj):
        profile_info = ProfileUtils.calculate_profile_completion(obj)
        percentage = profile_info['completion_percentage']

        if percentage == 100:
            color = 'green'
        elif percentage >= 70:
            color = 'orange'
        else:
            color = 'red'

        return format_html(
            '<span style="color: {};">{}%</span>',
            color, percentage
        )

    profile_completion.short_description = "Profile"

    def verification_summary(self, obj):
        if obj.pk:
            status = UserService.get_user_verification_status(obj)

            summary_html = f"<strong>Overall: {status['verification_percentage']}%</strong><br>"
            summary_html += f"Email: {'✓' if status['email_verified'] else '✗'}<br>"
            summary_html += f"Phone: {'✓' if status['phone_verified'] else '✗'}<br>"

            if status['missing_verifications']:
                summary_html += f"<br><strong>Missing:</strong> {', '.join(status['missing_verifications'])}"

            return format_html(summary_html)
        return "Save user first"

    verification_summary.short_description = "Verification Summary"

    actions = ['verify_emails', 'verify_phones']

    def verify_emails(self, request, queryset):
        count = 0
        for user in queryset:
            if not user.email_verified:
                UserService.verify_user_email(user)
                count += 1

        messages.success(request, f"Verified {count} email addresses")

    verify_emails.short_description = "Verify selected email addresses"

    def verify_phones(self, request, queryset):
        count = 0
        for user in queryset:
            if not user.phone_verified:
                UserService.verify_user_phone(user)
                count += 1

        messages.success(request, f"Verified {count} phone numbers")

    verify_phones.short_description = "Verify selected phone numbers"


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    """Admin for Member model"""

    list_display = [
        'member_number', 'user_display_name', 'stokvel', 'status', 'role',
        'days_since_joining', 'profile_status', 'payout_eligibility'
    ]
    list_filter = [
        'status', 'role', 'stokvel', 'approval_date', 'payout_preference'
    ]
    search_fields = [
        'user__first_name', 'user__last_name', 'user__email',
        'member_number', 'stokvel__name'
    ]
    readonly_fields = [
        'id', 'application_date', 'created_date', 'updated_date',
        'member_summary', 'engagement_score'
    ]

    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'stokvel', 'member_number', 'status', 'role')
        }),
        ('Important Dates', {
            'fields': ('application_date', 'approval_date', 'probation_end_date', 'exit_date')
        }),
        ('Bank References', {
            'fields': ('bank_reference_names',),
            'description': 'Names as they appear on bank statements for payment matching'
        }),
        ('Emergency Contact', {
            'fields': ('emergency_contact_name', 'emergency_contact_phone', 'emergency_contact_relationship')
        }),
        ('Additional Information', {
            'fields': ('occupation', 'employer', 'monthly_income_range', 'payout_preference')
        }),
        ('Notes', {
            'fields': ('application_notes', 'admin_notes')
        }),
        ('Summary', {
            'fields': ('member_summary', 'engagement_score'),
            'classes': ('collapse',)
        }),
        ('System Information', {
            'fields': ('id', 'created_date', 'updated_date'),
            'classes': ('collapse',)
        })
    )

    def user_display_name(self, obj):
        return obj.user.display_name

    user_display_name.short_description = "Member Name"
    user_display_name.admin_order_field = 'user__first_name'

    def profile_status(self, obj):
        profile_info = ProfileUtils.calculate_profile_completion(obj.user)
        percentage = profile_info['completion_percentage']

        if percentage == 100:
            return format_html('<span style="color: green;">✓ Complete</span>')
        else:
            return format_html('<span style="color: orange;">⚠ {}%</span>', percentage)

    profile_status.short_description = "Profile"

    def payout_eligibility(self, obj):
        can_receive, reason = MemberValidationService.can_receive_payout(obj)
        if can_receive:
            return format_html('<span style="color: green;">✓ Eligible</span>')
        else:
            return format_html('<span style="color: red;" title="{}">✗ Not Eligible</span>', reason)

    payout_eligibility.short_description = "Payout"

    def member_summary(self, obj):
        if obj.pk:
            summary = MemberService.get_member_summary(obj)

            html = f"<strong>Status:</strong> {obj.get_status_display()}<br>"
            html += f"<strong>Days since joining:</strong> {summary['days_since_joining']}<br>"
            html += f"<strong>Bank accounts:</strong> {summary['bank_accounts_count']}<br>"
            html += f"<strong>Total contributions:</strong> {summary['total_contributions']}<br>"
            html += f"<strong>Total penalties:</strong> {summary['total_penalties']}<br>"

            return format_html(html)
        return "Save member first"

    member_summary.short_description = "Member Summary"

    def engagement_score(self, obj):
        if obj.pk:
            engagement = MemberUtils.get_member_engagement_score(obj)
            color = 'green' if engagement['score'] >= 60 else 'orange' if engagement['score'] >= 40 else 'red'

            return format_html(
                '<span style="color: {};">{} ({})</span>',
                color, engagement['score'], engagement['level']
            )
        return "Not calculated"

    engagement_score.short_description = "Engagement"

    actions = ['activate_members', 'promote_from_probation']

    def activate_members(self, request, queryset):
        count = 0
        for member in queryset:
            try:
                if member.status in ['probation', 'suspended']:
                    MemberService.update_member_status(
                        member=member,
                        new_status='active',
                        reason="Activated via admin",
                        updated_by=request.user
                    )
                    count += 1
            except Exception as e:
                messages.error(request, f"Could not activate {member}: {str(e)}")

        if count:
            messages.success(request, f"Activated {count} members")

    activate_members.short_description = "Activate selected members"

    def promote_from_probation(self, request, queryset):
        count = 0
        for member in queryset:
            try:
                if member.status == 'probation':
                    MemberService.promote_from_probation(
                        member=member,
                        promoted_by=request.user
                    )
                    count += 1
            except Exception as e:
                messages.error(request, f"Could not promote {member}: {str(e)}")

        if count:
            messages.success(request, f"Promoted {count} members from probation")

    promote_from_probation.short_description = "Promote from probation"


@admin.register(MembershipApplication)
class MembershipApplicationAdmin(admin.ModelAdmin):
    """Admin for MembershipApplication model"""

    list_display = [
        'user_display_name', 'stokvel', 'status', 'submitted_date',
        'waiting_days', 'has_referral', 'review_status'
    ]
    list_filter = ['status', 'stokvel', 'submitted_date', 'referred_by']
    search_fields = [
        'user__first_name', 'user__last_name', 'user__email',
        'stokvel__name', 'motivation'
    ]
    readonly_fields = [
        'id', 'submitted_date', 'decision_date', 'waiting_days_display',
        'applicant_profile_summary'
    ]

    fieldsets = (
        ('Application Details', {
            'fields': ('user', 'stokvel', 'status', 'motivation')
        }),
        ('Referral Information', {
            'fields': ('referral_source', 'referred_by')
        }),
        ('Review Process', {
            'fields': ('reviewed_by', 'review_date', 'review_notes')
        }),
        ('Important Dates', {
            'fields': ('submitted_date', 'decision_date', 'waiting_days_display')
        }),
        ('Applicant Profile', {
            'fields': ('applicant_profile_summary',),
            'classes': ('collapse',)
        }),
        ('System Information', {
            'fields': ('id',),
            'classes': ('collapse',)
        })
    )

    def user_display_name(self, obj):
        return obj.user.display_name

    user_display_name.short_description = "Applicant"
    user_display_name.admin_order_field = 'user__first_name'

    def waiting_days(self, obj):
        days = obj.waiting_days
        if days <= 3:
            color = 'green'
        elif days <= 7:
            color = 'orange'
        else:
            color = 'red'

        return format_html('<span style="color: {};">{} days</span>', color, days)

    waiting_days.short_description = "Waiting"

    def has_referral(self, obj):
        return "✓" if obj.referred_by else "✗"

    has_referral.short_description = "Referred"
    has_referral.boolean = True

    def review_status(self, obj):
        if obj.status == 'submitted':
            return format_html('<span style="color: orange;">Pending Review</span>')
        elif obj.status == 'approved':
            return format_html('<span style="color: green;">✓ Approved</span>')
        elif obj.status == 'rejected':
            return format_html('<span style="color: red;">✗ Rejected</span>')
        else:
            return obj.get_status_display()

    review_status.short_description = "Review Status"

    def waiting_days_display(self, obj):
        return f"{obj.waiting_days} days"

    waiting_days_display.short_description = "Days Waiting"

    def applicant_profile_summary(self, obj):
        if obj.pk:
            profile_info = ProfileUtils.calculate_profile_completion(obj.user)

            html = f"<strong>Profile Completion:</strong> {profile_info['completion_percentage']}%<br>"
            html += f"<strong>Email Verified:</strong> {'✓' if obj.user.email_verified else '✗'}<br>"
            html += f"<strong>Phone Verified:</strong> {'✓' if obj.user.phone_verified else '✗'}<br>"

            if profile_info['missing_fields']:
                html += f"<br><strong>Missing:</strong> {', '.join(profile_info['missing_fields'])}"

            return format_html(html)
        return "Save application first"

    applicant_profile_summary.short_description = "Applicant Summary"

    actions = ['approve_applications', 'reject_applications']

    def approve_applications(self, request, queryset):
        count = 0
        for application in queryset:
            try:
                if application.status == 'submitted':
                    MembershipApplicationService.approve_application(
                        application=application,
                        reviewed_by=request.user,
                        notes="Approved via admin"
                    )
                    count += 1
            except Exception as e:
                messages.error(request, f"Could not approve application from {application.user}: {str(e)}")

        if count:
            messages.success(request, f"Approved {count} applications")

    approve_applications.short_description = "Approve selected applications"

    def reject_applications(self, request, queryset):
        count = 0
        for application in queryset:
            try:
                if application.status == 'submitted':
                    MembershipApplicationService.reject_application(
                        application=application,
                        reviewed_by=request.user,
                        notes="Rejected via admin"
                    )
                    count += 1
            except Exception as e:
                messages.error(request, f"Could not reject application from {application.user}: {str(e)}")

        if count:
            messages.success(request, f"Rejected {count} applications")

    reject_applications.short_description = "Reject selected applications"


@admin.register(MemberBankAccount)
class MemberBankAccountAdmin(admin.ModelAdmin):
    """Admin for MemberBankAccount model"""

    list_display = [
        'member_name', 'bank_name', 'masked_account_number',
        'account_type', 'is_primary', 'is_verified', 'created_date'
    ]
    list_filter = ['bank_name', 'account_type', 'is_primary', 'is_verified']
    search_fields = [
        'member__user__first_name', 'member__user__last_name',
        'account_holder_name', 'account_number', 'bank_name'
    ]
    readonly_fields = ['created_date', 'updated_date', 'masked_account_number']

    fieldsets = (
        ('Member', {
            'fields': ('member',)
        }),
        ('Bank Details', {
            'fields': ('bank_name', 'account_holder_name', 'account_number', 'branch_code', 'account_type')
        }),
        ('Settings', {
            'fields': ('is_primary', 'is_verified')
        }),
        ('System Information', {
            'fields': ('created_date', 'updated_date', 'masked_account_number'),
            'classes': ('collapse',)
        })
    )

    def member_name(self, obj):
        return obj.member.user.display_name

    member_name.short_description = "Member"
    member_name.admin_order_field = 'member__user__first_name'

    actions = ['verify_accounts', 'set_as_primary']

    def verify_accounts(self, request, queryset):
        count = 0
        for account in queryset:
            if not account.is_verified:
                MemberBankAccountService.verify_bank_account(
                    account=account,
                    verified_by=request.user
                )
                count += 1

        messages.success(request, f"Verified {count} bank accounts")

    verify_accounts.short_description = "Verify selected bank accounts"

    def set_as_primary(self, request, queryset):
        if queryset.count() != 1:
            messages.error(request, "Please select exactly one account to set as primary")
            return

        account = queryset.first()
        MemberBankAccountService.set_primary_account(account)
        messages.success(request, f"Set {account} as primary account")

    set_as_primary.short_description = "Set as primary account"


@admin.register(MemberActivity)
class MemberActivityAdmin(admin.ModelAdmin):
    """Admin for MemberActivity model"""

    list_display = [
        'member_name', 'activity_type', 'description_short', 'created_date'
    ]
    list_filter = ['activity_type', 'created_date', 'member__stokvel']
    search_fields = [
        'member__user__first_name', 'member__user__last_name',
        'description', 'member__stokvel__name'
    ]
    readonly_fields = ['created_date']

    def member_name(self, obj):
        return obj.member.user.display_name

    member_name.short_description = "Member"
    member_name.admin_order_field = 'member__user__first_name'

    def description_short(self, obj):
        return obj.description[:100] + "..." if len(obj.description) > 100 else obj.description

    description_short.short_description = "Description"


# accounts/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

from .models import User, Member, MembershipApplication
from .services import MemberActivityService


@receiver(post_save, sender=User)
def user_post_save(sender, instance, created, **kwargs):
    """Handle post-save operations for User"""
    if created:
        # Log user registration
        print(f"New user registered: {instance.username} ({instance.email})")

        # Set verification status based on email
        if instance.email and '@' in instance.email:
            # Could trigger email verification here
            pass


@receiver(post_save, sender=Member)
def member_post_save(sender, instance, created, **kwargs):
    """Handle post-save operations for Member"""
    if created:
        # Log member creation
        MemberActivityService.log_activity(
            member=instance,
            activity_type='status_changed',
            description=f"Member record created with status: {instance.status}"
        )
    else:
        # Check if status changed
        if instance.tracker.has_changed('status'):
            old_status = instance.tracker.previous('status')
            MemberActivityService.log_activity(
                member=instance,
                activity_type='status_changed',
                description=f"Status changed from {old_status} to {instance.status}"
            )


@receiver(post_save, sender=MembershipApplication)
def application_post_save(sender, instance, created, **kwargs):
    """Handle post-save operations for MembershipApplication"""
    if created:
        # Log application submission
        print(f"New membership application: {instance.user.display_name} -> {instance.stokvel.name}")

    # Check if status changed to approved
    if not created and instance.status == 'approved':
        # Could trigger welcome notifications here
        print(f"Application approved: {instance.user.display_name} -> {instance.stokvel.name}")

# Note: To use the tracker functionality in signals, you would need to install django-model-utils
# and add FieldTracker to the Member model. For now, we'll skip the status change detection in signals.