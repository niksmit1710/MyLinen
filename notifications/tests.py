from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from notifications.emails import send_order_email
from orders.models import Order


class TransactionalEmailTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='customer',
            email='customer@example.com',
            password='testpass123',
            user_type='customer',
        )
        self.order = Order.objects.create(
            user=self.user,
            full_name='Test Customer',
            email='order@example.com',
            phone_number='9876543210',
            address='123 Main Street',
            city='Surat',
            state='Gujarat',
            pincode='395007',
            subtotal_amount='2499.00',
            total_amount='2499.00',
            payment_method='cod',
        )

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        DEFAULT_FROM_EMAIL='MyLinen <orders@example.com>',
        SITE_URL='https://mylinen.example',
        EMAIL_SEND_ASYNC=False,
    )
    def test_send_order_email_uses_order_email_and_html_alternative(self):
        sent = send_order_email(self.order, 'placed')

        self.assertTrue(sent)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['order@example.com'])
        self.assertIn('Order Placed Successfully', mail.outbox[0].subject)
        self.assertIn('/orders/my-orders/', mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].alternatives[0][1], 'text/html')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.dummy.EmailBackend')
    def test_send_order_email_returns_false_when_email_disabled(self):
        sent = send_order_email(self.order, 'placed')

        self.assertFalse(sent)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_order_create_email_is_scheduled_after_commit(self):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            Order.objects.create(
                user=self.user,
                full_name='Second Customer',
                email='second@example.com',
                phone_number='9876543211',
                address='456 Main Street',
                city='Surat',
                state='Gujarat',
                pincode='395007',
                subtotal_amount='1000.00',
                total_amount='1000.00',
                payment_method='cod',
            )

        self.assertEqual(len(callbacks), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['second@example.com'])


class EmailDiagnosticsViewTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username='staff',
            email='staff@example.com',
            password='testpass123',
            user_type='customer',
            is_staff=True,
        )
        self.customer = User.objects.create_user(
            username='customer',
            email='customer@example.com',
            password='testpass123',
            user_type='customer',
        )

    def test_email_diagnostics_requires_staff(self):
        response = self.client.get(reverse('email_diagnostics'))
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.customer)
        response = self.client.get(reverse('email_diagnostics'))
        self.assertEqual(response.status_code, 302)

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        DEFAULT_FROM_EMAIL='MyLinen <orders@example.com>',
        EMAIL_HOST='smtp.gmail.com',
        EMAIL_PORT=587,
        EMAIL_USE_TLS=True,
        EMAIL_USE_SSL=False,
        EMAIL_HOST_USER='orders@example.com',
        EMAIL_HOST_PASSWORD='secret',
    )
    def test_staff_can_send_diagnostic_email(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(reverse('email_diagnostics'), {'to': 'test@example.com'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['test@example.com'])
