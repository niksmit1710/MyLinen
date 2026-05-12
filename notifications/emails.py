from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
import threading

class EmailThread(threading.Thread):
    def __init__(self, email):
        self.email = email
        threading.Thread.__init__(self)

    def run(self):
        try:
            print(f"DEBUG: Background thread starting email send...")
            self.email.send()
            print(f"DEBUG: Background thread email send complete.")
        except Exception as e:
            print(f"DEBUG: Background thread email error: {e}")

def send_order_email(order, event_type, context_extra=None):
    """
    Utility to send order lifecycle emails.
    event_type: 'placed', 'confirmed', 'shipped', 'delivered', 'cancelled', etc.
    """
    print(f"DEBUG: Preparing email for event: {event_type}")
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
        'customer_name': order.full_name,
        'event_type': event_type,
        'site_name': 'MyLinen',
        'site_url': settings.SITE_URL if hasattr(settings, 'SITE_URL') else 'http://localhost:8000',
        'year': timezone.now().year,
    }
    if context_extra:
        context.update(context_extra)

    html_content = render_to_string('notifications/emails/order_update.html', context)
    text_content = render_to_string('notifications/emails/order_update.txt', context)

    email = EmailMultiAlternatives(
        subject,
        text_content,
        settings.DEFAULT_FROM_EMAIL,
        [order.email or order.user.email]
    )
    email.attach_alternative(html_content, "text/html")
    
    # Send asynchronously
    EmailThread(email).start()
