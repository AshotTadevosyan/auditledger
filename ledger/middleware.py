from ipaddress import ip_address
from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import Http404, HttpResponseForbidden
from .models import EngagementMembership


class AccessMiddleware:
    """Local loopback access, or fail-closed authenticated engagement access."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.HOSTED:
            try:
                local = ip_address(request.META.get('REMOTE_ADDR', '')).is_loopback
            except ValueError:
                local = False
            if not local:
                return HttpResponseForbidden('Audit Ledger is restricted to this computer.')
        response = self.get_response(request)
        response['Cache-Control'] = 'no-store'
        response['Referrer-Policy'] = 'same-origin'
        response['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        )
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        request.can_edit = not settings.HOSTED
        if not settings.HOSTED:
            return None
        name = request.resolver_match.url_name
        if name in {'login', 'logout', 'health'}:
            return None
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.is_active:
            return HttpResponseForbidden('Account disabled.')
        # Every newly added application route must be classified explicitly.
        reads = {'dashboard', 'overview', 'register', 'detail', 'report', 'export', 'history'}
        writes = {'create_engagement', 'edit_engagement', 'engagement_transition',
                  'create', 'edit', 'transition', 'delete', 'progress'}
        if name not in reads | writes:
            return HttpResponseForbidden('Access denied.')
        if request.user.is_superuser:
            request.can_edit = True
            return None
        if name == 'dashboard':
            return None
        if name == 'create_engagement':
            if request.user.has_perm('ledger.add_engagement'):
                return None
            return HttpResponseForbidden('You cannot create engagements.')
        engagement_id = view_kwargs.get('engagement_id') or view_kwargs.get('pk')
        role = EngagementMembership.objects.filter(
            user=request.user, engagement_id=engagement_id).values_list('role', flat=True).first()
        if role is None:
            raise Http404()
        request.can_edit = role == 'editor'
        if name in writes and not request.can_edit:
            return HttpResponseForbidden('This engagement is read-only for your account.')
        return None
