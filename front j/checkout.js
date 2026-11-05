// Logic for checkout.html. Loaded after frontend.js, reuses its
// apiCall/escapeHtml/formatPrice/cart/loadCart/saveCart/updateCartCount
// helpers and shared authToken state.

// formatPrice(), escapeHtml(), apiCall(), cart, loadCart(), saveCart(),
// updateCartCount(), uploadPrescription() all come from frontend.js.

let prescriptionCache = [];
let currentLensQuote = null; // last response from /lens-catalog/quote
let selectedLensChoice = null; // { lens_type, price, label } - the customer's actual pick
let selectedUsages = []; // for the "help me choose advanced" flow, max 2
let lensTargetMode = 'all'; // 'all' | 'single' - which cart item(s) get the lens
let lensTargetProductId = null; // the specific product id when lensTargetMode === 'single'

function renderCheckoutItems() {
    const container = document.getElementById('checkoutItems');
    if (!container) return;

    container.innerHTML = cart
        .map((item) => {
            const lineTotal = (Number(item.price) || 0) * (Number(item.quantity) || 1);
            return `
        <div class="cart-row" data-cart-id="${item.id}">
            <div class="cart-row-info">
                <strong>${escapeHtml(item.name)}</strong>
                <div class="product-meta">${formatPrice(item.price)} جنيه للقطعة</div>
            </div>
            <div class="cart-row-qty">
                <button type="button" class="qty-btn" data-qty-change="-1">-</button>
                <span>${item.quantity}</span>
                <button type="button" class="qty-btn" data-qty-change="1">+</button>
            </div>
            <div class="cart-row-total">${formatPrice(lineTotal)} جنيه</div>
            <button type="button" class="table-action-btn" data-remove-item>إزالة</button>
        </div>
    `;
        })
        .join('');

    container.querySelectorAll('[data-qty-change]').forEach((btn) => {
        btn.addEventListener('click', () => {
            const row = btn.closest('[data-cart-id]');
            changeCartQty(Number(row.dataset.cartId), Number(btn.dataset.qtyChange));
        });
    });

    container.querySelectorAll('[data-remove-item]').forEach((btn) => {
        btn.addEventListener('click', () => {
            const row = btn.closest('[data-cart-id]');
            removeCartItem(Number(row.dataset.cartId));
        });
    });

    renderLensTargetSelector();
    updateCheckoutTotal();
}

function renderLensTargetSelector() {
    const group = document.getElementById('lensTargetGroup');
    const select = document.getElementById('lensTargetProductSelect');
    const scopeNote = document.getElementById('prescriptionScopeNote');
    if (!group || !select) return;

    if (cart.length <= 1) {
        // Nothing to choose between - only one frame in the cart, so it's
        // the obvious (and only) target. Hide the picker entirely rather
        // than showing a single-option dropdown that adds nothing.
        group.style.display = 'none';
        lensTargetMode = 'all';
        lensTargetProductId = null;
        if (scopeNote) scopeNote.textContent = 'الكشف ونوع العدسة اللي هتختارهم هيتطبقوا على المنتج ده.';
        return;
    }

    group.style.display = 'block';

    // If the previously chosen specific product was removed from the
    // cart (or the quantity/cart changed), the selection may no longer be
    // valid - fall back to the first item rather than pointing at nothing.
    const stillValid = cart.some((item) => item.id === lensTargetProductId);
    if (lensTargetMode === 'single' && !stillValid) {
        lensTargetProductId = cart[0]?.id ?? null;
    }

    select.innerHTML = cart
        .map((item) => `<option value="${item.id}">${escapeHtml(item.name)}</option>`)
        .join('');
    if (lensTargetProductId !== null) {
        select.value = String(lensTargetProductId);
    }
    select.style.display = lensTargetMode === 'single' ? 'block' : 'none';

    updateLensScopeNote();
}

