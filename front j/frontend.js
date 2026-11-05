const API_BASE_URL = '/api';
const CART_STORAGE_KEY = 'cart';
const PRODUCT_FALLBACK_IMAGE = 'favicon.svg';

// Arabic names for the fixed product categories (the API keys stay in
// English - they are what the database and the filters use).
const CATEGORY_LABELS_AR = {
    'men sunglasses': 'نظارات شمس رجالي',
    'womens sunglasses': 'نظارات شمس حريمي',
    'men medical fraims': 'نظارات طبية رجالي',
    'womens medical fraims': 'نظارات طبية حريمي',
    'kids glasses': 'نظارات أطفال',
};

function categoryLabel(category) {
    return CATEGORY_LABELS_AR[category] || category || '';
}

let authToken = localStorage.getItem('authToken');
let currentUser = null;
let cart = loadCart();
let shopState = {
    page: 1,
    perPage: 8,
    search: '',
    category: '',
    sortBy: 'id',
    sortDir: 'desc',
};

function loadCart() {
    try {
        const raw = localStorage.getItem(CART_STORAGE_KEY);
        const parsed = raw ? JSON.parse(raw) : [];
        return Array.isArray(parsed) ? parsed : [];
    } catch (_error) {
        return [];
    }
}

function saveCart() {
    localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(cart));
}

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function assetUrl(path) {
    if (!path) {
        return PRODUCT_FALLBACK_IMAGE;
    }

    if (path.startsWith('http://') || path.startsWith('https://') || path.startsWith('/')) {
        return path;
    }

    return `/static/${path.replace(/^\/+/, '')}`;
}

function formatPrice(value) {
    const amount = Number(value);
    return Number.isFinite(amount) ? amount.toFixed(2) : '0.00';
}

async function apiCall(endpoint, method = 'GET', data = null, isFormData = false, extraHeaders = {}) {
    const options = {
        method,
        headers: isFormData ? { ...extraHeaders } : { 'Content-Type': 'application/json', ...extraHeaders },
    };

    if (authToken) {
        options.headers.Authorization = `Bearer ${authToken}`;
    }

    if (data) {
        options.body = isFormData ? data : JSON.stringify(data);
    }

    try {
        const response = await fetch(`${API_BASE_URL}${endpoint}`, options);

        if (response.status === 204) {
            return null;
        }

        const contentType = response.headers.get('content-type') || '';
        const responseData = contentType.includes('application/json') ? await response.json() : await response.text();

        if (response.status === 401) {
            localStorage.removeItem('authToken');
            authToken = null;
            window.location.href = '/login.html';
            return null;
        }

        if (!response.ok) {
            const message = responseData?.message || responseData?.error || responseData || 'Request failed';
            console.error(`API Error: ${message}`);
            return null;
        }

        if (responseData && typeof responseData === 'object' && 'data' in responseData) {
            return responseData.data;
        }

        return responseData;
    } catch (error) {
        console.error('API Call Error:', error);
        return null;
    }
}

function updateCartCount() {
    const count = cart.reduce((total, item) => total + (Number(item.quantity) || 1), 0);
    const cartCount = document.getElementById('cart-count');
    if (cartCount) {
        cartCount.textContent = String(count);
    }
}

function upsertCartItem(product) {
    const existing = cart.find((item) => item.id === product.id);
    if (existing) {
        existing.quantity = (Number(existing.quantity) || 1) + 1;
    } else {
        cart.push({
            id: product.id,
            name: product.name,
            price: Number(product.price) || 0,
            quantity: 1,
            image_file: product.image_file,
        });
    }

    saveCart();
    updateCartCount();

    // Slide the cart in from the side so the customer sees what they just
    // added (and can go straight to checkout) instead of hunting for it.
    lastAddedCartId = product.id;
    openCartDrawer();
}

function showCart() {
    if (cart.length === 0) {
        showToast('السلة فاضية', 'info');
        return;
    }

    // The checkout page already shows the full cart - just bring it into view.
    if (/checkout\.html$/.test(window.location.pathname)) {
        window.scrollTo({ top: 0, behavior: 'smooth' });
        return;
    }

    openCartDrawer();
}

function addToCart(product) {
    // upsertCartItem() saves the cart and opens the side cart, which is the
    // confirmation - no separate toast needed. Browsing and filling the
    // cart are public; authentication is required only when the order is
    // submitted from checkout.
    upsertCartItem(product);

    if (typeof trackAddToCart === 'function') {
        trackAddToCart(product);
    }
}

function wireAddToCartButtons(scope = document) {
    scope.querySelectorAll('[data-add-to-cart]').forEach((button) => {
        button.addEventListener('click', () => {
            const product = {
                id: Number(button.dataset.id),
                name: button.dataset.name,
                price: Number(button.dataset.price),
                image_file: button.dataset.image,
            };
            addToCart(product);
        });
    });
}

