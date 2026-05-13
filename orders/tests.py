from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User, Wallet
from orders.models import Order, OrderItem
from products.models import Category, Product, ProductSizeStock, Size
from shipping.models import Shipment


class OrderEstimatedDeliveryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='customer1',
            password='testpass123',
            email='customer@example.com',
            user_type='customer',
        )
        self.category = Category.objects.create(name='Women')
        self.size = Size.objects.create(name='M')
        self.product = Product.objects.create(
            name='Linen Dress',
            description='Soft linen dress',
            price='2499.00',
            category=self.category,
            image=SimpleUploadedFile('dress.jpg', b'filecontent', content_type='image/jpeg'),
        )
        ProductSizeStock.objects.create(product=self.product, size=self.size, stock=10)

    def test_cod_checkout_creates_shipment_with_estimated_delivery_date(self):
        self.client.force_login(self.user)
        session = self.client.session
        session['cart'] = {
            f'{self.product.id}_{self.size.id}': {
                'product_id': self.product.id,
                'name': self.product.name,
                'price': float(self.product.price),
                'quantity': 1,
                'image': self.product.image.url,
                'size': self.size.name,
                'size_id': self.size.id,
            }
        }
        session.save()

        response = self.client.post(reverse('checkout'), {
            'full_name': 'Test Customer',
            'email': 'customer@example.com',
            'phone_number': '9876543210',
            'address': '123 Main Street',
            'city': 'Surat',
            'state': 'Gujarat',
            'pincode': '395007',
            'payment_method': 'cod',
        })

        self.assertRedirects(response, reverse('order_success'))
        order = Order.objects.get(user=self.user)
        shipment = Shipment.objects.get(order=order)

        self.assertEqual(shipment.status, order.status)
        self.assertEqual(
            shipment.estimated_delivery_date,
            timezone.localdate(order.created_at) + timedelta(days=7),
        )

    def test_wallet_only_checkout_uses_wallet_payment_method(self):
        wallet, _ = Wallet.objects.get_or_create(user=self.user)
        wallet.balance = self.product.price
        wallet.save()

        self.client.force_login(self.user)
        session = self.client.session
        session['cart'] = {
            f'{self.product.id}_{self.size.id}': {
                'product_id': self.product.id,
                'name': self.product.name,
                'price': float(self.product.price),
                'quantity': 1,
                'image': self.product.image.url,
                'size': self.size.name,
                'size_id': self.size.id,
            }
        }
        session.save()

        response = self.client.post(reverse('checkout'), {
            'full_name': 'Test Customer',
            'email': 'customer@example.com',
            'phone_number': '9876543210',
            'address': '123 Main Street',
            'city': 'Surat',
            'state': 'Gujarat',
            'pincode': '395007',
        })

        self.assertRedirects(response, reverse('order_success'))
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.payment_method, 'wallet')
        self.assertTrue(order.is_paid)

    def test_order_detail_uses_shipment_estimated_delivery_date(self):
        order = Order.objects.create(
            user=self.user,
            full_name='Test Customer',
            email='customer@example.com',
            phone_number='9876543210',
            address='123 Main Street',
            city='Surat',
            state='Gujarat',
            pincode='395007',
            subtotal_amount='2499.00',
            total_amount='2499.00',
            payment_method='cod',
        )
        Shipment.objects.create(
            order=order,
            status='confirmed',
            tracking_id='TRACK123',
            estimated_delivery_date=timezone.localdate() + timedelta(days=3),
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse('order_detail', args=[order.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context['order'].estimated_delivery_date,
            timezone.localdate() + timedelta(days=3),
        )

    def test_invoice_handles_order_item_without_variant(self):
        order = Order.objects.create(
            user=self.user,
            full_name='Test Customer',
            email='customer@example.com',
            phone_number='9876543210',
            address='123 Main Street',
            city='Surat',
            state='Gujarat',
            pincode='395007',
            subtotal_amount='2499.00',
            total_amount='2499.00',
            payment_method='cod',
        )
        OrderItem.objects.create(
            order=order,
            variant=None,
            product_name_at_purchase='Archived Product',
            color_at_purchase='Blue',
            size_at_purchase='M',
            price_at_purchase='2499.00',
            quantity=1,
            price='2499.00',
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse('download_invoice', args=[order.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_payment_success_rejects_invalid_json(self):
        response = self.client.post(
            reverse('payment_success'),
            data='not-json',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['status'], 'failed')
