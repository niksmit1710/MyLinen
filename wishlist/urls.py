from django.urls import path
from . import views

urlpatterns = [
    path('', views.view_wishlist, name='view_wishlist'),
    path('toggle/<int:product_id>/', views.toggle_wishlist, name='toggle_wishlist'),
    path('move-to-cart/<int:wishlist_item_id>/', views.move_to_cart, name='move_to_cart'),
]
