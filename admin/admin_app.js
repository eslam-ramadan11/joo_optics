const API_BASE_URL = '/api';

let authToken = localStorage.getItem('authToken');
let adminChart = null;
let productState = {
    page: 1,
    perPage: 10,
    search: '',
    category: '',
    sortBy: 'id',
    sortDir: 'desc',
};
let productCache = [];
let userCache = [];
let availableColorsCache = [];
let availableCategoriesCache = [];

// Arabic display labels for each canonical category value - the API
// returns the value only (matches what's stored on Product.category);
// the label mapping is a display-only concern that belongs here.
const CATEGORY_LABELS_AR = {
    'men sunglasses': 'نظارات شمس رجالي',
    'womens sunglasses': 'نظارات شمس حريمي',
    'men medical fraims': 'شنابر طبي رجالي',
    'womens medical fraims': 'شنابر طبي حريمي',
    'kids glasses': 'نظارات أطفال',
};

async function loadAvailableCategories() {
    const categories = await apiCall('/products/categories');
    availableCategoriesCache = Array.isArray(categories) ? categories : [];

    const optionsHtml = availableCategoriesCache
        .map((cat) => `<option value="${escapeHtml(cat)}">${escapeHtml(CATEGORY_LABELS_AR[cat] || cat)}</option>`)
        .join('');

    // prod-category / edit-prod-category / admin-product-category keep
    // their existing first <option> (a disabled placeholder or "All
    // Categories") and get the real categories appended after it.
    ['prod-category', 'edit-prod-category', 'admin-product-category'].forEach((id) => {
        const select = document.getElementById(id);
        if (select) select.insertAdjacentHTML('beforeend', optionsHtml);
    });

    // These two have no placeholder - a category must always be picked
    // when they're shown, so they're fully populated.
    ['coupon-apply-category', 'edit-coupon-apply-category'].forEach((id) => {
        const select = document.getElementById(id);
        if (select) select.innerHTML = optionsHtml;
    });
}

let couponCache = [];
let dealCache = [];
// Separate from productCache on purpose: productCache mirrors the
// paginated products table (10 per page), so using it to populate picker
// widgets (coupon "specific products", deals) only ever showed whichever
// page happened to be loaded. This holds up to 100 products (the API's
// per_page cap) specifically for those pickers.
let allProductsForPickers = [];

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
        return '/images/placeholder.jpg';
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

async function apiCall(endpoint, method = 'GET', data = null, isFormData = false) {
    const options = {
        method,
        headers: isFormData ? {} : { 'Content-Type': 'application/json' },
    };

    if (authToken) {
        options.headers.Authorization = `Bearer ${authToken}`;
    }

    if (data) {
        options.body = isFormData ? data : JSON.stringify(data);
    }

    const response = await fetch(`${API_BASE_URL}${endpoint}`, options);
    if (response.status === 204) {
        return null;
    }

    const contentType = response.headers.get('content-type') || '';
    const responseData = contentType.includes('application/json') ? await response.json() : await response.text();

    if (response.status === 401 || response.status === 403) {
        if (endpoint.startsWith('/admin')) {
            localStorage.removeItem('authToken');
            authToken = null;
            window.location.href = 'admin_login.html';
        }
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
}

function switchTab(event, tabId) {
    document.querySelectorAll('.tab-content').forEach((tab) => tab.classList.remove('active'));
    document.querySelectorAll('.sidebar-nav a').forEach((link) => link.classList.remove('active'));

    const selectedTab = document.getElementById(`${tabId}-tab`);
    if (selectedTab) {
        selectedTab.classList.add('active');
    }

    if (event?.currentTarget) {
        event.currentTarget.classList.add('active');
    }
}

function setLoadingRows(tbodyId, message, colspan = 6) {
    const tbody = document.getElementById(tbodyId);
    if (tbody) {
        tbody.innerHTML = `<tr><td colspan="${colspan}" style="text-align:center; color:#94a3b8;">${escapeHtml(message)}</td></tr>`;
    }
}

function updateStats(stats) {
    const values = document.querySelectorAll('.stat-value');
    if (values[0]) values[0].textContent = `${Number(stats.total_sales || 0).toLocaleString()} EGP`;
    if (values[1]) values[1].textContent = String(stats.total_orders || 0);
    if (values[2]) values[2].textContent = String(stats.total_customers || 0);
}

function renderChart(labels, data) {
    const canvas = document.getElementById('salesChart');
    if (!canvas) {
        return;
    }

    const ctx = canvas.getContext('2d');
    if (adminChart) {
        adminChart.destroy();
    }

    adminChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels.length > 0 ? labels : ['No Data'],
            datasets: [{
                label: 'المبيعات بالجنيه المصري',
                data: data.length > 0 ? data : [0],
                backgroundColor: [
                    'rgba(249, 115, 22, 0.8)',
                    'rgba(249, 115, 22, 0.6)',
                    'rgba(249, 115, 22, 0.4)',
                    'rgba(249, 115, 22, 0.5)',
                    'rgba(249, 115, 22, 0.3)',
                ],
                borderColor: '#F97316',
                borderWidth: 1,
                borderRadius: 5,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: { color: '#E2E8F0', font: { family: 'Cairo' } },
                },
            },
            scales: {
                y: { beginAtZero: true, grid: { color: '#1e293b' }, ticks: { color: '#94a3b8' } },
                x: { grid: { display: false }, ticks: { color: '#94a3b8', font: { family: 'Cairo' } } },
            },
        },
    });
}

async function loadDashboardStats() {
    const stats = await apiCall('/admin/dashboard-stats');
    if (!stats) {
        return;
    }

    updateStats(stats);
    renderChart(stats.chart_labels || [], stats.chart_data || []);
}

function buildProductQuery(page = productState.page) {
    const params = new URLSearchParams({
        page: String(page),
        per_page: String(productState.perPage),
        sort_by: productState.sortBy,
        sort_dir: productState.sortDir,
    });

    if (productState.search) {
        params.set('search', productState.search);
    }

    if (productState.category) {
        params.set('category', productState.category);
    }

    return params.toString();
}

