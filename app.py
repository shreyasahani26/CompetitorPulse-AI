from flask import Flask, flash, redirect, render_template, request, url_for
from urllib.parse import urlparse
import re

from analyzer import analyze_article
from config import SECRET_KEY
from database import get_connection, init_db
from notifier import send_new_articles_alert
from scraper import scan_competitor

app = Flask(__name__)
app.secret_key = SECRET_KEY


def get_competitors():
    with get_connection() as connection:
        rows = connection.execute("""
            SELECT c.*,
                   (
                       SELECT COUNT(*)
                       FROM articles a
                       WHERE a.competitor_id = c.id
                   ) AS article_count
            FROM competitors c
            ORDER BY c.created_at DESC
        """).fetchall()

        return [dict(row) for row in rows]


def get_dashboard_stats():
    with get_connection() as connection:
        return {
            "competitors": connection.execute(
                "SELECT COUNT(*) FROM competitors"
            ).fetchone()[0],

            "articles": connection.execute(
                "SELECT COUNT(*) FROM articles"
            ).fetchone()[0],

            "scans": connection.execute(
                "SELECT COUNT(*) FROM scan_history"
            ).fetchone()[0],

            "prices": connection.execute(
                "SELECT COUNT(*) FROM price_history"
            ).fetchone()[0],
        }


def get_recent_articles(limit=30):
    with get_connection() as connection:
        rows = connection.execute("""
            SELECT a.*, c.domain
            FROM articles a
            JOIN competitors c ON c.id = a.competitor_id
            ORDER BY a.first_seen_at DESC
            LIMIT ?
        """, (limit,)).fetchall()

        return [dict(row) for row in rows]


def get_recent_scans(limit=15):
    with get_connection() as connection:
        rows = connection.execute("""
            SELECT s.*, c.domain
            FROM scan_history s
            JOIN competitors c ON c.id = s.competitor_id
            ORDER BY s.scanned_at DESC
            LIMIT ?
        """, (limit,)).fetchall()

        return [dict(row) for row in rows]


def get_competitor(competitor_id):
    with get_connection() as connection:
        row = connection.execute("""
            SELECT *
            FROM competitors
            WHERE id = ?
        """, (competitor_id,)).fetchone()

        return dict(row) if row else None


def record_scan(competitor_id, status, message, new_count=0):
    with get_connection() as connection:
        connection.execute("""
            INSERT INTO scan_history (
                competitor_id,
                status,
                message,
                new_articles
            )
            VALUES (?, ?, ?, ?)
        """, (
            competitor_id,
            status,
            str(message)[:1000],
            new_count
        ))


def save_article(competitor_id, article):
    analysis = analyze_article(article)

    keywords = [
        item["keyword"]
        for item in analysis
    ]

    with get_connection() as connection:
        existing = connection.execute("""
            SELECT id
            FROM articles
            WHERE competitor_id = ?
              AND url = ?
        """, (
            competitor_id,
            article["url"]
        )).fetchone()

        if existing:
            connection.execute("""
                UPDATE articles
                SET title = ?,
                    description = ?,
                    published_at = ?,
                    keywords = ?,
                    last_seen_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                article.get("title", ""),
                article.get("description", ""),
                article.get("published_at"),
                ", ".join(keywords),
                existing["id"]
            ))

            return False

        connection.execute("""
            INSERT INTO articles (
                competitor_id,
                url,
                title,
                description,
                published_at,
                keywords
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            competitor_id,
            article["url"],
            article.get("title", ""),
            article.get("description", ""),
            article.get("published_at"),
            ", ".join(keywords)
        ))

        return True


def run_scan(competitor_id):
    competitor = get_competitor(competitor_id)

    if not competitor:
        return False, "Competitor not found."

    domain = competitor["domain"]

    try:
        articles = scan_competitor(domain)
        new_articles = []

        for article in articles:
            if save_article(competitor_id, article):
                analysis = analyze_article(article)

                article["keywords"] = [
                    item["keyword"]
                    for item in analysis
                ]

                new_articles.append(article)

        with get_connection() as connection:
            connection.execute("""
                UPDATE competitors
                SET last_scanned_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (competitor_id,))

        message = (
            f"Scan completed. Discovered {len(articles)} articles; "
            f"{len(new_articles)} are new."
        )

        record_scan(
            competitor_id,
            "success",
            message,
            len(new_articles)
        )

        if new_articles:
            notification_results = send_new_articles_alert(
                domain,
                new_articles
            )

            failures = [
                result[1]
                for result in notification_results
                if not result[0]
            ]

            if failures:
                message += " Notifications: " + "; ".join(failures)

        return True, message

    except Exception as exc:
        message = f"Scan failed: {type(exc).__name__}: {exc}"

        try:
            record_scan(
                competitor_id,
                "failed",
                message
            )
        except Exception:
            pass

        return False, message


@app.route("/")
def index():
    return render_template(
        "index.html",
        competitors=get_competitors(),
        stats=get_dashboard_stats(),
        articles=get_recent_articles(),
        scans=get_recent_scans()
    )


@app.route("/add-competitor", methods=["POST"])
def add_competitor():
    raw_domain = request.form.get(
        "domain", ""
    ).strip().lower()

    if raw_domain.startswith(("http://", "https://")):
        parsed = urlparse(raw_domain)

        if (
            parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            flash(
                "Enter only the domain, without a path or query.",
                "error"
            )
            return redirect(url_for("index"))

        raw_domain = parsed.hostname or ""

    raw_domain = raw_domain.removeprefix("www.")

    if not re.fullmatch(
        r"(?=.{1,253}$)"
        r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
        r"[a-z]{2,63}",
        raw_domain
    ):
        flash(
            "Enter a valid domain, such as example.com.",
            "error"
        )
        return redirect(url_for("index"))

    try:
        with get_connection() as connection:
            connection.execute("""
                INSERT OR IGNORE INTO competitors (domain)
                VALUES (?)
            """, (raw_domain,))

        flash(
            f"{raw_domain} added successfully.",
            "success"
        )

    except Exception as exc:
        flash(
            f"Could not add competitor: {exc}",
            "error"
        )

    return redirect(url_for("index"))


@app.route("/scan/<int:competitor_id>", methods=["POST"])
def scan(competitor_id):
    success, message = run_scan(competitor_id)

    flash(
        message,
        "success" if success else "error"
    )

    return redirect(url_for("index"))


@app.route("/scan-all", methods=["POST"])
def scan_all():
    competitors = get_competitors()

    if not competitors:
        flash(
            "Add a competitor before scanning.",
            "error"
        )
        return redirect(url_for("index"))

    messages = []
    all_success = True

    for competitor in competitors:
        success, message = run_scan(competitor["id"])

        if not success:
            all_success = False

        messages.append(
            f'{competitor["domain"]}: {message}'
        )

    flash(
        " | ".join(messages),
        "success" if all_success else "error"
    )

    return redirect(url_for("index"))


@app.route("/health")
def health():
    return {
        "status": "ok",
        "application": "CompetitorPulse AI"
    }


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )