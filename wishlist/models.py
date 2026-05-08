from django.db import models
from django.conf import settings
from products.models import ProductVariant

class Wishlist(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wishlist')
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name='wishlisted_by', null=True, blank=True)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'variant')
        ordering = ['-added_at']

    def __str__(self):
        return f"{self.user.username}'s wishlist: {self.variant.product.name} ({self.variant.color.name})"
