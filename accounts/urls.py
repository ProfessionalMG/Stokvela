from django.urls import path
from django.contrib.auth.views import LogoutView

app_name = 'accounts'

urlpatterns = [
    # Authentication
    path('login/', CustomLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(next_page='accounts:login'), name='logout'),
    path('register/', UserRegistrationView.as_view(), name='register'),

    # User Profile Management
    path('profile/', UserProfileView.as_view(), name='profile'),

    # Member Management for Stokvels
    path('stokvel/<uuid:stokvel_pk>/members/', views.MemberListView.as_view(), name='member_list'),
    path('member/<uuid:pk>/', MemberDetailView.as_view(), name='member_detail'),
    path('member/<uuid:pk>/edit/', MemberUpdateView.as_view(), name='member_update'),
    path('member/<uuid:pk>/dashboard/', MemberDashboardView.as_view(), name='member_dashboard'),
    path('member/<uuid:pk>/activity/', MemberActivityView.as_view(), name='member_activity'),

    # Membership Applications
    path('stokvel/<uuid:stokvel_pk>/apply/', MembershipApplicationCreateView.as_view(), name='apply'),
    path('stokvel/<uuid:stokvel_pk>/applications/', MembershipApplicationListView.as_view(),
         name='application_list'),
    path('application/<uuid:pk>/review/', ApplicationReviewView.as_view(), name='application_review'),

    # Bank Account Management
    path('member/<uuid:member_pk>/bank-accounts/', MemberBankAccountListView.as_view(), name='bank_account_list'),
    path('member/<uuid:member_pk>/bank-accounts/add/', MemberBankAccountCreateView.as_view(),
         name='bank_account_create'),

    # Reports
    path('stokvel/<uuid:pk>/member-reports/', StokvelMemberReportsView.as_view(), name='member_reports'),

    # AJAX endpoints
    path('ajax/bank-account/<uuid:pk>/verify/', VerifyBankAccountView.as_view(), name='ajax_verify_bank_account'),
    path('ajax/bank-account/<uuid:pk>/set-primary/', SetPrimaryBankAccountView.as_view(),
         name='ajax_set_primary_bank_account'),
    path('ajax/member/<uuid:pk>/promote-probation/', PromoteFromProbationView.as_view(),
         name='ajax_promote_probation'),
]