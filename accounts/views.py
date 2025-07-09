# accounts/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth import login
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.http import JsonResponse, HttpResponseRedirect
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import transaction
from datetime import date, timedelta

from .models import User, Member, MembershipApplication, MemberBankAccount, MemberActivity
from stokvel.models import Stokvel
from .services import (
    UserService, MembershipApplicationService, MemberService,
    MemberBankAccountService, MemberActivityService, MemberValidationService
)
from .forms import (
    UserRegistrationForm, UserProfileForm, MembershipApplicationForm,
    MemberBankAccountForm, MemberUpdateForm, ApplicationReviewForm
)
from .utils import ProfileUtils, MemberUtils, ApplicationUtils, NotificationUtils


class CustomLoginView(LoginView):
    """Custom login view with additional functionality"""
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)

        # Log login activity for members
        user = form.get_user()
        members = user.memberships.filter(status__in=['active', 'probation'])

        for member in members:
            MemberActivityService.log_activity(
                member=member,
                activity_type='login',
                description=f"User logged in from {self.request.META.get('REMOTE_ADDR', 'unknown IP')}"
            )

        return response


class UserRegistrationView(CreateView):
    """User registration view"""
    model = User
    form_class = UserRegistrationForm
    template_name = 'accounts/register.html'
    success_url = reverse_lazy('accounts:profile')

    def form_valid(self, form):
        try:
            with transaction.atomic():
                # Use service to create user
                user = UserService.create_user_account(
                    username=form.cleaned_data['username'],
                    email=form.cleaned_data['email'],
                    password=form.cleaned_data['password1'],
                    first_name=form.cleaned_data['first_name'],
                    last_name=form.cleaned_data['last_name'],
                    phone_number=form.cleaned_data.get('phone_number', ''),
                    date_of_birth=form.cleaned_data.get('date_of_birth'),
                    preferred_language=form.cleaned_data.get('preferred_language', 'en')
                )

                # Log the user in
                login(self.request, user)

                # Send welcome email
                NotificationUtils.send_welcome_email(user)

                messages.success(
                    self.request,
                    'Welcome! Your account has been created successfully. '
                    'Please complete your profile and verify your email.'
                )

                return HttpResponseRedirect(self.success_url)

        except ValidationError as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)


class UserProfileView(LoginRequiredMixin, UpdateView):
    """User profile management view"""
    model = User
    form_class = UserProfileForm
    template_name = 'accounts/profile.html'
    success_url = reverse_lazy('accounts:profile')

    def get_object(self):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Profile completion status
        context['profile_completion'] = ProfileUtils.calculate_profile_completion(user)

        # User's memberships
        context['memberships'] = user.memberships.all().select_related('stokvel')

        # Pending applications
        context['pending_applications'] = user.applications.filter(
            status__in=['submitted', 'under_review']
        )

        # Verification status
        context['verification_status'] = UserService.get_user_verification_status(user)

        return context

    def form_valid(self, form):
        try:
            # Use service to update profile
            UserService.update_user_profile(
                user=self.request.user,
                updates=form.cleaned_data
            )

            messages.success(self.request, 'Profile updated successfully!')
            return super().form_valid(form)

        except ValidationError as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)


