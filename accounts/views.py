import secrets
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.module_loading import import_string
from django.shortcuts import redirect, render

from .models import User, Wallet
from wishlist.models import Wishlist
from orders.models import Order


OTP_TTL_SECONDS = 300
OTP_MAX_ATTEMPTS = 5


def _generate_otp():
    return f"{secrets.randbelow(1_000_000):06d}"


def _hash_otp(mobile, otp):
    return salted_hmac("accounts.login_otp", f"{mobile}:{otp}").hexdigest()


def _send_login_otp(mobile, otp):
    sender_path = getattr(settings, "LOGIN_OTP_SENDER", "")
    if sender_path:
        sender = import_string(sender_path)
        sender(mobile, otp)
        return True
    return settings.DEBUG


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    next_url = request.GET.get('next', '') or request.POST.get('next', '')

    if request.method == 'POST':
        mobile = request.POST.get('mobile', '').strip()
        if mobile:
            otp = _generate_otp()
            if not _send_login_otp(mobile, otp):
                messages.error(request, 'OTP delivery is not configured. Please use username/password login.')
                return render(request, 'accounts/login.html', {'next': next_url})

            request.session['login_mobile'] = mobile
            request.session['login_otp_hash'] = _hash_otp(mobile, otp)
            request.session['login_otp_expires_at'] = int(time.time()) + OTP_TTL_SECONDS
            request.session['login_otp_attempts'] = 0
            if settings.DEBUG:
                messages.info(request, f'Development OTP for +91 {mobile}: {otp}')
            else:
                messages.info(request, f'OTP sent to +91 {mobile}.')
            return render(request, 'accounts/otp_verification.html', {'next': next_url})
        
        # Legacy username/password login (if still needed)
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        if username and password:
            user = authenticate(request, username=username, password=password)
            if user:
                login(request, user)
                return redirect(next_url or 'home')
            messages.error(request, 'Invalid username or password.')

    return render(request, 'accounts/login.html', {'next': next_url})


def verify_otp(request):
    if request.method == 'POST':
        otp = request.POST.get('otp', '').strip()
        mobile = request.session.get('login_mobile')
        otp_hash = request.session.get('login_otp_hash')
        expires_at = request.session.get('login_otp_expires_at', 0)
        attempts = request.session.get('login_otp_attempts', 0)
        next_url = request.POST.get('next', '') or 'home'

        if not mobile or not otp_hash:
            messages.error(request, 'OTP session expired. Please request a new OTP.')
            return redirect('login')

        if int(time.time()) > expires_at:
            for key in ('login_mobile', 'login_otp_hash', 'login_otp_expires_at', 'login_otp_attempts'):
                request.session.pop(key, None)
            messages.error(request, 'OTP expired. Please request a new OTP.')
            return redirect('login')

        if attempts >= OTP_MAX_ATTEMPTS:
            for key in ('login_mobile', 'login_otp_hash', 'login_otp_expires_at', 'login_otp_attempts'):
                request.session.pop(key, None)
            messages.error(request, 'Too many invalid OTP attempts. Please request a new OTP.')
            return redirect('login')

        request.session['login_otp_attempts'] = attempts + 1

        if constant_time_compare(_hash_otp(mobile, otp), otp_hash):
            # Check if user exists, else create
            user = User.objects.filter(phone_number=mobile).first()
            if not user:
                # Create new user
                username = f"user_{mobile}"
                user = User.objects.create_user(
                    username=username,
                    phone_number=mobile,
                    user_type='customer'
                )
            
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            for key in ('login_mobile', 'login_otp_hash', 'login_otp_expires_at', 'login_otp_attempts'):
                request.session.pop(key, None)
            messages.success(request, f'Welcome back!')
            return redirect(next_url)
        else:
            messages.error(request, 'Invalid OTP. Please try again.')
            return render(request, 'accounts/otp_verification.html', {'next': next_url})

    return redirect('login')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        username   = request.POST.get('username', '').strip()
        email      = request.POST.get('email', '').strip()
        password1  = request.POST.get('password1', '')
        password2  = request.POST.get('password2', '')
        first_name = request.POST.get('first_name', '').strip()
        last_name  = request.POST.get('last_name', '').strip()

        error = None
        if not username or not email or not password1:
            error = 'Please fill in all required fields.'
        elif password1 != password2:
            error = 'Passwords do not match.'
        elif len(password1) < 6:
            error = 'Password must be at least 6 characters.'
        elif User.objects.filter(username=username).exists():
            error = 'That username is already taken.'
        elif User.objects.filter(email=email).exists():
            error = 'An account with that email already exists.'

        if error:
            messages.error(request, error)
        else:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password1,
                first_name=first_name,
                last_name=last_name,
                user_type='customer',
            )
            login(request, user)
            messages.success(request, f'Welcome, {user.get_display_name()}!')
            return redirect('home')

    return render(request, 'accounts/register.html')


def logout_view(request):
    logout(request)
    return redirect('home')


@login_required
def profile_view(request):
    if request.method == 'POST':
        # Update profile logic
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        
        user = request.user
        user.first_name = first_name
        user.last_name = last_name
        user.email = email
        user.phone_number = phone_number
        user.save()
        messages.success(request, 'Profile updated successfully!')
        return redirect('profile')

    wishlist_items = Wishlist.objects.filter(user=request.user).select_related('variant', 'variant__product', 'variant__color')
    orders = Order.objects.filter(user=request.user).order_by('-created_at')

    # Wallet data
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    wallet_transactions = wallet.transactions.all()[:20]

    return render(request, 'accounts/profile.html', {
        'wishlist_items': wishlist_items,
        'orders': orders,
        'wallet_balance': wallet.balance,
        'wallet_transactions': wallet_transactions,
    })
