from django.test import TestCase
from django.urls import reverse


class CartCheckoutTests(TestCase):
    def test_cart_checkout_redirects_to_order_checkout(self):
        response = self.client.get(reverse('cart_checkout'))

        self.assertRedirects(response, reverse('checkout'), fetch_redirect_response=False)
