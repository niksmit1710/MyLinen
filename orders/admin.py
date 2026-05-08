from django.contrib import admin
from .models import Order, OrderItem, Coupon, ReturnExchangeRequest, ReturnExchangeImage


class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'phone_number', 'total_amount', 'wallet_amount_used', 'payment_method', 'status', 'is_paid']
    list_filter = ['status', 'payment_method', 'is_paid']
    list_editable = ['status']
    readonly_fields = ['wallet_amount_used']
    search_fields = ['user__username', 'id', 'coupon_code', 'phone_number', 'email']


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ['code', 'discount_type', 'discount_value', 'is_active', 'valid_from', 'valid_to', 'used_count']
    list_filter = ['is_active', 'discount_type', 'valid_from', 'valid_to']
    search_fields = ['code']


# Return & Exchange Admin
class ReturnExchangeImageInline(admin.TabularInline):
    model = ReturnExchangeImage
    extra = 0
    fields = ('image', 'position')
    readonly_fields = ()


@admin.register(ReturnExchangeRequest)
class ReturnExchangeRequestAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'user', 'order', 'get_product_name', 'request_type',
        'reason', 'status', 'requested_at'
    ]
    list_filter = ['status', 'request_type', 'reason', 'requested_at']
    list_editable = ['status']
    search_fields = [
        'user__username', 'order__id', 'order_item__product_name_at_purchase', 'comment'
    ]
    readonly_fields = ('user', 'order', 'order_item', 'request_type', 'reason', 'comment', 'exchange_size', 'is_refunded', 'requested_at', 'updated_at')
    fields = (
        'user', 'order', 'order_item', 'request_type', 'reason', 'comment',
        'exchange_size', 'status', 'is_refunded', 'admin_notes', 'requested_at', 'updated_at'
    )
    inlines = [ReturnExchangeImageInline]

    def get_product_name(self, obj):
        return obj.order_item.product_name_at_purchase


admin.site.register(Order, OrderAdmin)
@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ['id', 'order', 'product_name_at_purchase', 'color_at_purchase', 'size_at_purchase', 'quantity', 'price']
    list_filter = ['order__status']
    search_fields = ['product_name_at_purchase', 'order__id']
