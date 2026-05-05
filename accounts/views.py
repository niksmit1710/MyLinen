from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .models import User, Wallet
from wishlist.models import Wishlist
from orders.models import Order


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    next_url = request.GET.get('next', '') or request.POST.get('next', '')

    if request.method == 'POST':
        mobile = request.POST.get('mobile', '').strip()
        if mobile:
            # Simulate sending OTP
            request.session['login_mobile'] = mobile
            request.session['login_otp'] = '123456' # Mock OTP
            messages.info(request, f'OTP sent to +91 {mobile} (Use 123456 for testing)')
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
        correct_otp = request.session.get('login_otp')
        next_url = request.POST.get('next', '') or 'home'

        if otp == correct_otp:
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
            del request.session['login_mobile']
            del request.session['login_otp']
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
