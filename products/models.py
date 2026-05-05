import os
import uuid

from django.db import models
from django.conf import settings


class Color(models.Model):
    name = models.CharField(max_length=50, unique=True)
    hex_code = models.CharField(
        max_length=7,
        help_text="Hex colour code, e.g. #FF5733",
        default='#000000'
    )

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

class Category(models.Model):
    name = models.CharField(max_length=100)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='subcategories'
    )

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} → {self.name}"
        return self.name

class Product(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    mrp = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="[DEPRECATED] Use Variant MRP. Maximum Retail Price (Strikethrough price)")
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="[DEPRECATED] Use Variant Price. Selling Price")
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    color = models.ForeignKey(
        'Color',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products'
    )
    image = models.ImageField(upload_to='products/', null=True, blank=True, help_text="[DEPRECATED] Use Variant images instead.")

    def __str__(self):
        return self.name

    @property
    def discount_percentage(self):
        # Fallback to first variant or deprecated fields
        variant = self.variants.all()[0] if self.variants.all() else None
        if variant:
            mrp = variant.current_mrp
            price = variant.current_price
        else:
            mrp = self.mrp
            price = self.price

        if mrp and mrp > price:
            return int(((mrp - price) / mrp) * 100)
        return 0

    @property
    def display_price(self):
        variant = self.variants.all()[0] if self.variants.all() else None
        return variant.current_price if variant else self.price

    @property
    def base_price(self):
        variant = self.variants.all()[0] if self.variants.all() else None
        return variant.price if variant else self.price

    @property
    def is_on_sale(self):
        variant = self.variants.all()[0] if self.variants.all() else None
        if variant:
            return variant.is_on_sale
        return False

    @property
    def display_mrp(self):
        variant = self.variants.all()[0] if self.variants.all() else None
        return variant.current_mrp if variant else self.mrp

    @property
    def primary_image(self):
        """Return the first variant's primary image or fall back to the deprecated field."""
        # 1. Try first variant's image
        variant = self.variants.all()[0] if self.variants.all() else None
        if variant:
            img = variant.primary_image
            if img: return img
        
        # 2. Try product-level gallery images (deprecated)
        img = self.deprecated_images.all()[0] if self.deprecated_images.all() else None
        if img: return img.image

        # 3. Fallback to deprecated main image field
        return self.image

    @property
    def all_images(self):
        """Return all gallery images across variants."""
        all_imgs = []
        for variant in self.variants.all():
            if variant.image:
                all_imgs.append(variant.image)
            all_imgs.extend([img.image for img in variant.images.all()])
        
        # Add product-level gallery images
        all_imgs.extend([img.image for img in self.deprecated_images.all()])
        
        if not all_imgs and self.image:
            return [self.image]
        return all_imgs


class ProductVariant(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='variants'
    )
    color = models.ForeignKey(
        Color,
        on_delete=models.CASCADE,
        related_name='variants'
    )
    mrp = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True, 
        help_text="Override MRP for this color"
    )
    price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True, 
        help_text="Override Price for this color"
    )
    image = models.ImageField(
        upload_to='products/variants/', 
        null=True, 
        blank=True,
        help_text="Primary image for this color (Optional if gallery images exist)"
    )
    is_active = models.BooleanField(default=True)

    # Sale Fields
    sale_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Price during sale"
    )
    sale_active = models.BooleanField(default=False)
    sale_start = models.DateTimeField(null=True, blank=True)
    sale_end = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('product', 'color')
        verbose_name = "Product Variant"
        verbose_name_plural = "Product Variants"

    def __str__(self):
        return f"{self.product.name} - {self.color.name}"

    def get_effective_price(self):
        """Returns the sale price if sale is active and valid, else returns selling price."""
        from django.utils import timezone
        now = timezone.now()
        
        # Check if sale is active
        if self.sale_active and self.sale_price is not None:
            # Check date range if specified
            start_ok = not self.sale_start or now >= self.sale_start
            end_ok = not self.sale_end or now <= self.sale_end
            
            if start_ok and end_ok:
                return self.sale_price
        
        return self.price or self.product.price

    @property
    def is_on_sale(self):
        from django.utils import timezone
        now = timezone.now()
        if self.sale_active and self.sale_price is not None:
            start_ok = not self.sale_start or now >= self.sale_start
            end_ok = not self.sale_end or now <= self.sale_end
            return start_ok and end_ok
        return False

    @property
    def current_price(self):
        return self.get_effective_price()

    @property
    def current_mrp(self):
        return self.mrp or self.product.mrp

    @property
    def primary_image(self):
        """Return this variant's image or the first image from its gallery."""
        if self.image:
            return self.image
        img = self.images.all()[0] if self.images.all() else None
        return img.image if img else None


