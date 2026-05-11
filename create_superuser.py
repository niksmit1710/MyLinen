import os
import django

# ✅ Set settings module FIRST
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mylinen.settings')

# ✅ Initialize Django
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

try:
    if not User.objects.filter(username='admin').exists():
        User.objects.create_superuser(
            username='admin',
            email='admin@gmail.com',
            password='admin123'
        )
        print("Superuser created")
    else:
        print("Superuser already exists")

except Exception as e:
    print("Error:", e)