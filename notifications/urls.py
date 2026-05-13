from django.urls import path

from . import views


urlpatterns = [
    path('email-diagnostics/', views.email_diagnostics, name='email_diagnostics'),
]
