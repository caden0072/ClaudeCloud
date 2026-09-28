"""Find a contact email on a business website (homepage + common contact pages)."""
import hashlib
import html
import re
import time
from urllib.parse import urljoin, urlparse

import requests

from . import config

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}")
CONTACT_LINK_RE = re.compile(r'href=["\']([^"\']*(contact|about|connect|visit|staff|team)[^"\']*)["\']', re.I)
JUNK_DOMAINS = ("sentry", "wixpress", "example.com", "domain.com", "email.com", "yourdomain",
                "godaddy", "squarespace", "wix.com", "schema.org", "w3.org", "mysite")
JUNK_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js")
PREFERRED_PREFIX = ("info", "contact", "office", "hello", "admin", "events", "hr", "frontdesk",
                    "membership", "manager", "church", "welcome")
# Addresses nobody should cold-email about an event.
JUNK_LOCAL_RE = re.compile(r"^(cpo|privacy|legal|dpo|compliance|careers?|jobs|recruit\w*|no-?reply|"
                           r"do-?not-?reply|webmaster|abuse|press|media|accessibility|ada|unsubscribe|"
                           r"billing|accounting|payroll|ar|ap)$")
FALLBACK_PATHS = ["/contact", "/contact-us", "/about", "/about-us"]


def _fetch(session, url, cache_dir):
    key = hashlib.sha256(url.encode()).hexdigest()
    path = cache_dir / f"{key}.html"
    if path.exists():
        return path.read_text(errors="ignore")
    try:
        resp = session.get(url, timeout=15, allow_redirects=True)
    except requests.RequestException:
        # Network/proxy failures are not cached, so a later run retries them.
        return None
    text = resp.text if resp.ok and "html" in resp.headers.get("content-type", "") else ""
    path.write_text(text)
    time.sleep(0.5)  # be polite
    return text


def _emails_in(page):
    page = html.unescape(page).replace("%40", "@").replace("[at]", "@").replace("(at)", "@")
    found = []
    for m in EMAIL_RE.findall(page):
        e = m.strip(".").lower()
        if e.endswith(JUNK_EXT) or any(j in e for j in JUNK_DOMAINS) or JUNK_LOCAL_RE.match(e.partition("@")[0]):
            continue
        if e not in found:
            found.append(e)
    return found


def _rank(emails, site_domain):
    def score(e):
        local, _, dom = e.partition("@")
        on_site = site_domain and (dom == site_domain or dom.endswith("." + site_domain))
        return (0 if on_site else 1, 0 if local.startswith(PREFERRED_PREFIX) else 1, len(e))
    return sorted(emails, key=score)


def find_email(website):
    """Return (email, source_url), ("", note), or (None, note) if the site could not be fetched."""
    if not website:
        return "", "no website"
    cache_dir = config.CACHE_DIR / "web"
    cache_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = config.HTTP_USER_AGENT
    domain = urlparse(website).netloc.lower().removeprefix("www.")

    home = _fetch(session, website, cache_dir)
    if home is None:
        return None, "fetch failed (network)"
    if not home:
        return "", "website unreachable"
    found = _emails_in(home)
    if found:
        return _rank(found, domain)[0], website

    links = []
    for href, _ in CONTACT_LINK_RE.findall(home):
        full = urljoin(website, href)
        if urlparse(full).netloc.lower().removeprefix("www.") == domain and full not in links:
            links.append(full)
    links += [urljoin(website, p) for p in FALLBACK_PATHS if urljoin(website, p) not in links]
    for url in links[:5]:
        found = _emails_in(_fetch(session, url, cache_dir) or "")
        if found:
            return _rank(found, domain)[0], url
    return "", "no email listed"
