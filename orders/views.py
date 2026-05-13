from datetime import timedelta
import json
import os

import razorpay
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Prefetch
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from products.models import ProductSizeStock
from shipping.models import Shipment

from accounts.models import User
from .models import (
    Order, OrderItem, Coupon,
    ReturnExchangeRequest, ReturnExchangeImage,
    RETURN_WINDOW_DAYS, RETURN_REASONS,
)


DEFAULT_ESTIMATED_DELIVERY_DAYS = 7


def _default_estimated_delivery_date(order=None):
    if order and order.created_at:
        return timezone.localdate(order.created_at) + timedelta(days=DEFAULT_ESTIMATED_DELIVERY_DAYS)
    return timezone.localdate() + timedelta(days=DEFAULT_ESTIMATED_DELIVERY_DAYS)


def _attach_shipment_details(orders):
    for order in orders:
        shipment = None
        if hasattr(order, 'prefetched_shipments') and order.prefetched_shipments:
            shipment = order.prefetched_shipments[0]
        else:
            shipment = order.shipment_set.order_by('estimated_delivery_date', 'id').first()

        order.primary_shipment = shipment
        order.estimated_delivery_date = (
            shipment.estimated_delivery_date if shipment else _default_estimated_delivery_date(order)
        )

    return orders


def _render_checkout(request, cart, total, form_data=None, error=None):
    applied_coupon = None
    discount_amount = 0
    final_total = total

    coupon_code = request.session.get('applied_coupon')
    if coupon_code:
        try:
            coupon = Coupon.objects.get(code=coupon_code)
            if coupon.is_valid() and total >= coupon.min_order_value:
                applied_coupon = coupon
                discount_amount = coupon.calculate_discount(total)
                final_total = total - discount_amount
            else:
                # If coupon became invalid or cart total dropped
                del request.session['applied_coupon']
        except Coupon.DoesNotExist:
            del request.session['applied_coupon']

    from accounts.models import Wallet
    from decimal import Decimal
    
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    wallet_balance = wallet.balance
    
    # Calculate wallet deduction
    wallet_used = min(wallet_balance, final_total)
    payable_amount = final_total - wallet_used

    if not form_data:
        form_data = {
            'full_name': request.user.get_full_name() or request.user.username,
            'email': request.user.email,
            'phone_number': request.user.phone_number,
        }

    return render(request, 'checkout.html', {
        'cart': cart,
        'total': total,
        'applied_coupon': applied_coupon,
        'discount_amount': discount_amount,
        'final_total': final_total,
        'wallet_balance': wallet_balance,
        'wallet_used': wallet_used,
        'payable_amount': payable_amount,
        'RAZORPAY_KEY_ID': settings.RAZORPAY_KEY_ID,
        'form_data': form_data,
        'error': error,
    })


