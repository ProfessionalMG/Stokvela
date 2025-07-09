from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', RedirectView.as_view(url='/stokvels/', permanent=False)),  # Redirect root to stokvels
    path('stokvels/', include('stokvel.urls')),
    # path('accounts/', include('accounts.urls')),  # To be added later
    # path('finances/', include('finances.urls')),  # To be added later
]