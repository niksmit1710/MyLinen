from django.db.models.signals import post_save, post_init
from django.dispatch import receiver
from .models import Order, ReturnExchangeRequest
from notifications.emails import send_order_email

@receiver(post_init, sender=Order)
def remember_status(sender, instance, **kwargs):
    instance._previous_status = instance.status

@receiver(post_save, sender=Order)
def order_status_changed(sender, instance, created, **kwargs):
    if created:
        # Order Placed
        print(f"DEBUG: Triggering 'placed' email for Order #{instance.id}")
        send_order_email(instance, 'placed')
    else:
        # Check if status has changed
        if hasattr(instance, '_previous_status') and instance._previous_status != instance.status:
            print(f"DEBUG: Status changed for Order #{instance.id}: {instance._previous_status} -> {instance.status}")
            if instance.status in ['confirmed', 'shipped', 'delivered', 'cancelled']:
                print(f"DEBUG: Triggering '{instance.status}' email for Order #{instance.id}")
                send_order_email(instance, instance.status)

@receiver(post_init, sender=ReturnExchangeRequest)
def remember_request_status(sender, instance, **kwargs):
    instance._previous_status = instance.status

@receiver(post_save, sender=ReturnExchangeRequest)
def return_request_status_changed(sender, instance, created, **kwargs):
    if not created:
        if hasattr(instance, '_previous_status') and instance._previous_status != instance.status:
            print(f"DEBUG: Status changed for Request #{instance.id}: {instance._previous_status} -> {instance.status}")
            event_map = {
                'approved': f'{instance.request_type}_approved',
                'rejected': f'{instance.request_type}_rejected',
                'pickup_scheduled': 'pickup_scheduled',
                'completed': 'pickup_completed'
            }
            
            event_type = event_map.get(instance.status)
            if event_type:
                print(f"DEBUG: Triggering '{event_type}' email for Order #{instance.order.id}")
                send_order_email(instance.order, event_type)
