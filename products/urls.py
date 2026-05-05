from django.urls import path
from . import views

urlpatterns = [
    path('', views.homepage, name='home'),
    path('shop/', views.product_list, name='product_list'),
    path('product/<int:id>/', views.product_detail, name='product_detail'),
    path('product/<int:id>/review/', views.submit_review, name='submit_review'),
    path('about-us/', views.about_us, name='about_us'),
]