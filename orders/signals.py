from django.db.models.signals import post_save, post_init
from django.db import transaction
from django.dispatch import receiver
from .models import Order, ReturnExchangeRequest
from notifications.emails import send_order_email

@receiver(post_init, sender=Order)
def remember_status(sender, instance, **kwargs):
    instance._previous_status = instance.status

@receiver(post_save, sender=Order)
def order_status_changed(sender, instance, created, **kwargs):
    if created:
        # Order Placed — bind instance by default arg so the callback is not affected
        # by later mutations before the transaction commits.
        transaction.on_commit(lambda o=instance: send_order_email(o, 'placed'))
    else:
        # Check if status has changed
        if hasattr(instance, '_previous_status') and instance._previous_status != instance.status:
            if instance.status in ['confirmed', 'shipped', 'delivered', 'cancelled']:
                event_type = instance.status
                transaction.on_commit(
                    lambda o=instance, e=event_type: send_order_email(o, e)
                )
            instance._previous_status = instance.status

@receiver(post_init, sender=ReturnExchangeRequest)
def remember_request_status(sender, instance, **kwargs):
    instance._previous_status = instance.status

@receiver(post_save, sender=ReturnExchangeRequest)
def return_request_status_changed(sender, instance, created, **kwargs):
    if not created:
        if hasattr(instance, '_previous_status') and instance._previous_status != instance.status:
            event_map = {
                'approved': f'{instance.request_type}_approved',
                'rejected': f'{instance.request_type}_rejected',
                'pickup_scheduled': 'pickup_scheduled',
                'completed': 'pickup_completed'
            }
            
            event_type = event_map.get(instance.status)
            if event_type:
                order = instance.order
                transaction.on_commit(
                    lambda o=order, e=event_type: send_order_email(o, e)
                )
            instance._previous_status = instance.status
