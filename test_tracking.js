// test_tracking.js - genuinely executable tests for front j/tracking.js.
//
// Run with: node test_tracking.js
//
// This is plain Node (no npm packages, no test framework) - the project
// has no JS test runner configured, and adding one just for this would be
// a large, unnecessary dependency for a handful of pure-function checks.
// A minimal browser-like environment is stubbed below so the real
// tracking.js file can be loaded and executed as-is, not reimplemented.

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

let failures = 0;
let passed = 0;

function test(name, fn) {
    try {
        fn();
        passed++;
        console.log(`  PASS: ${name}`);
    } catch (e) {
        failures++;
        console.log(`  FAIL: ${name}: ${e.message}`);
    }
}

function makeSandbox({ search = '', cookie = '' } = {}) {
    const calls = { fbq: [], gtag: [] };
    const storage = {};

    const documentStub = {
        _cookie: cookie,
        get cookie() { return this._cookie; },
        set cookie(v) { this._cookie = v; },
        addEventListener: () => {}, // DOMContentLoaded init - not exercised in these tests
        createElement: () => ({ }),
        head: { appendChild: () => {} },
        getElementsByTagName: () => [{ parentNode: { insertBefore: () => {} } }],
    };

    const sandbox = {
        window: {},
        document: documentStub,
        location: { search },
        localStorage: {
            getItem: (k) => (k in storage ? storage[k] : null),
            setItem: (k, v) => { storage[k] = v; },
        },
        URLSearchParams,
        console,
        fbq: (...args) => calls.fbq.push(args),
        gtag: (...args) => calls.gtag.push(args),
        setTimeout,
        clearTimeout,
        Date,
    };
    sandbox.window = sandbox; // functions reference window.fbq / window.gtag too
    sandbox.global = sandbox;

    const code = fs.readFileSync(path.join(__dirname, 'front j', 'tracking.js'), 'utf8');
    vm.createContext(sandbox);
    // fbq/gtag are pre-defined above (simulating "already loaded"), so
    // loadMetaPixel()/loadGa4() short-circuit and DOMContentLoaded's
    // auto-init doesn't interfere with the specific function under test.
    vm.runInContext(code, sandbox, { filename: 'tracking.js' });

    return { sandbox, calls };
}

console.log('=== CalculatorCompleted ===');
test('fires fbq trackCustom and gtag event with lens_type + price only', () => {
    const { sandbox, calls } = makeSandbox();
    sandbox.trackCalculatorCompleted('blue-cut', 550);

    assert.strictEqual(calls.fbq.length, 1);
    assert.strictEqual(calls.fbq[0][0], 'trackCustom');
    assert.strictEqual(calls.fbq[0][1], 'CalculatorCompleted');
    assert.strictEqual(calls.fbq[0][2].lens_type, 'blue-cut');
    assert.strictEqual(calls.fbq[0][2].value, 550);

    assert.strictEqual(calls.gtag.length, 1);
    assert.strictEqual(calls.gtag[0][0], 'event');
    assert.strictEqual(calls.gtag[0][1], 'calculator_completed');
    assert.strictEqual(calls.gtag[0][2].lens_type, 'blue-cut');
    assert.strictEqual(calls.gtag[0][2].value, 550);
});

test('never includes prescription data (SPH/CYL) - only lens_type and value are ever set', () => {
    const { sandbox, calls } = makeSandbox();
    sandbox.trackCalculatorCompleted('night-drive', 1200);

    const fbqKeys = Object.keys(calls.fbq[0][2]).sort();
    const gtagKeys = Object.keys(calls.gtag[0][2]).sort();
    assert.deepStrictEqual(fbqKeys, ['currency', 'lens_type', 'value']);
    assert.deepStrictEqual(gtagKeys, ['currency', 'lens_type', 'value']);
});

console.log('=== AddToCart ===');
test('fires with product_id, product_name, price, quantity, currency', () => {
    const { sandbox, calls } = makeSandbox();
    sandbox.trackAddToCart({ id: 42, name: 'Aviator Sunglasses', price: 350, quantity: 2 });

    assert.strictEqual(calls.fbq[0][1], 'AddToCart');
    assert.strictEqual(calls.fbq[0][2].content_ids[0], '42');
    assert.strictEqual(calls.fbq[0][2].content_name, 'Aviator Sunglasses');
    assert.strictEqual(calls.fbq[0][2].value, 700); // price * quantity
    assert.strictEqual(calls.fbq[0][2].currency, 'EGP');

    assert.strictEqual(calls.gtag[0][1], 'add_to_cart');
    assert.strictEqual(calls.gtag[0][2].items[0].item_id, '42');
    assert.strictEqual(calls.gtag[0][2].items[0].quantity, 2);
});

test('defaults quantity to 1 when not provided', () => {
    const { sandbox, calls } = makeSandbox();
    sandbox.trackAddToCart({ id: 5, name: 'X', price: 100 });
    assert.strictEqual(calls.fbq[0][2].value, 100);
});