function updateLensScopeNote() {
    const scopeNote = document.getElementById('prescriptionScopeNote');
    if (!scopeNote) return;

    if (lensTargetMode === 'single') {
        const item = cart.find((i) => i.id === lensTargetProductId);
        scopeNote.textContent = item
            ? `الكشف ونوع العدسة اللي هتختارهم هيتطبقوا بس على "${item.name}".`
            : 'اختار فوق أنهي منتج هتركب فيه العدسات.';
    } else {
        scopeNote.textContent = 'الكشف ونوع العدسة اللي هتختارهم هيتطبقوا على كل منتجات الطلب.';
    }
}

function wireLensTargetSelector() {
    const radios = document.querySelectorAll('input[name="lensTarget"]');
    const select = document.getElementById('lensTargetProductSelect');

    radios.forEach((radio) => {
        radio.addEventListener('change', () => {
            lensTargetMode = radio.value;
            if (lensTargetMode === 'single' && lensTargetProductId === null) {
                lensTargetProductId = cart[0]?.id ?? null;
                if (select && lensTargetProductId !== null) select.value = String(lensTargetProductId);
            }
            select.style.display = lensTargetMode === 'single' ? 'block' : 'none';
            updateLensScopeNote();
            updateCheckoutTotal();
        });
    });

    if (select) {
        select.addEventListener('change', () => {
            lensTargetProductId = Number(select.value);
            updateLensScopeNote();
            updateCheckoutTotal();
        });
    }
}

function getSelectedLensPrice() {
    if (!needsPrescriptionLenses() || !selectedLensChoice) {
        return 0;
    }
    return Number(selectedLensChoice.price) || 0;
}

function needsPrescriptionLenses() {
    const checked = document.querySelector('input[name="needsPrescription"]:checked');
    return checked ? checked.value === 'yes' : false;
}

function totalCartQuantity() {
    return cart.reduce((sum, item) => sum + (Number(item.quantity) || 1), 0);
}

let appliedCoupon = null; // { code, discount, subtotal, total }
let couponRevalidateToken = 0;

