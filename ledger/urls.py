from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('engagements/new/', views.edit, name='create_engagement'),
    path('engagements/<uuid:engagement_id>/', views.overview, name='overview'),
    path('engagements/<uuid:pk>/edit/', views.edit, name='edit_engagement'),
    path('engagements/<uuid:engagement_id>/state/<str:target>/', views.transition_view, name='engagement_transition'),
    path('engagements/<uuid:engagement_id>/report/', views.report, name='report'),
    path('engagements/<uuid:engagement_id>/export/<str:format>/', views.report, name='export'),
    path('engagements/<uuid:engagement_id>/history/', views.history, name='history'),
    path('engagements/<uuid:engagement_id>/actions/<uuid:pk>/progress/', views.progress, name='progress'),
    path('engagements/<uuid:engagement_id>/<str:kind>/', views.register, name='register'),
    path('engagements/<uuid:engagement_id>/<str:kind>/new/', views.edit, name='create'),
    path('engagements/<uuid:engagement_id>/<str:kind>/<uuid:pk>/', views.detail, name='detail'),
    path('engagements/<uuid:engagement_id>/<str:kind>/<uuid:pk>/edit/', views.edit, name='edit'),
    path('engagements/<uuid:engagement_id>/<str:kind>/<uuid:pk>/state/<str:target>/', views.transition_view, name='transition'),
    path('engagements/<uuid:engagement_id>/<str:kind>/<uuid:pk>/delete/', views.delete_view, name='delete'),
]
