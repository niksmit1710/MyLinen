from django.test import TestCase
from django.urls import reverse

from .models import Category, Product


class ProductDetailTests(TestCase):
    def test_product_without_active_variants_redirects_home(self):
        category = Category.objects.create(name='Women')
        product = Product.objects.create(
            name='Linen Dress',
            description='Soft linen dress',
            price='2499.00',
            category=category,
        )

        response = self.client.get(reverse('product_detail', args=[product.id]))

        self.assertRedirects(response, reverse('home'))
