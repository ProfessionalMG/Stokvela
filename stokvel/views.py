from django.shortcuts import render

# Create your views here.
# stokvel/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.http import JsonResponse, HttpResponseRedirect
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
from datetime import date

from .models import (
    Stokvel, StokvelConstitution, ContributionRule,
    PenaltyRule, StokvelCycle, StokvelBankAccount
)
from .services import (
    StokvelService, ConstitutionService, ContributionRuleService,
    PenaltyRuleService, CycleService, BankAccountService,
    StokvelValidationService
)
from .forms import (
    StokvelCreateForm, StokvelUpdateForm, ConstitutionForm,
    ContributionRuleForm, PenaltyRuleForm, CycleForm, BankAccountForm
)
from .utils import StokvelReportUtils


class StokvelListView(LoginRequiredMixin, ListView):
    """List all stokvels with search and filtering"""
    model = Stokvel
    template_name = 'stokvel/stokvel_list.html'
    context_object_name = 'stokvels'
    paginate_by = 10

    def get_queryset(self):
        queryset = Stokvel.objects.all()

        # Search functionality
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.search(search_query)

        # Filter by status
        status_filter = self.request.GET.get('status')
        if status_filter == 'active':
            queryset = queryset.active()
        elif status_filter == 'accepting':
            queryset = queryset.accepting_members()

        # Filter by establishment year
        year_filter = self.request.GET.get('year')
        if year_filter:
            try:
                year = int(year_filter)
                queryset = queryset.by_establishment_year(year)
            except ValueError:
                pass

        return queryset.order_by('-created_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('search', '')
        context['status_filter'] = self.request.GET.get('status', '')
        context['year_filter'] = self.request.GET.get('year', '')

        # Get available years for filtering
        years = Stokvel.objects.values_list(
            'date_established__year', flat=True
        ).distinct().order_by('-date_established__year')
        context['available_years'] = years

        return context


class StokvelDetailView(LoginRequiredMixin, DetailView):
    """Detailed view of a single stokvel"""
    model = Stokvel
    template_name = 'stokvel/stokvel_detail.html'
    context_object_name = 'stokvel'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        stokvel = self.object

        # Get comprehensive summary using service
        context['summary'] = StokvelService.get_stokvel_summary(stokvel)

        # Validation status
        is_valid, issues = StokvelValidationService.validate_stokvel_setup(stokvel)
        context['setup_valid'] = is_valid
        context['setup_issues'] = issues

        # Member acceptance status
        can_accept, reason = StokvelValidationService.can_accept_new_members(stokvel)
        context['can_accept_members'] = can_accept
        context['member_acceptance_reason'] = reason

        # Constitution compliance
        if hasattr(stokvel, 'constitution'):
            compliance_issues = ConstitutionService.validate_constitution_compliance(stokvel)
            context['constitution_compliance'] = len(compliance_issues) == 0
            context['compliance_issues'] = compliance_issues

        # Recent activity (you can expand this)
        context['recent_contributions'] = ContributionRule.objects.filter(
            stokvel=stokvel
        ).order_by('-created_date')[:5]

        context['recent_penalties'] = PenaltyRule.objects.filter(
            stokvel=stokvel
        ).order_by('-created_date')[:5]

        # Financial overview
        context['member_stats'] = StokvelReportUtils.calculate_member_statistics(stokvel)

        return context


class StokvelCreateView(LoginRequiredMixin, CreateView):
    """Create a new stokvel with constitution"""
    model = Stokvel
    form_class = StokvelCreateForm
    template_name = 'stokvel/stokvel_create.html'

    def form_valid(self, form):
        try:
            with transaction.atomic():
                # Use service to create stokvel with constitution
                constitution_data = {
                    'meeting_frequency': form.cleaned_data.get('meeting_frequency', 'monthly'),
                    'minimum_members': form.cleaned_data.get('minimum_members', 5),
                    'maximum_members': form.cleaned_data.get('maximum_members'),
                    'contribution_due_day': form.cleaned_data.get('contribution_due_day', 31),
                    'payout_frequency': form.cleaned_data.get('payout_frequency', 'monthly'),
                }

                stokvel = StokvelService.create_stokvel_with_constitution(
                    name=form.cleaned_data['name'],
                    description=form.cleaned_data['description'],
                    date_established=form.cleaned_data['date_established'],
                    constitution_data=constitution_data
                )

                messages.success(
                    self.request,
                    f'Stokvel "{stokvel.name}" created successfully with default constitution!'
                )

                return HttpResponseRedirect(reverse('stokvel:detail', kwargs={'pk': stokvel.pk}))

        except ValidationError as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)
        except Exception as e:
            messages.error(self.request, f'Error creating stokvel: {str(e)}')
            return self.form_invalid(form)


