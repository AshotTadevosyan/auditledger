from django.urls import include, path
from django.contrib.auth.views import LogoutView
from ledger.auth_views import LedgerLoginView, health

urlpatterns = [
    path('healthz/', health, name='health'),
    path('accounts/login/', LedgerLoginView.as_view(), name='login'),
    path('accounts/logout/', LogoutView.as_view(), name='logout'),
    path('', include('ledger.urls')),
]
