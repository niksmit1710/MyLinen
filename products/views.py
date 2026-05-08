import os

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.db.models import Avg, Count, F, ExpressionWrapper, FloatField, Prefetch
from django.db.models.functions import Coalesce, Round
from .models import Product, ProductVariant, Category, Review, Color, ReviewImage


def homepage(request):
    featured_products = Product.objects.filter(is_featured=True).annotate(
        avg_rating=Round(Coalesce(Avg('reviews__rating'), 0.0), 1),
        review_count=Count('reviews')
    ).order_by('-id')[:8]
    
    # Fallback to newest products if no products are marked as featured
    if not featured_products.exists():
        featured_products = Product.objects.annotate(
            avg_rating=Round(Coalesce(Avg('reviews__rating'), 0.0), 1),
            review_count=Count('reviews')
        ).order_by('-id')[:8]
    wishlist_product_ids = set()
    if request.user.is_authenticated:
        from wishlist.models import Wishlist
        wishlist_product_ids = set(Wishlist.objects.filter(user=request.user).values_list('variant__product_id', flat=True))

    also_like_products = Product.objects.exclude(
        id__in=[p.id for p in featured_products]
    ).annotate(
        avg_rating=Round(Coalesce(Avg('reviews__rating'), 0.0), 1),
        review_count=Count('reviews')
    ).order_by('?')[:12]

    return render(request, 'index.html', {
        'trending_products': featured_products,
        'also_like_products': also_like_products,
        'wishlist_product_ids': wishlist_product_ids,
    })


def product_list(request):
    products = Product.objects.select_related('category').prefetch_related(
        'variants', 
        'variants__color',
        'variants__images',
        'deprecated_images'
    ).annotate(
        avg_rating=Round(Coalesce(Avg('reviews__rating'), 0.0), 1),
        review_count=Count('reviews')
    ).all()
    # Annotate categories with product counts
    categories = Category.objects.filter(parent=None).annotate(
        product_count=Count('product', distinct=True) + Count('subcategories__product', distinct=True)
    ).prefetch_related(
        Prefetch('subcategories', queryset=Category.objects.annotate(
            product_count=Count('product', distinct=True)
        ))
    )

    # --- Search ---
    query = request.GET.get('q', '').strip()
    if query:
        from django.db.models import Q
        singular_query = query
        
        # Basic plural to singular logic
        lower_q = query.lower()
        if lower_q.endswith('ies'):
            singular_query = query[:-3] + 'y'
        elif lower_q.endswith('sses'):
            singular_query = query[:-2]
        elif lower_q.endswith('oes') or lower_q.endswith('ches') or lower_q.endswith('shes'):
            singular_query = query[:-2]
        elif lower_q.endswith('s') and not lower_q.endswith('ss'):
            singular_query = query[:-1]

        products = products.filter(
            Q(name__icontains=query) | 
            Q(name__icontains=singular_query) |
            Q(category__name__icontains=query) |
            Q(category__name__icontains=singular_query)
        ).distinct()

    # --- Category filter ---
    category_vals = request.GET.getlist('category')
    selected_categories_objs = []
    if category_vals:
        all_ids = set()
        for val in category_vals:
            if not val: continue
            if val.isdigit():
                matching_cats = Category.objects.filter(id=int(val))
            else:
                matching_cats = Category.objects.filter(name__iexact=val)
            
            for cat_obj in matching_cats:
                selected_categories_objs.append(cat_obj)
                all_ids.add(cat_obj.id)
                # include subcategories
                all_ids.update(cat_obj.subcategories.values_list('id', flat=True))
        
        if all_ids:
            products = products.filter(category_id__in=all_ids).distinct()

    # --- Price range filter ---
    min_price = request.GET.get('min_price', '').strip()
    max_price = request.GET.get('max_price', '').strip()
    if min_price:
        try:
            products = products.filter(variants__price__gte=float(min_price)).distinct()
        except ValueError:
            pass
    if max_price:
        try:
            products = products.filter(variants__price__lte=float(max_price)).distinct()
        except ValueError:
            pass

    # --- Color filter (multi-select) ---
    selected_color_ids = request.GET.getlist('color')
    selected_color_ids = [c for c in selected_color_ids if c.isdigit()]
    if selected_color_ids:
        products = products.filter(variants__color_id__in=selected_color_ids).distinct()

    # --- Discount filter ---
    discount_val = request.GET.get('discount', '').strip()
    if discount_val:
        try:
            discount_float = float(discount_val)
            # Filter variants with discount
            products = products.filter(
                variants__mrp__gt=F('variants__price'), 
                variants__mrp__isnull=False
            ).annotate(
                discount_calc=ExpressionWrapper(
                    100.0 * (F('variants__mrp') - F('variants__price')) / F('variants__mrp'),
                    output_field=FloatField()
                )
            ).filter(discount_calc__gte=discount_float).distinct()
        except ValueError:
            pass

    # --- Sort ---
    sort = request.GET.get('sort', '')
    if sort == 'price_asc':
        products = products.order_by('variants__price').distinct()
    elif sort == 'price_desc':
        products = products.order_by('-variants__price').distinct()
    elif sort == 'name_asc':
        products = products.order_by('name')
    else:
        products = products.order_by('-id')

    wishlist_product_ids = set()
    if request.user.is_authenticated:
        from wishlist.models import Wishlist
        wishlist_product_ids = set(Wishlist.objects.filter(user=request.user).values_list('variant__product_id', flat=True))

    # Determine the parent category for the sidebar filter display
    # (Using the first selected category to find the parent in our annotated list)
    filter_parent_category = None
    if selected_categories_objs:
        first_selected = selected_categories_objs[0]
        target_id = first_selected.parent_id if first_selected.parent_id else first_selected.id
        
        for cat in categories:
            if cat.id == target_id:
                filter_parent_category = cat
                break

    # Available colors for the filter sidebar
    all_colors = Color.objects.all()

    # Calculate filter count (excluding sort)
    filter_count = 0
    if category_vals: filter_count += 1
    if min_price or max_price: filter_count += 1
    if selected_color_ids: filter_count += 1
    if discount_val: filter_count += 1

    selected_category_names = ", ".join([c.name for c in selected_categories_objs])

    return render(request, 'product_list.html', {
        'products': products,
        'categories': categories,
        'query': query,
        'selected_categories': category_vals,
        'selected_category_name': selected_category_names,
        'selected_categories_objs': selected_categories_objs,
        'filter_parent_category': filter_parent_category,
        'min_price': min_price,
        'max_price': max_price,
        'sort': sort,
        'wishlist_product_ids': wishlist_product_ids,
        'all_colors': all_colors,
        'selected_color_ids': selected_color_ids,
        'filter_count': filter_count,
    })


