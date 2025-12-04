from django.urls import path
from . import views

urlpatterns = [
    path('health', views.HealthCheckView.as_view(), name='health'),
    path('shorten', views.ShortenURLView.as_view(), name='shorten'),
    path('stats/<str:short_code>', views.URLStatsView.as_view(), name='stats'),
    path('<str:short_code>', views.RedirectView.as_view(), name='redirect'),
]