@login_required
def checkout(request):
    cart = request.session.get('cart', {})
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if not cart:
        return redirect('cart_detail')

    from decimal import Decimal
    total = Decimal(sum(item['price'] * item['quantity'] for item in cart.values()))

    # Coupon Logic
    applied_coupon = None
    discount_amount = Decimal(0)
    final_total = total
    coupon_code = request.session.get('applied_coupon')
    if coupon_code:
        try:
            coupon = Coupon.objects.get(code=coupon_code)
            if coupon.is_valid() and total >= coupon.min_order_value:
                applied_coupon = coupon
                discount_amount = coupon.calculate_discount(total)
                final_total = total - discount_amount
        except Coupon.DoesNotExist:
            del request.session['applied_coupon']

    if request.method == 'GET':
        return _render_checkout(request, cart, total)

    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        email = request.POST.get('email', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        address = request.POST.get('address', '').strip()
        city = request.POST.get('city', '').strip()
        state = request.POST.get('state', '').strip()
        pincode = request.POST.get('pincode', '').strip()
        payment_method = request.POST.get('payment_method')
        
        form_data = {
            'full_name': full_name,
            'email': email,
            'phone_number': phone_number,
            'address': address,
            'city': city,
            'state': state,
            'pincode': pincode,
            'payment_method': payment_method,
        }

        # Re-calculate wallet logic to check if payment_method is required
        from accounts.models import Wallet
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        wallet_used_check = min(wallet.balance, final_total)
        payable_amount_check = final_total - wallet_used_check

        if not all([full_name, email, phone_number, address, city, state, pincode]):
            error = 'Please fill all checkout details.'
            if is_ajax:
                return JsonResponse({'status': 'failed', 'error': error}, status=400)
            return _render_checkout(request, cart, total, form_data=form_data, error=error)

        if payable_amount_check > 0 and not payment_method:
            error = 'Please select a payment method.'
            if is_ajax:
                return JsonResponse({'status': 'failed', 'error': error}, status=400)
            return _render_checkout(request, cart, total, form_data=form_data, error=error)
        
        if payable_amount_check == 0:
            payment_method = 'wallet'

        with transaction.atomic():
            locked_stocks = []
            for item in cart.values():
                stock_filter = {'size_id': item['size_id']}
                if item.get('variant_id'):
                    stock_filter['variant_id'] = item['variant_id']
                else:
                    stock_filter['product_id'] = item['product_id']

                stock = ProductSizeStock.objects.select_for_update().get(**stock_filter)
                locked_stocks.append((item, stock))

                if stock.stock < item['quantity']:
                    error = f"Only {stock.stock} item(s) left for {item['name']} ({item['size']})."
                    if is_ajax:
                        return JsonResponse({'status': 'failed', 'error': error}, status=409)
                    return _render_checkout(request, cart, total, form_data=form_data, error=error)

            # Wallet Logic
            from accounts.models import Wallet, WalletTransaction
            wallet, _ = Wallet.objects.select_for_update().get_or_create(user=request.user)
            wallet_used = min(wallet.balance, final_total)
            payable_amount = final_total - wallet_used

            order = Order.objects.create(
                user=request.user,
                full_name=full_name,
                email=email,
                phone_number=phone_number,
                address=address,
                city=city,
                state=state,
                pincode=pincode,
                subtotal_amount=total,
                coupon=applied_coupon,
                coupon_code=applied_coupon.code if applied_coupon else None,
                discount_amount=discount_amount,
                total_amount=final_total,
                payment_method=payment_method,
                wallet_amount_used=wallet_used,
                is_paid=(payable_amount == 0)
            )
            
            # Debit wallet
            if wallet_used > 0:
                wallet.balance -= wallet_used
                wallet.save()
                WalletTransaction.objects.create(
                    wallet=wallet,
                    transaction_type='debit',
                    amount=wallet_used,
                    description=f"Used for Order #{order.id}"
                )

            Shipment.objects.create(
                order=order,
                status=order.status,
                tracking_id='',
                estimated_delivery_date=_default_estimated_delivery_date(order),
            )

            # Update user profile information
            user = request.user
            name_parts = full_name.split(' ', 1)
            user.first_name = name_parts[0]
            if len(name_parts) > 1:
                user.last_name = name_parts[1]
            
            # Update email if not set or changed
            user.email = email

            # Update phone number if not set or changed, and if not already taken
            if not user.phone_number or user.phone_number != phone_number:
                if not User.objects.filter(phone_number=phone_number).exclude(id=user.id).exists():
                    user.phone_number = phone_number
            
            user.save()

            for item, stock in locked_stocks:
                OrderItem.objects.create(
                    order=order,
                    variant_id=item.get('variant_id'),
                    quantity=item['quantity'],
                    price=item['price'],
                    product_name_at_purchase=item['name'],
                    color_at_purchase=item.get('color', ''),
                    size_at_purchase=item['size'],
                    price_at_purchase=item['price']
                )

                stock.stock -= item['quantity']
                stock.save()

            if applied_coupon:
                applied_coupon.used_count += 1
                applied_coupon.save()

        # Clear coupon from session after order
        if 'applied_coupon' in request.session:
            del request.session['applied_coupon']

        # If fully paid via wallet
        if payable_amount == 0:
            request.session['last_order_id'] = order.id
            request.session['cart'] = {}
            if is_ajax:
                return JsonResponse({'status': 'paid', 'order_id': order.id})
            return redirect('order_success')

        if payment_method == 'cod':
            request.session['last_order_id'] = order.id
            request.session['cart'] = {}
            return redirect('order_success')

        if payment_method == 'online':
            client = razorpay.Client(auth=(
                settings.RAZORPAY_KEY_ID,
                settings.RAZORPAY_KEY_SECRET
            ))

            payment = client.order.create({
                'amount': int(payable_amount * 100),
                'currency': 'INR',
                'payment_capture': 1
            })

            order.payment_id = payment['id']
            order.save()
            request.session['last_order_id'] = order.id

            if is_ajax:
                return JsonResponse({
                    'status': 'created',
                    'payment': payment,
                    'order_id': order.id,
                    'razorpay_key_id': settings.RAZORPAY_KEY_ID,
                    'customer': {
                        'name': full_name,
                    }
                })

            return _render_checkout(request, cart, total, form_data=form_data)

    return redirect('cart_detail')


@login_required
def apply_coupon(request):
    if request.method == 'POST':
        code = request.POST.get('coupon_code', '').strip()
        cart = request.session.get('cart', {})
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        from decimal import Decimal
        total = Decimal(sum(item['price'] * item['quantity'] for item in cart.values()))

        try:
            coupon = Coupon.objects.get(code__iexact=code)
            if not coupon.is_valid():
                if is_ajax: return JsonResponse({'status': 'failed', 'error': 'Coupon is expired or inactive.'}, status=400)
                return redirect('cart_detail')
            
            if total < coupon.min_order_value:
                error_msg = f'Minimum order value for this coupon is Rs. {coupon.min_order_value}.'
                if is_ajax: return JsonResponse({'status': 'failed', 'error': error_msg}, status=400)
                return redirect('cart_detail')

            request.session['applied_coupon'] = coupon.code
            if is_ajax:
                discount = coupon.calculate_discount(total)
                return JsonResponse({
                    'status': 'success',
                    'message': f'Coupon "{coupon.code}" applied successfully!',
                    'discount_amount': float(discount),
                    'final_total': float(total - discount)
                })
            return redirect('cart_detail')

        except Coupon.DoesNotExist:
            if is_ajax: return JsonResponse({'status': 'failed', 'error': 'Invalid coupon code.'}, status=400)
            return redirect('cart_detail')

    return redirect('cart_detail')


@login_required
def remove_coupon(request):
    if 'applied_coupon' in request.session:
        del request.session['applied_coupon']
    
    # Redirect based on where we came from
    next_url = request.GET.get('next', 'cart_detail')
    return redirect(next_url)


@login_required
def order_success(request):
    order_id = request.session.get('last_order_id')
    order = get_object_or_404(
        Order.objects.prefetch_related(
            Prefetch(
                'shipment_set',
                queryset=Shipment.objects.order_by('estimated_delivery_date', 'id'),
                to_attr='prefetched_shipments',
            )
        ),
        id=order_id,
        user=request.user,
    )
    _attach_shipment_details([order])
    return render(request, 'order_success.html', {'order': order})
@csrf_exempt
def payment_success(request):
    if request.method == "POST":
        data = json.loads(request.body)

        client = razorpay.Client(auth=(
            settings.RAZORPAY_KEY_ID,
            settings.RAZORPAY_KEY_SECRET
        ))

        try:
            client.utility.verify_payment_signature({
                'razorpay_order_id': data['razorpay_order_id'],
                'razorpay_payment_id': data['razorpay_payment_id'],
                'razorpay_signature': data['razorpay_signature']
            })

            order = Order.objects.get(payment_id=data['razorpay_order_id'])
            order.is_paid = True
            order.save()
            request.session['cart'] = {}

            return JsonResponse({'status': 'success'})

        except:
            return JsonResponse({'status': 'failed'})

    return JsonResponse({'status': 'failed'})

@login_required
def my_orders(request):
    orders = list(
        Order.objects.filter(user=request.user)
        .prefetch_related(
            'items__variant',
            'items__variant__product',
            Prefetch(
                'shipment_set',
                queryset=Shipment.objects.order_by('estimated_delivery_date', 'id'),
                to_attr='prefetched_shipments',
            ),
        )
        .order_by('-created_at')
    )
    _attach_shipment_details(orders)
    return render(request, 'my_orders.html', {'orders': orders})


@login_required
def order_detail(request, order_id):
    order = get_object_or_404(
        Order.objects.prefetch_related(
            'items__variant',
            'items__variant__product',
            'items__variant__product__variants__size_stocks__size',
            'items__return_requests',
            'return_requests__images',
            Prefetch(
                'shipment_set',
                queryset=Shipment.objects.order_by('estimated_delivery_date', 'id'),
                to_attr='prefetched_shipments',
            ),
        ),
        id=order_id,
        user=request.user,
    )
    _attach_shipment_details([order])
    timeline = [
        {'value': 'pending', 'label': 'Order Placed'},
        {'value': 'confirmed', 'label': 'Confirmed'},
        {'value': 'shipped', 'label': 'Shipped'},
        {'value': 'delivered', 'label': 'Delivered'},
    ]

    current_step = next(
        (index for index, step in enumerate(timeline) if step['value'] == order.status),
        0,
    )

    for index, step in enumerate(timeline):
        step['completed'] = index <= current_step
        step['active'] = index == current_step

    # --- Return / Exchange eligibility ---
    return_eligible = False
    return_deadline = None
    eligible_item_ids = set()
    existing_requests = {}  # item_id -> request object

    if order.status == 'delivered':
        delivery_date = order.estimated_delivery_date
        return_deadline = delivery_date + timedelta(days=RETURN_WINDOW_DAYS)
        today = timezone.localdate()

        if today <= return_deadline:
            return_eligible = True

        # Map existing requests per item (active and completed)
        for req in order.return_requests.all():
            existing_requests[req.order_item_id] = req

        # Determine eligible items (delivered, within window, no active request)
        if return_eligible:
            for item in order.items.all():
                if item.id not in existing_requests:
                    eligible_item_ids.add(item.id)

    return render(request, 'order_detail.html', {
        'order': order,
        'timeline': timeline,
        'return_eligible': return_eligible,
        'return_deadline': return_deadline,
        'eligible_item_ids': list(eligible_item_ids),
        'existing_requests': existing_requests,
        'return_reasons': RETURN_REASONS,
    })


def _pdf_escape(value):
    return str(value).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def _build_invoice_pdf(lines):
    content = ['BT', '/F1 12 Tf', '50 790 Td', '16 TL']
    for index, line in enumerate(lines):
        prefix = '' if index == 0 else 'T* '
        content.append(f"{prefix}({_pdf_escape(line)}) Tj")
    content.append('ET')
    stream = '\n'.join(content).encode('latin-1', errors='replace')

    objects = [
        b'1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj',
        b'2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj',
        b'3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj',
        f"4 0 obj << /Length {len(stream)} >> stream\n".encode('latin-1') + stream + b"\nendstream endobj",
        b'5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj',
    ]

    pdf = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj + b'\n')

    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n".encode('latin-1'))
    pdf.extend(b'0000000000 65535 f \n')
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode('latin-1'))
    pdf.extend(
        f"trailer << /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode('latin-1')
    )
    return bytes(pdf)