function renderProductCard(product, index = 0) {
    const image = assetUrl(product.image_file);
    const delay = Math.min(index * 0.08, 0.6).toFixed(2);
    const inStock = (Number(product.stock_quantity) || 0) > 0;
    return `
        <div class="cardproduct reveal glow-card" style="transition-delay: ${delay}s" data-product-id="${product.id}">
            <div class="cardproduct-image-wrap">
                ${product.discount_badge ? `<span class="discount-badge">${escapeHtml(product.discount_badge)}</span>` : ''}
                ${!inStock ? '<span class="stock-badge">نفذت الكمية</span>' : ''}
                <a href="product.html?id=${product.id}" style="text-decoration:none; color:inherit;">
                    <img src="${escapeHtml(image)}" alt="${escapeHtml(product.name)}" loading="lazy">
                </a>
            </div>
            <a href="product.html?id=${product.id}" style="text-decoration:none; color:inherit;">
                <h3>${escapeHtml(product.name)}</h3>
            </a>
            <div class="cardproduct-price-row">
                <p class="price">${formatPrice(product.price)} جنيه</p>
                ${product.old_price ? `<p class="old-price">${formatPrice(product.old_price)} جنيه</p>` : ''}
            </div>
            <button type="button" class="button cardproduct-add-btn" data-add-to-cart data-id="${product.id}" data-name="${escapeHtml(product.name)}" data-price="${Number(product.price) || 0}" data-image="${escapeHtml(image)}" ${!inStock ? 'disabled' : ''}>
                <i class="fa-solid fa-bag-shopping"></i> ${inStock ? 'أضف للسلة' : 'نفذت الكمية'}
            </button>
        </div>
    `;
}

function updateUIForAuth() {
    const userButton = document.getElementById('userButton');
    const avatarBubble = document.getElementById('userAvatarBubble');
    const loginMenuBtn = document.getElementById('loginMenuBtn');
    const logoutMenuBtn = document.getElementById('logoutMenuBtn');
    const userInfoBtn = document.getElementById('userInfoBtn');

    if (!userButton) {
        return;
    }

    if (authToken) {
        if (avatarBubble) {
            const initial = (currentUser?.username || '?').charAt(0).toUpperCase();
            avatarBubble.textContent = initial;
        }
        userButton.title = currentUser?.username ? `مسجّل دخول باسم ${currentUser.username}` : 'حسابي';
        if (loginMenuBtn) loginMenuBtn.style.display = 'none';
        if (logoutMenuBtn) logoutMenuBtn.style.display = 'block';
        if (userInfoBtn) userInfoBtn.style.display = 'block';
    } else {
        if (avatarBubble) avatarBubble.textContent = '?';
        userButton.title = 'تسجيل الدخول / إنشاء حساب';
        if (loginMenuBtn) loginMenuBtn.style.display = 'block';
        if (logoutMenuBtn) logoutMenuBtn.style.display = 'none';
        if (userInfoBtn) userInfoBtn.style.display = 'none';
    }
}

function toggleUserMenu() {
    const menu = document.getElementById('userMenu');
    if (menu) {
        menu.style.display = menu.style.display === 'none' || !menu.style.display ? 'block' : 'none';
    }
}

function logout() {
    localStorage.removeItem('authToken');
    authToken = null;
    currentUser = null;
    updateUIForAuth();
    showToast('تم تسجيل الخروج', 'success');
    setTimeout(() => {
        window.location.href = '/index.html';
    }, 600);
}

async function loadCurrentUser() {
    if (!authToken) {
        return null;
    }

    const user = await apiCall('/user/profile');
    if (user) {
        currentUser = user;
        updateUIForAuth();
    }
    return user;
}

function showUserInfo() {
    if (!authToken) {
        showToast('سجّل دخول الأول', 'info');
        window.location.href = '/login.html';
        return;
    }

    window.location.href = '/account.html';
}

async function uploadPrescription(formData) {
    try {
        return await apiCall('/prescriptions', 'POST', formData, true);
    } catch (error) {
        // Intentionally silent here - callers already show their own
        // error message when this returns null, so alerting here too
        // would show the user two error popups for one failure.
        console.error('Upload error:', error);
        return null;
    }
}

function initRevealAnimations() {
    // FIX: this used to snapshot document.querySelectorAll('.reveal') once
    // and only ever check those specific elements. Product cards are added
    // to the DOM later (after the async product fetch resolves), so they
    // were never included in that snapshot and would stay invisible
    // forever. Re-querying on every check picks up anything added since.
    const checkReveal = () => {
        const triggerBottom = window.innerHeight * 0.88;
        document.querySelectorAll('.reveal:not(.active)').forEach((reveal) => {
            if (reveal.getBoundingClientRect().top < triggerBottom) {
                reveal.classList.add('active');
            }
        });
    };

    window.addEventListener('scroll', checkReveal);
    checkReveal();

    // Catch cards that get added after a fetch resolves, even if the user
    // isn't actively scrolling at that exact moment.
    const observer = new MutationObserver(() => checkReveal());
    observer.observe(document.body, { childList: true, subtree: true });
}

let calcSelectedUsages = [];

function initLensCalculator() {
    const form = document.getElementById('lensCalculatorForm');
    const resultsEl = document.getElementById('lensCalcResults');
    if (!form || !resultsEl) {
        return;
    }

    form.addEventListener('submit', async (event) => {
        event.preventDefault();

        if (typeof trackCalculatorStarted === 'function') {
            trackCalculatorStarted();
        }

        const sph_r = Number(document.getElementById('sph-r')?.value || 0);
        const cyl_r = Number(document.getElementById('cyl-r')?.value || 0);
        const sph_l = Number(document.getElementById('sph-l')?.value || 0);
        const cyl_l = Number(document.getElementById('cyl-l')?.value || 0);

        resultsEl.innerHTML = '<p class="product-meta"><span class="site-spinner"></span> جارٍ الحساب...</p>';
        calcSelectedUsages = [];

        const quote = await apiCall('/lens-catalog/quote', 'POST', { sph_r, cyl_r, sph_l, cyl_l });
        if (!quote) {
            resultsEl.innerHTML = '<p class="product-meta" style="color:#ef4444;">تعذر حساب السعر، حاول تاني.</p>';
            return;
        }

        renderLensCalcResults(quote);
    });
}

