import os
from pathlib import Path


# --- Paths ---
BASE_DIR = Path(__file__).resolve().parent  # Project root directory
SETTINGS_FILE = BASE_DIR / "settings.json"
SCHEMA_FILE = BASE_DIR / "schema.sql"
ENV_FILE = BASE_DIR / ".env"
ASSETS_DIR = BASE_DIR / "assets"
EAT_SOUND_FILE = ASSETS_DIR / "eats.mp3"

# --- Grid / window dimensions ---
CELL = 20               # Pixel size of one cell
COLS = 30               # Grid columns
ROWS = 25               # Grid rows
HUD_HEIGHT = 70         # Top HUD panel height in pixels

SCREEN_WIDTH = COLS * CELL
SCREEN_HEIGHT = ROWS * CELL + HUD_HEIGHT

# --- Gameplay constants ---
FOODS_PER_LEVEL = 3             # Foods to eat before leveling up
BASE_SPEED = 8                  # Starting speed (cells/sec)
SPEED_STEP = 2                  # Speed increase per level
POWERUP_DURATION_MS = 5000      # How long a picked-up power-up effect lasts
POWERUP_FIELD_MS = 8000         # How long a power-up stays on the field before despawning
POISON_RESPAWN_MS = 7000        # Delay before poison reappears
POWERUP_RESPAWN_RANGE_MS = (6000, 11000)  # Random delay range between power-up spawns

TOP_LEADERBOARD_LIMIT = 10
MAX_USERNAME_LEN = 16

# --- Color palette (RGB) ---
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

# --- Default user settings (used if settings.json is missing or invalid) ---
DEFAULT_SETTINGS = {
    "snake_color": [80, 220, 80],
    "grid_overlay": True,
    "sound": False,
}


def load_env_file() -> None:
    """Read .env and load KEY=VALUE pairs into os.environ without overwriting existing vars."""
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


load_env_file()  # Run at import time so DB env vars are available below

# --- PostgreSQL connection config (env vars take priority over hardcoded defaults) ---
DEFAULT_DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "phonebook_db"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "Qwaszx6804"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
}