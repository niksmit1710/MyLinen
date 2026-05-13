import os
import django

# ✅ Set settings module FIRST
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mylinen.settings')

# ✅ Initialize Django
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

try:
    username = os.environ.get('DJANGO_SUPERUSER_USERNAME')
    email = os.environ.get('DJANGO_SUPERUSER_EMAIL')
    password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')

    if not all([username, email, password]):
        raise ValueError(
            "Set DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_EMAIL, "
            "and DJANGO_SUPERUSER_PASSWORD before running this script."
        )

    if not User.objects.filter(username=username).exists():
        User.objects.create_superuser(
            username=username,
            email=email,
            password=password
        )
        print("Superuser created")
    else:
        print("Superuser already exists")

except Exception as e:
    print("Error:", e)
