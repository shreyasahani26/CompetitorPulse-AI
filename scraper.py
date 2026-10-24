import re

from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import feedparser
import requests

from bs4 import BeautifulSoup


USER_AGENT = (
    "CompetitorPulseAI/1.0 "
    "(content monitoring tool)"
)

TIMEOUT = 15

ARTICLE_HINTS = (
    "/blog/",
    "/blogs/",
    "/article/",
    "/articles/",
    "/news/",
    "/resources/",
    "/insights/",
    "/post/",
    "/posts/",
    "/updates/"
)

EXCLUDED_HINTS = (
    "/tag/",
    "/category/",
    "/author/",
    "/page/",
    "/search",
    "/login",
    "/signup",
    "/privacy",
    "/terms"
)


def fetch_url(url):
    response = requests.get(
        url,
        headers={
            "User-Agent": USER_AGENT
        },
        timeout=TIMEOUT,
        allow_redirects=True
    )

    response.raise_for_status()

    return response


def same_domain(url, domain):
    host = (
        urlparse(url).hostname or ""
    ).lower().removeprefix("www.")

    expected = domain.lower().removeprefix("www.")

    return (
        host == expected
        or host.endswith("." + expected)
    )


def extract_article_details(url):
    response = fetch_url(url)

    content_type = response.headers.get(
        "Content-Type",
        ""
    ).lower()

    if "html" not in content_type:
        return None

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    title_tag = (
        soup.find(
            "meta",
            property="og:title"
        )
        or soup.find(
            "meta",
            attrs={"name": "twitter:title"}
        )
    )

    title = (
        title_tag.get("content")
        if title_tag
        else None
    )

    if not title and soup.title:
        title = soup.title.get_text(
            " ",
            strip=True
        )

    description_tag = (
        soup.find(
            "meta",
            attrs={"name": "description"}
        )
        or soup.find(
            "meta",
            property="og:description"
        )
    )

    description = (
        description_tag.get("content", "")
        if description_tag
        else ""
    )

    published_tag = (
        soup.find(
            "meta",
            property="article:published_time"
        )
        or soup.find(
            "meta",
            attrs={"name": "datePublished"}
        )
        or soup.find(
            "meta",
            attrs={"name": "pubdate"}
        )
    )

    published_at = (
        published_tag.get("content")
        if published_tag
        else None
    )

    return {
        "url": response.url,
        "title": (title or "").strip(),
        "description": (description or "").strip(),
        "published_at": published_at
    }


def sitemap_urls(sitemap_url, domain, visited=None):
    if visited is None:
        visited = set()

    if sitemap_url in visited or len(visited) >= 10:
        return []

    visited.add(sitemap_url)

    try:
        response = fetch_url(sitemap_url)

        root = ElementTree.fromstring(
            response.content
        )

    except Exception:
        return []

    found = []

    for element in root.iter():
        if element.tag.split("}")[-1] != "loc":
            continue

        loc = (element.text or "").strip()

        if not loc:
            continue

        if not same_domain(loc, domain):
            continue

        if loc.lower().endswith(".xml"):
            found.extend(
                sitemap_urls(
                    loc,
                    domain,
                    visited
                )
            )
        else:
            found.append(loc)

    return found


def discover_article_urls(domain):
    homepage_url = f"https://{domain}/"

    try:
        response = fetch_url(homepage_url)

        homepage_url = response.url

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

    except Exception as exc:
        raise RuntimeError(
            f"Could not access homepage: {exc}"
        ) from exc

    listing_pages = {homepage_url}

    for link in soup.find_all("a", href=True):
        url = urljoin(
            homepage_url,
            link["href"]
        )

        path = urlparse(url).path.lower()

        if (
            same_domain(url, domain)
            and any(
                hint in path
                for hint in (
                    "/blog",
                    "/resource",
                    "/article",
                    "/news",
                    "/insight"
                )
            )
        ):
            listing_pages.add(url)

    discovered = set()

    for listing_page in list(listing_pages)[:20]:
        try:
            response = fetch_url(listing_page)

            page_soup = BeautifulSoup(
                response.text,
                "html.parser"
            )

            for link in page_soup.find_all(
                "a",
                href=True
            ):
                url = urljoin(
                    response.url,
                    link["href"]
                )

                path = urlparse(url).path.lower()

                if not same_domain(url, domain):
                    continue

                if any(
                    hint in path
                    for hint in EXCLUDED_HINTS
                ):
                    continue

                if any(
                    hint in path
                    for hint in ARTICLE_HINTS
                ):
                    discovered.add(url)

        except Exception:
            continue

    sitemap_list = [
        f"https://{domain}/sitemap.xml",
        f"https://{domain}/sitemap_index.xml"
    ]

    for sitemap in sitemap_list:
        for url in sitemap_urls(sitemap, domain):
            path = urlparse(url).path.lower()

            if any(
                hint in path
                for hint in EXCLUDED_HINTS
            ):
                continue

            if any(
                hint in path
                for hint in ARTICLE_HINTS
            ):
                discovered.add(url)

    feed_paths = [
        "/feed/",
        "/feed",
        "/rss.xml",
        "/blog/feed/"
    ]

    for feed_path in feed_paths:
        try:
            feed_url = urljoin(
                homepage_url,
                feed_path
            )

            response = fetch_url(feed_url)

            feed = feedparser.parse(
                response.content
            )

            for entry in feed.entries:
                url = entry.get("link")

                if url and same_domain(url, domain):
                    discovered.add(url)

        except Exception:
            continue

    return sorted(discovered)


def scan_competitor(domain):
    domain = domain.strip().lower()

    if domain.startswith(
        ("http://", "https://")
    ):
        parsed = urlparse(domain)

        if (
            parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "Enter a domain only, without a path or query."
            )

        domain = parsed.hostname or ""

    domain = domain.removeprefix("www.")

    if not re.fullmatch(
        r"(?=.{1,253}$)"
        r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
        r"[a-z]{2,63}",
        domain
    ):
        raise ValueError(
            "Please enter a valid domain name."
        )

    urls = discover_article_urls(domain)

    articles = []

    for url in urls[:100]:
        try:
            article = extract_article_details(url)

            if article and article["title"]:
                articles.append(article)

        except Exception:
            continue

    return articles