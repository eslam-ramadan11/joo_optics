// Logic for account.html. Loaded after frontend.js, reuses its
// apiCall/escapeHtml/formatPrice helpers and the shared authToken state.
//
// Defensive by design: any unexpected error during init is caught and
// shown on the page itself (not just the browser console), since silent
// blank pages are the hardest thing to debug remotely.

const ORDER_STATUS_LABELS = {
    pending: 'قيد الانتظار',
    processing: 'قيد التجهيز',
    shipped: 'تم الشحن',
    delivered: 'تم التسليم',
    cancelled: 'ملغي',
};

const ORDER_STATUS_CLASS = {
    pending: 'status-pending',
    processing: 'status-processing',
    shipped: 'status-shipped',
    delivered: 'status-delivered',
    cancelled: 'status-cancelled',
};

function showFatalError(message) {
    const el = document.getElementById('account-fatal-error');
    const msgEl = document.getElementById('account-fatal-error-message');
    if (el && msgEl) {
        msgEl.textContent = message;
        el.style.display = 'block';
    }
    document.getElementById('account-page').style.display = 'none';
    console.error('[account.js]', message);
}

function switchAccountTab(tabName) {
    document.querySelectorAll('.account-nav-btn').forEach((btn) => {
        btn.classList.toggle('active', btn.dataset.tab === tabName);
    });
    document.querySelectorAll('.account-tab-content').forEach((tab) => {
        tab.style.display = tab.id === `tab-${tabName}` ? 'block' : 'none';
    });
}

function wireAccountTabs() {
    document.querySelectorAll('.account-nav-btn').forEach((btn) => {
        btn.addEventListener('click', () => switchAccountTab(btn.dataset.tab));
    });
}

function fillSidebar(user) {
    const initial = (user.username || '?').charAt(0).toUpperCase();
    document.getElementById('account-avatar').textContent = initial;
    document.getElementById('account-sidebar-username').textContent = user.username || '';
    document.getElementById('overview-username').textContent = user.username || '';

    if (user.created_at) {
        const date = new Date(user.created_at).toLocaleDateString('ar-EG');
        document.getElementById('account-sidebar-since').textContent = `عضو منذ ${date}`;
    }
}

function fillProfileForm(user) {
    const usernameInput = document.getElementById('profileUsername');
    const emailInput = document.getElementById('profileEmail');
    const dobInput = document.getElementById('profileDob');
    if (usernameInput) usernameInput.value = user.username || '';
    if (emailInput) emailInput.value = user.email || '';
    // marshmallow dumps Date fields as YYYY-MM-DD, which is exactly what
    // <input type="date"> expects - no conversion needed. Existing
    // accounts created before this field existed will have it as null.
    if (dobInput) dobInput.value = user.date_of_birth || '';
}

function wireProfileForm() {
    const form = document.getElementById('profileForm');
    if (!form) return;

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        const msg = document.getElementById('profileMsg');
        const username = document.getElementById('profileUsername').value.trim();
        const email = document.getElementById('profileEmail').value.trim();
        const dateOfBirth = document.getElementById('profileDob').value;

        const payload = { username, email };
        if (dateOfBirth) {
            payload.date_of_birth = dateOfBirth;
        }

        const result = await apiCall('/user/profile', 'PUT', payload);
        if (result) {
            currentUser = result;
            updateUIForAuth();
            fillSidebar(result);
            msg.textContent = 'تم تحديث بياناتك بنجاح.';
            msg.style.color = '#22c55e';
        } else {
            msg.textContent = 'تعذر تحديث البيانات. ممكن اسم المستخدم أو الإيميل مستخدم قبل كده.';
            msg.style.color = '#ef4444';
        }
    });
}

function wirePasswordForm() {
    const form = document.getElementById('passwordForm');
    if (!form) return;

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        const msg = document.getElementById('passwordMsg');
        const oldPassword = document.getElementById('oldPassword').value;
        const newPassword = document.getElementById('newPassword').value;
        const confirmPassword = document.getElementById('confirmPassword').value;

        if (newPassword !== confirmPassword) {
            msg.textContent = 'كلمة السر الجديدة والتأكيد مش متطابقين.';
            msg.style.color = '#ef4444';
            return;
        }

        const result = await apiCall('/auth/change-password', 'POST', {
            old_password: oldPassword,
            new_password: newPassword,
        });

        if (result !== null) {
            form.reset();
            msg.textContent = 'تم تحديث كلمة السر بنجاح.';
            msg.style.color = '#22c55e';
        } else {
            msg.textContent = 'تعذر تحديث كلمة السر. راجع كلمة السر الحالية وحاول تاني.';
            msg.style.color = '#ef4444';
        }
    });
}