console.log('=== InitiateCheckout ===');
test('fires begin_checkout / InitiateCheckout with cart items and total', () => {
    const { sandbox, calls } = makeSandbox();
    const items = [{ id: 1, name: 'A', price: 100, quantity: 1 }, { id: 2, name: 'B', price: 200, quantity: 1 }];
    sandbox.trackInitiateCheckout(items, 300);

    assert.strictEqual(calls.fbq[0][1], 'InitiateCheckout');
    assert.strictEqual(calls.fbq[0][2].value, 300);
    assert.strictEqual(calls.fbq[0][2].num_items, 2);

    assert.strictEqual(calls.gtag[0][1], 'begin_checkout');
    assert.strictEqual(calls.gtag[0][2].items.length, 2);
});

console.log('=== ViewContent ===');
test('fires ViewContent / view_item with product data', () => {
    const { sandbox, calls } = makeSandbox();
    sandbox.trackViewContent({ id: 7, name: 'Cat Eye Frame', price: 420 });

    assert.strictEqual(calls.fbq[0][1], 'ViewContent');
    assert.strictEqual(calls.fbq[0][2].content_ids[0], '7');
    assert.strictEqual(calls.gtag[0][1], 'view_item');
});

console.log('=== CalculatorStarted ===');
test('fires a custom event with no parameters (no personal data possible)', () => {
    const { sandbox, calls } = makeSandbox();
    sandbox.trackCalculatorStarted();

    assert.strictEqual(calls.fbq[0][1], 'CalculatorStarted');
    assert.strictEqual(calls.gtag[0][1], 'calculator_started');
});

console.log('=== Purchase ===');
test('fires with event_id for Meta deduplication, transaction_id for GA4', () => {
    const { sandbox, calls } = makeSandbox();
    sandbox.trackPurchase('purchase_123', 123, 999.5);

    assert.strictEqual(calls.fbq[0][1], 'Purchase');
    assert.strictEqual(calls.fbq[0][2].value, 999.5);
    assert.strictEqual(calls.fbq[0][3].eventID, 'purchase_123');

    assert.strictEqual(calls.gtag[0][1], 'purchase');
    assert.strictEqual(calls.gtag[0][2].transaction_id, '123');
    assert.strictEqual(calls.gtag[0][2].value, 999.5);
});

console.log('=== UTM capture ===');
test('captures utm_ params from the URL and returns them', () => {
    const { sandbox } = makeSandbox({ search: '?utm_source=facebook&utm_medium=cpc&utm_campaign=summer' });
    const result = sandbox.captureAttribution();
    assert.strictEqual(result.utm_source, 'facebook');
    assert.strictEqual(result.utm_medium, 'cpc');
    assert.strictEqual(result.utm_campaign, 'summer');
});

test('a later visit with no UTM params keeps the previously stored attribution', () => {
    const { sandbox } = makeSandbox({ search: '?utm_source=instagram&utm_campaign=launch' });
    sandbox.captureAttribution();

    // Simulate a second page load, same session, no UTM on this URL.
    sandbox.location.search = '';
    const second = sandbox.captureAttribution();
    assert.strictEqual(second.utm_source, 'instagram');
    assert.strictEqual(second.utm_campaign, 'launch');
});

test('a fresh UTM-tagged visit overwrites the previously stored attribution', () => {
    const { sandbox } = makeSandbox({ search: '?utm_source=instagram' });
    sandbox.captureAttribution();

    sandbox.location.search = '?utm_source=google&utm_medium=cpc';
    const second = sandbox.captureAttribution();
    assert.strictEqual(second.utm_source, 'google');
    assert.strictEqual(second.utm_medium, 'cpc');
});

console.log('=== fbp / fbc capture ===');
test('reads fbp from the _fbp cookie', () => {
    const { sandbox } = makeSandbox({ cookie: '_fbp=fb.1.1234567890.abc123' });
    assert.strictEqual(sandbox.getFbp(), 'fb.1.1234567890.abc123');
});

test('constructs fbc from a fbclid URL param when no _fbc cookie exists yet', () => {
    const { sandbox } = makeSandbox({ search: '?fbclid=xyz789' });
    const fbc = sandbox.getFbc();
    assert.ok(fbc.startsWith('fb.1.'));
    assert.ok(fbc.endsWith('.xyz789'));
});

test('returns null for fbc when neither cookie nor fbclid is present', () => {
    const { sandbox } = makeSandbox();
    assert.strictEqual(sandbox.getFbc(), null);
});

console.log('=== No secrets in frontend (static check) ===');
test('tracking.js contains no access-token or api-secret looking values', () => {
    const source = fs.readFileSync(path.join(__dirname, 'front j', 'tracking.js'), 'utf8');
    // The only mentions of these terms should be in comments explaining
    // where the real secrets live (backend env vars) - never an assigned
    // string value that looks like an actual credential.
    const suspiciousAssignment = /(?:access_token|api_secret|ACCESS_TOKEN|API_SECRET)\s*[:=]\s*['"][^'"]+['"]/;
    assert.strictEqual(suspiciousAssignment.test(source), false);
});

test('META_PIXEL_ID and GA4_MEASUREMENT_ID are the only config constants, both empty placeholders', () => {
    const source = fs.readFileSync(path.join(__dirname, 'front j', 'tracking.js'), 'utf8');
    assert.ok(/const META_PIXEL_ID = '';/.test(source));
    assert.ok(/const GA4_MEASUREMENT_ID = '';/.test(source));
});

console.log(`\n${passed + failures} tests: ${passed} passed, ${failures} failed`);
process.exit(failures > 0 ? 1 : 0);
