import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = BASE_DIR / "settings.json"
SCHEMA_FILE = BASE_DIR / "schema.sql"
ENV_FILE = BASE_DIR / ".env"
ASSETS_DIR = BASE_DIR / "assets"
EAT_SOUND_FILE = ASSETS_DIR / "eats.mp3"

CELL = 20
COLS = 30
ROWS = 25
HUD_HEIGHT = 70

SCREEN_WIDTH = COLS * CELL
SCREEN_HEIGHT = ROWS * CELL + HUD_HEIGHT

FOODS_PER_LEVEL = 3
BASE_SPEED = 8
SPEED_STEP = 2
POWERUP_DURATION_MS = 5000
POWERUP_FIELD_MS = 8000
POISON_RESPAWN_MS = 7000
POWERUP_RESPAWN_RANGE_MS = (6000, 11000)

TOP_LEADERBOARD_LIMIT = 10
MAX_USERNAME_LEN = 16

BACKGROUND = (16, 20, 30)
GRID_COLOR = (33, 40, 56)
HUD_COLOR = (26, 33, 48)
BORDER_COLOR = (62, 76, 98)
TEXT_COLOR = (240, 243, 247)
MUTED_TEXT = (140, 148, 160)
ACCENT = (248, 198, 72)
DANGER = (192, 56, 56)
SUCCESS = (80, 200, 120)
OBSTACLE_COLOR = (92, 72, 56)
POISON_COLOR = (110, 18, 24)
POISON_HIGHLIGHT = (190, 60, 68)

DEFAULT_SETTINGS = {
    "snake_color": [80, 220, 80],
    "grid_overlay": True,
    "sound": False,
}


def load_env_file() -> None:
    if not ENV_FILE.exists():
        return

    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_env_file()

DEFAULT_DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "phonebook_db"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "Qwaszx6804"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
}