function renderAddresses(addresses) {
    const container = document.getElementById('addressList');
    if (!container) return;

    if (!Array.isArray(addresses) || addresses.length === 0) {
        container.innerHTML = '<div class="site-empty-state"><div class="site-empty-icon">📍</div>لا توجد عناوين محفوظة بعد.</div>';
        return;
    }

    container.innerHTML = addresses
        .map(
            (addr) => `
        <div class="contact-item address-item">
            <div>
                <strong>${escapeHtml(addr.city)}</strong>${addr.is_default ? ' <span class="price">(الافتراضي)</span>' : ''}
                <div>${escapeHtml(addr.full_address)}</div>
                <div class="product-meta">${escapeHtml(addr.phone_number)}</div>
            </div>
            <button type="button" class="table-action-btn" data-delete-address="${addr.id}">حذف</button>
        </div>
    `
        )
        .join('');

    container.querySelectorAll('[data-delete-address]').forEach((btn) => {
        btn.addEventListener('click', () => deleteAddress(Number(btn.dataset.deleteAddress)));
    });
}

async function loadAddresses() {
    const result = await apiCall('/shipping-addresses');
    const addresses = Array.isArray(result) ? result : [];
    renderAddresses(addresses);
    document.getElementById('stat-addresses').textContent = addresses.length;
    return addresses;
}

async function deleteAddress(addressId) {
    const confirmed = await showConfirm('تحذف العنوان ده؟');
    if (!confirmed) return;

    const result = await apiCall(`/shipping-addresses/${addressId}`, 'DELETE');
    if (result !== null) {
        showToast('تم حذف العنوان', 'success');
        loadAddresses();
    } else {
        showToast('تعذر حذف العنوان. ممكن يكون مستخدم في طلب سابق.', 'error');
    }
}

function wireAddressForm() {
    const form = document.getElementById('addressForm');
    if (!form) return;

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        const msg = document.getElementById('addressMsg');
        const payload = {
            city: document.getElementById('addressCity').value.trim(),
            full_address: document.getElementById('addressFull').value.trim(),
            phone_number: document.getElementById('addressPhone').value.trim(),
            is_default: document.getElementById('addressIsDefault').checked,
        };

        const result = await apiCall('/shipping-addresses', 'POST', payload);
        if (result) {
            form.reset();
            msg.textContent = 'تمت إضافة العنوان.';
            msg.style.color = '#22c55e';
            loadAddresses();
        } else {
            msg.textContent = 'تعذر إضافة العنوان. راجع البيانات وحاول تاني.';
            msg.style.color = '#ef4444';
        }
    });
}

function orderStatusBadge(status) {
    const label = ORDER_STATUS_LABELS[status] || status || 'غير معروف';
    const cls = ORDER_STATUS_CLASS[status] || 'status-pending';
    return `<span class="order-status-badge ${cls}">${escapeHtml(label)}</span>`;
}

// What the customer sees about payment, plus whether they can (re)start an
// online card payment. The server decides everything that matters (it
// re-checks ownership, order status and payment state on /initiate) -
// this only controls which button is shown.
function paymentLineText(order) {
    if (order.payment_status === 'completed') return 'تم الدفع ✅';
    if (order.payment_method === 'cash') return 'الدفع عند الاستلام';
    if (order.payment_status === 'failed') return 'فشلت عملية الدفع بالكارت';
    if (order.payment_status === 'pending') return 'الدفع بالكارت لم يكتمل';
    if (order.payment_status === 'manual_refund_required') return 'جاري رد المبلغ';
    if (order.payment_status === 'cancelled') return 'تم إلغاء الدفع';
    return 'لم يتم تحديد طريقة الدفع';
}

function canPayOnline(order) {
    if (order.status === 'cancelled' || order.status === 'delivered') return false;
    if (!order.payment_status) return true;
    return order.payment_method === 'paymob_card' && ['pending', 'failed'].includes(order.payment_status);
}

async function payOrderOnline(orderId, button) {
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = 'جاري التحويل لصفحة الدفع...';

    const result = await apiCall('/payments/paymob/initiate', 'POST', { order_id: orderId });
    if (result && result.iframe_url) {
        window.location.href = result.iframe_url;
        return;
    }

    button.disabled = false;
    button.textContent = originalText;
    showToast('تعذر بدء الدفع الأونلاين دلوقتي. حاول تاني بعد شوية أو كلمنا.', 'error');
}

function renderOrderRow(order, expandable) {
    const date = order.date_posted ? new Date(order.date_posted).toLocaleDateString('ar-EG') : '';
    return `
        <div class="card order-item" data-order-id="${order.id}" style="margin-bottom:14px; ${expandable ? 'cursor:pointer;' : ''}">
            <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:10px; align-items:center;">
                <div>
                    <strong>طلب رقم #${order.id}</strong>
                    <div class="product-meta">${escapeHtml(date)}</div>
                </div>
                <div style="text-align:right;">
                    <div class="price">${formatPrice(order.total_amount)} EGP</div>
                    ${orderStatusBadge(order.status)}
                </div>
            </div>
            <div class="product-meta" style="margin-top:10px;">${escapeHtml(paymentLineText(order))}</div>
            ${canPayOnline(order) ? `<button type="button" class="button" style="margin-top:10px;" data-pay-order="${order.id}">ادفع أونلاين بالكارت</button>` : ''}
            ${expandable ? `<div class="order-details" id="order-details-${order.id}" style="display:none; margin-top:14px; border-top:1px solid #1e293b; padding-top:14px;"></div>` : ''}
        </div>
    `;
}

