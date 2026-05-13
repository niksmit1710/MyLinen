#!/usr/bin/env bash
# Exit on error
set -o errexit

missing_env=()

check_env() {
    if [ -z "${!1}" ]; then
        missing_env+=("$1")
    fi
}

check_env "SECRET_KEY"
check_env "RAZORPAY_KEY_ID"
check_env "RAZORPAY_KEY_SECRET"
check_env "EMAIL_HOST_USER"
check_env "EMAIL_HOST_PASSWORD"

if [ -z "$CLOUDINARY_URL" ]; then
    check_env "CLOUDINARY_CLOUD_NAME"
    check_env "CLOUDINARY_API_KEY"
    check_env "CLOUDINARY_API_SECRET"
fi

if [ ${#missing_env[@]} -gt 0 ]; then
    echo "Missing required Render environment variable(s): ${missing_env[*]}"
    echo "Add them in Render Dashboard -> Service -> Environment, then redeploy."
    exit 1
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