async function fetchCouponValidation(code, items) {
    // Not using the shared apiCall() here on purpose: it returns null on
    // any non-2xx response and only logs the server's message to the
    // console, discarding it - but a failed coupon validation (expired,
    // not found, limit reached, etc.) needs that specific message shown
    // to the customer, not a generic failure.
    try {
        const response = await fetch(`${API_BASE_URL}/coupons/validate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
            },
            body: JSON.stringify({ code, items }),
        });
        const body = await response.json().catch(() => null);
        const message = body?.message || (response.ok ? null : 'تعذر التحقق من الكود.');
        return { ok: response.ok, data: body?.data || null, message };
    } catch (err) {
        return { ok: false, data: null, message: 'تعذر التحقق من الكود.' };
    }
}

function setCouponMessage(text, isError) {
    const msgEl = document.getElementById('couponMsg');
    if (!msgEl) return;
    msgEl.textContent = text || '';
    msgEl.style.color = isError ? '#ef4444' : '#22c55e';
}

function setAppliedCouponUi(coupon) {
    const row = document.getElementById('appliedCouponRow');
    const codeEl = document.getElementById('appliedCouponCode');
    const input = document.getElementById('couponCodeInput');

    if (coupon) {
        row.style.display = 'flex';
        codeEl.textContent = coupon.code;
        input.value = coupon.code;
        input.disabled = true;
        document.getElementById('applyCouponBtn').style.display = 'none';
    } else {
        row.style.display = 'none';
        input.disabled = false;
        document.getElementById('applyCouponBtn').style.display = 'inline-block';
    }
}

async function applyCoupon() {
    const input = document.getElementById('couponCodeInput');
    const code = input.value.trim();

    if (!code) {
        setCouponMessage('من فضلك اكتب كود الخصم', true);
        return;
    }

    const btn = document.getElementById('applyCouponBtn');
    btn.disabled = true;
    btn.textContent = '...';
    setCouponMessage('', false);

    const result = await fetchCouponValidation(code, buildOrderItemsPayload());

    btn.disabled = false;
    btn.textContent = 'تطبيق';

    if (!result.ok || !result.data) {
        appliedCoupon = null;
        setAppliedCouponUi(null);
        setCouponMessage(result.message, true);
        renderTotalsDisplay();
        return;
    }

    appliedCoupon = result.data;
    setAppliedCouponUi(appliedCoupon);
    setCouponMessage('', false);
    renderTotalsDisplay();
}

function removeCoupon() {
    appliedCoupon = null;
    setAppliedCouponUi(null);
    setCouponMessage('', false);
    renderTotalsDisplay();
}

async function revalidateAppliedCoupon() {
    // Called whenever something that could change the discount amount
    // changes (lens choice, which frame gets lenses, quantities) while a
    // coupon is already applied - keeps the shown discount accurate
    // instead of leaving a stale number up. Guarded the same way
    // onPrescriptionSelectionChange is, so rapid changes can't let an
    // older re-check overwrite a newer one.
    if (!appliedCoupon) return;

    const token = ++couponRevalidateToken;
    const result = await fetchCouponValidation(appliedCoupon.code, buildOrderItemsPayload());
    if (token !== couponRevalidateToken) return;

    if (!result.ok || !result.data) {
        // The coupon that was valid a moment ago no longer applies (e.g.
        // they removed the item it required) - drop it and say why,
        // rather than silently keeping a stale discount active.
        appliedCoupon = null;
        setAppliedCouponUi(null);
        setCouponMessage(result.message, true);
    } else {
        appliedCoupon = result.data;
    }

    renderTotalsDisplay();
}

function renderTotalsDisplay() {
    const framesTotal = cart.reduce((sum, item) => sum + (Number(item.price) || 0) * (Number(item.quantity) || 1), 0);
    const lensTotal = getSelectedLensPrice() * lensApplicableQuantity();
    const orderTotal = framesTotal + lensTotal;

    const subtotalRow = document.getElementById('checkoutSubtotalRow');
    const discountRow = document.getElementById('checkoutDiscountRow');
    const totalEl = document.getElementById('checkoutTotal');

    if (appliedCoupon) {
        subtotalRow.style.display = 'block';
        discountRow.style.display = 'block';
        document.getElementById('checkoutSubtotal').textContent = formatPrice(orderTotal);
        document.getElementById('checkoutDiscount').textContent = formatPrice(appliedCoupon.discount);
        totalEl.textContent = formatPrice(Math.max(0, orderTotal - appliedCoupon.discount));
    } else {
        subtotalRow.style.display = 'none';
        discountRow.style.display = 'none';
        totalEl.textContent = formatPrice(orderTotal);
    }
}

function wireCouponUi() {
    document.getElementById('applyCouponBtn')?.addEventListener('click', applyCoupon);
    document.getElementById('removeCouponBtn')?.addEventListener('click', removeCoupon);
    document.getElementById('couponCodeInput')?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            applyCoupon();
        }
    });
}

function lensApplicableQuantity() {
    if (lensTargetMode === 'single') {
        const item = cart.find((i) => i.id === lensTargetProductId);
        return item ? Number(item.quantity) || 1 : 0;
    }
    return totalCartQuantity();
}

function updateCheckoutTotal() {
    const totalEl = document.getElementById('checkoutTotal');
    if (!totalEl) return;

    // BUG FIX: this used to only ever total the frame prices - the lens
    // price the customer picked never affected what they saw here (and,
    // separately, never affected what they were actually charged either -
    // see order_service.py). Lens cost applies per unit, same as the frame,
    // and only to whichever frame(s) the customer chose to fit lenses into.
    renderTotalsDisplay();

    // Anything that reaches this function is exactly the kind of change
    // (lens choice, which frame gets lenses, quantity) that could affect
    // an already-applied coupon's discount - keep it in sync rather than
    // leaving a stale number showing.
    revalidateAppliedCoupon();
}

function changeCartQty(productId, delta) {
    const item = cart.find((i) => i.id === productId);
    if (!item) return;

    item.quantity = (Number(item.quantity) || 1) + delta;
    if (item.quantity < 1) {
        removeCartItem(productId);
        return;
    }

    saveCart();
    updateCartCount();
    renderCheckoutItems();
}

function removeCartItem(productId) {
    cart = cart.filter((i) => i.id !== productId);
    saveCart();
    updateCartCount();

    if (cart.length === 0) {
        document.getElementById('checkout-content').style.display = 'none';
        document.getElementById('checkout-empty-notice').style.display = 'block';
        return;
    }

    renderCheckoutItems();
}

async function populatePrescriptionSelect() {
    const select = document.getElementById('prescriptionSelect');
    if (!select) return;

    select.innerHTML = '<option value="">جاري التحميل...</option>';

    const result = await apiCall('/prescriptions');
    prescriptionCache = Array.isArray(result) ? result : [];
    if (prescriptionCache.length === 0) {
        select.innerHTML = '<option value="">لا توجد كشوفات بعد - ارفع واحد تحت</option>';
        renderLensQuoteArea();
        return;
    }

    select.innerHTML = '<option value="">-- اختار كشف --</option>' + prescriptionCache
        .map((p) => {
            const date = p.uploaded_at ? new Date(p.uploaded_at).toLocaleDateString() : '';
            return `<option value="${p.id}">كشف #${p.id} (SPH يمين:${p.sph_r} / شمال:${p.sph_l}) - ${escapeHtml(date)}</option>`;
        })
        .join('');

    select.addEventListener('change', onPrescriptionSelectionChange);
}

