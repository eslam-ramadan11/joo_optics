// tracking.js — Meta Pixel + Google Analytics 4 + UTM/attribution capture.
// Shared across every page (see each .html file's <script src="tracking.js">).
//
// SECURITY: this file contains NO secrets. META_PIXEL_ID and
// GA4_MEASUREMENT_ID below are not secrets - they're meant to be public
// (every site's Pixel/GA4 IDs are visible in their page source once
// installed). The Meta access token and GA4 API secret used for
// server-side reporting live only in environment variables on the
// backend (see config.py / app/services/tracking_service.py) and are
// never sent to or readable from the browser.

// ====== CONFIG — fill in with your real IDs before launch ======
// Leave either one empty to disable that platform entirely (every
// tracking function below checks for fbq/gtag existing before calling
// them, so leaving these blank is completely safe - PageView/etc. simply
// won't fire for the platform that isn't configured).
const META_PIXEL_ID = ''; // e.g. '1234567890123456'
const GA4_MEASUREMENT_ID = ''; // e.g. 'G-XXXXXXXXXX'

// ====== UTM + attribution capture/persistence ======
const ATTRIBUTION_STORAGE_KEY = 'joo_attribution_v1';

function captureAttribution() {
    const params = new URLSearchParams(window.location.search);
    const incoming = {
        utm_source: params.get('utm_source'),
        utm_medium: params.get('utm_medium'),
        utm_campaign: params.get('utm_campaign'),
        utm_content: params.get('utm_content'),
        utm_term: params.get('utm_term'),
    };
    const hasIncoming = Object.values(incoming).some((v) => v);

    let stored = {};
    try {
        stored = JSON.parse(localStorage.getItem(ATTRIBUTION_STORAGE_KEY) || '{}');
    } catch (e) {
        stored = {};
    }

    // Last-touch: a fresh UTM-tagged visit overwrites what's stored;
    // browsing further into the site with no UTM params on the URL
    // keeps whatever was captured earlier in the session.
    const merged = hasIncoming ? { ...stored, ...incoming } : stored;

    try {
        localStorage.setItem(ATTRIBUTION_STORAGE_KEY, JSON.stringify(merged));
    } catch (e) {
        // localStorage unavailable (private browsing, quota exceeded) -
        // attribution just won't persist across pages this visit. Not
        // fatal to anything else on the page.
    }

    return merged;
}

function getStoredAttribution() {
    try {
        return JSON.parse(localStorage.getItem(ATTRIBUTION_STORAGE_KEY) || '{}');
    } catch (e) {
        return {};
    }
}

function getCookie(name) {
    const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
    return match ? decodeURIComponent(match[1]) : null;
}

function getFbp() {
    // Set automatically by the Meta Pixel itself once loaded - just read it.
    return getCookie('_fbp');
}

function getFbc() {
    const existing = getCookie('_fbc');
    if (existing) return existing;

    const fbclid = new URLSearchParams(window.location.search).get('fbclid');
    if (!fbclid) return null;

    // Meta's documented fbc format when constructing it manually:
    // fb.<subdomain_index>.<creation_time_ms>.<fbclid>
    return `fb.1.${Date.now()}.${fbclid}`;
}

function getGa4ClientId() {
    // Async: GA4's client_id lives in a cookie gtag.js manages itself,
    // and the documented way to read it back is via gtag('get', ...).
    // Never blocks checkout - resolves to null on any failure or timeout.
    return new Promise((resolve) => {
        if (typeof gtag !== 'function' || !GA4_MEASUREMENT_ID) {
            resolve(null);
            return;
        }
        let resolved = false;
        const timeout = setTimeout(() => {
            if (!resolved) {
                resolved = true;
                resolve(null);
            }
        }, 1000);
        try {
            gtag('get', GA4_MEASUREMENT_ID, 'client_id', (clientId) => {
                if (!resolved) {
                    resolved = true;
                    clearTimeout(timeout);
                    resolve(clientId || null);
                }
            });
        } catch (e) {
            if (!resolved) {
                resolved = true;
                clearTimeout(timeout);
                resolve(null);
            }
        }
    });
}

async function getAttributionForOrder() {
    // Best-effort snapshot for the order-creation payload. Every field is
    // independently optional - checkout must work even if all of this is
    // unavailable (ad blocker, blocked cookies, GA4/Pixel not configured).
    const utm = getStoredAttribution();
    const ga4ClientId = await getGa4ClientId();
    return {
        utm_source: utm.utm_source || null,
        utm_medium: utm.utm_medium || null,
        utm_campaign: utm.utm_campaign || null,
        utm_content: utm.utm_content || null,
        utm_term: utm.utm_term || null,
        fbp: getFbp(),
        fbc: getFbc(),
        ga4_client_id: ga4ClientId,
    };
}

