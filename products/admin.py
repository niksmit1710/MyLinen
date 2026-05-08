from decimal import Decimal, ROUND_HALF_UP
from django.contrib import admin, messages
from django.contrib.admin import helpers
from django import forms
from django.shortcuts import render
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import path
from django.utils.translation import gettext_lazy as _
from .models import Product, ProductVariant, Category, Size, ProductSizeStock, Review, ProductImage, Color, ReviewImage

# --- Inlines ---

class ProductSizeStockInline(admin.TabularInline):
    model = ProductSizeStock
    extra = 1
    fields = ('variant', 'size', 'stock')

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 3
    fields = ('variant', 'image', 'position')

class ProductVariantInline(admin.StackedInline):
    model = ProductVariant
    extra = 1
    fields = (('color', 'price', 'mrp'), 'is_active')
    show_change_link = True

class ReviewImageInline(admin.TabularInline):
    model = ReviewImage
    extra = 1
    fields = ('image', 'position')

# --- Admin Classes ---

class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'is_featured')
    list_editable = ('is_featured',)
    list_filter = ('category', 'is_featured')
    search_fields = ('name', 'description')
    exclude = ('image', 'color', 'price', 'mrp')
    ordering = ['-id']
    inlines = [ProductVariantInline]

class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ('product', 'color', 'price', 'mrp', 'sale_price', 'sale_active', 'effective_price', 'is_active')
    list_editable = ('price', 'mrp', 'sale_price', 'sale_active', 'is_active')
    list_filter = ('product', 'color', 'is_active', 'sale_active')
    ordering = ['-id']
    inlines = [ProductImageInline, ProductSizeStockInline]
    
    change_list_template = "admin/products/productvariant/change_list.html"

    def effective_price(self, obj):
        return obj.get_effective_price()
    effective_price.short_description = _("Effective Price")

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('bulk-price/', self.admin_site.admin_view(self.bulk_price_view), name='productvariant-bulk-price'),
        ]
        return custom_urls + urls

    def bulk_price_view(self, request):
        if request.method != 'POST':
            return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

        ids = request.POST.getlist('ids')
        operation = request.POST.get('operation')
        try:
            value = Decimal(request.POST.get('value', '0'))
        except (TypeError, ValueError):
            value = Decimal('0')
            
        scope = request.POST.get('scope', 'price') # price, mrp, both
        round_to_nearest = request.POST.get('round_to_nearest') == 'on'
        is_preview = request.POST.get('preview') == '1'
        
        # Sale-related inputs
        sale_start = request.POST.get('sale_start')
        sale_end = request.POST.get('sale_end')

        queryset = ProductVariant.objects.filter(pk__in=ids).select_related('product')
        
        if not queryset.exists():
            return JsonResponse({'status': 'error', 'message': 'No items selected.'})

        changes = []
        to_update = []
        errors = []

        for item in queryset:
            old_price = item.price or Decimal('0.00')
            old_mrp = item.mrp or Decimal('0.00')
            old_sale_price = item.sale_price
            old_sale_active = item.sale_active
            
            new_price = old_price
            new_mrp = old_mrp
            new_sale_price = old_sale_price
            new_sale_active = old_sale_active
            new_sale_start = item.sale_start
            new_sale_end = item.sale_end

            # Apply Operation
            if operation == 'sync_mrp':
                new_mrp = new_price
            elif operation == 'increase_percent':
                if scope in ['price', 'both']:
                    new_price = (new_price * (1 + value / 100))
                if scope in ['mrp', 'both']:
                    new_mrp = (new_mrp * (1 + value / 100))
                if scope == 'sale' and new_sale_price is not None:
                    new_sale_price = (new_sale_price * (1 + value / 100))

            elif operation == 'decrease_percent':
                if scope in ['price', 'both']:
                    new_price = (new_price * (1 - value / 100))
                if scope in ['mrp', 'both']:
                    new_mrp = (new_mrp * (1 - value / 100))
                if scope == 'sale' and new_sale_price is not None:
                    new_sale_price = (new_sale_price * (1 - value / 100))

            elif operation == 'set_price':
                if scope == 'sale':
                    new_sale_price = value
                else:
                    new_price = value
            elif operation == 'set_mrp':
                new_mrp = value
            
            # Sale Mode Operations
            elif operation == 'apply_sale_percent':
                # Apply discount to Selling Price to get Sale Price
                if new_price:
                    new_sale_price = (new_price * (1 - value / 100))
                    new_sale_active = True
            elif operation == 'activate_sale':
                new_sale_active = True
            elif operation == 'deactivate_sale':
                new_sale_active = False
            elif operation == 'set_sale_dates':
                from django.utils.dateparse import parse_datetime
                from django.utils.timezone import make_aware, is_naive
                if sale_start:
                    dt = parse_datetime(sale_start)
                    if dt and is_naive(dt): dt = make_aware(dt)
                    new_sale_start = dt
                if sale_end:
                    dt = parse_datetime(sale_end)
                    if dt and is_naive(dt): dt = make_aware(dt)
                    new_sale_end = dt

            # Apply Rounding (only for monetary values)
            def apply_round(val):
                if val is None: return None
                if round_to_nearest:
                    return val.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
                return val.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            new_price = apply_round(new_price)
            new_mrp = apply_round(new_mrp)
            new_sale_price = apply_round(new_sale_price)

            # Validation
            if new_price < 0:
                errors.append(_(f"Price for {item} would be negative ({new_price})."))
            if new_mrp < new_price:
                errors.append(_(f"MRP for {item} would be less than Selling Price ({new_mrp} < {new_price})."))
            if new_sale_price is not None and new_sale_price < 0:
                errors.append(_(f"Sale Price for {item} would be negative ({new_sale_price})."))

            if errors and not is_preview:
                break 

            changes.append({
                'name': str(item),
                'old': f"P: {old_price} | M: {old_mrp} | S: {old_sale_price} ({'ACTIVE' if old_sale_active else 'OFF'})",
                'new': f"P: {new_price} | M: {new_mrp} | S: {new_sale_price} ({'ACTIVE' if new_sale_active else 'OFF'})"
            })
            
            if not is_preview:
                item.price = new_price
                item.mrp = new_mrp
                item.sale_price = new_sale_price
                item.sale_active = new_sale_active
                item.sale_start = new_sale_start
                item.sale_end = new_sale_end
                to_update.append(item)

        if errors:
            return JsonResponse({'status': 'error', 'message': "<br>".join(errors)})

        if is_preview:
            return JsonResponse({'status': 'success', 'changes': changes})
        else:
            ProductVariant.objects.bulk_update(to_update, ['price', 'mrp', 'sale_price', 'sale_active', 'sale_start', 'sale_end'])
            return JsonResponse({'status': 'success', 'message': _(f"Successfully updated {len(to_update)} variants.")})

class ColorAdmin(admin.ModelAdmin):
    list_display = ('name', 'hex_code')

class ReviewAdmin(admin.ModelAdmin):
    list_display = ('product', 'user', 'rating', 'title', 'created_at')
    list_filter = ('rating', 'created_at')
    search_fields = ('product__name', 'user__username', 'title', 'comment')
    readonly_fields = ('created_at',)
    inlines = [ReviewImageInline]

# --- Registrations ---

admin.site.register(Product, ProductAdmin)
admin.site.register(ProductVariant, ProductVariantAdmin)
admin.site.register(Category)
admin.site.register(Size)
admin.site.register(Color, ColorAdmin)
admin.site.register(Review, ReviewAdmin)