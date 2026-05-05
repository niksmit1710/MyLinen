from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from products.models import Product, ProductVariant, ProductSizeStock
from orders.models import Coupon

def add_to_cart(request, product_id):
    # Note: product_id here might be a legacy param, but we'll use variant_id from POST
    if request.method == 'POST':
        variant_id = request.POST.get('variant_id')
        size_id = request.POST.get('size_id')
        quantity = int(request.POST.get('quantity', 1))

        variant = get_object_or_404(ProductVariant, id=variant_id)
        size_stock = get_object_or_404(
            ProductSizeStock,
            variant=variant,
            size__id=size_id
        )

        # Stock check
        if quantity > size_stock.stock:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': 'Not enough stock'}, status=400)
            return redirect('product_detail', id=variant.product.id)

        cart = request.session.get('cart', {})

        # Key is now variant + size
        key = f"{variant.id}_{size_id}"

        if key in cart:
            cart[key]['quantity'] += quantity
            # Cap at stock
            if cart[key]['quantity'] > size_stock.stock:
                cart[key]['quantity'] = size_stock.stock
        else:
            cart[key] = {
                'variant_id': variant.id,
                'product_id': variant.product.id,
                'size_id': size_id,
                'name': variant.product.name,
                'color': variant.color.name,
                'image': variant.primary_image.url if variant.primary_image else '',
                'size': size_stock.size.name,
                'price': float(variant.current_price),
                'mrp': float(variant.current_mrp) if variant.current_mrp else None,
                'quantity': quantity
            }

        request.session['cart'] = cart
        request.session.modified = True
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'success',
                'cart_count': sum(item['quantity'] for item in cart.values())
            })

    return redirect('cart_detail')


from datetime import datetime, timedelta

def cart_detail(request):
    cart = request.session.get('cart', {})
    subtotal = 0
    delivery_date = datetime.now() + timedelta(days=10)
    
    for key, item in cart.items():
        item['total_price'] = item['price'] * item['quantity']
        item['total_mrp'] = (item.get('mrp') or item['price']) * item['quantity']
        subtotal += item['total_price']
        
        # Fetch available sizes for this variant
        try:
            variant = ProductVariant.objects.get(id=item.get('variant_id'))
            item['available_sizes'] = ProductSizeStock.objects.filter(
                variant=variant, 
                stock__gt=0
            ).select_related('size')
        except (ProductVariant.DoesNotExist, KeyError):
            item['available_sizes'] = []

    coupon_code = request.session.get('applied_coupon')
    discount_amount = 0
    applied_coupon = None

    if coupon_code:
        try:
            coupon = Coupon.objects.get(code=coupon_code)
            if coupon.is_valid():
                from decimal import Decimal
                if Decimal(subtotal) >= coupon.min_order_value:
                    discount_amount = float(coupon.calculate_discount(Decimal(subtotal)))
                    applied_coupon = coupon
            else:
                del request.session['applied_coupon']
        except Coupon.DoesNotExist:
            del request.session['applied_coupon']

    grand_total = float(subtotal) - discount_amount

    return render(request, 'cart.html', {
        'cart': cart,
        'subtotal': subtotal,
        'discount_amount': discount_amount,
        'grand_total': grand_total,
        'applied_coupon': applied_coupon,
        'delivery_date': delivery_date
    })
    
    
def update_cart(request, key):
    cart = request.session.get('cart', {})
    new_key = key

    if key in cart:
        quantity = request.POST.get('quantity')
        size_id = request.POST.get('size_id')
        
        variant_id = cart[key].get('variant_id')
        current_size_id = str(cart[key]['size_id'])
        
        if quantity:
            quantity = int(quantity)
            if quantity < 1: quantity = 1
        else:
            quantity = cart[key]['quantity']

        # Handle size change
        merged = False
        if size_id and size_id != current_size_id:
            try:
                size_stock = ProductSizeStock.objects.get(variant_id=variant_id, size_id=size_id)
                if size_stock.stock > 0:
                    if quantity > size_stock.stock:
                        quantity = size_stock.stock
                    
                    cart[key]['size_id'] = size_id
                    cart[key]['size'] = size_stock.size.name
                    new_key = f"{variant_id}_{size_id}"
                    
                    if new_key != key:
                        if new_key in cart:
                            cart[new_key]['quantity'] += quantity
                            if cart[new_key]['quantity'] > size_stock.stock:
                                cart[new_key]['quantity'] = size_stock.stock
                            del cart[key]
                            merged = True
                        else:
                            cart[new_key] = cart.pop(key)
                            merged = False
                        
                        cart[new_key]['quantity'] = quantity
                else:
                    return JsonResponse({'status': 'error', 'message': 'Selected size is out of stock'}, status=400)
            except ProductSizeStock.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': 'Invalid size selected'}, status=400)
        else:
            # Only quantity change
            try:
                stock = ProductSizeStock.objects.get(variant_id=variant_id, size_id=current_size_id).stock
                if quantity > stock:
                    quantity = stock
                    status = 'error'
                    message = f'Only {stock} items available'
                else:
                    status = 'success'
                    message = 'Quantity updated'
                
                cart[new_key]['quantity'] = quantity
            except ProductSizeStock.DoesNotExist:
                status = 'error'
                message = 'Product data error'

        request.session['cart'] = cart
        request.session.modified = True

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        subtotal = 0
        for k, item in cart.items():
            item['total_price'] = item['price'] * item['quantity']
            subtotal += item['total_price']

        coupon_code = request.session.get('applied_coupon')
        discount_amount = 0
        if coupon_code:
            try:
                coupon = Coupon.objects.get(code=coupon_code)
                if coupon.is_valid():
                    from decimal import Decimal
                    if Decimal(subtotal) >= coupon.min_order_value:
                        discount_amount = float(coupon.calculate_discount(Decimal(subtotal)))
            except Coupon.DoesNotExist:
                pass

        grand_total = float(subtotal) - discount_amount
        cart_count = sum(item['quantity'] for item in cart.values())

        return JsonResponse({
            'status': 'success',
            'new_key': new_key,
            'quantity': cart[new_key]['quantity'] if new_key in cart else 0,
            'size': cart[new_key]['size'] if new_key in cart else '',
            'item_total': cart[new_key]['price'] * cart[new_key]['quantity'] if new_key in cart else 0,
            'item_mrp_total': (cart[new_key].get('mrp') or cart[new_key]['price']) * cart[new_key]['quantity'] if new_key in cart else 0,
            'subtotal': subtotal,
            'discount_amount': discount_amount,
            'grand_total': grand_total,
            'cart_count': cart_count,
            'merged': merged
        })

    return redirect('cart_detail')

def remove_from_cart(request, key):
    cart = request.session.get('cart', {})

    if key in cart:
        del cart[key]

    request.session['cart'] = cart

    return redirect('cart_detail')

def checkout(request):
    coupon_code = request.POST.get('coupon')

    if coupon_code:
        try:
            coupon = Coupon.objects.get(code=coupon_code, is_active=True)
            # Placeholder logic - needs proper cart total implementation
        except:
            pass
    return render(request, 'checkout.html')
