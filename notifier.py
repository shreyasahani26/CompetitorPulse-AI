import os
import smtplib

from email.message import EmailMessage

import requests
from dotenv import load_dotenv

load_dotenv()


def send_slack_alert(message):
    webhook_url = os.getenv(
        "SLACK_WEBHOOK_URL",
        ""
    ).strip()

    if not webhook_url:
        return False, "Slack webhook not configured."

    try:
        response = requests.post(
            webhook_url,
            json={"text": message},
            timeout=15
        )

        response.raise_for_status()

        return True, "Slack alert sent."

    except requests.RequestException as exc:
        return False, f"Slack alert failed: {exc}"


def send_email_alert(subject, body):
    enabled = os.getenv(
        "EMAIL_ENABLED",
        "false"
    ).lower() == "true"

    if not enabled:
        return False, "Email notifications are disabled."

    host = os.getenv(
        "SMTP_HOST",
        "smtp.gmail.com"
    ).strip()

    port = int(os.getenv("SMTP_PORT", "587"))

    username = os.getenv(
        "SMTP_USERNAME",
        ""
    ).strip()

    password = os.getenv(
        "SMTP_PASSWORD",
        ""
    ).strip()

    recipient = os.getenv(
        "ALERT_EMAIL_TO",
        ""
    ).strip()

    if not all((host, username, password, recipient)):
        return False, "Email settings are incomplete."

    message = EmailMessage()

    message["Subject"] = subject
    message["From"] = username
    message["To"] = recipient

    message.set_content(body)

    try:
        with smtplib.SMTP(
            host,
            port,
            timeout=20
        ) as server:

            server.starttls()
            server.login(username, password)
            server.send_message(message)

        return True, "Email alert sent."

    except Exception as exc:
        return False, f"Email alert failed: {exc}"


def send_new_articles_alert(domain, articles):
    if not articles:
        return []

    lines = [
        (
            f"CompetitorPulse AI: {domain} has "
            f"{len(articles)} new article(s)."
        ),
        ""
    ]

    for article in articles[:20]:
        lines.extend([
            f'Title: {article.get("title", "Untitled")}',
            f'URL: {article.get("url", "")}',
            (
                "Published: "
                f'{article.get("published_at") or "Unknown"}'
            ),
            (
                "Keywords: "
                f'{", ".join(article.get("keywords", []))}'
            ),
            ""
        ])

    body = "\n".join(lines)

    return [
        send_slack_alert(body),
        send_email_alert(
            f"New competitor content: {domain}",
            body
        )
    ]