let lensQuoteRequestToken = 0;

async function onPrescriptionSelectionChange() {
    const select = document.getElementById('prescriptionSelect');
    const prescription = prescriptionCache.find((p) => String(p.id) === select.value);

    // A different prescription means any lens already picked no longer
    // necessarily applies (prices are tier-specific) - reset and re-quote.
    selectedLensChoice = null;
    selectedUsages = [];
    currentLensQuote = null;

    // Guards against switching prescriptions twice quickly and having the
    // first (now-stale) request's response arrive after the second's,
    // silently overwriting the quote that actually matches what's
    // currently selected in the dropdown.
    const requestToken = ++lensQuoteRequestToken;

    if (!prescription) {
        renderLensQuoteArea();
        updateCheckoutTotal();
        return;
    }

    const quoteArea = document.getElementById('lensQuoteArea');
    if (quoteArea) {
        quoteArea.innerHTML = '<p class="product-meta"><span class="site-spinner"></span> جاري حساب خيارات العدسات...</p>';
    }

    const quote = await apiCall('/lens-catalog/quote', 'POST', {
        sph_r: prescription.sph_r,
        cyl_r: prescription.cyl_r,
        sph_l: prescription.sph_l,
        cyl_l: prescription.cyl_l,
    });

    if (requestToken !== lensQuoteRequestToken) {
        // A newer selection change has started since this request went
        // out - drop this stale result instead of applying it.
        return;
    }

    currentLensQuote = quote;
    renderLensQuoteArea();
    updateCheckoutTotal();
}

function renderLensQuoteArea() {
    const container = document.getElementById('lensQuoteArea');
    if (!container) return;

    if (!currentLensQuote) {
        container.innerHTML = '<p class="product-meta">اختار كشف فوق عشان تشوف خيارات وأسعار العدسات.</p>';
        return;
    }

    if (currentLensQuote.is_special) {
        container.innerHTML = `
            <div class="lens-special-notice">
                <p>هذه الدرجة تحتاج استشارة خاصة لتحديد السعر المناسب.</p>
                <a class="button" href="https://wa.me/${currentLensQuote.whatsapp_number}" target="_blank" rel="noopener">تواصل معنا على واتساب</a>
            </div>
        `;
        return;
    }

    container.innerHTML = `
        <label class="lens-label">نوع العدسة</label>
        <div id="basicLensOptions"></div>
        <button type="button" id="advancedHelpBtn" class="table-action-btn" style="margin-top:10px;">✨ ساعدني في اختيار عدسات متقدمة</button>
        <div id="advancedLensArea" style="display:none; margin-top:15px;"></div>
    `;

    renderBasicLensOptions();

    document.getElementById('advancedHelpBtn').addEventListener('click', () => {
        const area = document.getElementById('advancedLensArea');
        const isHidden = area.style.display === 'none';
        area.style.display = isHidden ? 'block' : 'none';
        if (isHidden) {
            renderUsageCheckboxes();
        }
    });
}