class MemberListView(LoginRequiredMixin, ListView):
    """List members for a stokvel"""
    model = Member
    template_name = 'accounts/member_list.html'
    context_object_name = 'members'
    paginate_by = 20

    def dispatch(self, request, *args, **kwargs):
        self.stokvel = get_object_or_404(Stokvel, pk=kwargs['stokvel_pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        queryset = Member.objects.filter(stokvel=self.stokvel).select_related('user')

        # Filter by status
        status_filter = self.request.GET.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by role
        role_filter = self.request.GET.get('role')
        if role_filter:
            queryset = queryset.filter(role=role_filter)

        # Search functionality
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.search(search_query)

        return queryset.order_by('member_number')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['stokvel'] = self.stokvel
        context['search_query'] = self.request.GET.get('search', '')
        context['status_filter'] = self.request.GET.get('status', '')
        context['role_filter'] = self.request.GET.get('role', '')

        # Member statistics
        context['member_stats'] = MemberUtils.calculate_member_statistics(self.stokvel)

        # Leadership team
        context['leadership_team'] = Member.objects.filter(
            stokvel=self.stokvel,
            role__in=['chairperson', 'treasurer', 'secretary', 'admin'],
            status='active'
        ).select_related('user')

        return context


class MemberDetailView(LoginRequiredMixin, DetailView):
    """Detailed view of a member"""
    model = Member
    template_name = 'accounts/member_detail.html'
    context_object_name = 'member'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        member = self.object

        # Member summary using service
        context.update(MemberService.get_member_summary(member))

        # Profile completion
        context['profile_completion'] = ProfileUtils.calculate_profile_completion(member.user)

        # Engagement score
        context['engagement'] = MemberUtils.get_member_engagement_score(member)

        # Probation eligibility
        if member.status == 'probation':
            context['probation_eligibility'] = MemberUtils.check_probation_eligibility(member)

        # Payout eligibility
        can_receive, reason = MemberValidationService.can_receive_payout(member)
        context['payout_eligibility'] = {
            'eligible': can_receive,
            'reason': reason
        }

        # Member report
        context['member_report'] = MemberUtils.generate_member_report(member)

        return context


class MemberUpdateView(LoginRequiredMixin, UpdateView):
    """Update member information"""
    model = Member
    form_class = MemberUpdateForm
    template_name = 'accounts/member_update.html'

    def get_success_url(self):
        return reverse('accounts:member_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        member = self.object

        try:
            # Update status if changed
            if 'status' in form.changed_data:
                MemberService.update_member_status(
                    member=member,
                    new_status=form.cleaned_data['status'],
                    reason=form.cleaned_data.get('status_change_reason', ''),
                    updated_by=self.request.user
                )

            # Update role if changed
            if 'role' in form.changed_data:
                MemberService.update_member_role(
                    member=member,
                    new_role=form.cleaned_data['role'],
                    updated_by=self.request.user
                )

            # Update other fields
            for field in ['bank_reference_names', 'emergency_contact_name',
                          'emergency_contact_phone', 'admin_notes']:
                if field in form.changed_data:
                    setattr(member, field, form.cleaned_data[field])

            member.save()

            messages.success(self.request, f'Member {member.user.get_full_name()} updated successfully!')
            return super().form_valid(form)

        except ValidationError as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)


class MembershipApplicationListView(LoginRequiredMixin, ListView):
    """List membership applications for a stokvel"""
    model = MembershipApplication
    template_name = 'accounts/application_list.html'
    context_object_name = 'applications'
    paginate_by = 20

    def dispatch(self, request, *args, **kwargs):
        self.stokvel = get_object_or_404(Stokvel, pk=kwargs['stokvel_pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        queryset = MembershipApplication.objects.filter(
            stokvel=self.stokvel
        ).select_related('user', 'referred_by__user')

        # Filter by status
        status_filter = self.request.GET.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Search functionality
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.search(search_query)

        return queryset.order_by('-submitted_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['stokvel'] = self.stokvel
        context['search_query'] = self.request.GET.get('search', '')
        context['status_filter'] = self.request.GET.get('status', '')

        # Application statistics
        context['app_stats'] = ApplicationUtils.calculate_application_statistics(self.stokvel)

        # Pending applications summary
        context['pending_summary'] = ApplicationUtils.get_pending_applications_summary(self.stokvel)

        return context


class MembershipApplicationCreateView(LoginRequiredMixin, CreateView):
    """Create a membership application"""
    model = MembershipApplication
    form_class = MembershipApplicationForm
    template_name = 'accounts/application_create.html'

    def dispatch(self, request, *args, **kwargs):
        self.stokvel = get_object_or_404(Stokvel, pk=kwargs['stokvel_pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['stokvel'] = self.stokvel
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        try:
            # Use service to submit application
            application = MembershipApplicationService.submit_application(
                user=self.request.user,
                stokvel=self.stokvel,
                motivation=form.cleaned_data['motivation'],
                referral_source=form.cleaned_data.get('referral_source', ''),
                referred_by=form.cleaned_data.get('referred_by')
            )

            # Send confirmation email
            NotificationUtils.send_application_confirmation(application)

            messages.success(
                self.request,
                f'Your application to join {self.stokvel.name} has been submitted successfully!'
            )

            return HttpResponseRedirect(
                reverse('accounts:profile')
            )

        except ValidationError as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['stokvel'] = self.stokvel

        # Check if user can apply
        existing_membership = Member.objects.filter(
            user=self.request.user,
            stokvel=self.stokvel
        ).first()

        existing_application = MembershipApplication.objects.filter(
            user=self.request.user,
            stokvel=self.stokvel,
            status__in=['submitted', 'under_review']
        ).first()

        context['existing_membership'] = existing_membership
        context['existing_application'] = existing_application

        return context


class ApplicationReviewView(LoginRequiredMixin, UpdateView):
    """Review and approve/reject membership applications"""
    model = MembershipApplication
    form_class = ApplicationReviewForm
    template_name = 'accounts/application_review.html'

    def get_success_url(self):
        return reverse('accounts:application_list', kwargs={
            'stokvel_pk': self.object.stokvel.pk
        })

    def form_valid(self, form):
        application = self.object
        decision = form.cleaned_data['decision']
        notes = form.cleaned_data['review_notes']

        try:
            if decision == 'approve':
                member = MembershipApplicationService.approve_application(
                    application=application,
                    reviewed_by=self.request.user,
                    notes=notes
                )

                messages.success(
                    self.request,
                    f'Application approved! {member.user.get_full_name()} is now a member.'
                )

            elif decision == 'reject':
                MembershipApplicationService.reject_application(
                    application=application,
                    reviewed_by=self.request.user,
                    notes=notes
                )

                messages.success(
                    self.request,
                    f'Application has been rejected.'
                )

            # Send decision email
            NotificationUtils.send_application_decision(application)

            return HttpResponseRedirect(self.get_success_url())

        except ValidationError as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        application = self.object

        # User profile completion
        context['profile_completion'] = ProfileUtils.calculate_profile_completion(
            application.user
        )

        # Check if stokvel can accept new members
        from stokvel.services import StokvelValidationService
        can_accept, reason = StokvelValidationService.can_accept_new_members(
            application.stokvel
        )
        context['can_accept_members'] = can_accept
        context['acceptance_reason'] = reason

        return context


class MemberBankAccountListView(LoginRequiredMixin, ListView):
    """List bank accounts for a member"""
    model = MemberBankAccount
    template_name = 'accounts/bank_account_list.html'
    context_object_name = 'bank_accounts'

    def dispatch(self, request, *args, **kwargs):
        self.member = get_object_or_404(Member, pk=kwargs['member_pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return MemberBankAccount.objects.filter(member=self.member)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['member'] = self.member
        context['primary_account'] = self.member.bank_accounts.filter(is_primary=True).first()
        return context


class MemberBankAccountCreateView(LoginRequiredMixin, CreateView):
    """Create a new bank account for a member"""
    model = MemberBankAccount
    form_class = MemberBankAccountForm
    template_name = 'accounts/bank_account_create.html'

    def dispatch(self, request, *args, **kwargs):
        self.member = get_object_or_404(Member, pk=kwargs['member_pk'])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        try:
            # Use service to add bank account
            account = MemberBankAccountService.add_bank_account(
                member=self.member,
                bank_name=form.cleaned_data['bank_name'],
                account_holder_name=form.cleaned_data['account_holder_name'],
                account_number=form.cleaned_data['account_number'],
                account_type=form.cleaned_data['account_type'],
                branch_code=form.cleaned_data['branch_code'],
                is_primary=form.cleaned_data['is_primary']
            )

            messages.success(
                self.request,
                f'Bank account added successfully for {self.member.user.get_full_name()}!'
            )

            return HttpResponseRedirect(
                reverse('accounts:bank_account_list', kwargs={'member_pk': self.member.pk})
            )

        except ValidationError as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['member'] = self.member
        return context


class MemberDashboardView(LoginRequiredMixin, DetailView):
    """Dashboard view for a member"""
    model = Member
    template_name = 'accounts/member_dashboard.html'
    context_object_name = 'member'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        member = self.object

        # Member summary
        context.update(MemberService.get_member_summary(member))

        # Recent activities
        context['recent_activities'] = member.activities.order_by('-created_date')[:10]

        # Profile completion
        context['profile_completion'] = ProfileUtils.calculate_profile_completion(member.user)

        # Engagement metrics
        context['engagement'] = MemberUtils.get_member_engagement_score(member)

        # Quick stats for contributions and penalties (will be enhanced with finances app)
        context['financial_summary'] = {
            'total_contributions': getattr(member, 'contributions', None),
            'outstanding_penalties': getattr(member, 'penalties', None),
        }

        # Bank account status
        context['bank_account_status'] = {
            'total_accounts': member.bank_accounts.count(),
            'verified_accounts': member.bank_accounts.filter(is_verified=True).count(),
            'primary_account': member.bank_accounts.filter(is_primary=True).first(),
        }

        return context


# AJAX Views
class VerifyBankAccountView(LoginRequiredMixin, DetailView):
    """AJAX view to verify a bank account"""
    model = MemberBankAccount

    def post(self, request, *args, **kwargs):
        account = self.get_object()

        try:
            MemberBankAccountService.verify_bank_account(
                account=account,
                verified_by=request.user
            )

            return JsonResponse({
                'success': True,
                'message': f'Bank account verified successfully!'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=400)


class SetPrimaryBankAccountView(LoginRequiredMixin, DetailView):
    """AJAX view to set primary bank account"""
    model = MemberBankAccount

    def post(self, request, *args, **kwargs):
        account = self.get_object()

        try:
            MemberBankAccountService.set_primary_account(account)

            return JsonResponse({
                'success': True,
                'message': f'Primary account updated successfully!'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=400)


class PromoteFromProbationView(LoginRequiredMixin, DetailView):
    """AJAX view to promote member from probation"""
    model = Member

    def post(self, request, *args, **kwargs):
        member = self.get_object()

        try:
            MemberService.promote_from_probation(
                member=member,
                promoted_by=request.user
            )

            return JsonResponse({
                'success': True,
                'message': f'{member.user.get_full_name()} promoted to active member!'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=400)


class MemberActivityView(LoginRequiredMixin, ListView):
    """View member activity history"""
    model = MemberActivity
    template_name = 'accounts/member_activity.html'
    context_object_name = 'activities'
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        self.member = get_object_or_404(Member, pk=kwargs['member_pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        queryset = MemberActivity.objects.filter(member=self.member)

        # Filter by activity type
        activity_type = self.request.GET.get('type')
        if activity_type:
            queryset = queryset.filter(activity_type=activity_type)

        # Filter by date range
        days = self.request.GET.get('days')
        if days:
            try:
                days_int = int(days)
                start_date = timezone.now() - timedelta(days=days_int)
                queryset = queryset.filter(created_date__gte=start_date)
            except ValueError:
                pass

        return queryset.order_by('-created_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['member'] = self.member
        context['type_filter'] = self.request.GET.get('type', '')
        context['days_filter'] = self.request.GET.get('days', '')

        # Activity summary
        context['activity_summary'] = MemberActivityService.get_member_activity_summary(
            self.member
        )

        return context


class StokvelMemberReportsView(LoginRequiredMixin, DetailView):
    """Member reports for a stokvel"""
    model = Stokvel
    template_name = 'accounts/member_reports.html'
    context_object_name = 'stokvel'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        stokvel = self.object

        # Get report parameters
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')

        if start_date:
            try:
                start_date = timezone.datetime.strptime(start_date, '%Y-%m-%d').date()
            except ValueError:
                start_date = None

        if end_date:
            try:
                end_date = timezone.datetime.strptime(end_date, '%Y-%m-%d').date()
            except ValueError:
                end_date = None

        # Generate reports
        from .utils import ReportUtils
        context['membership_report'] = ReportUtils.generate_membership_report(
            stokvel, start_date, end_date
        )

        # Member engagement scores
        engagement_data = []
        for member in stokvel.members.filter(status__in=['active', 'probation']):
            engagement = MemberUtils.get_member_engagement_score(member)
            engagement_data.append({
                'member': member,
                'engagement': engagement
            })

        # Sort by engagement score
        engagement_data.sort(key=lambda x: x['engagement']['score'], reverse=True)
        context['member_engagement'] = engagement_data

        return context