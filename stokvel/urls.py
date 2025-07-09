from django.urls import path

app_name = 'stokvel'

urlpatterns = [
    # Main stokvel views
    path('', StokvelListView.as_view(), name='list'),
    path('create/', StokvelCreateView.as_view(), name='create'),
    path('<uuid:pk>/', StokvelDetailView.as_view(), name='detail'),
    path('<uuid:pk>/edit/', StokvelUpdateView.as_view(), name='update'),
    path('<uuid:pk>/dashboard/', StokvelDashboardView.as_view(), name='dashboard'),
    path('<uuid:pk>/reports/', StokvelReportsView.as_view(), name='reports'),

    # Constitution management
    path('<uuid:stokvel_pk>/constitution/', ConstitutionDetailView.as_view(), name='constitution_detail'),
    path('<uuid:stokvel_pk>/constitution/edit/', ConstitutionUpdateView.as_view(), name='constitution_update'),

    # Contribution rules management
    path('<uuid:stokvel_pk>/contribution-rules/', ContributionRuleListView.as_view(), name='contribution_rules'),
    path('<uuid:stokvel_pk>/contribution-rules/create/', ContributionRuleCreateView.as_view(),
         name='contribution_rule_create'),

    # Penalty rules management
    path('<uuid:stokvel_pk>/penalty-rules/', PenaltyRuleListView.as_view(), name='penalty_rules'),
    path('<uuid:stokvel_pk>/penalty-rules/create/', PenaltyRuleCreateView.as_view(), name='penalty_rule_create'),

    # Cycles management
    path('<uuid:stokvel_pk>/cycles/', CycleListView.as_view(), name='cycles'),
    path('<uuid:stokvel_pk>/cycles/create/', CycleCreateView.as_view(), name='cycle_create'),

    # Bank accounts management
    path('<uuid:stokvel_pk>/bank-accounts/', BankAccountListView.as_view(), name='bank_accounts'),
    path('<uuid:stokvel_pk>/bank-accounts/create/', BankAccountCreateView.as_view(), name='bank_account_create'),

    # AJAX endpoints
    path('ajax/cycle/<uuid:pk>/activate/', ActivateCycleView.as_view(), name='ajax_activate_cycle'),
    path('ajax/account/<uuid:pk>/set-primary/', SetPrimaryAccountView.as_view(), name='ajax_set_primary_account'),
    path('ajax/rule/<str:rule_type>/<uuid:pk>/deactivate/', DeactivateRuleView.as_view(),
         name='ajax_deactivate_rule'),
]