@login_required
def download_invoice(request, order_id):
    order = get_object_or_404(
        Order.objects.prefetch_related('items__variant__product'),
        id=order_id,
        user=request.user,
    )

    lines = [
        'MyLinen Invoice',
        '',
        f'Invoice for Order #{order.id}',
        f'Date: {order.created_at.strftime("%Y-%m-%d %H:%M")}',
        f'Customer: {order.full_name}',
        f'Payment Method: {order.get_payment_method_display()}',
        f'Order Status: {order.get_status_display()}',
        f'Payment Status: {"Paid" if order.is_paid else "Pending"}',
        '',
        'Items:',
    ]

    for item in order.items.all():
        line_total = item.price * item.quantity
        lines.append(
            f'- {item.variant.product.name} | Color: {item.color_at_purchase} | Size: {item.size_at_purchase} | Qty: {item.quantity} | Rs. {line_total}'
        )

    lines.extend([
        '',
        f'Subtotal: Rs. {order.subtotal_amount}',
        f'Discount: Rs. {order.discount_amount}',
        f'Total: Rs. {order.total_amount}',
        '',
        f'Shipping Address: {order.full_name}, {order.address}, {order.city}, {order.state} - {order.pincode}',
        f'Contact: {order.email} | {order.phone_number}',
    ])

    pdf_bytes = _build_invoice_pdf(lines)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="invoice-order-{order.id}.pdf"'
    return response