function renderBasicLensOptions() {
    const container = document.getElementById('basicLensOptions');
    if (!container || !currentLensQuote) return;

    container.innerHTML = currentLensQuote.basic_options
        .map(
            (opt) => `
        <div class="lens-option-card ${selectedLensChoice?.lens_type === opt.lens_type ? 'selected' : ''}" data-lens-type="${opt.lens_type}" data-price="${opt.price}" data-label="${escapeHtml(opt.label_ar)}">
            <span>${escapeHtml(opt.label_ar)}</span>
            <span class="lens-option-price">${formatPrice(opt.price)} EGP</span>
        </div>
    `
        )
        .join('');

    container.querySelectorAll('.lens-option-card').forEach((card) => {
        card.addEventListener('click', () => {
            selectedLensChoice = {
                lens_type: card.dataset.lensType,
                price: Number(card.dataset.price),
                label: card.dataset.label,
            };
            container.querySelectorAll('.lens-option-card').forEach((c) => c.classList.remove('selected'));
            card.classList.add('selected');
            // A basic pick replaces any advanced quality-card pick too -
            // only one overall choice can be active. Without this, picking
            // an advanced option first and then a basic one left both
            // cards visually "selected" even though selectedLensChoice
            // only ever pointed to the most recent one.
            document.querySelectorAll('#usageQualityOptions .lens-option-card').forEach((c) => c.classList.remove('selected'));
            if (typeof trackCalculatorCompleted === 'function') {
                trackCalculatorCompleted(selectedLensChoice.lens_type, selectedLensChoice.price);
            }
            updateCheckoutTotal();
        });
    });
}

function renderUsageCheckboxes() {
    const area = document.getElementById('advancedLensArea');
    if (!area || !currentLensQuote) return;

    const usageLabels = { computer: 'كمبيوتر وشاشات', sun: 'شمس وخروج', night: 'قيادة ليلية', antibreak: 'ضد الكسر' };

    area.innerHTML = `
        <p class="product-meta">اختار استخدام واحد أو اتنين بحد أقصى:</p>
        <div class="usage-checkbox-row" id="usageCheckboxRow">
            ${Object.entries(usageLabels)
                .map(
                    ([code, label]) => `
                <label class="usage-checkbox-item">
                    <input type="checkbox" value="${code}"> ${label}
                </label>
            `
                )
                .join('')}
        </div>
        <div id="usageQualityOptions"></div>
    `;

    area.querySelectorAll('.usage-checkbox-row input[type="checkbox"]').forEach((cb) => {
        cb.addEventListener('change', () => {
            const checked = Array.from(area.querySelectorAll('.usage-checkbox-row input:checked'));
            if (checked.length > 2) {
                cb.checked = false;
                showToast('يمكن اختيار استخدامين بحد أقصى', 'info');
                return;
            }
            selectedUsages = checked.map((c) => c.value);
            // Whatever was picked before no longer necessarily applies to
            // this new usage combination - clear it and require an
            // explicit re-pick rather than silently carrying it forward.
            selectedLensChoice = null;
            document.querySelectorAll('#basicLensOptions .lens-option-card').forEach((c) => c.classList.remove('selected'));
            renderUsageQualityOptions();
            updateCheckoutTotal();
        });
    });
}

