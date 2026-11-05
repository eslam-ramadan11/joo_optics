// Logic for payment-result.html. Paymob redirects the customer's browser
// here after they finish (or abandon) the hosted iframe. The query string
// it appends (success=true/false, id, etc.) is NOT trusted here - it's
// only used to find which order to ask our own backend about. The webhook
// (server-to-server, HMAC-verified) is what actually updates payment
// status; this page just polls our API until it sees the result, since the
// webhook can arrive a second or two after the redirect does.

function getOrderIdFromQuery() {
    const params = new URLSearchParams(window.location.search);
    // We set merchant_order_id = our own order id when registering the
    // order with Paymob, so this is the reliable field to read back.
    const merchantOrderId = params.get('merchant_order_id');
    if (merchantOrderId) {
        return Number(merchantOrderId);
    }
    return null;
}

function renderResult(status) {
    const title = document.getElementById('payment-result-title');
    const message = document.getElementById('payment-result-message');

    if (status === 'completed') {
        title.textContent = 'تم الدفع بنجاح ✅';
        message.textContent = 'شكرًا ليك! تم تأكيد الدفع وجاري تجهيز طلبك.';
    } else if (status === 'failed') {
        title.textContent = 'فشلت عملية الدفع ❌';
        message.textContent = 'الدفع لم يكتمل. تقدر تحاول تاني من صفحة طلباتك (زر "ادفع أونلاين بالكارت")، أو تكلمنا عشان نخليها كاش عند الاستلام.';
    } else if (status === 'pending') {
        title.textContent = 'الدفع قيد التأكيد';
        message.textContent = 'لسه بنأكد الدفع، وده ممكن ياخد ثواني. راجع صفحة طلباتك بعد شوية.';
    } else {
        title.textContent = 'ما لقيناش عملية دفع';
        message.textContent = 'ما لقيناش عملية دفع مرتبطة بالطلب ده. لو اتخصم منك مبلغ، كلمنا وابعتلنا رقم الطلب.';
    }
}

async function pollPaymentStatus(orderId, attemptsLeft) {
    const result = await apiCall(`/payments/order/${orderId}/status`);
    const status = result ? result.payment_status : null;

    if (status === 'completed' || status === 'failed' || attemptsLeft <= 0) {
        renderResult(status || 'not_started');

        // Client-side Purchase companion to the server-side event the
        // backend already fired (see app/services/tracking_service.py).
        // should_fire is only true the first time this is observed for
        // this order - a refresh of this exact page gets should_fire:
        // false and correctly does not fire again.
        if (result?.tracking?.should_fire && typeof trackPurchase === 'function') {
            trackPurchase(result.tracking.event_id, orderId, result.tracking.total_amount);
        }
        return;
    }

    setTimeout(() => pollPaymentStatus(orderId, attemptsLeft - 1), 2000);
}

document.addEventListener('DOMContentLoaded', () => {
    const orderId = getOrderIdFromQuery();
    if (!authToken) {
        window.location.href = '/login.html';
        return;
    }
    if (!orderId) {
        renderResult(null);
        return;
    }
    pollPaymentStatus(orderId, 5);
});
