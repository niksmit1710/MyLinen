from django.urls import path
from . import views

urlpatterns = [
    path('checkout/', views.checkout, name='checkout'),
    path('success/', views.order_success, name='order_success'),
    path('payment-success/', views.payment_success, name='payment_success'),
    path('apply-coupon/', views.apply_coupon, name='apply_coupon'),
    path('remove-coupon/', views.remove_coupon, name='remove_coupon'),
    path('my-orders/', views.my_orders, name='my_orders'),
    path('my-orders/<int:order_id>/', views.order_detail, name='order_detail'),
    path('my-orders/<int:order_id>/invoice/', views.download_invoice, name='download_invoice'),
    path('my-orders/<int:order_id>/reorder/', views.reorder, name='reorder'),
    path('my-orders/<int:order_id>/return-request/', views.submit_return_request, name='submit_return_request'),
]
