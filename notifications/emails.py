import logging
import threading

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


logger = logging.getLogger(__name__)


class EmailThread(threading.Thread):
    def __init__(self, email):
        super().__init__()
        self.email = email

    def run(self):
        _send_message(self.email)


def _email_backend_is_disabled():
    return settings.EMAIL_BACKEND.endswith('.dummy.EmailBackend')


def _order_recipients(order):
    recipients = [order.email or getattr(order.user, 'email', '')]
    return [email.strip() for email in recipients if email and email.strip()]


def _send_message(email):
    try:
        sent_count = email.send(fail_silently=False)
    except Exception:
        logger.exception("Transactional email failed: %s", email.subject)
        return False

    if sent_count:
        logger.info("Transactional email sent: %s", email.subject)
        return True

    logger.warning("Transactional email was not sent by backend: %s", email.subject)
    return False


def send_order_email(order, event_type, context_extra=None, async_send=None):
    """
    Send an order lifecycle email.

    event_type: placed, confirmed, shipped, delivered, cancelled, return_approved,
    return_rejected, exchange_approved, exchange_rejected, pickup_scheduled,
    pickup_completed.
    """
    recipients = _order_recipients(order)
    if not recipients:
        logger.warning("Skipping order email for order %s: no recipient email.", order.id)
        return False

    if _email_backend_is_disabled():
        logger.warning(
            "Skipping order email for order %s: EMAIL_BACKEND is dummy. "
            "Set RESEND_API_KEY (API email, Render free) or EMAIL_HOST_USER and EMAIL_HOST_PASSWORD or EMAIL_BACKEND.",
            order.id,
        )
        return False

    subject_map = {
        'placed': f'Order Placed Successfully - #{order.id}',
        'confirmed': f'Your Order #{order.id} has been Confirmed',
        'shipped': f'Good News! Your Order #{order.id} has been Shipped',
        'delivered': f'Your Order #{order.id} has been Delivered',
        'cancelled': f'Order #{order.id} has been Cancelled',
        'return_approved': f'Return Request Approved for Order #{order.id}',
        'return_rejected': f'Update on your Return Request - Order #{order.id}',
        'exchange_approved': f'Exchange Request Approved for Order #{order.id}',
        'exchange_rejected': f'Update on your Exchange Request - Order #{order.id}',
        'pickup_scheduled': f'Pickup Scheduled for your Order #{order.id}',
        'pickup_completed': f'Pickup Completed for your Order #{order.id}',
    }
    subject = subject_map.get(event_type, f'Update on your MyLinen Order #{order.id}')

    from django.utils import timezone
    context = {
        'order': order,
        'customer_name': order.full_name or order.user.get_full_name() or order.user.username,
        'event_type': event_type,
        'subject': subject,
        'site_name': 'MyLinen',
        'site_url': settings.SITE_URL.rstrip('/'),
        'year': timezone.now().year,
    }
    if context_extra:
        context.update(context_extra)

    text_content = render_to_string('notifications/emails/order_update.txt', context)
    html_content = render_to_string('notifications/emails/order_update.html', context)

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
        reply_to=[settings.EMAIL_HOST_USER] if settings.EMAIL_HOST_USER else None,
    )
    email.attach_alternative(html_content, "text/html")

    if async_send is None:
        async_send = settings.EMAIL_SEND_ASYNC

    if async_send:
        EmailThread(email).start()
        return True

    return _send_message(email)