function renderUsageQualityOptions() {
    const container = document.getElementById('usageQualityOptions');
    if (!container) return;

    if (selectedUsages.length === 0) {
        container.innerHTML = '';
        return;
    }

    const key = [...selectedUsages].sort().join('+');
    const entry = currentLensQuote.usage_options[key];

    if (!entry) {
        container.innerHTML = `
            <div class="lens-special-notice" style="margin-top:10px;">
                <p>مفيش عدسات متاحة لتركيبة الاستخدام دي حاليًا.</p>
                <a class="button" href="https://wa.me/${currentLensQuote.whatsapp_number}" target="_blank" rel="noopener">تواصل معنا على واتساب</a>
            </div>
        `;
        return;
    }

    container.innerHTML = `
        <p class="lens-label" style="margin-top:15px;">${escapeHtml(entry.label_ar)}</p>
        ${entry.qualities
            .map(
                (q) => `
            <div class="lens-option-card ${selectedLensChoice?.lens_type === q.lens_type ? 'selected' : ''}" data-lens-type="${q.lens_type}" data-price="${q.price}" data-label="${escapeHtml(entry.label_ar)} - ${escapeHtml(q.label_ar)}">
                <span>${escapeHtml(q.label_ar)}</span>
                <span class="lens-option-price">${formatPrice(q.price)} EGP</span>
            </div>
        `
            )
            .join('')}
    `;

    container.querySelectorAll('.lens-option-card').forEach((card) => {
        card.addEventListener('click', () => {
            selectedLensChoice = {
                lens_type: card.dataset.lensType,
                price: Number(card.dataset.price),
                label: card.dataset.label,
            };
            container.querySelectorAll('.lens-option-card').forEach((c) => c.classList.remove('selected'));
            card.classList.add('selected');
            // Also clear the "selected" look on basic options - only one
            // overall choice can be active at a time.
            document.querySelectorAll('#basicLensOptions .lens-option-card').forEach((c) => c.classList.remove('selected'));
            if (typeof trackCalculatorCompleted === 'function') {
                trackCalculatorCompleted(selectedLensChoice.lens_type, selectedLensChoice.price);
            }
            updateCheckoutTotal();
        });
    });
}

async function populateAddressSelect() {
    const select = document.getElementById('addressSelect');
    if (!select) return;

    select.innerHTML = '<option value="">جاري التحميل...</option>';

    const result = await apiCall('/shipping-addresses');
    const addresses = Array.isArray(result) ? result : [];
    if (addresses.length === 0) {
        select.innerHTML = '<option value="">لا يوجد عنوان محفوظ - أضف واحد تحت</option>';
        return;
    }

    select.innerHTML = addresses
        .map(
            (addr) =>
                `<option value="${addr.id}" ${addr.is_default ? 'selected' : ''}>${escapeHtml(addr.city)} - ${escapeHtml(addr.full_address)}</option>`
        )
        .join('');
}

function wireNewPrescriptionForm() {
    const form = document.getElementById('newPrescriptionForm');
    if (!form) return;

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        const fileInput = document.getElementById('np-file');
        if (!fileInput.files || fileInput.files.length === 0) {
            showToast('من فضلك اختار ملف الكشف عشان ترفعه.', 'error');
            return;
        }

        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        formData.append('sph_r', document.getElementById('np-sph-r').value || 0);
        formData.append('cyl_r', document.getElementById('np-cyl-r').value || 0);
        formData.append('axis_r', document.getElementById('np-axis-r').value || 0);
        formData.append('sph_l', document.getElementById('np-sph-l').value || 0);
        formData.append('cyl_l', document.getElementById('np-cyl-l').value || 0);
        formData.append('axis_l', document.getElementById('np-axis-l').value || 0);

        const result = await uploadPrescription(formData);
        if (result) {
            form.reset();
            await populatePrescriptionSelect();
            const select = document.getElementById('prescriptionSelect');
            if (select) {
                select.value = String(result.id);
                await onPrescriptionSelectionChange();
            }
        } else {
            showToast('تعذر رفع الكشف. من فضلك راجع البيانات وحاول تاني.', 'error');
        }
    });
}