function renderOrders(orders) {
    const container = document.getElementById('ordersList');
    if (!container) return;

    if (!Array.isArray(orders) || orders.length === 0) {
        container.innerHTML = '<div class="site-empty-state"><div class="site-empty-icon">🛍️</div>لسه ماعملتش أي طلبات.</div>';
        return;
    }

    const sorted = [...orders].sort((a, b) => new Date(b.date_posted) - new Date(a.date_posted));
    container.innerHTML = sorted.map((o) => renderOrderRow(o, true)).join('');

    container.querySelectorAll('.order-item').forEach((el) => {
        el.addEventListener('click', (event) => {
            // The pay button lives inside the clickable card - don't also
            // expand/collapse the details when it's clicked.
            if (event.target.closest('[data-pay-order]')) return;
            toggleOrderDetails(Number(el.dataset.orderId));
        });
    });

    return sorted;
}

function renderOverviewStats(orders) {
    document.getElementById('stat-total-orders').textContent = orders.length;

    if (orders.length > 0) {
        const sorted = [...orders].sort((a, b) => new Date(b.date_posted) - new Date(a.date_posted));
        const lastDate = sorted[0].date_posted ? new Date(sorted[0].date_posted).toLocaleDateString('ar-EG') : '-';
        document.getElementById('stat-last-order').textContent = lastDate;

        const recentContainer = document.getElementById('overview-recent-orders');
        recentContainer.innerHTML = sorted.slice(0, 3).map((o) => renderOrderRow(o, false)).join('');
    } else {
        document.getElementById('stat-last-order').textContent = '-';
        document.getElementById('overview-recent-orders').innerHTML =
            '<div class="site-empty-state"><div class="site-empty-icon">🛍️</div>لا توجد طلبات بعد - <a href="shop.html" style="color:#F97316;">ابدأ التسوق</a>.</div>';
    }
}

async function toggleOrderDetails(orderId) {
    const detailsEl = document.getElementById(`order-details-${orderId}`);
    if (!detailsEl) return;

    const isOpen = detailsEl.style.display !== 'none';
    if (isOpen) {
        detailsEl.style.display = 'none';
        return;
    }

    if (!detailsEl.dataset.loaded) {
        const order = await apiCall(`/orders/${orderId}`);
        if (!order) {
            detailsEl.innerHTML = '<p class="product-meta">تعذر تحميل تفاصيل الطلب.</p>';
        } else {
            const items = order.items || [];
            detailsEl.innerHTML =
                items
                    .map(
                        (item) => `
                <div class="product-meta" style="margin-bottom:6px;">
                    ${escapeHtml(item.product_name || ('منتج #' + item.product_id))} &times; ${item.quantity} - ${formatPrice(item.item_price)} EGP للقطعة
                </div>
            `
                    )
                    .join('') || '<p class="product-meta">لا توجد تفاصيل متاحة.</p>';
        }
        detailsEl.dataset.loaded = '1';
    }

    detailsEl.style.display = 'block';
}

async function loadOrders() {
    const result = await apiCall('/orders');
    const orders = Array.isArray(result) ? result : [];
    const sorted = renderOrders(orders) || [];
    renderOverviewStats(orders);
    return sorted;
}

async function initAccountPage() {
    try {
        if (typeof authToken === 'undefined') {
            showFatalError(
                'الصفحة لم تُحمّل بشكل صحيح. افتح الموقع من الرابط الرسمي (مش كملف على الجهاز) وحاول تاني.'
            );
            return;
        }

        if (!authToken) {
            document.getElementById('account-guest-notice').style.display = 'block';
            document.getElementById('account-page').style.display = 'none';
            return;
        }

        const user = currentUser || (await loadCurrentUser());
        if (!user) {
            showFatalError(
                'تعذر تحميل بياناتك. غالبًا الجلسة انتهت - سجّل خروج وادخل تاني.'
            );
            return;
        }

        document.getElementById('account-guest-notice').style.display = 'none';
        document.getElementById('account-page').style.display = 'flex';

        fillSidebar(user);
        fillProfileForm(user);

        document.addEventListener('click', (event) => {
            const payBtn = event.target.closest('[data-pay-order]');
            if (payBtn) {
                payOrderOnline(Number(payBtn.dataset.payOrder), payBtn);
            }
        });

        wireAccountTabs();
        wireProfileForm();
        wirePasswordForm();
        wireAddressForm();

        const loadingSpinner = '<div class="site-loading"><span class="site-spinner"></span> جارٍ التحميل...</div>';
        document.getElementById('addressList').innerHTML = loadingSpinner;
        document.getElementById('ordersList').innerHTML = loadingSpinner;
        document.getElementById('overview-recent-orders').innerHTML = loadingSpinner;

        await Promise.all([loadAddresses(), loadOrders()]);
    } catch (err) {
        showFatalError(`حصل خطأ غير متوقع: ${err.message || err}`);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('account-page')) {
        initAccountPage();
    }
});
