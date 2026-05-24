"""
email_enricher.py
Free email enrichment by crawling a business's own website.
Checks homepage + common contact pages, extracts mailto: links
and regex-matched emails, filters out noise.
"""

import re
import time
import requests
import urllib3
from urllib.parse import urlparse

# Suppress SSL warnings for sites with self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Emails containing these strings are almost certainly not real contact emails
EMAIL_BLACKLIST = {
    'noreply', 'no-reply', 'donotreply', 'do-not-reply',
    'example', 'wixpress', 'wordpress', 'squarespace',
    'sentry', 'gdpr', 'privacy', 'abuse', 'admin',
    'webmaster', 'postmaster', 'bounces', 'mailer-daemon',
    'service@paypal', 'service@ebay',
}

# Common paths where contact emails are usually listed
CONTACT_PATHS = [
    '/contact', '/contact-us', '/contacts', '/contact_us',
    '/about', '/about-us', '/reach-us', '/get-in-touch',
    '/info', '/support', '/help',
]

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )
}

EMAIL_PATTERN = re.compile(
    r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',
    re.IGNORECASE
)
MAILTO_PATTERN = re.compile(
    r'mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})',
    re.IGNORECASE
)


def _extract_emails_from_html(html: str) -> list[str]:
    """Extract and filter emails from raw HTML string."""
    # mailto: links are most reliable (they're intentionally exposed)
    mailtos = MAILTO_PATTERN.findall(html)
    # Regex over all text as fallback
    raw = EMAIL_PATTERN.findall(html)

    # Deduplicate while preserving priority order (mailto first)
    seen = set()
    combined = []
    for e in mailtos + raw:
        e = e.lower().strip()
        if e not in seen:
            seen.add(e)
            combined.append(e)

    filtered = []
    for e in combined:
        # Skip file extensions accidentally matched
        if e.endswith(('.png', '.jpg', '.jpeg', '.gif', '.css', '.js', '.svg', '.webp')):
            continue
        # Skip blacklisted patterns
        if any(bl in e for bl in EMAIL_BLACKLIST):
            continue
        # Skip very long or obviously broken ones
        if len(e) > 80:
            continue
        filtered.append(e)

    return filtered


def _fetch(url: str, timeout: int = 8) -> str | None:
    """Fetch URL, return HTML or None on failure."""
    try:
        r = requests.get(url, timeout=timeout, headers=HEADERS,
                         allow_redirects=True, verify=False)
        if r.status_code == 200 and 'text' in r.headers.get('Content-Type', ''):
            return r.text
    except Exception:
        pass
    return None


def find_email_for_website(website_url: str) -> str | None:
    """
    Given a business website URL, attempt to find a public contact email.
    Checks homepage then common contact/about pages.
    Returns the first plausible email found, or None.
    """
    if not website_url:
        return None

    # Normalize
    website_url = website_url.strip()
    if not website_url.startswith(('http://', 'https://')):
        website_url = 'https://' + website_url

    parsed = urlparse(website_url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    pages_to_check = [website_url] + [base + path for path in CONTACT_PATHS]

    for url in pages_to_check:
        html = _fetch(url)
        if html:
            emails = _extract_emails_from_html(html)
            if emails:
                return emails[0]

    return None


def enrich_campaign(campaign_id: int, leads: list[dict],
                    update_email_fn, progress_store: dict,
                    delay: float = 0.5):
    """
    Background enrichment runner.
    Iterates leads that have a website but no email, scrapes email,
    saves to DB, and updates the progress_store dict in place.
    delay: seconds to wait between requests (be polite to servers).
    """
    eligible = [l for l in leads if l.get('website') and not l.get('email')]
    total = len(eligible)

    progress_store[campaign_id] = {
        'status': 'running',
        'total': total,
        'processed': 0,
        'found': 0,
    }

    if total == 0:
        progress_store[campaign_id]['status'] = 'done'
        return

    for lead in eligible:
        if progress_store.get(campaign_id, {}).get('status') == 'cancelled':
            break

        email = find_email_for_website(lead['website'])
        if email:
            update_email_fn(lead['id'], email)
            progress_store[campaign_id]['found'] += 1

        progress_store[campaign_id]['processed'] += 1
        time.sleep(delay)

    progress_store[campaign_id]['status'] = 'done'