function wireNewAddressForm() {
    const form = document.getElementById('newAddressForm');
    if (!form) return;

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        const payload = {
            city: document.getElementById('np-city').value.trim(),
            full_address: document.getElementById('np-address').value.trim(),
            phone_number: document.getElementById('np-phone').value.trim(),
        };

        const result = await apiCall('/shipping-addresses', 'POST', payload);
        if (result) {
            form.reset();
            await populateAddressSelect();
            const select = document.getElementById('addressSelect');
            if (select) select.value = String(result.id);
        } else {
            showToast('تعذر حفظ العنوان. من فضلك راجع البيانات وحاول تاني.', 'error');
        }
    });
}

function wireNeedsPrescriptionToggle() {
    const radios = document.querySelectorAll('input[name="needsPrescription"]');
    const group = document.getElementById('prescriptionFieldsGroup');

    radios.forEach((radio) => {
        radio.addEventListener('change', () => {
            const wantsLenses = needsPrescriptionLenses();
            group.style.display = wantsLenses ? 'block' : 'none';
            if (wantsLenses && typeof trackCalculatorStarted === 'function') {
                trackCalculatorStarted();
            }
            updateCheckoutTotal();
        });
    });
}

function buildOrderItemsPayload() {
    const wantsLenses = needsPrescriptionLenses();
    const prescriptionId = wantsLenses ? document.getElementById('prescriptionSelect').value : null;
    const lensType = wantsLenses && selectedLensChoice ? selectedLensChoice.lens_type : '';

    return cart.map((item) => {
        // Only the chosen frame(s) get the prescription/lens type -
        // everything else in the cart goes through as a plain, no-lens
        // item, even when the order overall "wants lenses".
        const appliesHere = wantsLenses && (lensTargetMode === 'all' || item.id === lensTargetProductId);
        return {
            product_id: item.id,
            prescription_id: appliesHere && prescriptionId ? Number(prescriptionId) : null,
            lens_type: appliesHere ? lensType : '',
            quantity: Number(item.quantity) || 1,
        };
    });
}

