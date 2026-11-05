// Lightweight toast notification + confirm modal system, styled to match
// the rest of the site. Replaces native alert()/confirm() everywhere, since
// browser-native popups look out of place next to a custom design and
// block the whole page.
//
// Usage:
//   showToast('Saved successfully', 'success');
//   showToast('Something went wrong', 'error');
//   const ok = await showConfirm('Delete this address?');

(function () {
    function ensureContainer() {
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            document.body.appendChild(container);
        }
        return container;
    }

    window.showToast = function showToast(message, type) {
        type = type || 'info';
        const container = ensureContainer();

        const toast = document.createElement('div');
        toast.className = `site-toast site-toast-${type}`;
        toast.textContent = message;
        container.appendChild(toast);

        // Force a reflow so the transition below actually animates in.
        void toast.offsetWidth;
        toast.classList.add('site-toast-visible');

        const remove = () => {
            toast.classList.remove('site-toast-visible');
            setTimeout(() => toast.remove(), 300);
        };

        toast.addEventListener('click', remove);
        setTimeout(remove, 4000);
    };

    window.showConfirm = function showConfirm(message) {
        return new Promise((resolve) => {
            const overlay = document.createElement('div');
            overlay.className = 'site-confirm-overlay';
            overlay.innerHTML = `
                <div class="site-confirm-box">
                    <p>${(message || '').replace(/[<>&]/g, (c) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;' }[c]))}</p>
                    <div class="site-confirm-actions">
                        <button type="button" class="site-confirm-cancel">Cancel</button>
                        <button type="button" class="site-confirm-ok">Confirm</button>
                    </div>
                </div>
            `;
            document.body.appendChild(overlay);

            const cleanup = (result) => {
                overlay.remove();
                resolve(result);
            };

            overlay.querySelector('.site-confirm-cancel').addEventListener('click', () => cleanup(false));
            overlay.querySelector('.site-confirm-ok').addEventListener('click', () => cleanup(true));
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) cleanup(false);
            });
        });
    };
})();
