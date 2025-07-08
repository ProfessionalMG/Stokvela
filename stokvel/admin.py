# stokvel/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from django.contrib import messages

from .models import (
    Stokvel, StokvelConstitution, ContributionRule,
    PenaltyRule, StokvelCycle, StokvelBankAccount
)
from .services import (
    StokvelService, ConstitutionService, ContributionRuleService,
    PenaltyRuleService, CycleService, BankAccountService,
    StokvelValidationService
)


@admin.register(Stokvel)
class StokvelAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'date_established', 'is_active', 'is_accepting_members',
        'member_count', 'constitution_status', 'setup_status'
    ]
    list_filter = ['is_active', 'is_accepting_members', 'date_established']
    search_fields = ['name', 'description', 'registration_number']
    readonly_fields = ['id', 'created_date', 'updated_date', 'setup_validation']

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'registration_number', 'date_established')
        }),
        ('Status', {
            'fields': ('is_active', 'is_accepting_members')
        }),
        ('System Information', {
            'fields': ('id', 'created_date', 'updated_date'),
            'classes': ('collapse',)
        }),
        ('Setup Validation', {
            'fields': ('setup_validation',),
            'classes': ('collapse',)
        })
    )

    def member_count(self, obj):
        count = obj.members.count()
        active_count = obj.members.filter(status='active').count()
        return f"{active_count}/{count}"

    member_count.short_description = "Active/Total Members"

    def constitution_status(self, obj):
        if hasattr(obj, 'constitution'):
            return format_html('<span style="color: green;">✓ Configured</span>')
        else:
            return format_html('<span style="color: red;">✗ Missing</span>')

    constitution_status.short_description = "Constitution"

    def setup_status(self, obj):
        is_valid, issues = StokvelValidationService.validate_stokvel_setup(obj)
        if is_valid:
            return format_html('<span style="color: green;">✓ Complete</span>')
        else:
            return format_html('<span style="color: orange;">⚠ {} issues</span>', len(issues))

    setup_status.short_description = "Setup Status"

    def setup_validation(self, obj):
        if obj.pk:
            is_valid, issues = StokvelValidationService.validate_stokvel_setup(obj)
            if is_valid:
                return format_html('<div style="color: green;"><strong>✓ Setup Complete</strong></div>')
            else:
                issues_html = '<br>'.join([f"• {issue}" for issue in issues])
                return format_html(
                    '<div style="color: orange;"><strong>Setup Issues:</strong><br>{}</div>',
                    issues_html
                )
        return "Save stokvel first to see validation status"

    setup_validation.short_description = "Setup Validation"

    actions = ['activate_stokvels', 'deactivate_stokvels']

    def activate_stokvels(self, request, queryset):
        count = 0
        for stokvel in queryset:
            try:
                StokvelService.update_stokvel_status(stokvel, True, "Activated via admin")
                count += 1
            except Exception as e:
                messages.error(request, f"Could not activate {stokvel.name}: {str(e)}")

        if count:
            messages.success(request, f"Successfully activated {count} stokvel(s)")

    activate_stokvels.short_description = "Activate selected stokvels"

    def deactivate_stokvels(self, request, queryset):
        count = 0
        for stokvel in queryset:
            try:
                StokvelService.update_stokvel_status(stokvel, False, "Deactivated via admin")
                count += 1
            except Exception as e:
                messages.error(request, f"Could not deactivate {stokvel.name}: {str(e)}")

        if count:
            messages.success(request, f"Successfully deactivated {count} stokvel(s)")

    deactivate_stokvels.short_description = "Deactivate selected stokvels"


class StokvelConstitutionInline(admin.StackedInline):
    model = StokvelConstitution
    extra = 0
    max_num = 1


@admin.register(StokvelConstitution)
class StokvelConstitutionAdmin(admin.ModelAdmin):
    list_display = [
        'stokvel', 'meeting_frequency', 'minimum_members', 'maximum_members',
        'payout_frequency', 'contribution_due_day'
    ]
    list_filter = ['meeting_frequency', 'payout_frequency', 'payout_order_method']
    search_fields = ['stokvel__name']
    readonly_fields = ['created_date', 'updated_date']

    fieldsets = (
        ('Stokvel', {
            'fields': ('stokvel',)
        }),
        ('Meeting Requirements', {
            'fields': ('meeting_frequency', 'minimum_attendance_percentage')
        }),
        ('Member Requirements', {
            'fields': ('minimum_members', 'maximum_members', 'probation_period_months')
        }),
        ('Financial Rules', {
            'fields': ('contribution_start_day', 'contribution_due_day')
        }),
        ('Exit and Suspension', {
            'fields': ('notice_period_days', 'suspension_rules')
        }),
        ('Payout Rules', {
            'fields': ('payout_frequency', 'payout_order_method')
        }),
        ('Constitution Document', {
            'fields': ('constitution_text',),
            'classes': ('collapse',)
        }),
        ('System Information', {
            'fields': ('created_date', 'updated_date'),
            'classes': ('collapse',)
        })
    )


