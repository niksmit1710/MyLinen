"""
Custom Cloudinary template tags for optimized image delivery.
Usage: {% load cloudinary_tags %}
       <img src="{% cloudinary_url image_field width=500 %}" loading="lazy" alt="...">
"""
from django import template
from django.conf import settings

register = template.Library()


def _is_cloudinary_url(url):
    return url and 'res.cloudinary.com' in str(url)


@register.simple_tag
def cloudinary_url(image_field, width=None, height=None, crop='fill', quality='auto', fetch_format='auto'):
    """
    Return an optimized Cloudinary URL with auto format and quality.
    Falls back to the raw URL if not a Cloudinary image.
    """
    if not image_field:
        return ''

    raw_url = str(image_field.url) if hasattr(image_field, 'url') else str(image_field)

    if not _is_cloudinary_url(raw_url):
        return raw_url

    try:
        import cloudinary
        # Build transformation options
        options = {
            'quality': quality,
            'fetch_format': fetch_format,
        }
        if width:
            options['width'] = width
            options['crop'] = crop
        if height:
            options['height'] = height

        # Extract public_id from URL
        # URL format: .../upload/v123/products/image.jpg
        parts = raw_url.split('/upload/')
        if len(parts) == 2:
            right = parts[1]
            # Strip version segment if present (v12345/)
            if right.startswith('v') and '/' in right:
                right = right.split('/', 1)[1]
            # Strip extension for Cloudinary to apply fetch_format
            public_id_with_ext = right
            # Build transformation string
            transforms = []
            if width:
                transforms.append(f'w_{width}')
            if height:
                transforms.append(f'h_{height}')
            transforms.append(f'c_{crop}')
            transforms.append(f'q_{quality}')
            transforms.append(f'f_{fetch_format}')
            transform_str = ','.join(transforms)
            optimized_url = f"{parts[0]}/upload/{transform_str}/{public_id_with_ext}"
            return optimized_url
    except Exception:
        pass

    return raw_url


@register.simple_tag
def cloudinary_card_url(image_field):
    """Shortcut for product card images: 500px wide, auto quality/format."""
    return cloudinary_url(image_field, width=500, crop='fill')


@register.simple_tag
def cloudinary_thumb_url(image_field):
    """Shortcut for thumbnail images: 150px wide."""
    return cloudinary_url(image_field, width=150, height=190, crop='fill')


@register.simple_tag
def cloudinary_hero_url(image_field):
    """Shortcut for hero / main product images: 900px wide."""
    return cloudinary_url(image_field, width=900, crop='limit')
