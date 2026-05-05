from django.contrib import admin
from .models import Shipment


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ['id', 'order', 'status', 'tracking_id', 'estimated_delivery_date']
    list_filter = ['status', 'estimated_delivery_date']
    search_fields = ['order__id', 'tracking_id']