async function placeOrder() {
    const msg = document.getElementById('checkoutMsg');
    const addressId = document.getElementById('addressSelect').value;
    const paymentMethod = document.querySelector('input[name="paymentMethod"]:checked').value;
    const wantsLenses = needsPrescriptionLenses();

    if (!addressId) {
        msg.textContent = 'من فضلك اختار أو ضيف عنوان شحن الأول.';
        msg.style.color = '#ef4444';
        return;
    }

    if (wantsLenses) {
        const prescriptionId = document.getElementById('prescriptionSelect').value;

        if (!prescriptionId) {
            msg.textContent = 'من فضلك اختار أو ارفع كشف الأول.';
            msg.style.color = '#ef4444';
            return;
        }

        if (currentLensQuote?.is_special) {
            msg.textContent = 'الدرجة دي محتاجة تسعير يدوي - من فضلك تواصل معنا على واتساب.';
            msg.style.color = '#ef4444';
            return;
        }

        if (!selectedLensChoice) {
            msg.textContent = 'من فضلك اختار نوع العدسة الأول.';
            msg.style.color = '#ef4444';
            return;
        }

        if (lensTargetMode === 'single' && !lensTargetProductId) {
            msg.textContent = 'من فضلك اختار أنهي منتج هتركب فيه العدسات.';
            msg.style.color = '#ef4444';
            return;
        }
    }

    const attribution = typeof getAttributionForOrder === 'function'
        ? await getAttributionForOrder()
        : {};

    const payload = {
        address_id: Number(addressId),
        items: buildOrderItemsPayload(),
        coupon_code: appliedCoupon ? appliedCoupon.code : null,
        ...attribution,
    };

    const placeBtn = document.getElementById('placeOrderBtn');
    placeBtn.disabled = true;
    placeBtn.textContent = 'جاري تنفيذ الطلب...';

    const idempotencyStorageKey = 'joo_pending_order_idempotency_key';
    let orderIdempotencyKey = sessionStorage.getItem(idempotencyStorageKey);
    if (!orderIdempotencyKey) {
        orderIdempotencyKey = typeof crypto.randomUUID === 'function'
            ? crypto.randomUUID()
            : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
        sessionStorage.setItem(idempotencyStorageKey, orderIdempotencyKey);
    }
    const order = await apiCall(
        '/orders',
        'POST',
        payload,
        false,
        { 'Idempotency-Key': orderIdempotencyKey }
    );

    if (!order) {
        placeBtn.disabled = false;
        placeBtn.textContent = 'تأكيد الطلب';
        msg.style.color = '#ef4444';
        msg.textContent = 'تعذر تنفيذ الطلب. من فضلك راجع المنتجات والكشف والعنوان وحاول تاني.';
        return;
    }

    // Order exists in the database from here on - clear the cart regardless
    // of which payment path is taken next.
    cart = [];
    saveCart();
    sessionStorage.removeItem(idempotencyStorageKey);
    updateCartCount();

    if (paymentMethod === 'cash') {
        await apiCall('/payments', 'POST', { order_id: order.id, payment_method: 'cash' });

        // Cash on delivery never visits payment-result.html (it redirects
        // straight to account.html below), so this is the only place a
        // client-side Purchase companion event can fire for this path.
        // Uses the same backend-atomic check the Paymob flow uses (see
        // payment-result.js) - safe even if this somehow ran twice.
        if (typeof trackPurchase === 'function') {
            const statusResult = await apiCall(`/payments/order/${order.id}/status`);
            if (statusResult?.tracking?.should_fire) {
                trackPurchase(statusResult.tracking.event_id, order.id, statusResult.tracking.total_amount);
            }
        }

        placeBtn.disabled = false;
        placeBtn.textContent = 'تأكيد الطلب';
        msg.style.color = '#22c55e';
        msg.textContent = `تم تنفيذ الطلب رقم ${order.id} بنجاح! جاري تحويلك لصفحة طلباتك...`;
        setTimeout(() => {
            window.location.href = '/account.html';
        }, 1800);
        return;
    }

    // paymob_card: hand off to Paymob's hosted iframe. The order already
    // exists and is unpaid - the iframe page (and later the webhook) are
    // what actually mark it as paid, this tab just navigates there.
    placeBtn.textContent = 'جاري التحويل لصفحة الدفع...';
    const paymobResult = await apiCall('/payments/paymob/initiate', 'POST', { order_id: order.id });

    if (!paymobResult || !paymobResult.iframe_url) {
        placeBtn.disabled = false;
        placeBtn.textContent = 'تأكيد الطلب';
        msg.style.color = '#ef4444';
        msg.textContent = `تم تنفيذ الطلب رقم ${order.id}، لكن بدء الدفع الأونلاين فشل. ` +
            'تقدر تعيد محاولة الدفع من صفحة طلباتك، أو تتواصل معنا عشان ندبرها كاش عند الاستلام.';
        return;
    }

    window.location.href = paymobResult.iframe_url;
}

function wirePlaceOrderButton() {
    const btn = document.getElementById('placeOrderBtn');
    if (btn) {
        btn.addEventListener('click', placeOrder);
    }
}

async function initCheckoutPage() {
    if (!authToken) {
        document.getElementById('checkout-guest-notice').style.display = 'block';
        return;
    }

    cart = loadCart();
    if (cart.length === 0) {
        document.getElementById('checkout-empty-notice').style.display = 'block';
        return;
    }

    document.getElementById('checkout-content').style.display = 'block';

    if (typeof trackInitiateCheckout === 'function') {
        const total = cart.reduce((sum, item) => sum + (Number(item.price) || 0) * (Number(item.quantity) || 1), 0);
        trackInitiateCheckout(cart, total);
    }

    renderCheckoutItems();
    wireNewPrescriptionForm();
    wireNewAddressForm();
    wirePlaceOrderButton();
    wireNeedsPrescriptionToggle();
    wireLensTargetSelector();
    wireCouponUi();

    await Promise.all([populatePrescriptionSelect(), populateAddressSelect()]);
    updateCheckoutTotal();
}

document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('checkout-page')) {
        initCheckoutPage();
    }
});
