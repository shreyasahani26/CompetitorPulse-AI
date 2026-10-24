import os

from dotenv import load_dotenv
from sklearn.feature_extraction.text import TfidfVectorizer

load_dotenv()


def extract_keywords(title, description="", limit=8):
    text = f"{title or ''} {description or ''}".strip()

    if not text:
        return []

    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9-]{2,}\b",
        max_features=100
    )

    try:
        matrix = vectorizer.fit_transform([text])

        features = vectorizer.get_feature_names_out()
        scores = matrix.toarray()[0]

        ranked = sorted(
            zip(features, scores),
            key=lambda item: item[1],
            reverse=True
        )

        return [
            keyword
            for keyword, score in ranked[:limit]
            if score > 0
        ]

    except ValueError:
        return []


def get_search_volume(keyword):
    """
    Real search volume requires a configured keyword research API.
    Do not invent search-volume figures.
    """

    provider = os.getenv(
        "KEYWORD_API_PROVIDER",
        ""
    ).strip()

    api_key = os.getenv(
        "KEYWORD_API_KEY",
        ""
    ).strip()

    if not provider or not api_key:
        return None

    # Provider-specific integration must be implemented
    # using the selected provider's official API.
    return None


def analyze_article(article):
    keywords = extract_keywords(
        article.get("title", ""),
        article.get("description", "")
    )

    return [
        {
            "keyword": keyword,
            "search_volume": get_search_volume(keyword)
        }
        for keyword in keywords
    ]