// Splits "Name - Arabic description" into its two parts for display only.
// The part after " - " is treated as a description only when it is Arabic
// text (e.g. "PG - حماية 50% ..."); labels like "Photogray - Blue Cut" are
// a single product name and are left whole. The full label is still what
// gets stored in data-label, so nothing downstream changes.
function splitLensLabel(label) {
    const text = String(label || '');
    const idx = text.indexOf(' - ');
    if (idx > 0 && /[؀-ۿ]/.test(text.slice(idx + 3))) {
        return { name: text.slice(0, idx), desc: text.slice(idx + 3) };
    }
    return { name: text, desc: '' };
}

function lensOptionCardHtml(opt, extraClass = '', badgeHtml = '') {
    const { name, desc } = splitLensLabel(opt.label);
    return `
        <article class="lens-opt ${extraClass}" tabindex="0" role="button"
                 data-lens-type="${escapeHtml(opt.lens_type)}" data-price="${escapeHtml(opt.price)}" data-label="${escapeHtml(opt.fullLabel)}">
            ${badgeHtml}
            <h4 class="lens-opt-name">${escapeHtml(name)}</h4>
            ${desc ? `<p class="lens-opt-desc">${escapeHtml(desc)}</p>` : ''}
            <div class="lens-opt-footer">
                <span class="lens-opt-price">${formatPrice(opt.price)} <small>EGP</small></span>
                <span class="lens-opt-btn">اختار</span>
            </div>
        </article>
    `;
}

function wireLensOptionCards(container) {
    const choose = (card) => showCalcBuyPrompt(card.dataset.lensType, card.dataset.price, card.dataset.label);
    container.querySelectorAll('.lens-opt').forEach((card) => {
        card.addEventListener('click', () => choose(card));
        card.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                choose(card);
            }
        });
    });
}

function renderLensCalcResults(quote) {
    const resultsEl = document.getElementById('lensCalcResults');
    if (!resultsEl) return;

    if (quote.is_special) {
        resultsEl.innerHTML = `
            <div class="lens-special-notice">
                <p>الأرقام دي محتاجة استشارة خاصة لتحديد السعر المناسب.</p>
                <a class="button" href="https://wa.me/${quote.whatsapp_number}" target="_blank" rel="noopener">تواصل معنا على واتساب</a>
            </div>
        `;
        return;
    }

    resultsEl.innerHTML = `
        <h3 class="calc-results-title">اختار نوع العدسة</h3>
        <div id="calcBasicOptions" class="lens-opt-grid"></div>
        <button type="button" id="calcAdvancedBtn" class="calc-advanced-btn" aria-expanded="false" aria-controls="calcAdvancedArea">
            <span>✨ ساعدني في اختيار عدسات متقدمة</span>
            <i class="fa-solid fa-chevron-down" aria-hidden="true"></i>
        </button>
        <div id="calcAdvancedArea" class="calc-wizard" style="display:none;"></div>
    `;

    renderCalcBasicOptions(quote);

    document.getElementById('calcAdvancedBtn').addEventListener('click', (event) => {
        const btn = event.currentTarget;
        const area = document.getElementById('calcAdvancedArea');
        const isHidden = area.style.display === 'none';
        area.style.display = isHidden ? 'block' : 'none';
        btn.setAttribute('aria-expanded', String(isHidden));
        btn.classList.toggle('open', isHidden);
        if (isHidden) {
            renderCalcUsageCheckboxes(quote);
        }
    });
}

function renderCalcBasicOptions(quote) {
    const container = document.getElementById('calcBasicOptions');
    if (!container) return;

    container.innerHTML = quote.basic_options
        .map((opt) => lensOptionCardHtml({ lens_type: opt.lens_type, price: opt.price, label: opt.label_ar, fullLabel: opt.label_ar }))
        .join('');

    wireLensOptionCards(container);
}

// ---- Advanced lens assistant (wizard) --------------------------------
// Step 1: pick up to two uses. Step 2: recommendations. The selection rule
// (max 2), the combo lookup in quote.usage_options and the prices are
// unchanged - only the presentation is a step-by-step wizard.

const CALC_USAGE_META = {
    computer: { icon: '💻', label: 'كمبيوتر وشاشات' },
    sun: { icon: '☀️', label: 'شمس وخروج' },
    night: { icon: '🚗', label: 'قيادة ليلية' },
    antibreak: { icon: '🛡️', label: 'ضد الكسر' },
};