def product_detail(request, id):
    product = get_object_or_404(
        Product.objects.prefetch_related(
            Prefetch('variants', queryset=ProductVariant.objects.filter(is_active=True).select_related('color').prefetch_related('images', 'size_stocks__size')),
            'deprecated_images',
            'deprecated_size_stocks__size'
        ), 
        id=id
    )
    
    variants = product.variants.all()
    if not variants:
        # Handle product with no variants gracefully
        return redirect('homepage')

    # Pick the first available variant as default
    default_variant = variants.first()
    
    in_wishlist = False
    if request.user.is_authenticated:
        from wishlist.models import Wishlist
        in_wishlist = Wishlist.objects.filter(user=request.user, variant__product=product).exists()

    # Reviews data (prefetch images for each review)
    reviews = product.reviews.select_related('user').prefetch_related('review_images').all()
    review_count = reviews.count()
    avg_rating = reviews.aggregate(avg=Avg('rating'))['avg'] or 0
    avg_rating = round(avg_rating, 1)

    # Rating distribution
    rating_dist = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
    dist_qs = reviews.values('rating').annotate(count=Count('id'))
    for entry in dist_qs:
        rating_dist[entry['rating']] = entry['count']

    # Calculate percentages for rating bars
    rating_bars = []
    for star in range(5, 0, -1):
        count = rating_dist[star]
        pct = (count / review_count * 100) if review_count > 0 else 0
        rating_bars.append({'star': star, 'count': count, 'pct': round(pct)})

    # Verified buyer check
    is_verified_buyer = False
    user_review = None
    user_review_images = []
    if request.user.is_authenticated:
        user_review = Review.objects.filter(product=product, user=request.user).first()
        if user_review:
            user_review_images = user_review.review_images.all()
        from orders.models import OrderItem
        is_verified_buyer = OrderItem.objects.filter(
            order__user=request.user,
            variant__product=product, # Buyer of ANY variant of this product
            order__status='delivered'
        ).exists()

    # Prepare variant data for JS
    variants_json = []
    for v in variants:
        # Get sizes for this variant, fallback to product-level sizes if variant has none
        variant_sizes = list(v.size_stocks.all())
        if not variant_sizes:
            variant_sizes = list(product.deprecated_size_stocks.all())

        variants_json.append({
            'id': v.id,
            'color_name': v.color.name,
            'price': float(v.current_price),
            'mrp': float(v.current_mrp) if v.current_mrp else None,
            'is_on_sale': v.is_on_sale,
            'original_price': float(v.price) if v.price else None,
            'image_url': v.primary_image.url if v.primary_image else '',
            'sizes': [
                {
                    'id': ss.size.id,
                    'name': ss.size.name,
                    'stock': ss.stock
                } for ss in variant_sizes
            ]
        })

    # Related products: same category, excluding current product
    related_products = Product.objects.filter(
        category=product.category
    ).exclude(id=product.id).annotate(
        avg_rating=Round(Coalesce(Avg('reviews__rating'), 0.0), 1),
        review_count=Count('reviews')
    ).order_by('?')[:12]

    return render(request, 'product_detail.html', {
        'product': product,
        'variants': variants,
        'default_variant': default_variant,
        'variants_json': variants_json,
        'in_wishlist': in_wishlist,
        'reviews': reviews,
        'review_count': review_count,
        'avg_rating': avg_rating,
        'rating_bars': rating_bars,
        'user_review': user_review,
        'user_review_images': user_review_images,
        'is_verified_buyer': is_verified_buyer,
        'related_products': related_products,
    })


