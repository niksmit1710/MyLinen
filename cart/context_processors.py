def cart_contents(request):
    cart = request.session.get('cart', {})
    cart_product_ids = []
    for key in cart.keys():
        try:
            # Handle both string and int keys if necessary
            pid = str(key).split('_')[0]
            cart_product_ids.append(int(pid))
        except (ValueError, IndexError):
            pass
    cart_count = sum(item['quantity'] for item in cart.values())
            
    return {
        'cart_product_ids': cart_product_ids,
        'cart_count': cart_count
    }
