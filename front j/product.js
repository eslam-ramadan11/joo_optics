// Logic for product.html. Loaded after frontend.js, reuses its
// apiCall/escapeHtml/formatPrice/assetUrl/upsertCartItem helpers.

let currentProduct = null;
let selectedColor = null;
let currentQty = 1;

function getProductIdFromQuery() {
    const params = new URLSearchParams(window.location.search);
    const id = params.get('id');
    return id ? Number(id) : null;
}

function buildImageSet(product, color) {
    // General/default images: the main product photo plus any gallery
    // images that aren't tagged to a specific color.
    const generalImages = [
        { image_file: product.image_file, color: null },
        ...(product.images || []).filter((img) => !img.color),
    ];

    if (!color) {
        return generalImages;
    }

    const colorImages = (product.images || []).filter(
        (img) => (img.color || '').toLowerCase() === color.toLowerCase()
    );

    // If this color has no photos of its own yet, fall back to the
    // general set rather than showing an empty gallery.
    return colorImages.length > 0 ? colorImages : generalImages;
}

function renderGallery(product, color) {
    const images = buildImageSet(product, color).slice(0, 3);
    const mainImg = document.getElementById('mainImage');
    const thumbContainer = document.getElementById('thumbGallery');

    const urls = images.map((img) => assetUrl(img.image_file));
    if (urls.length === 0) {
        urls.push(assetUrl(product.image_file));
    }

    mainImg.src = urls[0];
    mainImg.alt = product.name;

    thumbContainer.innerHTML = urls
        .map(
            (url, i) => `<img src="${escapeHtml(url)}" alt="${escapeHtml(product.name)} ${i + 1}" class="${i === 0 ? 'active-thumb' : ''}" data-thumb-index="${i}">`
        )
        .join('');

    thumbContainer.querySelectorAll('img').forEach((thumbEl, i) => {
        thumbEl.addEventListener('click', () => {
            mainImg.src = urls[i];
            thumbContainer.querySelectorAll('img').forEach((t) => t.classList.remove('active-thumb'));
            thumbEl.classList.add('active-thumb');
        });
    });
}

function renderColorSwatches(product) {
    const group = document.getElementById('colorSwatchGroup');
    const container = document.getElementById('colorSwatches');

    const colors = (product.colors || '')
        .split(',')
        .map((c) => c.trim())
        .filter(Boolean);

    if (colors.length <= 1) {
        group.style.display = 'none';
        return;
    }

    group.style.display = 'block';
    container.innerHTML = colors
        .map(
            (c, i) => `<button type="button" class="color-swatch ${i === 0 ? 'active' : ''}" data-color="${escapeHtml(c)}">${escapeHtml(c)}</button>`
        )
        .join('');

    container.querySelectorAll('.color-swatch').forEach((btn) => {
        btn.addEventListener('click', () => {
            container.querySelectorAll('.color-swatch').forEach((b) => b.classList.remove('active'));
            btn.classList.add('active');
            selectedColor = btn.dataset.color;
            renderGallery(currentProduct, selectedColor);
        });
    });

    selectedColor = colors[0];
}

function updateProductSeo(product) {
    const description = `${product.name} - ${product.category} من Joo Optics. السعر ${formatPrice(product.price)} جنيه. اطلب أونلاين في مصر.`;
    // og:image must be an absolute URL (with domain) - WhatsApp/Facebook/etc.
    // can't resolve a relative path like assetUrl() normally returns when
    // they fetch the link preview.
    const imageUrl = `${window.location.origin}${assetUrl(product.image_file)}`;

    document.title = `${product.name} - Joo Optics`;

    // FIX: frontend.js's sitewide setCanonicalTag() strips all query
    // params, which works for filtered views like shop.html?category=X but
    // is wrong here - ?id=X IS the product's identity, so every product
    // would otherwise canonicalize to the same bare /product.html.
    let canonical = document.querySelector('link[rel="canonical"]');
    if (!canonical) {
        canonical = document.createElement('link');
        canonical.rel = 'canonical';
        document.head.appendChild(canonical);
    }
    canonical.href = window.location.origin + window.location.pathname + window.location.search;

    const descTag = document.querySelector('meta[name="description"]');
    if (descTag) descTag.setAttribute('content', description);

    const ogTitle = document.querySelector('meta[property="og:title"]');
    if (ogTitle) ogTitle.setAttribute('content', `${product.name} - Joo Optics`);

    const ogDesc = document.querySelector('meta[property="og:description"]');
    if (ogDesc) ogDesc.setAttribute('content', description);

    const ogImage = document.querySelector('meta[property="og:image"]');
    if (ogImage) ogImage.setAttribute('content', imageUrl);

    const ogType = document.querySelector('meta[property="og:type"]');
    if (ogType) ogType.setAttribute('content', 'product');

    // JSON-LD structured data, so search engines can show price/stock
    // directly in results instead of just a plain blue link.
    const ld = {
        '@context': 'https://schema.org/',
        '@type': 'Product',
        name: product.name,
        image: [imageUrl],
        description,
        category: product.category,
        offers: {
            '@type': 'Offer',
            priceCurrency: 'EGP',
            price: product.price,
            availability: (Number(product.stock_quantity) || 0) > 0
                ? 'https://schema.org/InStock'
                : 'https://schema.org/OutOfStock',
        },
    };

    let script = document.getElementById('product-jsonld');
    if (!script) {
        script = document.createElement('script');
        script.type = 'application/ld+json';
        script.id = 'product-jsonld';
        document.head.appendChild(script);
    }
    script.textContent = JSON.stringify(ld);
}

