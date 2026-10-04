from ipaddress import ip_address
from django.http import HttpResponseForbidden


class LocalOnlyMiddleware:
    """The unauthenticated MVP accepts loopback clients only, including exports."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
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
