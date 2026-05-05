from django.conf import settings
from django.db import models
from django.utils import timezone
from accounts.models import User
from products.models import Product, Size

import os
import uuid


STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('confirmed', 'Confirmed'),
    ('shipped', 'Shipped'),
    ('delivered', 'Delivered'),
]
PAYMENT_METHODS = [
    ('cod', 'Cash on Delivery'),
    ('online', 'Online Payment'),
]
DISCOUNT_TYPE_CHOICES = [
    ('percentage', 'Percentage (%)'),
    ('fixed', 'Fixed Amount (Rs.)'),
]


class Coupon(models.Model):
    code = models.CharField(max_length=50, unique=True)
    discount_type = models.CharField(max_length=10, choices=DISCOUNT_TYPE_CHOICES, default='percentage')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2,
                                         help_text="Percentage (0-100) or flat Rs. amount")
    min_order_value = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                          help_text="Minimum cart total required to use this coupon")
    max_discount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True,
                                       help_text="Maximum discount cap for percentage coupons (leave blank for no cap)")
    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_to = models.DateTimeField()
    usage_limit = models.IntegerField(blank=True, null=True,
                                      help_text="Max number of times this coupon can be used (leave blank for unlimited)")
    used_count = models.IntegerField(default=0, editable=False)

    class Meta:
        ordering = ['-valid_from']

    def __str__(self):
        return self.code

    def is_valid(self):
        now = timezone.now()
        return (
            self.is_active and
            self.valid_from <= now <= self.valid_to and
            (self.usage_limit is None or self.used_count < self.usage_limit)
        )

    def calculate_discount(self, cart_total):
        """Return the discount amount (Decimal) for the given cart_total."""
        if self.discount_type == 'percentage':
            discount = (cart_total * self.discount_value) / 100
            if self.max_discount is not None:
                discount = min(discount, self.max_discount)
        else:
            discount = self.discount_value
        return min(discount, cart_total)  # discount can't exceed cart total


class Order(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=200)
    email = models.EmailField(max_length=254, null=True, blank=True)
    phone_number = models.CharField(max_length=15, null=True, blank=True)
    address = models.TextField()
    pincode = models.CharField(max_length=10)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100, null=True, blank=True)
    subtotal_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, blank=True, null=True, related_name='orders')
    coupon_code = models.CharField(max_length=50, blank=True, null=True)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    payment_id = models.CharField(max_length=200, blank=True, null=True)
    is_paid = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHODS)

    def __str__(self):
        return f"Order {self.id}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    variant = models.ForeignKey("products.ProductVariant", on_delete=models.SET_NULL, null=True, blank=True)
    
    # Snapshot data to preserve order history
    product_name_at_purchase = models.CharField(max_length=255, null=True, blank=True)
    color_at_purchase = models.CharField(max_length=50, null=True, blank=True)
    size_at_purchase = models.CharField(max_length=10, null=True, blank=True)
    price_at_purchase = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    quantity = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2) # Keep this for compatibility/totals

    def __str__(self):
        return f"{self.product_name_at_purchase} ({self.color_at_purchase} - {self.size_at_purchase})"


# ===== Return & Exchange System =====

RETURN_EXCHANGE_TYPES = [
    ('return', 'Return'),
    ('exchange', 'Exchange'),
]

RETURN_REASONS = [
    ('size_issue', 'Size doesn\'t fit'),
    ('damaged', 'Product is damaged'),
    ('wrong_item', 'Received wrong item'),
    ('quality_issue', 'Quality not as expected'),
    ('other', 'Other'),
]

REQUEST_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
    ('pickup_scheduled', 'Pickup Scheduled'),
    ('completed', 'Completed'),
]

RETURN_WINDOW_DAYS = 7


class ReturnExchangeRequest(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='return_requests'
    )
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name='return_requests'
    )
    order_item = models.ForeignKey(
        OrderItem, on_delete=models.CASCADE, related_name='return_requests'
    )
    request_type = models.CharField(max_length=10, choices=RETURN_EXCHANGE_TYPES)
    reason = models.CharField(max_length=20, choices=RETURN_REASONS)
    comment = models.TextField(blank=True)
    exchange_size = models.ForeignKey(
        Size, on_delete=models.SET_NULL, null=True, blank=True,
        help_text="New size for exchange (only for exchange requests)"
    )
    status = models.CharField(
        max_length=20, choices=REQUEST_STATUS_CHOICES, default='pending'
    )
    admin_notes = models.TextField(blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-requested_at']

    def __str__(self):
        return f"{self.get_request_type_display()} — Order #{self.order_id} — {self.order_item.product_name_at_purchase}"

    @property
    def is_active(self):
        """Request is active if not completed or rejected."""
        return self.status not in ('completed', 'rejected')


def return_image_upload_path(instance, filename):
    """Generate a secure upload path with UUID filename."""
    ext = os.path.splitext(filename)[1].lower()
    safe_name = f"{uuid.uuid4().hex}{ext}"
    return f"returns/{safe_name}"


class ReturnExchangeImage(models.Model):
    request = models.ForeignKey(
        ReturnExchangeRequest, on_delete=models.CASCADE, related_name='images'
    )
    image = models.ImageField(upload_to=return_image_upload_path)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['position']

    def __str__(self):
        return f"Return #{self.request_id} — Image {self.position}"
