// script.js
document.addEventListener("DOMContentLoaded", () => {
    // Initialize Lucide icons
    if (window.lucide) lucide.createIcons();

    // Mobile Menu Toggle
    const mobileMenuToggle = document.querySelector('.mobile-menu-toggle');
    const mobileMenuClose = document.querySelector('.mobile-menu-close');
    const mobileNav = document.getElementById('mobileNav');

    if (mobileMenuToggle && mobileNav) {
        mobileMenuToggle.addEventListener('click', () => {
            mobileNav.classList.add('active');
            document.body.style.overflow = 'hidden'; // Prevent scrolling when menu is open
        });
    }

    if (mobileMenuClose && mobileNav) {
        mobileMenuClose.addEventListener('click', () => {
            mobileNav.classList.remove('active');
            document.body.style.overflow = '';
        });
    }

    // Close menu when clicking outside the content
    if (mobileNav) {
        mobileNav.addEventListener('click', (e) => {
            if (e.target === mobileNav) {
                mobileNav.classList.remove('active');
                document.body.style.overflow = '';
            }
        });

        // Close menu when a link is clicked
        const mobileLinks = mobileNav.querySelectorAll('a');
        mobileLinks.forEach(link => {
            link.addEventListener('click', () => {
                mobileNav.classList.remove('active');
                document.body.style.overflow = '';
            });
        });
    }

    // Product List Filter Toggle
    const filterTrigger = document.getElementById('filterTrigger');
    const filterClose = document.getElementById('filterClose');
    const filterSidebar = document.getElementById('filterSidebar');
    const filterOverlay = document.getElementById('filterOverlay');

    if (filterTrigger && filterSidebar) {
        filterTrigger.addEventListener('click', () => {
            filterSidebar.classList.add('active');
            if (filterOverlay) filterOverlay.classList.add('active');
            document.body.style.overflow = 'hidden';
        });
    }

    if (filterSidebar) {
        const closeFilter = () => {
            filterSidebar.classList.remove('active');
            if (filterOverlay) filterOverlay.classList.remove('active');
            document.body.style.overflow = '';
        };

        if (filterClose) filterClose.addEventListener('click', closeFilter);
        if (filterOverlay) filterOverlay.addEventListener('click', closeFilter);
    }

    // Explicit Cleanup for Mobile Nav on Load
    if (mobileNav) {
        mobileNav.classList.remove('active');
        document.body.style.overflow = '';
    }
});

let currentIndex = 0;
const totalSlides = 6;
const visibleSlides = 3;
const maxIndex = totalSlides - visibleSlides; // We can only slide 3 times (0, 1, 2, 3)

function currentSlide(index) {
    const track = document.getElementById('sliderTrack');
    const dots = document.querySelectorAll('.dot');

    // Safety check: don't slide past the last visible set
    if (index > maxIndex) index = 0;
    if (index < 0) index = maxIndex;

    currentIndex = index;

    // Move by 16.666% (which is 1/6th of the track) per index
    const moveAmount = currentIndex * (100 / totalSlides);
    track.style.transform = `translateX(-${moveAmount}%)`;

    // Update dots
    dots.forEach((dot, i) => {
        dot.classList.toggle('active', i === currentIndex);
    });
}

function startAutoSlide() {
    // Clear any existing intervals to prevent "speeding up"
    if (window.slideInterval) clearInterval(window.slideInterval);

    window.slideInterval = setInterval(() => {
        currentIndex++;
        if (currentIndex > maxIndex) {
            currentIndex = 0;
        }
        currentSlide(currentIndex);
    }, 4000);
}

// Start everything
document.addEventListener('DOMContentLoaded', () => {
    startAutoSlide();
});

//icon refresh

document.addEventListener('DOMContentLoaded', () => {
    // This line searches for all <i data-lucide="..."> tags and replaces them with SVGs
    lucide.createIcons();
});

// Product List script
document.addEventListener('DOMContentLoaded', () => {
    // 1. Initialize Icons
    if (window.lucide) lucide.createIcons();
});