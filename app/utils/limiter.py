"""Flask-Limiter configuration for rate limiting."""
import os

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# FIX: this was hardcoded to "memory://" even though _env.example documents
# a RATELIMIT_STORAGE_URL setting (e.g. redis://... for production, where
# multiple gunicorn workers each need to share one counter). The env var was
# never actually read, so setting it in .env silently did nothing.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=os.environ.get('RATELIMIT_STORAGE_URL', 'memory://'),
)

# Rate limit policies for different endpoint categories
RATE_LIMITS = {
    'auth': '5 per minute',
    'products': '100 per minute',
    'orders': '20 per minute',
    'payments': '10 per minute',
    'prescriptions': '30 per minute',
}
