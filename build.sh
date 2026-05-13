#!/usr/bin/env bash
# Exit on error
set -o errexit

if [ -z "$SECRET_KEY" ]; then
    echo "WARNING: SECRET_KEY is not set. Django will generate a temporary key for this deploy."
fi

if [ -z "$RAZORPAY_KEY_ID" ] || [ -z "$RAZORPAY_KEY_SECRET" ]; then
    echo "WARNING: Razorpay environment variables are not fully set. Online payments will not work until configured."
fi

if [ -z "$EMAIL_HOST_USER" ] || [ -z "$EMAIL_HOST_PASSWORD" ]; then
    echo "WARNING: Email environment variables are not fully set. SMTP email delivery will not work until configured."
fi

if [ -z "$CLOUDINARY_URL" ] && { [ -z "$CLOUDINARY_CLOUD_NAME" ] || [ -z "$CLOUDINARY_API_KEY" ] || [ -z "$CLOUDINARY_API_SECRET" ]; }; then
    echo "WARNING: Cloudinary environment variables are not fully set. Uploaded media may not persist across deploys."
fi

pip install -r requirements.txt

python manage.py migrate
python manage.py collectstatic --no-input

# Create the correct Site entry for allauth
python manage.py shell -c "
from django.contrib.sites.models import Site
site = Site.objects.get_or_create(id=1)[0]
site.domain = 'mylinen.onrender.com'
site.name = 'MyLinen'
site.save()
print('Site configured:', site.domain)
"

# Create superuser if needed
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_EMAIL" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    python create_superuser.py
else
    echo "Skipping superuser creation; DJANGO_SUPERUSER_* environment variables are not fully set."
fi
