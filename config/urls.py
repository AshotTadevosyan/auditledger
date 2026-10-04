from django.urls import include, path
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.contrib.staticfiles.views import serve

urlpatterns = [path('', include('ledger.urls'))]
# Local-only application; serve packaged assets even with DEBUG=False.
urlpatterns += [path('static/<path:path>', serve, {'insecure': True})]
