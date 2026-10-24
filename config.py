import os

from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv(
    "FLASK_SECRET_KEY",
    "local-development-key-change-before-deployment"
)

MAX_ARTICLES_PER_SCAN = 100

REQUEST_TIMEOUT = 15