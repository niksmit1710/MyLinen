from django.contrib.auth import get_user_model

User = get_user_model()

username = "admin"
password = "admin123"

user, created = User.objects.get_or_create(username=username)

user.set_password(password)   # IMPORTANT (hash password)
user.is_staff = True
user.is_superuser = True
user.save()

print("Superuser ready")