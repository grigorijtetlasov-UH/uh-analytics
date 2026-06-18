"""MCI configuration — weights, thresholds, API settings."""

import os
from pathlib import Path
from dotenv import load_dotenv

# --- Paths ---
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Load .env from mci/ directory explicitly
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    # Force reload and override
    load_dotenv(dotenv_path=str(ENV_FILE), override=True)

    # Read .env file directly to handle BOM
    env_content = ENV_FILE.read_text(encoding='utf-8-sig')
    for line in env_content.split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' in line:
            key, value = line.split('=', 1)
            os.environ[key.strip()] = value.strip()


# --- API Keys (with fallback to environment) ---
def get_env(key: str, default: str = "") -> str:
    """Get environment variable, trying both os.environ and direct read."""
    val = os.environ.get(key)
    if val:
        return val

    # Try reading from .env again
    if ENV_FILE.exists():
        try:
            content = ENV_FILE.read_text(encoding='utf-8-sig')
            for line in content.split('\n'):
                if line.startswith(key + '='):
                    return line.split('=', 1)[1].strip()
        except:
            pass

    return default


ANTHROPIC_API_KEY = get_env("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = get_env("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = get_env("TELEGRAM_CHAT_ID", "")



# --- Sub-index weights (must sum to 1.0) ---
WEIGHTS = {
    "security":       0.25,
    "economy":        0.25,
    "infrastructure": 0.20,
    "social":         0.15,
    "realestate":     0.05,
    "market":         0.05,
    "weather":        0.05,
}

# --- MCI scale ---
# 0-20  = Panic      (red)     — stop ads, cut budgets
# 20-40 = Fear       (orange)  — conservative, essentials only
# 40-60 = Neutral    (yellow)  — business as usual
# 60-80 = Optimism   (green)   — increase budgets, push promos
# 80-100= Euphoria   (blue)    — max push, big campaigns

MCI_LABELS = {
    (0, 20):   ("🔴 Паника",    "Минимизировать расходы, только необходимое"),
    (20, 40):  ("🟠 Страх",     "Консервативная стратегия, акцент на рассрочку"),
    (40, 60):  ("🟡 Нейтрально","Обычный режим, следить за трендами"),
    (60, 80):  ("🟢 Оптимизм",  "Увеличивать бюджеты, запускать акции"),
    (80, 100): ("🔵 Эйфория",   "Максимальный push, большие кампании"),
}


def get_mci_label(score: float) -> tuple[str, str]:
    for (lo, hi), (label, advice) in MCI_LABELS.items():
        if lo <= score < hi:
            return label, advice
    return "🔵 Эйфория", "Максимальный push"


# --- Regions for tracking ---
REGIONS = [
    "Kyiv", "Kharkiv", "Odesa", "Dnipro", "Lviv",
    "Zaporizhzhia", "Vinnytsia", "Poltava", "Chernihiv", "Mykolaiv",
]