// ====== Pixel + GA4 base snippet loading ======
function loadMetaPixel() {
    if (!META_PIXEL_ID || window.fbq) return;

    /* eslint-disable */
    !function (f, b, e, v, n, t, s) {
        if (f.fbq) return; n = f.fbq = function () {
            n.callMethod ? n.callMethod.apply(n, arguments) : n.queue.push(arguments)
        };
        if (!f._fbq) f._fbq = n; n.push = n; n.loaded = !0; n.version = '2.0';
        n.queue = []; t = b.createElement(e); t.async = !0;
        t.src = v; s = b.getElementsByTagName(e)[0];
        s.parentNode.insertBefore(t, s)
    }(window, document, 'script', 'https://connect.facebook.net/en_US/fbevents.js');
    /* eslint-enable */

    fbq('init', META_PIXEL_ID);
    fbq('track', 'PageView');
}

function loadGa4() {
    if (!GA4_MEASUREMENT_ID || window.gtag) return;

    const script = document.createElement('script');
    script.async = true;
    script.src = `https://www.googletagmanager.com/gtag/js?id=${GA4_MEASUREMENT_ID}`;
    document.head.appendChild(script);

    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { dataLayer.push(arguments); };
    gtag('js', new Date());
    gtag('config', GA4_MEASUREMENT_ID);
}

// ====== Event helpers ======
// Every function below is safe to call unconditionally, even if Pixel/GA4
// never loaded (not configured, blocked, script failed) - each checks
// typeof before calling fbq/gtag, so a missing script is a silent no-op,
// never a thrown error that could interrupt the page's own logic.

function trackViewContent(product) {
    if (typeof fbq === 'function') {
        fbq('track', 'ViewContent', {
            content_ids: [String(product.id)],
            content_name: product.name,
            content_type: 'product',
            value: product.price,
            currency: 'EGP',
        });
    }
    if (typeof gtag === 'function') {
        gtag('event', 'view_item', {
            currency: 'EGP',
            value: product.price,
            items: [{ item_id: String(product.id), item_name: product.name, price: product.price }],
        });
    }
}

function trackCalculatorStarted() {
    if (typeof fbq === 'function') {
        fbq('trackCustom', 'CalculatorStarted');
    }
    if (typeof gtag === 'function') {
        gtag('event', 'calculator_started');
    }
}

function trackCalculatorCompleted(lensType, price) {
    // Only lens type and price ever go out here - never prescription
    // numbers (SPH/CYL/axis) or any other personal data. Callers must
    // only pass exactly these two values.
    if (typeof fbq === 'function') {
        fbq('trackCustom', 'CalculatorCompleted', {
            lens_type: lensType,
            value: price,
            currency: 'EGP',
        });
    }
    if (typeof gtag === 'function') {
        gtag('event', 'calculator_completed', {
            lens_type: lensType,
            value: price,
            currency: 'EGP',
        });
    }
}

function trackAddToCart(product) {
    const quantity = product.quantity || 1;
    if (typeof fbq === 'function') {
        fbq('track', 'AddToCart', {
            content_ids: [String(product.id)],
            content_name: product.name,
            content_type: 'product',
            value: product.price * quantity,
            currency: 'EGP',
        });
    }
    if (typeof gtag === 'function') {
        gtag('event', 'add_to_cart', {
            currency: 'EGP',
            value: product.price * quantity,
            items: [{ item_id: String(product.id), item_name: product.name, price: product.price, quantity }],
        });
    }
}

function trackInitiateCheckout(cartItems, totalValue) {
    if (typeof fbq === 'function') {
        fbq('track', 'InitiateCheckout', {
            content_ids: cartItems.map((i) => String(i.id)),
            value: totalValue,
            currency: 'EGP',
            num_items: cartItems.length,
        });
    }
    if (typeof gtag === 'function') {
        gtag('event', 'begin_checkout', {
            currency: 'EGP',
            value: totalValue,
            items: cartItems.map((i) => ({ item_id: String(i.id), item_name: i.name, price: i.price, quantity: i.quantity })),
        });
    }
}

function trackPurchase(eventId, orderId, value) {
    // Client-side companion to the server-side event the backend already
    // fired (see app/services/tracking_service.py) - shares the same
    // event_id so Meta can deduplicate the two into one conversion. Only
    // ever called after the backend confirms (via
    // /api/payments/order/<id>/status) that this is genuinely the first
    // time for this order - see payment-result.js. Never call this
    // directly from anywhere else.
    if (typeof fbq === 'function') {
        fbq('track', 'Purchase', {
            value: value,
            currency: 'EGP',
            content_ids: [String(orderId)],
        }, { eventID: eventId });
    }
    if (typeof gtag === 'function') {
        gtag('event', 'purchase', {
            transaction_id: String(orderId),
            currency: 'EGP',
            value: value,
        });
    }
}

document.addEventListener('DOMContentLoaded', () => {
    captureAttribution();
    loadMetaPixel();
    loadGa4();
});