@login_required
def reorder(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    cart = request.session.get('cart', {})

    for item in order.items.all():
        if not item.variant:
            continue
        try:
            # Try to find the same size for this variant
            stock = ProductSizeStock.objects.filter(variant=item.variant, size__name=item.size_at_purchase).first()
            if stock and stock.stock > 0:
                key = f"{item.variant.id}_{stock.size_id}"
                quantity = min(item.quantity, stock.stock)

                if key in cart:
                    cart[key]['quantity'] += quantity
                else:
                    cart[key] = {
                        'variant_id': item.variant.id,
                        'product_id': item.variant.product.id,
                        'size_id': stock.size_id,
                        'name': item.product_name_at_purchase,
                        'color': item.color_at_purchase,
                        'price': float(item.price_at_purchase),
                        'quantity': quantity,
                        'image': item.variant.primary_image.url if item.variant.primary_image else '',
                        'size': item.size_at_purchase,
                    }
        except Exception:
            continue

    request.session['cart'] = cart
    return redirect('cart_detail')


@login_required
def submit_return_request(request, order_id):
    """Handle AJAX return/exchange request submission."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request.'}, status=400)

    order = get_object_or_404(Order, id=order_id, user=request.user)

    # Must be delivered
    if order.status != 'delivered':
        return JsonResponse({'status': 'error', 'message': 'Only delivered orders are eligible.'}, status=400)

    # Check 7-day window
    shipment = order.shipment_set.order_by('estimated_delivery_date', 'id').first()
    delivery_date = shipment.estimated_delivery_date if shipment else _default_estimated_delivery_date(order)
    deadline = delivery_date + timedelta(days=RETURN_WINDOW_DAYS)
    if timezone.localdate() > deadline:
        return JsonResponse({'status': 'error', 'message': 'Return/exchange window has closed.'}, status=400)

    # Parse form data
    item_id = request.POST.get('order_item_id')
    request_type = request.POST.get('request_type')
    reason = request.POST.get('reason')
    comment = request.POST.get('comment', '').strip()
    exchange_size_id = request.POST.get('exchange_size_id')

    if not item_id or not request_type or not reason:
        return JsonResponse({'status': 'error', 'message': 'Please fill all required fields.'}, status=400)

    # Validate item belongs to this order
    try:
        order_item = OrderItem.objects.get(id=item_id, order=order)
    except OrderItem.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Invalid order item.'}, status=400)

    # Check no active request exists for this item
    active_exists = ReturnExchangeRequest.objects.filter(
        order_item=order_item
    ).exclude(status__in=['completed', 'rejected']).exists()
    if active_exists:
        return JsonResponse({'status': 'error', 'message': 'An active request already exists for this item.'}, status=400)

    # Validate exchange size and stock
    exchange_size = None
    if request_type == 'exchange':
        if not exchange_size_id:
            return JsonResponse({'status': 'error', 'message': 'Please select a new size for exchange.'}, status=400)
        try:
            from products.models import Size
            exchange_size = Size.objects.get(id=exchange_size_id)
            stock = ProductSizeStock.objects.get(variant=order_item.variant, size=exchange_size)
            if stock.stock < order_item.quantity:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Size {exchange_size.name} is out of stock. Only {stock.stock} available.'
                }, status=400)
        except (Size.DoesNotExist, ProductSizeStock.DoesNotExist):
            return JsonResponse({'status': 'error', 'message': 'Selected size is not available.'}, status=400)

    # Validate images
    images = request.FILES.getlist('images')
    ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
    MAX_SIZE = 2 * 1024 * 1024
    for img_file in images[:5]:  # Max 5
        ext = os.path.splitext(img_file.name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return JsonResponse({'status': 'error', 'message': f'"{img_file.name}" is not a supported format.'}, status=400)
        if img_file.size > MAX_SIZE:
            return JsonResponse({'status': 'error', 'message': f'"{img_file.name}" exceeds the 2MB limit.'}, status=400)

    # Create the request
    ret_request = ReturnExchangeRequest.objects.create(
        user=request.user,
        order=order,
        order_item=order_item,
        request_type=request_type,
        reason=reason,
        comment=comment,
        exchange_size=exchange_size,
    )

    # Save images
    for idx, img_file in enumerate(images[:5]):
        ReturnExchangeImage.objects.create(
            request=ret_request,
            image=img_file,
            position=idx,
        )

    return JsonResponse({
        'status': 'success',
        'message': f'{ret_request.get_request_type_display()} request submitted successfully.',
        'request_id': ret_request.id,
        'request_status': ret_request.status,
        'request_type': ret_request.request_type,
    })
