from django.test import TestCase
from django.urls import reverse

from .models import User


class ProfileViewTests(TestCase):
    def test_profile_update_rejects_duplicate_phone_number(self):
        existing_user = User.objects.create_user(
            username='existing',
            password='testpass123',
            phone_number='9876543210',
            user_type='customer',
        )
        user = User.objects.create_user(
            username='customer',
            password='testpass123',
            phone_number='9123456780',
            user_type='customer',
        )

        self.client.force_login(user)
        response = self.client.post(reverse('profile'), {
            'first_name': 'Test',
            'last_name': 'Customer',
            'email': 'customer@example.com',
            'phone_number': existing_user.phone_number,
        })

        user.refresh_from_db()
        self.assertRedirects(response, reverse('profile'))
        self.assertEqual(user.phone_number, '9123456780')
