"""Flask application factory.

create_app(config_class=None) matches how the rest of the project actually
calls it: debug_auth.py does `create_app(TestConfig)`, conftest.py does
`create_app()` then overrides app.config afterwards, and CONTRIBUTING.md
documents the same `config_class=None` signature. This file itself was
missing from every upload, so it's rebuilt here to match those call sites
exactly rather than inventing a different convention.
"""
import os
from sqlalchemy import text

from flask import Flask, jsonify, request
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from app.extensions import db, migrate, jwt, bcrypt, cors
from app.utils.limiter import limiter
from app.utils.exceptions import APIError
from app.utils.response import api_response

_INSECURE_DEFAULTS = {'change-me-in-production', 'change-me-jwt-secret', None, ''}
# Only these are treated as "known safe, not production" - anything else
# (including FLASK_ENV being unset entirely, which is exactly what a
# deployment that forgot to configure it would look like) is treated as
# production for the purposes of this check. This is the inverse of the
# previous logic, which only checked when FLASK_ENV == 'production'
# explicitly - a deployer who simply forgot to set it would have booted
# with an insecure default secret and no warning at all.
_SAFE_NON_PRODUCTION_ENVS = {'development', 'dev', 'testing', 'test'}


def create_app(config_class=None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class or Config)

    # SECURITY / PRODUCTION READINESS: refuse to boot with an unsafe or
    # incomplete configuration unless we have affirmative evidence this
    # isn't production (explicit FLASK_ENV, or a TestConfig-style config
    # class with TESTING=True already applied via from_object above - e.g.
    # debug_auth.py's TestConfig). Fails closed: an unset or unrecognized
    # FLASK_ENV is treated as production. All problems are collected and
    # reported together rather than one at a time, so fixing this doesn't
    # require multiple fail/restart cycles to discover each issue in turn.
    flask_env = (os.environ.get('FLASK_ENV') or '').strip().lower()
    is_known_safe = flask_env in _SAFE_NON_PRODUCTION_ENVS or app.config.get('TESTING')
    if not is_known_safe:
        problems = []

        for secret_name in ('SECRET_KEY', 'JWT_SECRET_KEY'):
            secret_value = app.config.get(secret_name)
            if (
                secret_value in _INSECURE_DEFAULTS
                or not isinstance(secret_value, str)
                or secret_value.lower().startswith('change-me')
                or len(secret_value) < 32
            ):
                problems.append(
                    f'{secret_name} is missing, a placeholder (starts with "change-me") or shorter '
                    f'than 32 characters - generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
                )
        if app.config.get('SECRET_KEY') == app.config.get('JWT_SECRET_KEY'):
            problems.append('SECRET_KEY and JWT_SECRET_KEY must be different values')

        db_uri = app.config.get('SQLALCHEMY_DATABASE_URI') or ''
        if db_uri.startswith('sqlite:'):
            problems.append(
                'SQLALCHEMY_DATABASE_URI is SQLite - production requires PostgreSQL (set DATABASE_URL)'
            )

        cors_origins = app.config.get('CORS_ORIGINS') or []
        if '*' in cors_origins or cors_origins == ['http://localhost:5000']:
            problems.append(
                'CORS_ORIGINS is a wildcard or still the localhost default - set it to your real domain(s)'
            )

        site_base_url = app.config.get('SITE_BASE_URL') or ''
        if site_base_url.startswith('http://'):
            problems.append('SITE_BASE_URL uses http:// - production must use https://')

        # Read directly rather than via app.config: RATELIMIT_STORAGE_URL
        # is intentionally not duplicated into Config (see the NOTE in
        # config.py) - app/utils/limiter.py is the actual source of truth,
        # this just validates the same env var it reads.
        if os.environ.get('RATELIMIT_STORAGE_URL', 'memory://') == 'memory://':
            problems.append(
                'RATELIMIT_STORAGE_URL is in-memory - set it to a shared store (e.g. Redis) so '
                'limits are enforced consistently across multiple worker processes'
            )

        for key in ('PAYMOB_API_KEY', 'PAYMOB_INTEGRATION_ID', 'PAYMOB_IFRAME_ID', 'PAYMOB_HMAC_SECRET'):
            if not app.config.get(key):
                problems.append(f'{key} is not set')

        if problems:
            raise RuntimeError(
                'Refusing to start: this looks like a production environment (FLASK_ENV is not '
                'explicitly development/testing) but is not fully configured for it:\n'
                + '\n'.join(f'  - {p}' for p in problems)
                + '\nSet the above via environment variables, or set FLASK_ENV=development if this '
                'is intentionally a local/dev environment.'
            )

    # --- extensions ---
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    bcrypt.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config.get('CORS_ORIGINS', '*')}})
    limiter.init_app(app)

    # Off by default: ProxyFix makes the app TRUST X-Forwarded-For/-Proto/
    # -Host headers to determine the real client IP and scheme. That's
    # correct and necessary behind a real reverse proxy (nginx, a load
    # balancer, Cloudflare) - but enabling it without one actually in
    # front of the app means anyone can fake their own IP by just sending
    # that header directly, which would make rate limiting *less*
    # trustworthy, not more. Set TRUST_PROXY_HEADERS=true once a real
    # proxy is actually in place.
    if os.environ.get('TRUST_PROXY_HEADERS', '').strip().lower() in ('true', '1', 'yes'):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    @app.after_request
    def set_security_headers(response):
        # Safe on every request regardless of environment - none of these
        # change how the site actually behaves, only how browsers are
        # told to treat the response.
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        response.headers.setdefault(
            'Content-Security-Policy-Report-Only',
            "default-src 'self'; img-src 'self' data: https:; "
            "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
            "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com "
            "https://cdn.jsdelivr.net https://connect.facebook.net "
            "https://www.googletagmanager.com; connect-src 'self' https:; "
            "font-src 'self' https://cdnjs.cloudflare.com data:; "
            "frame-src 'self' https://accept.paymob.com; object-src 'none'; "
            "base-uri 'self'; form-action 'self'; report-uri /api/csp-report"
        )
        # Only added once a request has actually arrived over HTTPS - so
        # this has zero effect during local HTTP development and starts
        # protecting automatically the moment the site is truly served
        # over TLS, with no separate flag to remember to flip.
        #
        # A Content-Security-Policy is deliberately NOT set here: this
        # site loads Font Awesome and Chart.js from cdnjs.cloudflare.com
        # and cdn.jsdelivr.net, Meta Pixel from connect.facebook.net,
        # GA4 from googletagmanager.com, and redirects to Paymob for
        # payment - a CSP that misses any of these would silently break
        # them, and that can't be verified without a live browser to
        # test against. Add one deliberately, in report-only mode first,
        # once that's possible to check.
        if request.is_secure:
            response.headers.setdefault(
                'Strict-Transport-Security', 'max-age=31536000; includeSubDomains'
            )
        return response

    # --- blueprints ---
    from app.routes.auth import bp as auth_bp
    from app.routes.user import bp as user_bp
    from app.routes.products import bp as products_bp
    from app.routes.orders import bp as orders_bp
    from app.routes.payments import bp as payments_bp
    from app.routes.prescriptions import bp as prescriptions_bp
    from app.routes.shipping_addresses import bp as shipping_addresses_bp
    from app.routes.admin import bp as admin_bp
    from app.routes.docs import bp as docs_bp
    from app.routes.public_ui import bp as public_ui_bp
    from app.routes.static_ui import bp as static_ui_bp
    from app.routes.lens_catalog import bp as lens_catalog_bp
    from app.routes.coupons import bp as coupons_bp
    from app.routes.deals import bp as deals_bp

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(user_bp, url_prefix='/api/user')
    app.register_blueprint(products_bp, url_prefix='/api/products')
    app.register_blueprint(orders_bp, url_prefix='/api/orders')
    app.register_blueprint(payments_bp, url_prefix='/api/payments')
    app.register_blueprint(prescriptions_bp, url_prefix='/api/prescriptions')
    app.register_blueprint(shipping_addresses_bp, url_prefix='/api/shipping-addresses')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(docs_bp)
    app.register_blueprint(public_ui_bp)
    app.register_blueprint(static_ui_bp)
    app.register_blueprint(lens_catalog_bp, url_prefix='/api/lens-catalog')
    app.register_blueprint(coupons_bp, url_prefix='/api/coupons')
    app.register_blueprint(deals_bp, url_prefix='/api/deals')

    @app.get('/api/health')
    def health():
        """Minimal liveness/readiness endpoint for load balancers."""
        try:
            db.session.execute(text('SELECT 1'))
            return jsonify({'status': 'healthy', 'database': 'ok'}), 200
        except Exception:
            app.logger.exception('Health check database probe failed')
            return jsonify({'status': 'unhealthy', 'database': 'unavailable'}), 503

    @app.post('/api/csp-report')
    def csp_report():
        app.logger.warning('CSP report: %s', request.get_json(silent=True) or {})
        return '', 204

    # --- error handlers ---
    @app.errorhandler(APIError)
    def handle_api_error(err: APIError):
        return api_response(False, {}, err.message, err.status_code)

    @app.errorhandler(404)
    def handle_404(err):
        return jsonify({'success': False, 'data': {}, 'message': 'Not found'}), 404

    @app.errorhandler(429)
    def handle_429(err):
        # Flask-Limiter's default 429 is an HTML page; the frontend always
        # calls response.json(), so it would show a cryptic parse error
        # instead of telling the person to simply wait a minute.
        return jsonify({
            'success': False, 'data': {},
            'message': 'Too many attempts. Please wait a minute and try again.',
        }), 429

    @app.errorhandler(500)
    def handle_500(err):
        app.logger.exception('Unhandled server error')
        message = 'Internal server error'
        # LOCAL DEVELOPMENT ONLY: show the real cause in the response so a
        # non-technical developer can see what broke without digging
        # through the terminal. Never exposed in production (FLASK_ENV is
        # not development) or under tests.
        env = (os.environ.get('FLASK_ENV') or '').strip().lower()
        if env in ('development', 'dev') and not app.config.get('TESTING'):
            original = getattr(err, 'original_exception', None) or err
            message = f'Internal server error [{type(original).__name__}: {original}]'
        return jsonify({'success': False, 'data': {}, 'message': message}), 500

    return app