class ProductImage(models.Model):
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name='images',
        null=True, # Temporarily null for migration
        blank=True
    )
    # Keeping product for migration reference
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='deprecated_images',
        null=True,
        blank=True
    )
    image = models.ImageField(upload_to='products/')
    position = models.PositiveIntegerField(default=0, help_text="Display order (lower = first)")

    class Meta:
        ordering = ['position']

    def __str__(self):
        return f"Image {self.position}"
    
    
class Size(models.Model):
    name = models.CharField(max_length=10)  # S, M, L, XL

    def __str__(self):
        return self.name
    
    
class ProductSizeStock(models.Model):
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name='size_stocks',
        null=True, # Temporarily null for migration
        blank=True
    )
    # Keeping product for migration reference
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='deprecated_size_stocks',
        null=True,
        blank=True
    )
    size = models.ForeignKey(Size, on_delete=models.CASCADE)
    stock = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = (('variant', 'size'), ('product', 'size')) # Temporary to allow migration

    def __str__(self):
        name = self.variant.product.name if self.variant else self.product.name
        return f"{name} - {self.size.name} ({self.stock})"


class Review(models.Model):
    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='reviews'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reviews'
    )
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES)
    title = models.CharField(max_length=200, blank=True)
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('product', 'user')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.product.name} ({self.rating}★)"

    @property
    def star_range(self):
        return range(self.rating)

    @property
    def empty_star_range(self):
        return range(5 - self.rating)


def review_image_upload_path(instance, filename):
    """Generate a secure upload path with UUID filename."""
    ext = os.path.splitext(filename)[1].lower()
    safe_name = f"{uuid.uuid4().hex}{ext}"
    return f"reviews/{safe_name}"


class ReviewImage(models.Model):
    ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
    MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB
    MAX_IMAGES_PER_REVIEW = 5
    MAX_DIMENSION = 1200  # px

    review = models.ForeignKey(
        Review,
        on_delete=models.CASCADE,
        related_name='review_images'
    )
    image = models.ImageField(upload_to=review_image_upload_path)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['position']

    def __str__(self):
        return f"Review #{self.review_id} - Image {self.position}"

    def save(self, *args, **kwargs):
        """Save and then compress/resize the image using Pillow."""
        super().save(*args, **kwargs)
        self._compress_image()

    def _compress_image(self):
        """Resize to max 1200px wide and re-save as optimised JPEG/PNG."""
        from PIL import Image as PILImage

        img_path = self.image.path
        try:
            img = PILImage.open(img_path)
        except Exception:
            return

        # Resize if wider than MAX_DIMENSION
        if img.width > self.MAX_DIMENSION:
            ratio = self.MAX_DIMENSION / img.width
            new_size = (self.MAX_DIMENSION, int(img.height * ratio))
            img = img.resize(new_size, PILImage.LANCZOS)

        # Determine save format
        ext = os.path.splitext(img_path)[1].lower()
        if ext in ('.jpg', '.jpeg'):
            img = img.convert('RGB')
            img.save(img_path, 'JPEG', quality=85, optimize=True)
        elif ext == '.png':
            img.save(img_path, 'PNG', optimize=True)
        elif ext == '.webp':
            img.save(img_path, 'WEBP', quality=85)