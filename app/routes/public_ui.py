"""Serve public storefront pages from the repository `front j/` folder."""
import os
from xml.sax.saxutils import escape

from flask import Blueprint, send_from_directory, current_app, Response

bp = Blueprint('public_ui', __name__)


def _public_dir() -> str:
    return os.path.abspath(os.path.join(current_app.root_path, '..', 'front j'))


@bp.route('/robots.txt')
def robots():
    """Serve robots.txt with an ABSOLUTE Sitemap URL.

    Search engines ignore a relative "Sitemap: /sitemap.xml" line, so the
    static file's last line is replaced here using SITE_BASE_URL.
    """
    robots_path = os.path.join(_public_dir(), 'robots.txt')
    try:
        with open(robots_path, encoding='utf-8') as fh:
            lines = [ln.rstrip('\r\n') for ln in fh if not ln.lower().startswith('sitemap:')]
    except OSError:
        lines = ['User-agent: *', 'Allow: /']

    while lines and not lines[-1].strip():
        lines.pop()

    base_url = (current_app.config.get('SITE_BASE_URL') or '').rstrip('/')
    if base_url:
        lines += ['', f'Sitemap: {base_url}/sitemap.xml']

    return Response('\n'.join(lines) + '\n', mimetype='text/plain')


@bp.route('/sitemap.xml')
def sitemap():
    """Generate the sitemap dynamically so every real product gets its own
    entry - a static file would go stale the moment a product is added."""
    from app.models.models import Product

    base_url = current_app.config.get('SITE_BASE_URL', '').rstrip('/')

    static_pages = ['/', '/shop.html', '/about.html', '/contact.html', '/login.html']
    urls = [f'{base_url}{path}' for path in static_pages]

    products = Product.query.with_entities(Product.id).all()
    urls += [f'{base_url}/product.html?id={p.id}' for p in products]

    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url in urls:
        xml_parts.append(f'<url><loc>{escape(url)}</loc></url>')
    xml_parts.append('</urlset>')

    return Response('\n'.join(xml_parts), mimetype='application/xml')


@bp.route('/')
@bp.route('/index.html')
def index():
    return send_from_directory(_public_dir(), 'index.html')


@bp.route('/shop.html')
def shop():
    return send_from_directory(_public_dir(), 'shop.html')


@bp.route('/login.html')
def login():
    return send_from_directory(_public_dir(), 'login.html')


@bp.route('/contact.html')
def contact():
    return send_from_directory(_public_dir(), 'contact.html')


@bp.route('/style.css')
def style():
    return send_from_directory(_public_dir(), 'style.css')


@bp.route('/frontend.js')
def frontend():
    return send_from_directory(_public_dir(), 'frontend.js')


@bp.route('/toast.js')
def toast_js():
    return send_from_directory(_public_dir(), 'toast.js')


@bp.route('/favicon.svg')
def favicon():
    return send_from_directory(_public_dir(), 'favicon.svg')


@bp.route('/chat-widget.js')
def chat_widget_js():
    return send_from_directory(_public_dir(), 'chat-widget.js')


@bp.route('/account.html')
def account():
    return send_from_directory(_public_dir(), 'account.html')


@bp.route('/account.js')
def account_js():
    return send_from_directory(_public_dir(), 'account.js')


@bp.route('/checkout.html')
def checkout():
    return send_from_directory(_public_dir(), 'checkout.html')


@bp.route('/checkout.js')
def checkout_js():
    return send_from_directory(_public_dir(), 'checkout.js')


@bp.route('/about.html')
def about():
    return send_from_directory(_public_dir(), 'about.html')


@bp.route('/tracking.js')
def tracking_js():
    return send_from_directory(_public_dir(), 'tracking.js')


@bp.route('/product.html')
def product():
    return send_from_directory(_public_dir(), 'product.html')


@bp.route('/product.js')
def product_js():
    return send_from_directory(_public_dir(), 'product.js')


@bp.route('/payment-result.html')
def payment_result():
    return send_from_directory(_public_dir(), 'payment-result.html')


@bp.route('/payment-result.js')
def payment_result_js():
    return send_from_directory(_public_dir(), 'payment-result.js')


@bp.route('/images/<path:filename>')
def images(filename: str):
    return send_from_directory(os.path.join(_public_dir(), 'images'), filename)