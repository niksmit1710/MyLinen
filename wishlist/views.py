from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from products.models import Product, ProductVariant
from .models import Wishlist

@login_required
def toggle_wishlist(request, product_id):
    variant_id = request.POST.get('variant_id')
    
    if variant_id:
        variant = get_object_or_404(ProductVariant, id=variant_id)
        wishlist_item, created = Wishlist.objects.get_or_create(user=request.user, variant=variant)
        if not created:
            wishlist_item.delete()
            action = 'removed'
        else:
            action = 'added'
    else:
        product = get_object_or_404(Product, id=product_id)
        # If no variant_id, toggle the whole product: 
        # If any variant is wishlisted, remove all. Otherwise, add the best available variant.
        existing_items = Wishlist.objects.filter(user=request.user, variant__product=product)
        
        if existing_items.exists():
            existing_items.delete()
            action = 'removed'
        else:
            # Select the first active and in-stock variant
            variant = ProductVariant.objects.filter(
                product=product,
                is_active=True,
                size_stocks__stock__gt=0
            ).distinct().first()
            
            # Fallback to first variant if no in-stock variant found
            if not variant:
                variant = ProductVariant.objects.filter(product=product).first()

            if not variant:
                return JsonResponse({'status': 'failed', 'error': 'No variants available for this product.'}, status=400)
            
            Wishlist.objects.create(user=request.user, variant=variant)
            action = 'added'
        
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success', 'action': action})
    
    return redirect('product_detail', id=product_id)

@login_required
def view_wishlist(request):
    wishlist_items = Wishlist.objects.filter(user=request.user).select_related(
        'variant', 
        'variant__product', 
        'variant__color'
    ).prefetch_related(
        'variant__images',
        'variant__size_stocks__size'
    )
    return render(request, 'wishlist.html', {'wishlist_items': wishlist_items})

@login_required
def move_to_cart(request, wishlist_item_id):
    if request.method == 'POST':
        from products.models import ProductSizeStock
        wishlist_item = get_object_or_404(Wishlist, id=wishlist_item_id, user=request.user)
        variant = wishlist_item.variant
        product = variant.product
        
        size_id = request.POST.get('size_id')
        
        if size_id:
            size_stock = ProductSizeStock.objects.filter(variant=variant, size_id=size_id, stock__gt=0).first()
        else:
            size_stock = ProductSizeStock.objects.filter(variant=variant, stock__gt=0).first()
        
        if not size_stock:
            return JsonResponse({'status': 'failed', 'error': 'Selected size is out of stock.'}, status=400)

        # Cart logic
        cart = request.session.get('cart', {})
        # New key format: variantID_sizeID
        key = f"{variant.id}_{size_stock.size.id}"
        
        if key in cart:
            cart[key]['quantity'] += 1
        else:
            cart[key] = {
                'product_id': product.id,
                'variant_id': variant.id,
                'size_id': size_stock.size.id,
                'name': product.name,
                'color': variant.color.name,
                'image': variant.primary_image.url if variant.primary_image else '',
                'size': size_stock.size.name,
                'price': float(variant.current_price),
                'mrp': float(variant.current_mrp) if variant.current_mrp else None,
                'quantity': 1
            }
        
        request.session['cart'] = cart
        wishlist_item.delete()
        
        return JsonResponse({'status': 'success', 'message': 'Moved to cart!'})
    
    return JsonResponse({'status': 'failed', 'error': 'Invalid request.'}, status=405)
