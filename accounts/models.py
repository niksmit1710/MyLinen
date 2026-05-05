from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.db import models


class User(AbstractUser):
    USER_TYPES = (
        ('customer', 'Customer'),
        ('seller', 'Seller'),
        ('shipper', 'Shipper'),
    )
    
    user_type = models.CharField(max_length=10, choices=USER_TYPES)
    phone_number = models.CharField(max_length=15, unique=True, null=True, blank=True)

    def get_display_name(self):
        """
        Return a privacy-safe display name for public-facing content.
        Anonymizes names by masking (e.g., 'John Doe' -> 'J*** D***').
        """
        name = self.get_full_name().strip()
        
        if not name:
            # Look up the most recent order's full_name
            from orders.models import Order
            name = (
                Order.objects
                .filter(user=self)
                .order_by('-created_at')
                .values_list('full_name', flat=True)
                .first()
            )

        if name:
            parts = name.split()
            if len(parts) >= 2:
                # Mask first and last name: 'John Doe' -> 'J*** D***'
                first = parts[0]
                last = parts[-1]
                return f"{first[0]}*** {last[0]}***"
            elif len(parts) == 1:
                # Single name: 'John' -> 'J***'
                return f"{name[0]}***"
        
        return 'Verified Customer'


class Wallet(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='wallet'
    )
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user} — ₹{self.balance}"


class WalletTransaction(models.Model):
    TRANSACTION_TYPES = [
        ('credit', 'Credit'),
        ('debit', 'Debit'),
    ]

    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transaction_type.title()} ₹{self.amount} — {self.description}"