function renderProductRows(items) {
    const tbody = document.getElementById('products-tbody');
    if (!tbody) {
        return;
    }

    if (items.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:#94a3b8;">No products found.</td></tr>';
        return;
    }

    tbody.innerHTML = items.map((product) => `
        <tr>
            <td>${product.id}</td>
            <td>
                <div style="display:flex; align-items:center; gap:12px;">
                    <img src="${escapeHtml(assetUrl(product.image_file))}" alt="${escapeHtml(product.name)}" style="width:48px; height:48px; object-fit:cover; border-radius:10px;">
                    <div>
                        <div style="font-weight:700; color:#fff;">${escapeHtml(product.name)}</div>
                        <div style="font-size:12px; color:#94a3b8;">${escapeHtml(product.discount_badge || '')}</div>
                    </div>
                </div>
            </td>
            <td>${escapeHtml(product.category)}</td>
            <td>${formatPrice(product.price)}</td>
            <td>${product.old_price ? formatPrice(product.old_price) : '-'}</td>
            <td>${escapeHtml(product.colors)}</td>
            <td>${Number(product.stock_quantity) || 0}</td>
            <td>
                <button type="button" class="table-action-btn edit-product-btn" data-id="${product.id}">Edit</button>
                <button type="button" class="table-action-btn images-product-btn" data-id="${product.id}">Images</button>
                <button type="button" class="table-action-btn delete-product-btn" data-id="${product.id}">Delete</button>
            </td>
        </tr>
    `).join('');

    tbody.querySelectorAll('.edit-product-btn').forEach((button) => {
        button.addEventListener('click', () => {
            const product = productCache.find((item) => item.id === Number(button.dataset.id));
            if (product) {
                openEditProduct(product);
            }
        });
    });

    tbody.querySelectorAll('.images-product-btn').forEach((button) => {
        button.addEventListener('click', () => {
            const product = productCache.find((item) => item.id === Number(button.dataset.id));
            if (product) {
                openImagesModal(product);
            }
        });
    });

    tbody.querySelectorAll('.delete-product-btn').forEach((button) => {
        button.addEventListener('click', async () => {
            const productId = Number(button.dataset.id);
            if (!window.confirm('حذف المنتج ده؟ (لو المنتج موجود في طلبات سابقة مش هينحذف - خلّي المخزون 0 بدل الحذف)')) {
                return;
            }

            const deleted = await apiCall(`/products/${productId}`, 'DELETE');
            if (deleted !== null) {
                await loadProducts();
                await loadDashboardStats();
            } else {
                alert('تعذر حذف المنتج - على الأرجح موجود في طلبات سابقة. خلّي كمية المخزون 0 بدل الحذف عشان ميتباعش تاني.');
            }
        });
    });
}

function renderProductsPagination(meta) {
    const pagination = document.getElementById('products-pagination');
    if (!pagination) {
        return;
    }

    const totalPages = Math.max(1, Math.ceil((meta.total || 0) / (meta.per_page || productState.perPage)));
    pagination.innerHTML = `
        <button type="button" class="pagination-btn" ${meta.page <= 1 ? 'disabled' : ''} data-page="${meta.page - 1}">Previous</button>
        <span class="pagination-info">Page ${meta.page} of ${totalPages}</span>
        <button type="button" class="pagination-btn" ${meta.page >= totalPages ? 'disabled' : ''} data-page="${meta.page + 1}">Next</button>
    `;

    pagination.querySelectorAll('.pagination-btn').forEach((button) => {
        button.addEventListener('click', () => {
            const nextPage = Number(button.dataset.page);
            if (Number.isFinite(nextPage) && nextPage >= 1) {
                productState.page = nextPage;
                loadProducts();
            }
        });
    });
}

async function loadProducts() {
    setLoadingRows('products-tbody', 'Loading products...', 8);
    const data = await apiCall(`/products?${buildProductQuery()}`);
    if (!data) {
        setLoadingRows('products-tbody', 'Failed to load products.', 9);
        return;
    }

    productCache = Array.isArray(data.items) ? data.items : [];
    renderProductRows(productCache);
    renderProductsPagination({ page: data.page || 1, per_page: data.per_page || productState.perPage, total: data.total || 0 });
}

function closeImagesModal() {
    const overlay = document.getElementById('imagesModalOverlay');
    if (overlay) overlay.remove();
}

function renderImagesModalGallery(product) {
    const gallery = document.getElementById('imagesModalGallery');
    if (!gallery) return;

    const allImages = [
        { id: null, color: null, image_file: product.image_file, isMain: true },
        ...(product.images || []),
    ];

    gallery.innerHTML = allImages.map((img) => `
        <div style="position:relative;">
            <img src="${escapeHtml(assetUrl(img.image_file))}" style="width:100%; aspect-ratio:1/1; object-fit:cover; border-radius:10px;">
            <div style="font-size:11px; color:#94a3b8; text-align:center; margin-top:4px;">${img.isMain ? 'Main' : escapeHtml(img.color || 'General')}</div>
            ${img.isMain ? '' : `<button type="button" class="table-action-btn delete-image-btn" data-image-id="${img.id}" style="width:100%; margin-top:4px; font-size:11px; padding:4px;">Delete</button>`}
        </div>
    `).join('');

    gallery.querySelectorAll('.delete-image-btn').forEach((btn) => {
        btn.addEventListener('click', async () => {
            if (!window.confirm('Delete this image?')) return;
            const result = await apiCall(`/products/${product.id}/images/${btn.dataset.imageId}`, 'DELETE');
            if (result !== null) {
                const updated = await apiCall(`/products/${product.id}`);
                if (updated) {
                    renderImagesModalGallery(updated);
                    await loadProducts();
                }
            } else {
                alert('Could not delete this image.');
            }
        });
    });
}

