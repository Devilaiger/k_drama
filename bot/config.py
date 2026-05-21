import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from bot/.env
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

# App Configuration
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Admin Configuration
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
SECONDARY_ADMIN_ID = int(os.environ.get("SECONDARY_ADMIN_ID", 0))
# Load all admin IDs from env — no hardcoded values
# ADMIN_IDS env var supports comma-separated list e.g. "123456,789012"
_admin_ids_raw = os.environ.get("ADMIN_IDS", "")
_extra_ids = [int(x.strip()) for x in _admin_ids_raw.split(",") if x.strip().isdigit()]
_raw = [ADMIN_ID, SECONDARY_ADMIN_ID] + _extra_ids
# Deduplicate and remove unset (0) values
ADMIN_IDS = list(dict.fromkeys(uid for uid in _raw if uid != 0))

# Channel Configuration
STORAGE_CHANNEL_ID = int(os.environ.get("STORAGE_CHANNEL_ID", 0))
MAIN_CHANNEL_LINK = os.environ.get("MAIN_CHANNEL_LINK", "")
SECOND_CHANNEL_LINK = os.environ.get("SECOND_CHANNEL_LINK", "")
REQUIRED_CHANNELS_RAW = os.environ.get("REQUIRED_CHANNELS", "@Seoul_Entertainment_DKD")
REQUIRED_CHANNELS = [c.strip() for c in REQUIRED_CHANNELS_RAW.split(",") if c.strip()]

# Database Configuration
# Priority: MONGO_URI, then mongo_url
MONGO_URI = os.environ.get("MONGO_URI") or os.environ.get("mongo_url")
if not MONGO_URI:
    raise ValueError("MONGO_URI or mongo_url not set in environment variables.")

# Optional: Redis Configuration
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Category Emojis
CATEGORY_EMOJIS = {
    "K-Hindi": "🎙️",
    "K-Original": "🎌",
    "Japanese Drama": "🎌",
    "CT Drama": "🏮",
    "Global": "🌍",
    "Pakistan": "🇵🇰",
    "Anime": "🎨"
}

def get_category_emoji(category: str) -> str:
    return CATEGORY_EMOJIS.get(category, "📂")