function renderCalcUsageCheckboxes(quote) {
    const area = document.getElementById('calcAdvancedArea');
    if (!area) return;

    calcSelectedUsages = [];

    area.innerHTML = `
        <ol class="wizard-steps" aria-label="خطوات المساعد">
            <li class="active" id="wizStep1">1. الاستخدام</li>
            <li id="wizStep2">2. الترشيحات</li>
        </ol>

        <div id="wizPanel1">
            <h3 class="wizard-title">محتاج النظارة لإيه؟</h3>
            <p class="wizard-hint">اختار استخدام واحد أو اتنين بحد أقصى.</p>
            <div class="usage-tiles" id="calcUsageCheckboxRow">
                ${Object.entries(CALC_USAGE_META)
                    .map(
                        ([code, meta]) => `
                    <label class="usage-tile">
                        <input type="checkbox" value="${code}">
                        <span class="usage-tile-body">
                            <span class="usage-tile-icon" aria-hidden="true">${meta.icon}</span>
                            <span class="usage-tile-label">${meta.label}</span>
                        </span>
                    </label>`
                    )
                    .join('')}
            </div>
            <button type="button" class="button wizard-next" id="wizNextBtn" disabled>التالي - شوف الترشيحات</button>
        </div>

        <div id="wizPanel2" style="display:none;">
            <div id="calcUsageQualityOptions"></div>
            <button type="button" class="wizard-back" id="wizBackBtn"><i class="fa-solid fa-arrow-right" aria-hidden="true"></i> تعديل الاختيار</button>
        </div>
    `;

    const nextBtn = area.querySelector('#wizNextBtn');
    const backBtn = area.querySelector('#wizBackBtn');

    const showStep = (n) => {
        area.querySelector('#wizPanel1').style.display = n === 1 ? 'block' : 'none';
        area.querySelector('#wizPanel2').style.display = n === 2 ? 'block' : 'none';
        area.querySelector('#wizStep1').classList.toggle('active', n === 1);
        area.querySelector('#wizStep2').classList.toggle('active', n === 2);
    };

    area.querySelectorAll('#calcUsageCheckboxRow input[type="checkbox"]').forEach((cb) => {
        cb.addEventListener('change', () => {
            const checked = Array.from(area.querySelectorAll('#calcUsageCheckboxRow input:checked'));
            if (checked.length > 2) {
                cb.checked = false;
                showToast('يمكن اختيار استخدامين بحد أقصى', 'info');
                return;
            }
            calcSelectedUsages = checked.map((c) => c.value);
            nextBtn.disabled = calcSelectedUsages.length === 0;
        });
    });

    nextBtn.addEventListener('click', () => {
        if (calcSelectedUsages.length === 0) return;
        renderCalcUsageQualityOptions(quote);
        showStep(2);
    });

    backBtn.addEventListener('click', () => showStep(1));
}

function renderCalcUsageQualityOptions(quote) {
    const container = document.getElementById('calcUsageQualityOptions');
    if (!container) return;

    if (calcSelectedUsages.length === 0) {
        container.innerHTML = '';
        return;
    }

    const key = [...calcSelectedUsages].sort().join('+');
    const entry = quote.usage_options[key];

    if (!entry) {
        container.innerHTML = `
            <div class="lens-special-notice">
                <p>مفيش عدسات متاحة لتركيبة الاستخدام دي حاليًا.</p>
                <a class="button" href="https://wa.me/${quote.whatsapp_number}" target="_blank" rel="noopener">تواصل معنا على واتساب</a>
            </div>
        `;
        return;
    }

    container.innerHTML = `
        <h3 class="wizard-title">${escapeHtml(entry.label_ar)}</h3>
        <p class="wizard-hint">دي الخيارات المتاحة لمقاسك، من الاقتصادي للأعلى جودة.</p>
        <div class="lens-opt-grid">
            ${entry.qualities
                .map((q) =>
                    lensOptionCardHtml(
                        { lens_type: q.lens_type, price: q.price, label: entry.label_ar, fullLabel: `${entry.label_ar} - ${q.label_ar}` },
                        `quality-${escapeHtml(q.quality)}`,
                        `<span class="lens-opt-badge">${escapeHtml(q.label_ar)}</span>`
                    )
                )
                .join('')}
        </div>
    `;

    wireLensOptionCards(container);
}

function showCalcBuyPrompt(lensType, price, label) {
    if (typeof trackCalculatorCompleted === 'function') {
        trackCalculatorCompleted(lensType, Number(price));
    }
    showToast(`تم اختيار "${label}" - ${formatPrice(price)} EGP. جارٍ تحويلك للمتجر لاختيار الشنبر...`, 'success');
    setTimeout(() => {
        window.location.href = '/shop.html';
    }, 1500);
}

async function loadProductCarousel(sectionId, containerId, endpoint) {
    const section = document.getElementById(sectionId);
    const container = document.getElementById(containerId);
    if (!section || !container) {
        return;
    }

    const data = await apiCall(endpoint);
    // Two possible shapes depending on the endpoint: the paginated
    // product list wraps items in {items: [...]}, while best-sellers
    // returns the array directly - handle both rather than picking one.
    const items = Array.isArray(data) ? data : (Array.isArray(data?.items) ? data.items : []);

    if (items.length === 0) {
        // Hide the whole section rather than showing an empty carousel
        // with a heading and nothing under it (same pattern as Today's
        // Deals) - a brand-new store with no sales yet, for example,
        // legitimately has no "best sellers" to show.
        return;
    }

    container.innerHTML = items.map(renderProductCard).join('');
    wireAddToCartButtons(container);
    section.style.display = 'block';
}