function openImagesModal(product) {
    closeImagesModal();

    const productColors = (product.colors || '').split(',').map((c) => c.trim()).filter(Boolean);
    const colorOptions = ['<option value="">General (no specific color)</option>']
        .concat(productColors.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`))
        .join('');

    const overlay = document.createElement('div');
    overlay.id = 'imagesModalOverlay';
    overlay.style.cssText = 'position:fixed; inset:0; background:rgba(0,0,0,0.6); z-index:3000; display:flex; align-items:center; justify-content:center; padding:20px;';
    overlay.innerHTML = `
        <div style="background:#111827; border:1px solid #1e293b; border-radius:14px; padding:24px; width:min(560px, 100%); max-height:85vh; overflow-y:auto;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
                <h3 style="margin:0;">Manage Images - ${escapeHtml(product.name)}</h3>
                <button type="button" id="closeImagesModalBtn" style="background:none; border:none; color:#94a3b8; font-size:22px; cursor:pointer; padding:0;">&times;</button>
            </div>
            <p style="color:#94a3b8; font-size:13px;">Upload extra photos for the product page gallery. Choose "General" for a photo shown regardless of color, or pick one of this product's colors so it only shows when that color is selected.</p>
            <div id="imagesModalGallery" style="display:grid; grid-template-columns:repeat(3, 1fr); gap:10px; margin-bottom:20px;"></div>
            <form id="addImageForm">
                <div class="input-group">
                    <input type="file" id="new-image-file" accept="image/png,image/jpeg,image/gif" required>
                    <select id="new-image-color">${colorOptions}</select>
                </div>
                <button type="submit" class="submit-btn">Upload Image</button>
            </form>
        </div>
    `;
    document.body.appendChild(overlay);

    renderImagesModalGallery(product);

    document.getElementById('closeImagesModalBtn').addEventListener('click', closeImagesModal);
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeImagesModal();
    });

    document.getElementById('addImageForm').addEventListener('submit', async (event) => {
        event.preventDefault();
        const fileInput = document.getElementById('new-image-file');
        if (!fileInput.files || fileInput.files.length === 0) {
            alert('Choose a file first.');
            return;
        }

        const formData = new FormData();
        formData.append('image', fileInput.files[0]);
        const color = document.getElementById('new-image-color').value.trim();
        if (color) {
            formData.append('color', color);
        }

        const result = await apiCall(`/products/${product.id}/images`, 'POST', formData, true);
        if (result) {
            const updated = await apiCall(`/products/${product.id}`);
            if (updated) {
                renderImagesModalGallery(updated);
                await loadProducts();
            }
            document.getElementById('addImageForm').reset();
        } else {
            alert('Could not upload the image. Check the file type and size (max 5MB).');
        }
    });
}

async function loadAvailableColors() {
    const colors = await apiCall('/products/colors');
    availableColorsCache = Array.isArray(colors) ? colors : [];
    renderColorCheckboxes('prod-colors-checkboxes');
    renderColorCheckboxes('edit-prod-colors-checkboxes');
}

function renderColorCheckboxes(containerId, checkedColors = []) {
    const container = document.getElementById(containerId);
    if (!container) return;

    container.innerHTML = availableColorsCache
        .map(
            (color) => `
        <label class="color-checkbox-item">
            <input type="checkbox" value="${escapeHtml(color)}" ${checkedColors.includes(color) ? 'checked' : ''}>
            ${escapeHtml(color)}
        </label>
    `
        )
        .join('');
}

function getCheckedColors(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return [];
    return Array.from(container.querySelectorAll('input[type="checkbox"]:checked')).map((cb) => cb.value);
}

function openEditProduct(product) {
    const container = document.getElementById('editProductContainer');
    if (!container) {
        return;
    }

    document.getElementById('edit-product-id').value = product.id;
    document.getElementById('edit-prod-name').value = product.name || '';
    document.getElementById('edit-prod-price').value = product.price ?? '';
    document.getElementById('edit-prod-old-price').value = product.old_price ?? '';
    document.getElementById('edit-prod-category').value = product.category || '';
    document.getElementById('edit-prod-stock').value = product.stock_quantity ?? '';
    document.getElementById('edit-prod-discount').value = product.discount_badge || '';

    const currentColors = (product.colors || '').split(',').map((c) => c.trim()).filter(Boolean);
    renderColorCheckboxes('edit-prod-colors-checkboxes', currentColors);

    container.style.display = 'block';
    container.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function submitCreateProduct(event) {
    event.preventDefault();

    const image = document.getElementById('prod-image').files[0];
    if (!image) {
        alert('Product image is required');
        return;
    }

    const colors = getCheckedColors('prod-colors-checkboxes');
    if (colors.length === 0) {
        alert('Choose at least one color');
        return;
    }

    const formData = new FormData();
    formData.append('name', document.getElementById('prod-name').value.trim());
    formData.append('price', document.getElementById('prod-price').value);
    formData.append('category', document.getElementById('prod-category').value);
    formData.append('colors', colors.join(','));
    formData.append('stock_quantity', document.getElementById('prod-stock').value);
    formData.append('discount_badge', document.getElementById('prod-discount').value.trim());
    if (document.getElementById('prod-old-price').value) {
        formData.append('old_price', document.getElementById('prod-old-price').value);
    }
    formData.append('image', image);

    const result = await apiCall('/products', 'POST', formData, true);
    if (result) {
        alert('Product added successfully');
        event.target.reset();
        renderColorCheckboxes('prod-colors-checkboxes');
        await loadProducts();
        await loadDashboardStats();
    }
}

async function submitEditProduct(event) {
    event.preventDefault();

    const productId = Number(document.getElementById('edit-product-id').value);
    const payload = {};

    const name = document.getElementById('edit-prod-name').value.trim();
    const price = document.getElementById('edit-prod-price').value;
    const oldPrice = document.getElementById('edit-prod-old-price').value;
    const category = document.getElementById('edit-prod-category').value;
    const colors = getCheckedColors('edit-prod-colors-checkboxes');
    const stockQuantity = document.getElementById('edit-prod-stock').value;
    const discountBadge = document.getElementById('edit-prod-discount').value.trim();

    if (name) payload.name = name;
    if (price !== '') payload.price = Number(price);
    if (oldPrice !== '') payload.old_price = Number(oldPrice);
    if (category) payload.category = category;
    if (colors.length > 0) payload.colors = colors.join(',');
    if (stockQuantity !== '') payload.stock_quantity = Number(stockQuantity);
    payload.discount_badge = discountBadge || null;

    const result = await apiCall(`/products/${productId}`, 'PUT', payload);
    if (result) {
        alert('Product updated successfully');
        document.getElementById('editProductContainer').style.display = 'none';
        event.target.reset();
        await loadProducts();
        await loadDashboardStats();
    }
}

function initProductFilters() {
    const searchForm = document.getElementById('admin-product-search-form');
    const resetButton = document.getElementById('admin-product-reset');
    const sortSelect = document.getElementById('admin-product-sort');
    const categorySelect = document.getElementById('admin-product-category');

    if (searchForm) {
        searchForm.addEventListener('submit', (event) => {
            event.preventDefault();
            productState.search = document.getElementById('admin-product-search').value.trim();
            productState.category = categorySelect?.value || '';
            const [sortBy, sortDir] = (sortSelect?.value || 'id-desc').split('-');
            productState.sortBy = sortBy;
            productState.sortDir = sortDir || 'desc';
            productState.page = 1;
            loadProducts();
        });
    }

    if (categorySelect) {
        categorySelect.addEventListener('change', () => searchForm?.requestSubmit());
    }

    if (sortSelect) {
        sortSelect.addEventListener('change', () => searchForm?.requestSubmit());
    }

    if (resetButton) {
        resetButton.addEventListener('click', () => {
            document.getElementById('admin-product-search').value = '';
            if (categorySelect) categorySelect.value = '';
            if (sortSelect) sortSelect.value = 'id-desc';
            productState = {
                page: 1,
                perPage: 10,
                search: '',
                category: '',
                sortBy: 'id',
                sortDir: 'desc',
            };
            loadProducts();
        });
    }
}

function paymentStatusBadge(order) {
    if (!order.payment_status) {
        return '<span style="color:#64748b; font-size:13px;">لا يوجد دفع بعد</span>';
    }

    const labels = {
        pending: 'قيد الانتظار',
        completed: 'مكتمل',
        failed: 'فشل',
        cancelled: 'ملغي',
        manual_refund_required: 'يحتاج استرداد يدوي!',
    };
    const classes = {
        pending: 'status-pending',
        completed: 'status-completed',
        failed: 'status-cancelled',
        cancelled: 'status-cancelled',
        manual_refund_required: 'status-alert',
    };
    const label = labels[order.payment_status] || order.payment_status;
    const cls = classes[order.payment_status] || 'status-pending';

    let html = `<span class="status-badge ${cls}">${escapeHtml(label)}</span>`;
    if (order.payment_method) {
        html += `<div style="font-size:11px; color:#64748b; margin-top:3px;">${escapeHtml(order.payment_method)}</div>`;
    }
    if (order.payment_status === 'manual_refund_required') {
        html += `<button type="button" class="table-action-btn mark-refunded-btn" data-payment-id="${order.payment_id}" style="margin-top:5px; display:block; width:100%;">تم الاسترداد ✓</button>`;
    }
    return html;
}

// Digits only, with Egypt's country code, for a wa.me link. Returns '' if
// the number can't be turned into something dialable.
function whatsappDigits(phone) {
    let digits = String(phone || '').replace(/\D/g, '');
    if (digits.startsWith('00')) digits = digits.slice(2);
    if (digits.startsWith('0')) digits = '2' + digits;
    return digits.length >= 10 ? digits : '';
}

function deliveryCellHtml(shipping) {
    if (!shipping) {
        return '<span style="color:#94a3b8;">—</span>';
    }
    const wa = whatsappDigits(shipping.phone_number);
    return `
        <div><strong>${escapeHtml(shipping.city)}</strong></div>
        <div style="font-size:12px; color:#cbd5e1; max-width:220px;">${escapeHtml(shipping.full_address)}</div>
        <div style="margin-top:4px; direction:ltr; text-align:right;">
            <a href="tel:${escapeHtml(shipping.phone_number)}" style="color:#F97316;">${escapeHtml(shipping.phone_number)}</a>
            ${wa ? `<a href="https://wa.me/${escapeHtml(wa)}" target="_blank" rel="noopener" style="color:#22c55e; margin-inline-start:8px;">WhatsApp</a>` : ''}
        </div>
    `;
}

function totalCellHtml(order) {
    const total = Number(order.total_amount || 0).toFixed(2);
    let html = `<strong>${escapeHtml(total)} EGP</strong>`;
    if (Number(order.discount_amount) > 0) {
        html += `<div style="font-size:11px; color:#22c55e;">خصم ${escapeHtml(Number(order.discount_amount).toFixed(2))}${order.coupon_code ? ` (${escapeHtml(order.coupon_code)})` : ''}</div>`;
    }
    return html;
}

function renderOrderRows(orders) {
    const tbody = document.getElementById('orders-tbody');
    if (!tbody) {
        return;
    }

    if (orders.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" style="text-align:center; color:#94a3b8;">No orders found.</td></tr>';
        return;
    }

    tbody.innerHTML = orders.map((order) => {
        const details = Array.isArray(order.items) ? order.items.map((item) => `
            <div><strong>Product:</strong> ${escapeHtml(item.product_name || ('#' + item.product_id))} | <strong>Qty:</strong> ${escapeHtml(item.quantity)}${item.item_price != null ? ` | <strong>Unit:</strong> ${escapeHtml(Number(item.item_price).toFixed(2))} EGP` : ''}</div>
            ${item.lens_type ? `
                <div class="lens-details-box">
                    <strong>Lens:</strong> ${escapeHtml(item.lens_type)}<br>
                    <strong>Right:</strong> SPH ${escapeHtml(item.sph_r)}, CYL ${escapeHtml(item.cyl_r)}, AXIS ${escapeHtml(item.axis_r)}<br>
                    <strong>Left:</strong> SPH ${escapeHtml(item.sph_l)}, CYL ${escapeHtml(item.cyl_l)}, AXIS ${escapeHtml(item.axis_l)}
                </div>
            ` : ''}
        `).join('') : '';

        return `
            <tr>
                <td>#${escapeHtml(order.order_id)}</td>
                <td>${escapeHtml(order.username || `User ${order.user_id || ''}`)}${order.customer_email ? `<div style="font-size:11px; color:#64748b;">${escapeHtml(order.customer_email)}</div>` : ''}</td>
                <td>${deliveryCellHtml(order.shipping)}</td>
                <td>${totalCellHtml(order)}</td>
                <td>${new Date(order.date).toLocaleDateString('ar-EG')}</td>
                <td>
                    <select class="order-status-select" data-order-id="${order.order_id}">
                        <option value="pending" ${order.status === 'pending' ? 'selected' : ''}>pending</option>
                        <option value="processing" ${order.status === 'processing' ? 'selected' : ''}>processing</option>
                        <option value="shipped" ${order.status === 'shipped' ? 'selected' : ''}>shipped</option>
                        <option value="delivered" ${order.status === 'delivered' ? 'selected' : ''}>delivered</option>
                        <option value="cancelled" ${order.status === 'cancelled' ? 'selected' : ''}>cancelled</option>
                    </select>
                    <button type="button" class="table-action-btn order-update-btn" data-order-id="${order.order_id}">Update</button>
                </td>
                <td>${paymentStatusBadge(order)}</td>
                <td>${details}</td>
                <td>${order.prescription_url ? `<button type="button" class="table-action-btn view-prescription-btn" data-url="${escapeHtml(order.prescription_url)}">View</button>` : 'No file'}</td>
            </tr>
        `;
    }).join('');

    tbody.querySelectorAll('.order-update-btn').forEach((button) => {
        button.addEventListener('click', async () => {
            const orderId = Number(button.dataset.orderId);
            const select = tbody.querySelector(`.order-status-select[data-order-id="${orderId}"]`);
            if (!select) {
                return;
            }

            const result = await apiCall(`/orders/${orderId}`, 'PUT', { status: select.value });
            if (result) {
                alert('Order updated successfully');
                await loadOrders();
            }
        });
    });

    tbody.querySelectorAll('.view-prescription-btn').forEach((button) => {
        button.addEventListener('click', () => viewPrescriptionFile(button.dataset.url));
    });

    tbody.querySelectorAll('.mark-refunded-btn').forEach((button) => {
        button.addEventListener('click', async () => {
            if (!window.confirm('تأكيد إنك استرجعت الفلوس فعليًا للعميل خارج النظام (Paymob أو تحويل بنكي)؟ الحالة هتتحول لـ"ملغي".')) {
                return;
            }
            const paymentId = button.dataset.paymentId;
            const result = await apiCall(`/payments/${paymentId}`, 'PUT', { payment_status: 'cancelled' });
            if (result) {
                await loadOrders();
            } else {
                alert('تعذر تحديث حالة الدفع.');
            }
        });
    });
}

async function viewPrescriptionFile(url) {
    // FIX: this used to be a plain <a href="..." target="_blank"> link.
    // The prescription download endpoint requires a JWT Bearer token, but
    // a normal browser navigation (clicking a link, opening a new tab)
    // never sends custom headers - only fetch()/XHR calls do. So the
    // request arrived with no Authorization header, got rejected, and the
    // admin just saw a blank/error tab instead of the prescription. This
    // fetches it properly (with the auth header, like every other API
    // call here) and opens the result as a blob URL instead.
    // Open the tab right now, inside the click, and fill it in afterwards:
    // browsers (Safari, and Chrome on phones) block window.open() calls that
    // happen after an await, which made the file "not open" for the admin.
    const viewerTab = window.open('', '_blank');
    const closeViewer = () => { if (viewerTab) viewerTab.close(); };

    try {
        const response = await fetch(url, {
            headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
        });

        if (!response.ok) {
            closeViewer();
            if (response.status === 401) {
                alert('انتهت الجلسة، سجّل الدخول تاني وجرب مرة أخرى.');
            } else if (response.status === 404) {
                alert('ملف الكشف غير موجود على السيرفر (ممكن يكون اتحذف أو اتنقل).');
            } else {
                alert('تعذر تحميل ملف الكشف (كود الخطأ: ' + response.status + ').');
            }
            return;
        }

        const blob = await response.blob();
        const blobUrl = URL.createObjectURL(blob);
        if (viewerTab) {
            viewerTab.location.href = blobUrl;
        } else {
            window.open(blobUrl, '_blank');
        }
        // Revoke after a delay long enough for the new tab to load it -
        // revoking immediately can race with the tab opening the URL.
        setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
    } catch (err) {
        closeViewer();
        alert('تعذر تحميل ملف الكشف. تأكد من اتصالك بالسيرفر وحاول مرة أخرى.');
    }
}

async function loadOrders() {
    setLoadingRows('orders-tbody', 'Loading orders...', 9);
    const orders = await apiCall('/admin/orders');
    renderOrderRows(Array.isArray(orders) ? orders : []);
}

function renderCustomerRows(users) {
    const tbody = document.getElementById('customers-tbody');
    if (!tbody) {
        return;
    }

    if (users.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:#94a3b8;">No customers found.</td></tr>';
        return;
    }

    tbody.innerHTML = users.map((user) => `
        <tr>
            <td>${user.id}</td>
            <td>${escapeHtml(user.username)}</td>
            <td>${escapeHtml(user.email)}</td>
            <td>${user.is_admin ? '<span class="status-badge status-completed">Admin</span>' : '<span class="status-badge status-pending">Customer</span>'}</td>
            <td>${user.date_of_birth ? `${new Date(user.date_of_birth).toLocaleDateString('ar-EG')} (${user.age})` : '-'}</td>
            <td>${user.created_at ? new Date(user.created_at).toLocaleDateString('ar-EG') : '-'}</td>
        </tr>
    `).join('');
}

async function loadCustomers() {
    setLoadingRows('customers-tbody', 'Loading customers...', 6);
    const users = await apiCall('/admin/users');
    userCache = Array.isArray(users) ? users : [];
    renderCustomerRows(userCache);
}

function renderAdminManagementRows(users) {
    const tbody = document.getElementById('admin-management-tbody');
    if (!tbody) return;

    if (users.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; color:#94a3b8;">No users found.</td></tr>';
        return;
    }

    tbody.innerHTML = users.map((user) => `
        <tr>
            <td>${user.id}</td>
            <td>${escapeHtml(user.username)}</td>
            <td>${escapeHtml(user.email)}</td>
            <td>${user.is_admin ? '<span class="status-badge status-completed">Admin</span>' : '<span class="status-badge status-pending">Customer</span>'}</td>
            <td>
                ${user.is_admin
                    ? `<button type="button" class="table-action-btn" data-demote="${user.id}">إزالة صلاحية المشرف</button>`
                    : `<button type="button" class="table-action-btn" data-promote="${user.id}">ترقية لمشرف</button>`
                }
            </td>
        </tr>
    `).join('');

    tbody.querySelectorAll('[data-promote]').forEach((btn) => {
        btn.addEventListener('click', () => setUserAdminStatus(Number(btn.dataset.promote), true));
    });
    tbody.querySelectorAll('[data-demote]').forEach((btn) => {
        btn.addEventListener('click', () => setUserAdminStatus(Number(btn.dataset.demote), false));
    });
}

async function setUserAdminStatus(userId, makeAdmin) {
    const actionLabel = makeAdmin ? 'ترقية هذا المستخدم ليصبح مشرفًا؟' : 'إزالة صلاحية المشرف من هذا المستخدم؟';
    if (!window.confirm(actionLabel)) {
        return;
    }

    const result = await apiCall(`/admin/users/${userId}/role`, 'PUT', { is_admin: makeAdmin });
    if (result) {
        alert('تم تحديث الصلاحية بنجاح');
        await Promise.all([loadCustomers(), loadAdminManagement()]);
    } else {
        alert('تعذر تحديث الصلاحية - راجع القيود الموضحة أعلى الجدول (لا يمكنك إزالة صلاحيتك الخاصة أو صلاحية آخر مشرف).');
    }
}

async function loadAdminManagement() {
    setLoadingRows('admin-management-tbody', 'Loading...', 5);
    const users = await apiCall('/admin/users');
    renderAdminManagementRows(Array.isArray(users) ? users : []);
}

function initCreateAdminForm() {
    const form = document.getElementById('createAdminForm');
    if (!form) return;

    form.addEventListener('submit', async (event) => {
        event.preventDefault();

        const payload = {
            username: document.getElementById('new-admin-username').value.trim(),
            email: document.getElementById('new-admin-email').value.trim(),
            password: document.getElementById('new-admin-password').value,
        };

        const result = await apiCall('/admin/users', 'POST', payload);
        if (result) {
            alert(`تم إنشاء حساب المشرف "${result.username}" بنجاح`);
            form.reset();
            await Promise.all([loadCustomers(), loadAdminManagement()]);
        } else {
            alert('تعذر إنشاء الحساب - تأكد إن اسم المستخدم والبريد الإلكتروني غير مستخدمين من قبل.');
        }
    });
}

function initLogout() {
    const logoutBtn = document.getElementById('logoutBtn');
    if (!logoutBtn) {
        return;
    }

    logoutBtn.addEventListener('click', () => {
        localStorage.removeItem('authToken');
        authToken = null;
        window.location.href = 'admin_login.html';
    });
}

async function ensureAdminAccess() {
    if (!authToken) {
        window.location.href = 'admin_login.html';
        return false;
    }

    const stats = await apiCall('/admin/dashboard-stats');
    if (!stats) {
        return false;
    }

    updateStats(stats);
    renderChart(stats.chart_labels || [], stats.chart_data || []);
    return true;
}

function initCreateForm() {
    const form = document.getElementById('addProductForm');
    if (form) {
        form.addEventListener('submit', submitCreateProduct);
    }

    const editForm = document.getElementById('editProductForm');
    if (editForm) {
        editForm.addEventListener('submit', submitEditProduct);
    }

    const cancelButton = document.getElementById('cancelEditBtn');
    if (cancelButton) {
        cancelButton.addEventListener('click', () => {
            const container = document.getElementById('editProductContainer');
            if (container) {
                container.style.display = 'none';
            }
            editForm?.reset();
        });
    }
}

function wireCouponApplyToConditionals(prefix) {
    const applyToSelect = document.getElementById(`${prefix}coupon-apply-to`);
    const productsSelect = document.getElementById(`${prefix}coupon-apply-products`);
    const categorySelect = document.getElementById(`${prefix}coupon-apply-category`);
    if (!applyToSelect) return;

    const update = () => {
        productsSelect.style.display = applyToSelect.value === 'specific_products' ? 'block' : 'none';
        categorySelect.style.display = applyToSelect.value === 'category' ? 'block' : 'none';
    };

    applyToSelect.addEventListener('change', update);
    update();
}

async function loadAllProductsForPickers() {
    const data = await apiCall('/products?page=1&per_page=100&sort_by=name&sort_dir=asc');
    allProductsForPickers = data && Array.isArray(data.items) ? data.items : [];
    populateCouponProductSelect(document.getElementById('coupon-apply-products'));
    populateCouponProductSelect(document.getElementById('edit-coupon-apply-products'));
    populateDealProductSelect();
}

function populateCouponProductSelect(selectEl) {
    if (!selectEl) return;
    selectEl.innerHTML = allProductsForPickers
        .map((p) => `<option value="${p.id}">${escapeHtml(p.name)} (${formatPrice(p.price)} EGP)</option>`)
        .join('');
}

function getCouponStatusInfo(coupon) {
    if (!coupon.is_active) {
        return { label: 'معطل', cls: 'status-cancelled' };
    }
    const now = new Date();
    if (coupon.start_date && new Date(coupon.start_date) > now) {
        return { label: 'لسه ما بدأش', cls: 'status-pending' };
    }
    if (coupon.end_date && new Date(coupon.end_date) < now) {
        return { label: 'منتهي', cls: 'status-cancelled' };
    }
    if (coupon.max_total_uses !== null && coupon.total_uses >= coupon.max_total_uses) {
        return { label: 'اتستهلك بالكامل', cls: 'status-cancelled' };
    }
    return { label: 'فعال', cls: 'status-completed' };
}

function initCreateCouponForm() {
    const form = document.getElementById('createCouponForm');
    if (!form) return;

    wireCouponApplyToConditionals('');

    form.addEventListener('submit', async (event) => {
        event.preventDefault();

        const applyTo = document.getElementById('coupon-apply-to').value;
        let applyToValue = null;
        if (applyTo === 'specific_products') {
            const selected = Array.from(document.getElementById('coupon-apply-products').selectedOptions).map((o) => o.value);
            if (selected.length === 0) {
                alert('اختار منتج واحد على الأقل');
                return;
            }
            applyToValue = selected.join(',');
        } else if (applyTo === 'category') {
            applyToValue = document.getElementById('coupon-apply-category').value;
        }

        const payload = {
            code: document.getElementById('coupon-code').value.trim(),
            discount_type: document.getElementById('coupon-discount-type').value,
            discount_value: Number(document.getElementById('coupon-discount-value').value),
            start_date: document.getElementById('coupon-start-date').value || null,
            end_date: document.getElementById('coupon-end-date').value || null,
            is_active: document.getElementById('coupon-is-active').checked,
            max_total_uses: document.getElementById('coupon-max-total-uses').value ? Number(document.getElementById('coupon-max-total-uses').value) : null,
            max_uses_per_customer: document.getElementById('coupon-max-per-customer').value ? Number(document.getElementById('coupon-max-per-customer').value) : null,
            apply_to: applyTo,
            apply_to_value: applyToValue,
            min_order_amount: document.getElementById('coupon-min-order').value ? Number(document.getElementById('coupon-min-order').value) : null,
            max_discount_amount: document.getElementById('coupon-max-discount').value ? Number(document.getElementById('coupon-max-discount').value) : null,
        };

        const result = await apiCall('/admin/coupons', 'POST', payload);
        if (result) {
            alert(`تم إنشاء كود "${result.code}" بنجاح`);
            form.reset();
            document.getElementById('coupon-is-active').checked = true;
            await loadCoupons();
        } else {
            alert('تعذر إنشاء الكود - تأكد إن الكود مش مستخدم من قبل والبيانات صحيحة.');
        }
    });
}

function renderCouponRows(coupons) {
    const tbody = document.getElementById('coupons-tbody');
    if (!tbody) return;

    if (coupons.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:#94a3b8;">لا توجد أكواد خصم بعد.</td></tr>';
        return;
    }

    const applyToLabels = {
        all: 'كل المنتجات', cart: 'السلة بالكامل', specific_products: 'منتجات محددة',
        category: 'قسم معين', lenses_only: 'العدسات فقط', frames_only: 'الشنابر فقط',
    };

    tbody.innerHTML = coupons.map((c) => {
        const status = getCouponStatusInfo(c);
        const valueLabel = c.discount_type === 'percentage' ? `${c.discount_value}%` : `${formatPrice(c.discount_value)} EGP`;
        const usageLabel = `${c.total_uses} / ${c.max_total_uses ?? '∞'}`;
        return `
        <tr>
            <td><strong>${escapeHtml(c.code)}</strong></td>
            <td>${c.discount_type === 'percentage' ? 'نسبة %' : 'مبلغ ثابت'}</td>
            <td>${valueLabel}</td>
            <td><span class="status-badge ${status.cls}">${status.label}</span></td>
            <td>${usageLabel}</td>
            <td>${applyToLabels[c.apply_to] || c.apply_to}</td>
            <td>
                <button type="button" class="table-action-btn edit-coupon-btn" data-id="${c.id}">Edit</button>
                <button type="button" class="table-action-btn delete-coupon-btn" data-id="${c.id}">Delete</button>
            </td>
        </tr>
    `;
    }).join('');

    tbody.querySelectorAll('.edit-coupon-btn').forEach((btn) => {
        btn.addEventListener('click', () => {
            const coupon = couponCache.find((c) => c.id === Number(btn.dataset.id));
            if (coupon) openEditCoupon(coupon);
        });
    });

    tbody.querySelectorAll('.delete-coupon-btn').forEach((btn) => {
        btn.addEventListener('click', async () => {
            if (!window.confirm('حذف كود الخصم ده؟ (لو اتستخدم قبل كده في أي طلب، مش هينحذف - هتحتاج تعطله بدل ما تحذفه)')) return;
            const result = await apiCall(`/admin/coupons/${btn.dataset.id}`, 'DELETE');
            if (result !== null) {
                await loadCoupons();
            } else {
                alert('تعذر حذف الكود - على الأرجح استُخدم في طلبات سابقة. جرب تعطيله بدل الحذف.');
            }
        });
    });
}

async function loadCoupons() {
    setLoadingRows('coupons-tbody', 'Loading...', 7);
    const coupons = await apiCall('/admin/coupons');
    couponCache = Array.isArray(coupons) ? coupons : [];
    renderCouponRows(couponCache);
}

function openEditCoupon(coupon) {
    const container = document.getElementById('editCouponContainer');
    if (!container) return;

    document.getElementById('edit-coupon-id').value = coupon.id;
    document.getElementById('edit-coupon-code').value = coupon.code;
    document.getElementById('edit-coupon-discount-type').value = coupon.discount_type;
    document.getElementById('edit-coupon-discount-value').value = coupon.discount_value;
    document.getElementById('edit-coupon-max-discount').value = coupon.max_discount_amount ?? '';
    document.getElementById('edit-coupon-start-date').value = coupon.start_date ? coupon.start_date.slice(0, 10) : '';
    document.getElementById('edit-coupon-end-date').value = coupon.end_date ? coupon.end_date.slice(0, 10) : '';
    document.getElementById('edit-coupon-is-active').checked = coupon.is_active;
    document.getElementById('edit-coupon-max-total-uses').value = coupon.max_total_uses ?? '';
    document.getElementById('edit-coupon-max-per-customer').value = coupon.max_uses_per_customer ?? '';
    document.getElementById('edit-coupon-apply-to').value = coupon.apply_to;
    document.getElementById('edit-coupon-min-order').value = coupon.min_order_amount ?? '';

    const productsSelect = document.getElementById('edit-coupon-apply-products');
    const categorySelect = document.getElementById('edit-coupon-apply-category');
    if (coupon.apply_to === 'specific_products' && coupon.apply_to_value) {
        const ids = coupon.apply_to_value.split(',');
        Array.from(productsSelect.options).forEach((opt) => {
            opt.selected = ids.includes(opt.value);
        });
    } else if (coupon.apply_to === 'category' && coupon.apply_to_value) {
        categorySelect.value = coupon.apply_to_value;
    }

    productsSelect.style.display = coupon.apply_to === 'specific_products' ? 'block' : 'none';
    categorySelect.style.display = coupon.apply_to === 'category' ? 'block' : 'none';

    container.style.display = 'block';
    container.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function initEditCouponForm() {
    const form = document.getElementById('editCouponForm');
    if (!form) return;

    wireCouponApplyToConditionals('edit-');

    form.addEventListener('submit', async (event) => {
        event.preventDefault();

        const couponId = Number(document.getElementById('edit-coupon-id').value);
        const applyTo = document.getElementById('edit-coupon-apply-to').value;
        let applyToValue = null;
        if (applyTo === 'specific_products') {
            const selected = Array.from(document.getElementById('edit-coupon-apply-products').selectedOptions).map((o) => o.value);
            if (selected.length === 0) {
                alert('اختار منتج واحد على الأقل');
                return;
            }
            applyToValue = selected.join(',');
        } else if (applyTo === 'category') {
            applyToValue = document.getElementById('edit-coupon-apply-category').value;
        }

        const payload = {
            code: document.getElementById('edit-coupon-code').value.trim(),
            discount_type: document.getElementById('edit-coupon-discount-type').value,
            discount_value: Number(document.getElementById('edit-coupon-discount-value').value),
            start_date: document.getElementById('edit-coupon-start-date').value || null,
            end_date: document.getElementById('edit-coupon-end-date').value || null,
            is_active: document.getElementById('edit-coupon-is-active').checked,
            max_total_uses: document.getElementById('edit-coupon-max-total-uses').value ? Number(document.getElementById('edit-coupon-max-total-uses').value) : null,
            max_uses_per_customer: document.getElementById('edit-coupon-max-per-customer').value ? Number(document.getElementById('edit-coupon-max-per-customer').value) : null,
            apply_to: applyTo,
            apply_to_value: applyToValue,
            min_order_amount: document.getElementById('edit-coupon-min-order').value ? Number(document.getElementById('edit-coupon-min-order').value) : null,
            max_discount_amount: document.getElementById('edit-coupon-max-discount').value ? Number(document.getElementById('edit-coupon-max-discount').value) : null,
        };

        const result = await apiCall(`/admin/coupons/${couponId}`, 'PUT', payload);
        if (result) {
            alert('تم تحديث كود الخصم بنجاح');
            document.getElementById('editCouponContainer').style.display = 'none';
            await loadCoupons();
        } else {
            alert('تعذر تحديث الكود.');
        }
    });
}

function populateDealProductSelect() {
    const select = document.getElementById('deal-product-select');
    if (!select) return;

    const dealtProductIds = new Set(dealCache.map((d) => d.product?.id));
    const available = allProductsForPickers.filter((p) => !dealtProductIds.has(p.id));

    if (available.length === 0) {
        select.innerHTML = '<option value="">كل المنتجات مضافة بالفعل</option>';
        return;
    }

    select.innerHTML = available
        .map((p) => `<option value="${p.id}">${escapeHtml(p.name)} (${formatPrice(p.price)} EGP)</option>`)
        .join('');
}

function initDealsForm() {
    const btn = document.getElementById('addDealBtn');
    if (!btn) return;

    btn.addEventListener('click', async () => {
        const select = document.getElementById('deal-product-select');
        const productId = select.value;
        if (!productId) {
            alert('اختار منتج الأول');
            return;
        }

        const result = await apiCall('/admin/deals', 'POST', { product_id: Number(productId) });
        if (result) {
            await loadDeals();
        } else {
            alert('تعذرت إضافة المنتج لعروض اليوم.');
        }
    });
}

function renderDealRows(deals) {
    const tbody = document.getElementById('deals-tbody');
    if (!tbody) return;

    if (deals.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; color:#94a3b8;">مفيش عروض مضافة دلوقتي - أضف منتج من الفورم فوق.</td></tr>';
        return;
    }

    tbody.innerHTML = deals.map((d, index) => {
        const p = d.product;
        if (!p) return '';
        return `
        <tr>
            <td>${index + 1}</td>
            <td><img src="${escapeHtml(assetUrl(p.image_file))}" style="width:50px; height:50px; object-fit:cover; border-radius:6px;"></td>
            <td>${escapeHtml(p.name)}</td>
            <td>${formatPrice(p.price)} EGP${p.discount_badge ? ` <span class="status-badge status-completed">${escapeHtml(p.discount_badge)}</span>` : ''}</td>
            <td>
                <button type="button" class="table-action-btn deal-move-btn" data-id="${d.id}" data-dir="up" ${index === 0 ? 'disabled' : ''}>&uarr;</button>
                <button type="button" class="table-action-btn deal-move-btn" data-id="${d.id}" data-dir="down" ${index === deals.length - 1 ? 'disabled' : ''}>&darr;</button>
                <button type="button" class="table-action-btn delete-product-btn deal-remove-btn" data-id="${d.id}">Remove</button>
            </td>
        </tr>
    `;
    }).join('');

    tbody.querySelectorAll('.deal-move-btn').forEach((btn) => {
        btn.addEventListener('click', () => moveDeal(Number(btn.dataset.id), btn.dataset.dir));
    });

    tbody.querySelectorAll('.deal-remove-btn').forEach((btn) => {
        btn.addEventListener('click', async () => {
            if (!window.confirm('إزالة المنتج ده من عروض اليوم؟')) return;
            const result = await apiCall(`/admin/deals/${btn.dataset.id}`, 'DELETE');
            if (result !== null) {
                await loadDeals();
            } else {
                alert('تعذرت الإزالة.');
            }
        });
    });
}

async function moveDeal(dealId, direction) {
    const index = dealCache.findIndex((d) => d.id === dealId);
    if (index === -1) return;

    const swapWith = direction === 'up' ? index - 1 : index + 1;
    if (swapWith < 0 || swapWith >= dealCache.length) return;

    const reordered = [...dealCache];
    [reordered[index], reordered[swapWith]] = [reordered[swapWith], reordered[index]];

    const result = await apiCall('/admin/deals/reorder', 'PUT', { deal_ids: reordered.map((d) => d.id) });
    if (result !== null) {
        await loadDeals();
    } else {
        alert('تعذر تحديث الترتيب.');
    }
}

async function loadDeals() {
    setLoadingRows('deals-tbody', 'Loading...', 5);
    const deals = await apiCall('/admin/deals');
    dealCache = Array.isArray(deals) ? deals : [];
    renderDealRows(dealCache);
    populateDealProductSelect();
}

let adminCountdownInterval = null;

function renderDealsCountdownStatus(endsAtIso) {
    const status = document.getElementById('deals-countdown-status');
    const cancelBtn = document.getElementById('deals-countdown-cancel-btn');
    if (!status) return;

    if (adminCountdownInterval) {
        clearInterval(adminCountdownInterval);
        adminCountdownInterval = null;
    }

    if (!endsAtIso) {
        status.textContent = 'مفيش عداد شغال دلوقتي - العروض هتفضل ظاهرة على طول.';
        if (cancelBtn) cancelBtn.style.display = 'none';
        return;
    }

    if (cancelBtn) cancelBtn.style.display = 'inline-block';

    const endsAt = new Date(endsAtIso).getTime();
    const tick = () => {
        const remaining = endsAt - Date.now();
        if (remaining <= 0) {
            status.textContent = 'العداد خلص - العروض مبقاش ظاهرة في الصفحة الرئيسية دلوقتي.';
            clearInterval(adminCountdownInterval);
            return;
        }
        const totalSeconds = Math.floor(remaining / 1000);
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;
        const pad = (n) => String(n).padStart(2, '0');
        status.textContent = `العداد شغال - هينتهي بعد ${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
    };

    tick();
    adminCountdownInterval = setInterval(tick, 1000);
}

async function loadDealsCountdown() {
    const result = await apiCall('/admin/deals/countdown');
    renderDealsCountdownStatus(result ? result.ends_at : null);
}

function initDealsCountdownControls() {
    document.querySelectorAll('.deals-countdown-preset').forEach((btn) => {
        btn.addEventListener('click', async () => {
            const result = await apiCall('/admin/deals/countdown', 'PUT', {
                duration_minutes: Number(btn.dataset.minutes),
            });
            if (result) {
                renderDealsCountdownStatus(result.ends_at);
            } else {
                alert('تعذر بدء العداد.');
            }
        });
    });

    document.getElementById('deals-countdown-set-btn')?.addEventListener('click', async () => {
        const input = document.getElementById('deals-countdown-custom');
        if (!input.value) {
            alert('اختار تاريخ ووقت الأول');
            return;
        }
        const result = await apiCall('/admin/deals/countdown', 'PUT', { ends_at: input.value });
        if (result) {
            renderDealsCountdownStatus(result.ends_at);
        } else {
            alert('تعذر بدء العداد - تأكد إن الوقت اللي اخترته لسه في المستقبل.');
        }
    });

    document.getElementById('deals-countdown-cancel-btn')?.addEventListener('click', async () => {
        if (!window.confirm('إلغاء العداد؟ العروض هتفضل ظاهرة على طول لحد ما تشغل عداد جديد أو تشيلها بنفسك.')) return;
        const result = await apiCall('/admin/deals/countdown', 'DELETE');
        if (result !== null) {
            renderDealsCountdownStatus(null);
        } else {
            alert('تعذر إلغاء العداد.');
        }
    });
}

async function initAdminPage() {
    authToken = localStorage.getItem('authToken');
    if (!(await ensureAdminAccess())) {
        return;
    }

    initLogout();
    initCreateForm();
    initProductFilters();
    initCreateAdminForm();
    initCreateCouponForm();
    initEditCouponForm();
    initDealsForm();
    initDealsCountdownControls();
    await loadAvailableColors();
    await loadAvailableCategories();

    await Promise.all([
        loadDashboardStats(),
        loadProducts(),
        loadOrders(),
        loadCustomers(),
        loadAdminManagement(),
        loadCoupons(),
        loadDeals(),
        loadDealsCountdown(),
        loadAllProductsForPickers(),
    ]);
}

document.addEventListener('DOMContentLoaded', initAdminPage);

window.switchTab = switchTab;