def submit_review(request, id):
    """Handle AJAX review submission with optional image uploads."""
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'Please login to submit a review.'}, status=401)

    product = get_object_or_404(Product, id=id)

    # Only verified buyers (with a delivered order) can review
    from orders.models import OrderItem
    is_verified_buyer = OrderItem.objects.filter(
        order__user=request.user,
        variant__product=product,
        order__status='delivered'
    ).exists()
    if not is_verified_buyer:
        return JsonResponse({'status': 'error', 'message': 'Only verified buyers can submit a review.'}, status=403)

    if request.method == 'POST':
        rating = request.POST.get('rating')
        title = request.POST.get('title', '').strip()
        comment = request.POST.get('comment', '').strip()

        if not rating or not comment:
            return JsonResponse({'status': 'error', 'message': 'Rating and comment are required.'})

        try:
            rating = int(rating)
            if rating < 1 or rating > 5:
                raise ValueError
        except (ValueError, TypeError):
            return JsonResponse({'status': 'error', 'message': 'Invalid rating value.'})

        # --- Validate uploaded images ---
        images = request.FILES.getlist('images')
        if len(images) > ReviewImage.MAX_IMAGES_PER_REVIEW:
            return JsonResponse({
                'status': 'error',
                'message': f'Maximum {ReviewImage.MAX_IMAGES_PER_REVIEW} images allowed.'
            })

        for img_file in images:
            # Check file size
            if img_file.size > ReviewImage.MAX_FILE_SIZE:
                return JsonResponse({
                    'status': 'error',
                    'message': f'"{img_file.name}" exceeds the 2MB size limit.'
                })
            # Check extension
            ext = os.path.splitext(img_file.name)[1].lower()
            if ext not in ReviewImage.ALLOWED_EXTENSIONS:
                return JsonResponse({
                    'status': 'error',
                    'message': f'"{img_file.name}" is not a supported format. Use JPG, PNG, or WEBP.'
                })
            # Check content type
            allowed_types = {'image/jpeg', 'image/png', 'image/webp'}
            if img_file.content_type not in allowed_types:
                return JsonResponse({
                    'status': 'error',
                    'message': f'"{img_file.name}" has an invalid content type.'
                })

        # --- Create or update the review (atomic to prevent duplicates) ---
        review_obj, created = Review.objects.update_or_create(
            product=product,
            user=request.user,
            defaults={
                'rating': rating,
                'title': title,
                'comment': comment,
            }
        )
        action = 'created' if created else 'updated'

        # Delete old images and replace with new ones (only if new images uploaded)
        if not created and images:
            review_obj.review_images.all().delete()

        # --- Save uploaded images ---
        for idx, img_file in enumerate(images):
            ReviewImage.objects.create(
                review=review_obj,
                image=img_file,
                position=idx
            )

        # Recalculate stats
        reviews = product.reviews.all()
        new_count = reviews.count()
        new_avg = reviews.aggregate(avg=Avg('rating'))['avg'] or 0
        new_avg = round(new_avg, 1)

        # Build image URLs for the AJAX response
        image_urls = [ri.image.url for ri in review_obj.review_images.all()]

        return JsonResponse({
            'status': 'success',
            'action': action,
            'review_count': new_count,
            'avg_rating': new_avg,
            'display_name': request.user.get_display_name(),
            'rating': rating,
            'title': title,
            'comment': comment,
            'image_urls': image_urls,
        })

    return JsonResponse({'status': 'error', 'message': 'Invalid request.'})


def about_us(request):
    return render(request, 'about_us.html')