class StokvelUpdateView(LoginRequiredMixin, UpdateView):
    """Update stokvel basic information"""
    model = Stokvel
    form_class = StokvelUpdateForm
    template_name = 'stokvel/stokvel_update.html'

    def get_success_url(self):
        return reverse('stokvel:detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, f'Stokvel "{self.object.name}" updated successfully!')
        return super().form_valid(form)


class ConstitutionDetailView(LoginRequiredMixin, DetailView):
    """View stokvel constitution"""
    model = StokvelConstitution
    template_name = 'stokvel/constitution_detail.html'
    context_object_name = 'constitution'

    def get_object(self):
        stokvel = get_object_or_404(Stokvel, pk=self.kwargs['stokvel_pk'])
        return get_object_or_404(StokvelConstitution, stokvel=stokvel)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['stokvel'] = self.object.stokvel

        # Constitution compliance check
        compliance_issues = ConstitutionService.validate_constitution_compliance(
            self.object.stokvel
        )
        context['compliance_issues'] = compliance_issues
        context['is_compliant'] = len(compliance_issues) == 0

        return context


class ConstitutionUpdateView(LoginRequiredMixin, UpdateView):
    """Update stokvel constitution"""
    model = StokvelConstitution
    form_class = ConstitutionForm
    template_name = 'stokvel/constitution_update.html'

    def get_object(self):
        stokvel = get_object_or_404(Stokvel, pk=self.kwargs['stokvel_pk'])
        return get_object_or_404(StokvelConstitution, stokvel=stokvel)

    def get_success_url(self):
        return reverse('stokvel:constitution_detail', kwargs={'stokvel_pk': self.object.stokvel.pk})

    def form_valid(self, form):
        try:
            # Use service to update constitution with validation
            updates = {
                field: form.cleaned_data[field]
                for field in form.changed_data
            }

            ConstitutionService.update_constitution(self.object.stokvel, updates)

            messages.success(
                self.request,
                'Constitution updated successfully!'
            )
            return super().form_valid(form)

        except ValidationError as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['stokvel'] = self.object.stokvel
        return context


class ContributionRuleListView(LoginRequiredMixin, ListView):
    """List contribution rules for a stokvel"""
    model = ContributionRule
    template_name = 'stokvel/contribution_rules_list.html'
    context_object_name = 'rules'
    paginate_by = 20

    def get_queryset(self):
        self.stokvel = get_object_or_404(Stokvel, pk=self.kwargs['stokvel_pk'])
        queryset = ContributionRule.objects.filter(stokvel=self.stokvel)

        # Filter by type
        rule_type = self.request.GET.get('type')
        if rule_type:
            queryset = queryset.by_type(rule_type)

        # Filter by active status
        active_filter = self.request.GET.get('active')
        if active_filter == 'true':
            queryset = queryset.active()
        elif active_filter == 'false':
            queryset = queryset.filter(is_active=False)

        return queryset.order_by('-created_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['stokvel'] = self.stokvel
        context['type_filter'] = self.request.GET.get('type', '')
        context['active_filter'] = self.request.GET.get('active', '')

        # Get current active rules
        context['active_rules'] = ContributionRuleService.get_active_contribution_rules(
            self.stokvel
        )

        return context


class ContributionRuleCreateView(LoginRequiredMixin, CreateView):
    """Create a new contribution rule"""
    model = ContributionRule
    form_class = ContributionRuleForm
    template_name = 'stokvel/contribution_rule_create.html'

    def dispatch(self, request, *args, **kwargs):
        self.stokvel = get_object_or_404(Stokvel, pk=kwargs['stokvel_pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['stokvel'] = self.stokvel
        return kwargs

    def form_valid(self, form):
        try:
            # Use service to create contribution rule
            rule = ContributionRuleService.create_contribution_rule(
                stokvel=self.stokvel,
                name=form.cleaned_data['name'],
                contribution_type=form.cleaned_data['contribution_type'],
                amount=form.cleaned_data['amount'],
                frequency=form.cleaned_data['frequency'],
                effective_from=form.cleaned_data['effective_from'],
                effective_until=form.cleaned_data.get('effective_until'),
                is_mandatory=form.cleaned_data['is_mandatory'],
                description=form.cleaned_data['description']
            )

            messages.success(
                self.request,
                f'Contribution rule "{rule.name}" created successfully!'
            )

            return HttpResponseRedirect(
                reverse('stokvel:contribution_rules', kwargs={'stokvel_pk': self.stokvel.pk})
            )

        except ValidationError as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['stokvel'] = self.stokvel
        return context


class PenaltyRuleListView(LoginRequiredMixin, ListView):
    """List penalty rules for a stokvel"""
    model = PenaltyRule
    template_name = 'stokvel/penalty_rules_list.html'
    context_object_name = 'rules'
    paginate_by = 20

    def get_queryset(self):
        self.stokvel = get_object_or_404(Stokvel, pk=self.kwargs['stokvel_pk'])
        queryset = PenaltyRule.objects.filter(stokvel=self.stokvel)

        # Filter by type
        penalty_type = self.request.GET.get('type')
        if penalty_type:
            queryset = queryset.by_type(penalty_type)

        # Filter by active status
        active_filter = self.request.GET.get('active')
        if active_filter == 'true':
            queryset = queryset.active()
        elif active_filter == 'false':
            queryset = queryset.filter(is_active=False)

        return queryset.order_by('-created_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['stokvel'] = self.stokvel
        context['type_filter'] = self.request.GET.get('type', '')
        context['active_filter'] = self.request.GET.get('active', '')
        return context


class PenaltyRuleCreateView(LoginRequiredMixin, CreateView):
    """Create a new penalty rule"""
    model = PenaltyRule
    form_class = PenaltyRuleForm
    template_name = 'stokvel/penalty_rule_create.html'

    def dispatch(self, request, *args, **kwargs):
        self.stokvel = get_object_or_404(Stokvel, pk=kwargs['stokvel_pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['stokvel'] = self.stokvel
        return kwargs

    def form_valid(self, form):
        try:
            # Use service to create penalty rule
            rule = PenaltyRuleService.create_penalty_rule(
                stokvel=self.stokvel,
                name=form.cleaned_data['name'],
                penalty_type=form.cleaned_data['penalty_type'],
                calculation_method=form.cleaned_data['calculation_method'],
                amount=form.cleaned_data['amount'],
                grace_period_days=form.cleaned_data['grace_period_days'],
                maximum_amount=form.cleaned_data.get('maximum_amount'),
                effective_from=form.cleaned_data['effective_from'],
                description=form.cleaned_data['description']
            )

            messages.success(
                self.request,
                f'Penalty rule "{rule.name}" created successfully!'
            )

            return HttpResponseRedirect(
                reverse('stokvel:penalty_rules', kwargs={'stokvel_pk': self.stokvel.pk})
            )

        except ValidationError as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['stokvel'] = self.stokvel
        return context


class CycleListView(LoginRequiredMixin, ListView):
    """List cycles for a stokvel"""
    model = StokvelCycle
    template_name = 'stokvel/cycles_list.html'
    context_object_name = 'cycles'
    paginate_by = 10

    def get_queryset(self):
        self.stokvel = get_object_or_404(Stokvel, pk=self.kwargs['stokvel_pk'])
        return StokvelCycle.objects.filter(stokvel=self.stokvel).order_by('-start_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['stokvel'] = self.stokvel
        context['current_cycle'] = CycleService.get_current_cycle(self.stokvel)
        return context


class CycleCreateView(LoginRequiredMixin, CreateView):
    """Create a new stokvel cycle"""
    model = StokvelCycle
    form_class = CycleForm
    template_name = 'stokvel/cycle_create.html'

    def dispatch(self, request, *args, **kwargs):
        self.stokvel = get_object_or_404(Stokvel, pk=kwargs['stokvel_pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['stokvel'] = self.stokvel
        return kwargs

    def form_valid(self, form):
        try:
            # Use service to create cycle
            cycle = CycleService.create_cycle(
                stokvel=self.stokvel,
                name=form.cleaned_data['name'],
                start_date=form.cleaned_data['start_date'],
                end_date=form.cleaned_data['end_date'],
                description=form.cleaned_data['description']
            )

            messages.success(
                self.request,
                f'Cycle "{cycle.name}" created successfully!'
            )

            return HttpResponseRedirect(
                reverse('stokvel:cycles', kwargs={'stokvel_pk': self.stokvel.pk})
            )

        except ValidationError as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['stokvel'] = self.stokvel
        return context


class BankAccountListView(LoginRequiredMixin, ListView):
    """List bank accounts for a stokvel"""
    model = StokvelBankAccount
    template_name = 'stokvel/bank_accounts_list.html'
    context_object_name = 'accounts'

    def get_queryset(self):
        self.stokvel = get_object_or_404(Stokvel, pk=self.kwargs['stokvel_pk'])
        return StokvelBankAccount.objects.filter(stokvel=self.stokvel).order_by('-is_primary', '-created_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['stokvel'] = self.stokvel
        context['primary_account'] = StokvelBankAccount.objects.filter(
            stokvel=self.stokvel, is_primary=True, is_active=True
        ).first()
        return context


class BankAccountCreateView(LoginRequiredMixin, CreateView):
    """Create a new bank account"""
    model = StokvelBankAccount
    form_class = BankAccountForm
    template_name = 'stokvel/bank_account_create.html'

    def dispatch(self, request, *args, **kwargs):
        self.stokvel = get_object_or_404(Stokvel, pk=kwargs['stokvel_pk'])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        try:
            # Use service to add bank account
            account = BankAccountService.add_bank_account(
                stokvel=self.stokvel,
                bank_name=form.cleaned_data['bank_name'],
                account_name=form.cleaned_data['account_name'],
                account_number=form.cleaned_data['account_number'],
                branch_code=form.cleaned_data['branch_code'],
                account_type=form.cleaned_data['account_type'],
                is_primary=form.cleaned_data['is_primary']
            )

            messages.success(
                self.request,
                f'Bank account "{account.account_name}" added successfully!'
            )

            return HttpResponseRedirect(
                reverse('stokvel:bank_accounts', kwargs={'stokvel_pk': self.stokvel.pk})
            )

        except ValidationError as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['stokvel'] = self.stokvel
        return context


class StokvelDashboardView(LoginRequiredMixin, DetailView):
    """Dashboard view for a stokvel"""
    model = Stokvel
    template_name = 'stokvel/dashboard.html'
    context_object_name = 'stokvel'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        stokvel = self.object

        # Basic summary
        context['summary'] = StokvelService.get_stokvel_summary(stokvel)

        # Member statistics
        context['member_stats'] = StokvelReportUtils.calculate_member_statistics(stokvel)

        # Current cycle
        context['current_cycle'] = CycleService.get_current_cycle(stokvel)

        # Recent activity
        context['recent_contribution_rules'] = ContributionRule.objects.filter(
            stokvel=stokvel
        ).order_by('-created_date')[:3]

        # Setup validation
        is_valid, issues = StokvelValidationService.validate_stokvel_setup(stokvel)
        context['setup_complete'] = is_valid
        context['setup_issues'] = issues

        # Quick stats
        context['active_contribution_rules'] = ContributionRule.objects.filter(
            stokvel=stokvel, is_active=True
        ).count()

        context['active_penalty_rules'] = PenaltyRule.objects.filter(
            stokvel=stokvel, is_active=True
        ).count()

        return context


# AJAX Views
class ActivateCycleView(LoginRequiredMixin, DetailView):
    """AJAX view to activate a cycle"""
    model = StokvelCycle

    def post(self, request, *args, **kwargs):
        cycle = self.get_object()

        try:
            CycleService.activate_cycle(cycle)

            return JsonResponse({
                'success': True,
                'message': f'Cycle "{cycle.name}" activated successfully!'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=400)


class SetPrimaryAccountView(LoginRequiredMixin, DetailView):
    """AJAX view to set primary bank account"""
    model = StokvelBankAccount

    def post(self, request, *args, **kwargs):
        account = self.get_object()

        try:
            BankAccountService.set_primary_account(account)

            return JsonResponse({
                'success': True,
                'message': f'"{account.account_name}" set as primary account!'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=400)


class DeactivateRuleView(LoginRequiredMixin, DetailView):
    """AJAX view to deactivate contribution/penalty rules"""

    def post(self, request, *args, **kwargs):
        rule_type = kwargs.get('rule_type')
        rule_id = kwargs.get('pk')

        try:
            if rule_type == 'contribution':
                rule = get_object_or_404(ContributionRule, pk=rule_id)
                ContributionRuleService.deactivate_rule(rule)
            elif rule_type == 'penalty':
                rule = get_object_or_404(PenaltyRule, pk=rule_id)
                rule.is_active = False
                rule.save()
            else:
                raise ValidationError("Invalid rule type")

            return JsonResponse({
                'success': True,
                'message': f'Rule "{rule.name}" deactivated successfully!'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=400)


class StokvelReportsView(LoginRequiredMixin, DetailView):
    """Reports and analytics for a stokvel"""
    model = Stokvel
    template_name = 'stokvel/reports.html'
    context_object_name = 'stokvel'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        stokvel = self.object

        # Get year for reports
        year = self.request.GET.get('year')
        if year:
            try:
                year = int(year)
            except ValueError:
                year = timezone.now().year
        else:
            year = timezone.now().year

        context['report_year'] = year

        # Member statistics
        context['member_stats'] = StokvelReportUtils.calculate_member_statistics(stokvel)

        # Contribution statistics
        context['contribution_stats'] = StokvelReportUtils.calculate_contribution_statistics(
            stokvel
        )

        # Compliance report
        context['compliance_report'] = StokvelReportUtils.get_payment_compliance_report(
            stokvel, year
        )

        # Available years for filtering
        cycles = StokvelCycle.objects.filter(stokvel=stokvel)
        available_years = set()
        for cycle in cycles:
            available_years.add(cycle.start_date.year)
            available_years.add(cycle.end_date.year)
        context['available_years'] = sorted(available_years, reverse=True)

        return context