function renderProductInfo(product) {
    updateProductSeo(product);
    document.getElementById('productCategory').textContent = categoryLabel(product.category);
    document.getElementById('productName').textContent = product.name;
    document.getElementById('productPrice').textContent = `${formatPrice(product.price)} EGP`;

    const oldPriceEl = document.getElementById('productOldPrice');
    if (product.old_price) {
        oldPriceEl.textContent = `${formatPrice(product.old_price)} EGP`;
        oldPriceEl.style.display = 'inline';
    } else {
        oldPriceEl.style.display = 'none';
    }

    const badgeEl = document.getElementById('productDiscountBadge');
    if (product.discount_badge) {
        badgeEl.textContent = product.discount_badge;
        badgeEl.style.display = 'inline-block';
    } else {
        badgeEl.style.display = 'none';
    }

    const stock = Number(product.stock_quantity) || 0;
    const stockEl = document.getElementById('productStock');
    stockEl.textContent = stock > 0 ? `متوفر (${stock})` : 'غير متوفر حاليًا';
    stockEl.style.color = stock > 0 ? '' : '#ef4444';
}

function renderBreadcrumbs(product) {
    const el = document.getElementById('breadcrumbs');
    if (!el) return;

    el.innerHTML = `
        <a href="index.html">الرئيسية</a>
        <span class="breadcrumb-sep">/</span>
        <a href="shop.html">المتجر</a>
        <span class="breadcrumb-sep">/</span>
        <a href="shop.html?category=${encodeURIComponent(product.category)}">${escapeHtml(categoryLabel(product.category))}</a>
        <span class="breadcrumb-sep">/</span>
        <span class="breadcrumb-current">${escapeHtml(product.name)}</span>
    `;
    el.style.display = 'block';
}

function wireQuantityControls(product) {
    const qtyValueEl = document.getElementById('qtyValue');
    const stock = Number(product.stock_quantity) || 0;

    document.getElementById('qtyMinus').addEventListener('click', () => {
        if (currentQty > 1) {
            currentQty -= 1;
            qtyValueEl.textContent = currentQty;
        }
    });

    document.getElementById('qtyPlus').addEventListener('click', () => {
        if (stock === 0 || currentQty < stock) {
            currentQty += 1;
            qtyValueEl.textContent = currentQty;
        } else {
            showToast(`المتاح بس ${stock} قطعة`, 'info');
        }
    });
}

function wireAddToCart(product) {
    const btn = document.getElementById('addToCartBtn');
    const stock = Number(product.stock_quantity) || 0;

    if (stock === 0) {
        btn.disabled = true;
        btn.textContent = 'غير متوفر حاليًا';
        return;
    }

    btn.addEventListener('click', () => {
        for (let i = 0; i < currentQty; i += 1) {
            upsertCartItem(product);
        }
        // upsertCartItem() opens the side cart, which shows what was added.
    });
}

async function loadRelatedProducts(product) {
    const section = document.getElementById('related-products-section');
    const container = document.getElementById('related-products');
    if (!section || !container) return;

    const params = new URLSearchParams({
        category: product.category,
        per_page: '8',
        sort_by: 'id',
        sort_dir: 'desc',
    });

    const data = await apiCall(`/products?${params.toString()}`);
    if (!data || !Array.isArray(data.items)) {
        return;
    }

    const related = data.items.filter((p) => p.id !== product.id).slice(0, 4);
    if (related.length === 0) {
        return;
    }

    container.innerHTML = related.map(renderProductCard).join('');
    wireAddToCartButtons(container);
    section.style.display = 'block';
}

async function initProductPage() {
    const productId = getProductIdFromQuery();
    const loadingEl = document.getElementById('product-loading');
    const notFoundEl = document.getElementById('product-not-found');
    const contentEl = document.getElementById('product-content');

    if (!productId) {
        loadingEl.style.display = 'none';
        notFoundEl.style.display = 'block';
        return;
    }

    const product = await apiCall(`/products/${productId}`);

    loadingEl.style.display = 'none';

    if (!product) {
        notFoundEl.style.display = 'block';
        return;
    }

    currentProduct = product;
    contentEl.style.display = 'grid';

    renderBreadcrumbs(product);
    renderProductInfo(product);
    renderColorSwatches(product);
    renderGallery(product, selectedColor);
    wireQuantityControls(product);
    wireAddToCart(product);
    loadRelatedProducts(product);

    if (typeof trackViewContent === 'function') {
        trackViewContent(product);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('product-page')) {
        initProductPage();
    }
});
