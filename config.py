import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv()


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'change-me-in-production')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', f'sqlite:///{os.path.join(basedir, "site.db")}')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES', 900))  # 15 minutes default
    JWT_REFRESH_TOKEN_EXPIRES = int(os.getenv('JWT_REFRESH_TOKEN_EXPIRES', 2592000))  # 30 days default
    # Always absolute: a relative value from .env (e.g. "uploads/prescriptions")
    # would resolve against the process's current directory in one place and
    # against app/ in send_file() in another, making downloads 404.
    PRESCRIPTIONS_UPLOAD_FOLDER = os.path.abspath(os.path.join(
        basedir, os.getenv('PRESCRIPTIONS_UPLOAD_FOLDER', os.path.join('uploads', 'prescriptions'))
    ))
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', 5 * 1024 * 1024))
    STOCK_RESERVATION_MINUTES = int(os.getenv('STOCK_RESERVATION_MINUTES', 30))
    ALLOWED_PRESCRIPTION_EXTENSIONS = set(os.getenv('ALLOWED_PRESCRIPTION_EXTENSIONS', 'png,jpg,jpeg,pdf').split(','))

    # FIX: this was documented in _env.example but never actually read into
    # Config, so setting CORS_ORIGINS in .env had no effect - CORS silently
    # fell back to '*'.
    CORS_ORIGINS = [origin.strip() for origin in os.getenv(
        'CORS_ORIGINS', 'http://localhost:5000'
    ).split(',') if origin.strip()]
    # NOTE: rate-limit storage is intentionally NOT configured here. It's
    # read directly from the RATELIMIT_STORAGE_URL env var in
    # app/utils/limiter.py (that's the single source of truth) - a second
    # copy used to live here too, but nothing ever actually read it back
    # out of app.config, so it was dead duplication rather than a real
    # second configuration path.

    # Used to build absolute URLs in sitemap.xml and Open Graph tags.
    # IMPORTANT: set this to your real domain once you have one deployed
    # (e.g. https://joooptics.com) - search engines reject/ignore a
    # sitemap whose URLs point at localhost.
    SITE_BASE_URL = os.getenv('SITE_BASE_URL', 'http://localhost:5000')

    # Paymob (Accept API) - see PAYMOB_SETUP.md for how to obtain these from
    # your Paymob dashboard. Left blank by default; PaymobError is raised
    # with a clear message if a payment is attempted before these are set.
    PAYMOB_BASE_URL = os.getenv('PAYMOB_BASE_URL', 'https://accept.paymob.com')
    PAYMOB_API_KEY = os.getenv('PAYMOB_API_KEY', '')
    PAYMOB_INTEGRATION_ID = os.getenv('PAYMOB_INTEGRATION_ID', '')
    PAYMOB_IFRAME_ID = os.getenv('PAYMOB_IFRAME_ID', '')
    PAYMOB_HMAC_SECRET = os.getenv('PAYMOB_HMAC_SECRET', '')

    # Meta (Facebook) Pixel ID is not a secret - it's meant to be visible in
    # every page's source once the Pixel snippet is added. The access
    # token IS a secret and is only ever used server-side (Conversions API).
    META_PIXEL_ID = os.getenv('META_PIXEL_ID', '')
    META_ACCESS_TOKEN = os.getenv('META_ACCESS_TOKEN', '')
    # Optional: only set while testing in Meta's Test Events tool - leave
    # unset in real production so test events don't mix with real ones.
    META_TEST_EVENT_CODE = os.getenv('META_TEST_EVENT_CODE', '')

    # GA4 Measurement ID (the "G-XXXXXXX" tag) is likewise not a secret.
    # The API secret is, and is only ever used server-side (Measurement
    # Protocol) for the one event (Purchase) reported from the backend.
    GA4_MEASUREMENT_ID = os.getenv('GA4_MEASUREMENT_ID', '')
    GA4_API_SECRET = os.getenv('GA4_API_SECRET', '')
