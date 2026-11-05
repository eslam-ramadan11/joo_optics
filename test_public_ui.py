"""Every local page/script/stylesheet the storefront HTML references must
actually be served by the Flask app.

This exists because the storefront is served through explicit routes in
app/routes/public_ui.py (not a catch-all static folder), so adding a new
page or script to "front j/" without also adding its route silently 404s on
the real server even though it works when the HTML is opened from disk.
That is exactly how about.html and tracking.js shipped broken once.
"""
import glob
import os
import re

import pytest

from app import create_app
from app.extensions import db

FRONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'front j')


@pytest.fixture
def reset_db():
    """Shadow conftest.py's autouse reset_db - this file makes its own app."""
    yield


@pytest.fixture
def client(tmp_path):
    db_path = (tmp_path / 'test.db').resolve()

    class TestConfig:
        TESTING = True
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{db_path.as_posix()}'
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        SECRET_KEY = 'test'
        JWT_SECRET_KEY = 'test'
        CORS_ORIGINS = ['http://localhost:5000']

    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
    return app.test_client()


def _local_references():
    refs = {}
    for path in sorted(glob.glob(os.path.join(FRONT_DIR, '*.html'))):
        with open(path, encoding='utf-8') as fh:
            html = fh.read()
        for ref in re.findall(r'(?:src|href)="([^"#?]+)', html):
            if ref.startswith(('http', '//', 'mailto:', 'tel:', 'data:', 'javascript:')):
                continue
            refs.setdefault('/' + ref.lstrip('/'), set()).add(os.path.basename(path))
    return refs


def test_every_local_reference_in_the_storefront_is_served(client):
    problems = []
    for url, pages in _local_references().items():
        # Image files are not shipped in the repo (they are added by the
        # store owner), so only check the routes that serve real code/pages.
        if url.startswith('/images/'):
            continue
        status = client.get(url).status_code
        if status != 200:
            problems.append(f'{url} -> {status} (referenced from {sorted(pages)})')
    assert not problems, 'Referenced but not served:\n' + '\n'.join(problems)


@pytest.mark.parametrize('url', ['/about.html', '/tracking.js'])
def test_about_page_and_tracking_script_are_served(client, url):
    assert client.get(url).status_code == 200


def test_robots_txt_has_an_absolute_sitemap_url(client):
    """Search engines ignore a relative 'Sitemap: /sitemap.xml' line, so the
    served robots.txt must build the absolute URL from SITE_BASE_URL."""
    client.application.config['SITE_BASE_URL'] = 'https://shop.example.com/'
    rv = client.get('/robots.txt')
    assert rv.status_code == 200
    assert rv.mimetype == 'text/plain'
    body = rv.get_data(as_text=True)
    assert 'Sitemap: https://shop.example.com/sitemap.xml' in body
    assert 'Sitemap: /sitemap.xml' not in body
    # The private areas must still be blocked.
    assert 'Disallow: /admin/' in body
    assert 'Disallow: /api/' in body