@admin.register(ContributionRule)
class ContributionRuleAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'stokvel', 'contribution_type', 'amount', 'frequency',
        'effective_from', 'effective_until', 'is_active', 'is_mandatory'
    ]
    list_filter = [
        'contribution_type', 'frequency', 'is_active', 'is_mandatory',
        'stokvel', 'effective_from'
    ]
    search_fields = ['name', 'stokvel__name', 'description']
    readonly_fields = ['created_date']
    date_hierarchy = 'effective_from'

    fieldsets = (
        ('Basic Information', {
            'fields': ('stokvel', 'name', 'contribution_type', 'description')
        }),
        ('Amount and Schedule', {
            'fields': ('amount', 'frequency')
        }),
        ('Effective Period', {
            'fields': ('effective_from', 'effective_until')
        }),
        ('Settings', {
            'fields': ('is_active', 'is_mandatory')
        }),
        ('System Information', {
            'fields': ('created_date',),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('stokvel')


@admin.register(PenaltyRule)
class PenaltyRuleAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'stokvel', 'penalty_type', 'calculation_method', 'amount',
        'grace_period_days', 'is_active', 'effective_from'
    ]
    list_filter = [
        'penalty_type', 'calculation_method', 'is_active', 'stokvel',
        'effective_from'
    ]
    search_fields = ['name', 'stokvel__name', 'description']
    readonly_fields = ['created_date', 'penalty_preview']

    fieldsets = (
        ('Basic Information', {
            'fields': ('stokvel', 'name', 'penalty_type', 'description')
        }),
        ('Calculation Method', {
            'fields': ('calculation_method', 'amount', 'maximum_amount')
        }),
        ('Grace Period', {
            'fields': ('grace_period_days',)
        }),
        ('Effective Period', {
            'fields': ('effective_from', 'effective_until', 'is_active')
        }),
        ('Preview', {
            'fields': ('penalty_preview',),
            'classes': ('collapse',)
        }),
        ('System Information', {
            'fields': ('created_date',),
            'classes': ('collapse',)
        })
    )

    def penalty_preview(self, obj):
        if obj.pk:
            from decimal import Decimal
            examples = []

            # Example calculations
            base_amounts = [Decimal('1000'), Decimal('2000'), Decimal('5000')]
            days_late_options = [1, 7, 30]

            for base in base_amounts:
                for days in days_late_options:
                    penalty = obj.calculate_penalty(base, days)
                    examples.append(f"R{base} contribution, {days} days late: R{penalty}")

            return format_html('<br>'.join(examples))
        return "Save penalty rule first to see preview"

    penalty_preview.short_description = "Penalty Calculation Examples"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('stokvel')


@admin.register(StokvelCycle)
class StokvelCycleAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'stokvel', 'start_date', 'end_date', 'status',
        'duration_display', 'progress_display', 'expected_total_contributions'
    ]
    list_filter = ['status', 'stokvel', 'start_date']
    search_fields = ['name', 'stokvel__name', 'description']
    readonly_fields = ['created_date', 'duration_display', 'progress_display']
    date_hierarchy = 'start_date'

    fieldsets = (
        ('Basic Information', {
            'fields': ('stokvel', 'name', 'description')
        }),
        ('Cycle Period', {
            'fields': ('start_date', 'end_date', 'duration_display')
        }),
        ('Financial Projections', {
            'fields': ('expected_total_contributions',)
        }),
        ('Status', {
            'fields': ('status', 'progress_display')
        }),
        ('System Information', {
            'fields': ('created_date',),
            'classes': ('collapse',)
        })
    )

    def duration_display(self, obj):
        if obj.pk:
            months = obj.duration_months
            return f"{months} months"
        return "-"

    duration_display.short_description = "Duration"

    def progress_display(self, obj):
        if obj.pk:
            progress = obj.get_progress_percentage()
            return f"{progress}%"
        return "-"

    progress_display.short_description = "Progress"

    actions = ['activate_cycles']

    def activate_cycles(self, request, queryset):
        count = 0
        for cycle in queryset:
            try:
                CycleService.activate_cycle(cycle)
                count += 1
            except Exception as e:
                messages.error(request, f"Could not activate {cycle.name}: {str(e)}")

        if count:
            messages.success(request, f"Successfully activated {count} cycle(s)")

    activate_cycles.short_description = "Activate selected cycles"


@admin.register(StokvelBankAccount)
class StokvelBankAccountAdmin(admin.ModelAdmin):
    list_display = [
        'stokvel', 'bank_name', 'account_name', 'masked_account_display',
        'account_type', 'is_primary', 'is_active', 'created_date'
    ]
    list_filter = ['bank_name', 'account_type', 'is_primary', 'is_active', 'stokvel']
    search_fields = ['stokvel__name', 'account_name', 'account_number']
    readonly_fields = ['created_date', 'masked_account_display']

    fieldsets = (
        ('Stokvel', {
            'fields': ('stokvel',)
        }),
        ('Bank Details', {
            'fields': ('bank_name', 'account_name', 'account_number', 'branch_code', 'account_type')
        }),
        ('Settings', {
            'fields': ('is_primary', 'is_active')
        }),
        ('System Information', {
            'fields': ('created_date', 'masked_account_display'),
            'classes': ('collapse',)
        })
    )

    def masked_account_display(self, obj):
        if obj.pk:
            return obj.masked_account_number
        return "-"

    masked_account_display.short_description = "Masked Account Number"

    actions = ['set_as_primary', 'deactivate_accounts']

    def set_as_primary(self, request, queryset):
        if queryset.count() != 1:
            messages.error(request, "Please select exactly one account to set as primary")
            return

        account = queryset.first()
        try:
            BankAccountService.set_primary_account(account)
            messages.success(request, f"Set {account.account_name} as primary account")
        except Exception as e:
            messages.error(request, f"Could not set as primary: {str(e)}")

    set_as_primary.short_description = "Set as primary account"

    def deactivate_accounts(self, request, queryset):
        count = 0
        for account in queryset:
            try:
                BankAccountService.deactivate_account(account)
                count += 1
            except Exception as e:
                messages.error(request, f"Could not deactivate {account.account_name}: {str(e)}")

        if count:
            messages.success(request, f"Successfully deactivated {count} account(s)")

    deactivate_accounts.short_description = "Deactivate selected accounts"


# stokvel/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

from .models import Stokvel, StokvelConstitution, ContributionRule, PenaltyRule, StokvelCycle
from .services import StokvelService, CycleService


@receiver(post_save, sender=Stokvel)
def stokvel_post_save(sender, instance, created, **kwargs):
    """Handle post-save operations for Stokvel"""
    if created:
        # Create default constitution for new stokvel
        if not hasattr(instance, 'constitution'):
            StokvelConstitution.objects.create(
                stokvel=instance,
                meeting_frequency='monthly',
                minimum_attendance_percentage=60,
                minimum_members=5,
                probation_period_months=3,
                contribution_start_day=1,
                contribution_due_day=31,
                notice_period_days=30,
                payout_frequency='monthly',
                payout_order_method='rotation'
            )


@receiver(post_save, sender=ContributionRule)
def contribution_rule_post_save(sender, instance, created, **kwargs):
    """Handle post-save operations for ContributionRule"""
    if created and instance.contribution_type == 'regular':
        # Update current cycle expected contributions
        current_cycle = CycleService.get_current_cycle(instance.stokvel)
        if current_cycle:
            # Recalculate expected contributions
            # This is a simplified calculation - in practice you might want more sophisticated logic
            active_members = instance.stokvel.members.filter(status='active').count()
            months_remaining = current_cycle.duration_months
            additional_expected = instance.amount * active_members * months_remaining

            current_cycle.expected_total_contributions += additional_expected
            current_cycle.save()


@receiver(post_save, sender=StokvelCycle)
def stokvel_cycle_post_save(sender, instance, created, **kwargs):
    """Handle post-save operations for StokvelCycle"""
    if instance.status == 'active':
        # Ensure only one active cycle per stokvel
        StokvelCycle.objects.filter(
            stokvel=instance.stokvel,
            status='active'
        ).exclude(pk=instance.pk).update(status='completed')


