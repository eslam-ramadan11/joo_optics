# Paymob Integration Setup

This project uses Paymob's Accept API for card/wallet payments. Cash on
delivery still works with no setup at all - this is only needed for the
"Pay Online Now" option.

## 1. Create a Paymob account

Sign up at https://accept.paymob.com (or https://portal.paymob.com
depending on your region) as a merchant. This requires business
verification before you can accept real payments - budget a few days for
approval. You can develop/test against their test mode in the meantime.

## 2. Get your credentials

From the Paymob dashboard:

- **API Key**: Settings -> Account Info -> API Key -> `PAYMOB_API_KEY`
- **Integration ID**: Developers -> Payment Integrations -> pick (or
  create) a "Card" integration -> its ID -> `PAYMOB_INTEGRATION_ID`
- **Iframe ID**: Developers -> Iframes -> create one, attach it to the
  integration above -> its ID -> `PAYMOB_IFRAME_ID`
- **HMAC Secret**: Settings -> Account Info -> HMAC Secret ->
  `PAYMOB_HMAC_SECRET`

Put all four in your `.env` (see `_env.example`).

## 3. Configure the two callback URLs in Paymob's dashboard

Go to Developers -> Payment Integrations -> your integration, and set:

- **Transaction processed callback** (server-to-server webhook - this is
  what actually confirms payment):
  `https://YOUR_DOMAIN/api/payments/paymob/webhook`

- **Transaction response callback** (browser redirect after the customer
  finishes in the iframe - UX only, never trusted for payment state):
  `https://YOUR_DOMAIN/payment-result.html`

Both **must** be publicly reachable HTTPS URLs - Paymob cannot call
`localhost`. Use a tunnel (ngrok, Cloudflare Tunnel) while developing
locally if you need to test real webhooks before deploying.

## 4. How the flow works in this codebase

1. Customer places an order (`POST /api/orders`) and picks "Pay Online Now"
   at checkout.
2. Frontend calls `POST /api/payments/paymob/initiate` with the order id.
3. Backend (`app/services/paymob_service.py`) does the 3-step Paymob
   handshake (auth token -> register order -> payment key) and returns an
   `iframe_url`.
4. Browser is redirected to that iframe_url; customer pays there.
5. Paymob calls our webhook server-to-server with the result. The webhook
   handler verifies the HMAC signature before touching the database -
   this is the ONLY thing that marks a payment as completed.
6. Paymob also redirects the customer's browser to `payment-result.html`,
   which polls `GET /api/payments/order/<id>/status` (our own DB, updated
   by the webhook in step 5) to show a real result - it does not trust the
   redirect's own query parameters.

## 5. Testing

Paymob provides test card numbers in their docs for sandbox/test mode.
Use those against your test integration before switching
`PAYMOB_INTEGRATION_ID`/`PAYMOB_IFRAME_ID` to live ones.

## 6. If something breaks

- 502 from `/api/payments/paymob/initiate`: check the four config values
  are set and correct; check the app logs for the specific Paymob API
  error.
- Payment stuck on "pending" after the customer pays: check that the
  webhook URL in the Paymob dashboard is reachable from the internet and
  returns 200; check the app logs for "Rejected Paymob webhook with
  invalid HMAC" (means `PAYMOB_HMAC_SECRET` doesn't match what's in your
  dashboard) or "Paymob webhook for unknown order.id" (means the
  merchant_order_id round-trip didn't match - shouldn't happen unless the
  order was somehow created outside this codebase's normal flow).
