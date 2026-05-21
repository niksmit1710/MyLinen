from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.mail import EmailMultiAlternatives
from django.shortcuts import render


def _email_config_status():
    resend_key = getattr(settings, 'ANYMAIL', {}).get('RESEND_API_KEY', '')
    return {
        'backend': settings.EMAIL_BACKEND,
        'host': settings.EMAIL_HOST,
        'port': settings.EMAIL_PORT,
        'use_tls': settings.EMAIL_USE_TLS,
        'use_ssl': settings.EMAIL_USE_SSL,
        'host_user_set': bool(settings.EMAIL_HOST_USER),
        'host_password_set': bool(settings.EMAIL_HOST_PASSWORD),
        'default_from_email': settings.DEFAULT_FROM_EMAIL,
        'dummy_backend': settings.EMAIL_BACKEND.endswith('.dummy.EmailBackend'),
        'resend_configured': bool(resend_key),
    }


@staff_member_required
def email_diagnostics(request):
    status = _email_config_status()
    recipient = request.POST.get('to', '').strip() or request.user.email

    if request.method == 'POST':
        if not recipient:
            messages.error(request, 'Enter a recipient email address.')
        elif status['dummy_backend']:
            messages.error(request, 'Email is disabled because the dummy backend is active. Set RESEND_API_KEY or SMTP credentials.')
        else:
            message = EmailMultiAlternatives(
                subject='MyLinen email diagnostics',
                body='If you received this, MyLinen email sending is working.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[recipient],
                reply_to=[settings.EMAIL_HOST_USER] if settings.EMAIL_HOST_USER else None,
            )

            try:
                sent_count = message.send(fail_silently=False)
            except Exception as exc:
                messages.error(request, f'Test email failed: {exc}')
            else:
                if sent_count:
                    messages.success(request, f'Test email sent to {recipient}.')
                else:
                    messages.error(request, 'Email backend returned 0 sent messages.')

    return render(request, 'notifications/email_diagnostics.html', {
        'email_status': status,
        'recipient': recipient,
    })
