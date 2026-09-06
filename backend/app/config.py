import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = f"sqlite:///{BASE_DIR / 'maple.db'}"
ARTIFACTS_DIR = BASE_DIR / "artifacts"
LOGS_DIR = ARTIFACTS_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

MYSQL_URL = os.getenv("MYSQL_URL", "mysql+pymysql://root:123456@127.0.0.1:3306/maple_auth?charset=utf8mb4")
JWT_SECRET = os.getenv("JWT_SECRET", "maple-dev-secret")
