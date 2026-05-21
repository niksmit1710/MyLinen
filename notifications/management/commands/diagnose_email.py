from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Show email configuration and optionally send a test transactional email."

    def add_arguments(self, parser):
        parser.add_argument('--to', help='Recipient email address for a live test send.')

    def handle(self, *args, **options):
        self.stdout.write(f"EMAIL_BACKEND: {settings.EMAIL_BACKEND}")
        self.stdout.write(f"EMAIL_HOST: {settings.EMAIL_HOST}")
        self.stdout.write(f"EMAIL_PORT: {settings.EMAIL_PORT}")
        self.stdout.write(f"EMAIL_USE_TLS: {settings.EMAIL_USE_TLS}")
        self.stdout.write(f"EMAIL_USE_SSL: {settings.EMAIL_USE_SSL}")
        self.stdout.write(f"EMAIL_HOST_USER set: {bool(settings.EMAIL_HOST_USER)}")
        self.stdout.write(f"EMAIL_HOST_PASSWORD set: {bool(settings.EMAIL_HOST_PASSWORD)}")
        self.stdout.write(f"DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}")
        self.stdout.write(f"DEBUG: {settings.DEBUG}")
        self.stdout.write(f"EMAIL_SEND_ASYNC: {getattr(settings, 'EMAIL_SEND_ASYNC', False)}")
        resend_on = bool(getattr(settings, 'ANYMAIL', {}).get('RESEND_API_KEY'))
        self.stdout.write(f"RESEND_API_KEY set: {resend_on}")

        if settings.EMAIL_BACKEND == 'anymail.backends.resend.EmailBackend':
            self.stdout.write(self.style.SUCCESS(
                "Using Resend API over HTTPS (works on Render free web services where SMTP is blocked)."
            ))

        if settings.EMAIL_BACKEND == 'django.core.mail.backends.console.EmailBackend':
            self.stdout.write(self.style.WARNING(
                "Console email backend is active (typical when DEBUG=True). "
                "Messages are printed to the server log, not delivered to inboxes."
            ))

        if settings.EMAIL_BACKEND.endswith('.dummy.EmailBackend'):
            self.stdout.write(self.style.WARNING(
                "Email is disabled because the dummy backend is active. "
                "Set RESEND_API_KEY for API email (Render free), or set EMAIL_HOST_USER and "
                "EMAIL_HOST_PASSWORD for SMTP, or set EMAIL_BACKEND explicitly."
            ))

        recipient = options.get('to')
        if not recipient:
            return

        message = EmailMultiAlternatives(
            subject='MyLinen email diagnostics',
            body='If you received this, MyLinen outbound email is working.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient],
            reply_to=[settings.EMAIL_HOST_USER] if settings.EMAIL_HOST_USER else None,
        )

        try:
            sent_count = message.send(fail_silently=False)
        except Exception as exc:
            raise CommandError(f"Test email failed: {exc}") from exc

        if not sent_count:
            raise CommandError("Email backend returned 0 sent messages.")

        self.stdout.write(self.style.SUCCESS(f"Test email sent to {recipient}."))
