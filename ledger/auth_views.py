from django.contrib.auth.views import LoginView
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.http import require_safe


class LedgerLoginView(LoginView):
    template_name = 'registration/login.html'


@require_safe
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse({'status': 'unavailable'}, status=503)
    return JsonResponse({'status': 'ok'})
