#!/usr/bin/env bash
# Exit on error
set -o errexit

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
python create_superuser.py