function loadHomepageProductCarousels() {
    loadProductCarousel('new-arrivals-section', 'new-arrivals-products', '/products?page=1&per_page=8&sort_by=id&sort_dir=desc');
    loadProductCarousel('best-sellers-section', 'best-sellers-products', '/products/best-sellers?limit=8');
    loadProductCarousel('sunglasses-section', 'sunglasses-products', '/products?page=1&per_page=8&category=men%20sunglasses,womens%20sunglasses');
    loadProductCarousel('medical-section', 'medical-products', '/products?page=1&per_page=8&category=men%20medical%20fraims,womens%20medical%20fraims');
}

let dailyDealsCountdownInterval = null;

function formatCountdown(msRemaining) {
    const totalSeconds = Math.max(0, Math.floor(msRemaining / 1000));
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    const pad = (n) => String(n).padStart(2, '0');
    return `⏰ ينتهي العرض خلال ${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
}

function startDailyDealsCountdown(endsAtIso) {
    const label = document.getElementById('daily-deals-countdown');
    const section = document.getElementById('daily-deals-section');
    if (!label || !endsAtIso) return;

    if (dailyDealsCountdownInterval) {
        clearInterval(dailyDealsCountdownInterval);
    }

    const endsAt = new Date(endsAtIso).getTime();
    label.style.display = 'block';

    const tick = () => {
        const remaining = endsAt - Date.now();
        if (remaining <= 0) {
            // Hide immediately for anyone with this tab already open -
            // the server also independently stops returning these
            // products on any fresh /api/deals call from this point on
            // (see deals.py), so this isn't the only thing enforcing it.
            clearInterval(dailyDealsCountdownInterval);
            if (section) section.style.display = 'none';
            return;
        }
        label.textContent = formatCountdown(remaining);
    };

    tick();
    dailyDealsCountdownInterval = setInterval(tick, 1000);
}

async function loadDailyDeals() {
    const section = document.getElementById('daily-deals-section');
    const container = document.getElementById('daily-deals-products');
    const countdownLabel = document.getElementById('daily-deals-countdown');
    if (!section || !container) {
        return;
    }

    const result = await apiCall('/deals');
    const items = result ? result.products : null;
    if (!items || items.length === 0) {
        // No deals set today, or the countdown already expired - hide the
        // whole section rather than showing an empty "Today's Deals"
        // heading with nothing under it.
        return;
    }

    container.innerHTML = items.map(renderProductCard).join('');
    wireAddToCartButtons(container);
    section.style.display = 'block';

    if (result.ends_at) {
        startDailyDealsCountdown(result.ends_at);
    } else if (countdownLabel) {
        countdownLabel.style.display = 'none';
    }
}

function renderShopPagination(meta) {
    const pagination = document.getElementById('shop-pagination');
    const summary = document.getElementById('shop-summary');

    if (summary) {
        const start = meta.total === 0 ? 0 : (meta.page - 1) * meta.per_page + 1;
        const end = Math.min(meta.page * meta.per_page, meta.total);
        summary.textContent = `عرض ${start}-${end} من ${meta.total} منتج`;
    }

    if (!pagination) {
        return;
    }

    const totalPages = Math.max(1, Math.ceil(meta.total / meta.per_page));
    pagination.innerHTML = `
        <button type="button" class="pagination-btn" ${meta.page <= 1 ? 'disabled' : ''} data-page="${meta.page - 1}">السابق</button>
        <span class="pagination-info">صفحة ${meta.page} من ${totalPages}</span>
        <button type="button" class="pagination-btn" ${meta.page >= totalPages ? 'disabled' : ''} data-page="${meta.page + 1}">التالي</button>
    `;

    pagination.querySelectorAll('.pagination-btn').forEach((button) => {
        button.addEventListener('click', () => {
            const nextPage = Number(button.dataset.page);
            if (!Number.isNaN(nextPage) && nextPage >= 1) {
                shopState.page = nextPage;
                loadShopProducts();
            }
        });
    });
}

async function loadShopProducts() {
    const container = document.getElementById('shop-grid');
    if (!container) {
        return;
    }

    container.innerHTML = '<div style="grid-column: 1 / -1;" class="site-loading"><span class="site-spinner"></span> جارٍ تحميل المنتجات...</div>';

    const params = new URLSearchParams({
        page: String(shopState.page),
        per_page: String(shopState.perPage),
        sort_by: shopState.sortBy,
        sort_dir: shopState.sortDir,
    });

    if (shopState.search) {
        params.set('search', shopState.search);
    }
    if (shopState.category) {
        params.set('category', shopState.category);
    }

    const data = await apiCall(`/products?${params.toString()}`);
    if (!data) {
        container.innerHTML = '<p style="grid-column: 1 / -1; text-align: center; color: #fca5a5;">تعذر تحميل المنتجات. حاول تاني بعد شوية.</p>';
        return;
    }

    const items = Array.isArray(data.items) ? data.items : [];
    if (items.length === 0) {
        container.innerHTML = '<p style="grid-column: 1 / -1; text-align: center;">لا توجد منتجات مطابقة.</p>';
        renderShopPagination({ page: data.page || 1, per_page: data.per_page || shopState.perPage, total: data.total || 0 });
        return;
    }

    container.innerHTML = items.map(renderProductCard).join('');
    wireAddToCartButtons(container);
    renderShopPagination({ page: data.page || shopState.page, per_page: data.per_page || shopState.perPage, total: data.total || items.length });
}

async function populateShopCategoryFilter() {
    const select = document.getElementById('shop-category');
    if (!select) return;

    const categories = await apiCall('/products/categories');
    if (!Array.isArray(categories)) return;

    const labels = CATEGORY_LABELS_AR;

    // Grouped views used by the homepage category cards. The API accepts a
    // comma-separated list, so ?category=a,b selects a matching option here.
    const groups = [
        { value: 'men sunglasses,womens sunglasses', label: 'كل النظارات الشمسية' },
        { value: 'men medical fraims,womens medical fraims', label: 'كل النظارات الطبية' },
        { value: 'men sunglasses,men medical fraims', label: 'كل الرجالي' },
        { value: 'womens sunglasses,womens medical fraims', label: 'كل الحريمي' },
    ];
    const groupOptions = groups
        .map((g) => `<option value="${escapeHtml(g.value)}">${escapeHtml(g.label)}</option>`)
        .join('');

    select.insertAdjacentHTML(
        'beforeend',
        groupOptions + categories.map((cat) => `<option value="${escapeHtml(cat)}">${escapeHtml(labels[cat] || cat)}</option>`).join('')
    );
}

async function initShopPage() {
    const searchForm = document.getElementById('shop-search-form');
    const searchInput = document.getElementById('shop-search');
    const categorySelect = document.getElementById('shop-category');
    const sortSelect = document.getElementById('shop-sort');
    const resetButton = document.getElementById('shop-reset');

    // Populated before anything reads/sets categorySelect.value below -
    // otherwise a ?category= URL param would try to select an <option>
    // that doesn't exist in the DOM yet.
    await populateShopCategoryFilter();

    // FIX: shopState.category was only ever set from the on-page dropdown -
    // a link like shop.html?category=Sunglasses (e.g. from a breadcrumb)
    // had no effect at all. Read it once on load and apply it.
    const urlCategory = new URLSearchParams(window.location.search).get('category');
    if (urlCategory) {
        shopState.category = urlCategory;
        if (categorySelect) categorySelect.value = urlCategory;
    }

    // Same treatment for the header's search box, which links here as
    // shop.html?search=... rather than submitting a form on this page.
    const urlSearch = new URLSearchParams(window.location.search).get('search');
    if (urlSearch) {
        shopState.search = urlSearch;
        if (searchInput) searchInput.value = urlSearch;
    }

    if (searchForm) {
        searchForm.addEventListener('submit', (event) => {
            event.preventDefault();
            shopState.search = searchInput?.value.trim() || '';
            shopState.category = categorySelect?.value || '';
            const [sortBy, sortDir] = (sortSelect?.value || 'id-desc').split('-');
            shopState.sortBy = sortBy;
            shopState.sortDir = sortDir || 'desc';
            shopState.page = 1;
            loadShopProducts();
        });
    }

    if (resetButton) {
        resetButton.addEventListener('click', () => {
            if (searchInput) searchInput.value = '';
            if (categorySelect) categorySelect.value = '';
            if (sortSelect) sortSelect.value = 'id-desc';
            shopState.search = '';
            shopState.category = '';
            shopState.sortBy = 'id';
            shopState.sortDir = 'desc';
            shopState.page = 1;
            loadShopProducts();
        });
    }

    if (categorySelect) {
        categorySelect.addEventListener('change', () => searchForm?.requestSubmit());
    }

    if (sortSelect) {
        sortSelect.addEventListener('change', () => searchForm?.requestSubmit());
    }

    loadShopProducts();
}

function showLoadingMessage() {
    const revealSections = document.querySelectorAll('.reveal');
    revealSections.forEach((section) => section.classList.add('active'));
}

async function initAuth() {
    if (authToken) {
        await loadCurrentUser();
    }
    updateUIForAuth();
}

function setCanonicalTag() {
    // Set dynamically (rather than hardcoding a domain in every HTML file)
    // so this is correct whether the site is running on localhost, a
    // staging domain, or the final production domain - no per-file update
    // needed when that changes. Strips query params (e.g. shop.html
    // ?category=X) so filtered views don't count as separate pages.
    let link = document.querySelector('link[rel="canonical"]');
    if (!link) {
        link = document.createElement('link');
        link.rel = 'canonical';
        document.head.appendChild(link);
    }
    link.href = window.location.origin + window.location.pathname;
}

// ===== Hero Slider (index.html only) =====
let heroSlideIndex = 0;
let heroSlideInterval = null;
const HERO_AUTOPLAY_MS = 6000;

function renderHeroDots() {
    const dotsContainer = document.getElementById('heroDots');
    const slideCount = document.querySelectorAll('.hero-slide').length;
    if (!dotsContainer || slideCount === 0) return;

    dotsContainer.innerHTML = '';
    for (let i = 0; i < slideCount; i++) {
        const dot = document.createElement('button');
        dot.type = 'button';
        dot.className = 'hero-dot' + (i === heroSlideIndex ? ' active' : '');
        dot.setAttribute('aria-label', `الشريحة ${i + 1}`);
        dot.addEventListener('click', () => {
            heroSliderGoTo(i);
            resetHeroAutoplay();
        });
        dotsContainer.appendChild(dot);
    }
}

function heroSliderGoTo(index) {
    const slides = document.querySelectorAll('.hero-slide');
    if (slides.length === 0) return;
    heroSlideIndex = ((index % slides.length) + slides.length) % slides.length;
    slides.forEach((slide, i) => slide.classList.toggle('active', i === heroSlideIndex));
    renderHeroDots();
}

function heroSliderGo(direction) {
    heroSliderGoTo(heroSlideIndex + direction);
    resetHeroAutoplay();
}

function resetHeroAutoplay() {
    if (heroSlideInterval) {
        clearInterval(heroSlideInterval);
        heroSlideInterval = null;
    }
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (!prefersReducedMotion) {
        heroSlideInterval = setInterval(() => heroSliderGoTo(heroSlideIndex + 1), HERO_AUTOPLAY_MS);
    }
}

function initHeroSlider() {
    const slider = document.getElementById('heroSlider');
    if (!slider) return;

    renderHeroDots();
    resetHeroAutoplay();

    let touchStartX = null;
    slider.addEventListener('touchstart', (e) => { touchStartX = e.touches[0].clientX; }, { passive: true });
    slider.addEventListener('touchend', (e) => {
        if (touchStartX === null) return;
        const deltaX = e.changedTouches[0].clientX - touchStartX;
        if (Math.abs(deltaX) > 40) {
            heroSliderGo(deltaX > 0 ? -1 : 1);
        }
        touchStartX = null;
    }, { passive: true });

    slider.addEventListener('mouseenter', () => {
        if (heroSlideInterval) {
            clearInterval(heroSlideInterval);
            heroSlideInterval = null;
        }
    });
    slider.addEventListener('mouseleave', resetHeroAutoplay);
}

// ===== Mobile nav + header search (all pages with the new header) =====
function toggleMobileNav() {
    document.getElementById('mainNav')?.classList.toggle('open');
}

function toggleHeaderSearch() {
    const form = document.getElementById('headerSearchForm');
    if (!form) return;
    form.classList.toggle('open');
    if (form.classList.contains('open')) {
        document.getElementById('headerSearchInput')?.focus();
    }
}

function initHeaderSearch() {
    const form = document.getElementById('headerSearchForm');
    if (!form) return;
    form.addEventListener('submit', (e) => {
        e.preventDefault();
        const query = document.getElementById('headerSearchInput')?.value.trim();
        if (query) {
            window.location.href = `shop.html?search=${encodeURIComponent(query)}`;
        }
    });
}

document.addEventListener('DOMContentLoaded', async () => {
    authToken = localStorage.getItem('authToken');
    cart = loadCart();
    updateCartCount();
    showLoadingMessage();
    initRevealAnimations();
    initLensCalculator();
    setCanonicalTag();
    initHeroSlider();
    initHeaderSearch();
    await initAuth();

    if (document.getElementById('new-arrivals-section')) {
        loadHomepageProductCarousels();
    }

    if (document.getElementById('daily-deals-section')) {
        loadDailyDeals();
    }

    if (document.getElementById('shop-grid')) {
        initShopPage();
    }
});

window.showCart = showCart;
window.toggleUserMenu = toggleUserMenu;
window.logout = logout;
window.showUserInfo = showUserInfo;
window.heroSliderGo = heroSliderGo;
window.toggleMobileNav = toggleMobileNav;
window.toggleHeaderSearch = toggleHeaderSearch;


// ==================== Side cart (slides in from the right) ====================
// Built entirely here and injected on demand, so every page that loads
// frontend.js gets it without any per-page markup. It reads and writes the
// same `cart` array / localStorage key the checkout page uses, so the two
// can never disagree.

let lastAddedCartId = null;
let cartDrawerReturnFocus = null;

function ensureCartDrawer() {
    let root = document.getElementById('cartDrawer');
    if (root) return root;

    root = document.createElement('div');
    root.id = 'cartDrawer';
    root.className = 'cart-drawer';
    root.setAttribute('dir', 'rtl');
    root.innerHTML = `
        <div class="cart-drawer-overlay" data-cart-drawer-close></div>
        <aside class="cart-drawer-panel" role="dialog" aria-modal="true" aria-labelledby="cartDrawerTitle" tabindex="-1">
            <div class="cart-drawer-head">
                <h3 id="cartDrawerTitle">سلة التسوق <span id="cartDrawerCount"></span></h3>
                <button type="button" class="cart-drawer-x" data-cart-drawer-close aria-label="إغلاق السلة">&times;</button>
            </div>
            <div class="cart-drawer-body" id="cartDrawerBody"></div>
            <div class="cart-drawer-foot" id="cartDrawerFoot"></div>
        </aside>
    `;
    document.body.appendChild(root);

    root.addEventListener('click', (event) => {
        if (event.target.closest('[data-cart-drawer-close]')) {
            closeCartDrawer();
        }
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && root.classList.contains('open')) {
            closeCartDrawer();
        }
    });

    // Keep Tab inside the open drawer.
    root.addEventListener('keydown', (event) => {
        if (event.key !== 'Tab') return;
        const focusable = root.querySelectorAll('button, a[href], [tabindex]:not([tabindex="-1"])');
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    });

    return root;
}

function renderCartDrawer() {
    const root = ensureCartDrawer();
    const body = root.querySelector('#cartDrawerBody');
    const foot = root.querySelector('#cartDrawerFoot');
    const countEl = root.querySelector('#cartDrawerCount');

    const totalQty = cart.reduce((sum, item) => sum + (Number(item.quantity) || 1), 0);
    countEl.textContent = totalQty > 0 ? `(${totalQty})` : '';

    if (cart.length === 0) {
        body.innerHTML = `
            <div class="cart-drawer-empty">
                <p>السلة فاضية دلوقتي.</p>
                <button type="button" class="button" data-cart-drawer-close>تصفح المنتجات</button>
            </div>
        `;
        foot.innerHTML = '';
        return;
    }

    body.innerHTML = `<ul class="cart-drawer-list">${cart
        .map((item) => {
            const qty = Number(item.quantity) || 1;
            const lineTotal = (Number(item.price) || 0) * qty;
            const justAdded = item.id === lastAddedCartId ? ' just-added' : '';
            return `
            <li class="cd-item${justAdded}" data-cart-id="${escapeHtml(item.id)}">
                <img class="cd-img" src="${escapeHtml(assetUrl(item.image_file))}" alt="" loading="lazy"
                     onerror="this.onerror=null;this.style.visibility='hidden';">
                <div class="cd-info">
                    <strong class="cd-name">${escapeHtml(item.name)}</strong>
                    <span class="cd-unit">${formatPrice(item.price)} جنيه</span>
                    <div class="cd-qty">
                        <button type="button" data-cd-qty="-1" aria-label="تقليل الكمية">&minus;</button>
                        <span aria-live="polite">${qty}</span>
                        <button type="button" data-cd-qty="1" aria-label="زيادة الكمية">+</button>
                    </div>
                </div>
                <div class="cd-side">
                    <span class="cd-line">${formatPrice(lineTotal)} جنيه</span>
                    <button type="button" class="cd-remove" data-cd-remove>إزالة</button>
                </div>
            </li>`;
        })
        .join('')}</ul>`;

    const subtotal = cart.reduce((sum, item) => sum + (Number(item.price) || 0) * (Number(item.quantity) || 1), 0);
    foot.innerHTML = `
        <div class="cd-subtotal"><span>إجمالي المنتجات</span><strong>${formatPrice(subtotal)} جنيه</strong></div>
        <p class="cd-note">العدسات والكوبون بيتحددوا في صفحة إتمام الطلب.</p>
        <a class="button cd-checkout" href="checkout.html">إتمام الطلب</a>
        <button type="button" class="cd-continue" data-cart-drawer-close>كمّل التسوق</button>
    `;

    body.querySelectorAll('[data-cd-qty]').forEach((btn) => {
        btn.addEventListener('click', () => {
            const id = Number(btn.closest('[data-cart-id]').dataset.cartId);
            changeDrawerQty(id, Number(btn.dataset.cdQty));
        });
    });
    body.querySelectorAll('[data-cd-remove]').forEach((btn) => {
        btn.addEventListener('click', () => {
            const id = Number(btn.closest('[data-cart-id]').dataset.cartId);
            removeDrawerItem(id);
        });
    });

    // Bring the item that was just added into view if the list is long.
    const added = body.querySelector('.cd-item.just-added');
    if (added && typeof added.scrollIntoView === 'function') {
        added.scrollIntoView({ block: 'nearest' });
    }
}

function changeDrawerQty(productId, delta) {
    const item = cart.find((i) => i.id === productId);
    if (!item) return;

    item.quantity = (Number(item.quantity) || 1) + delta;
    if (item.quantity < 1) {
        removeDrawerItem(productId);
        return;
    }

    lastAddedCartId = null;
    saveCart();
    updateCartCount();
    renderCartDrawer();
}

function removeDrawerItem(productId) {
    cart = cart.filter((i) => i.id !== productId);
    lastAddedCartId = null;
    saveCart();
    updateCartCount();
    renderCartDrawer();
}

function openCartDrawer() {
    const root = ensureCartDrawer();
    renderCartDrawer();

    if (!root.classList.contains('open')) {
        cartDrawerReturnFocus = document.activeElement;
        root.classList.add('open');
        document.body.classList.add('cart-drawer-open');
    }

    // Move keyboard focus into the dialog. Done on the next frame: the panel
    // only becomes focusable once the browser has applied the "open" styles.
    const panel = root.querySelector('.cart-drawer-panel');
    const closeBtn = root.querySelector('.cart-drawer-x');
    window.setTimeout(() => {
        if (root.classList.contains('open')) {
            (closeBtn || panel).focus();
        }
    }, 50);
}

function closeCartDrawer() {
    const root = document.getElementById('cartDrawer');
    if (!root || !root.classList.contains('open')) return;

    root.classList.remove('open');
    document.body.classList.remove('cart-drawer-open');
    lastAddedCartId = null;

    if (cartDrawerReturnFocus && typeof cartDrawerReturnFocus.focus === 'function') {
        cartDrawerReturnFocus.focus({ preventScroll: true });
    }
    cartDrawerReturnFocus = null;
}

// Another tab changed the cart: stay in sync.
window.addEventListener('storage', (event) => {
    if (event.key !== CART_STORAGE_KEY) return;
    cart = loadCart();
    updateCartCount();
    const root = document.getElementById('cartDrawer');
    if (root && root.classList.contains('open')) {
        renderCartDrawer();
    }
});
