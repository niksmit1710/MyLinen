import os

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

class Command(BaseCommand):
    help = "Create superuser safely"

    def add_arguments(self, parser):
        parser.add_argument('--username', default=os.environ.get('DJANGO_SUPERUSER_USERNAME'))
        parser.add_argument('--email', default=os.environ.get('DJANGO_SUPERUSER_EMAIL'))
        parser.add_argument('--password', default=os.environ.get('DJANGO_SUPERUSER_PASSWORD'))

    def handle(self, *args, **kwargs):
        User = get_user_model()

        username = kwargs.get('username')
        email = kwargs.get('email')
        password = kwargs.get('password')

        if not all([username, email, password]):
            self.stderr.write(
                self.style.ERROR(
                    "Provide --username, --email, and --password, or set "
                    "DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_EMAIL, and "
                    "DJANGO_SUPERUSER_PASSWORD."
                )
            )
            return

        if not User.objects.filter(username=username).exists():
            User.objects.create_superuser(
                username=username,
                email=email,
                password=password
            )
            self.stdout.write(self.style.SUCCESS("Superuser created"))
        else:
            self.stdout.write(self.style.WARNING("Superuser already exists"))
