"""
persistence.py  –  Save / load leaderboard and settings to/from JSON files.
"""
import json, os

LEADERBOARD_FILE = "leaderboard.json"
SETTINGS_FILE    = "settings.json"

# ── Default settings ──────────────────────────────────────────────────────────
DEFAULT_SETTINGS = {
    "sound":       True,
    "car_color":   "blue",      # "blue" | "red"
    "difficulty":  "normal",    # "easy" | "normal" | "hard"
}

# ── Leaderboard ───────────────────────────────────────────────────────────────

def load_leaderboard() -> list[dict]:
    """Return list of top-10 entries sorted by score descending."""
    if not os.path.exists(LEADERBOARD_FILE):
        return []
    with open(LEADERBOARD_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = []
    return sorted(data, key=lambda e: e.get("score", 0), reverse=True)[:10]


def save_leaderboard(entries: list[dict]) -> None:
    """Persist the leaderboard list (max 10 entries)."""
    with open(LEADERBOARD_FILE, "w", encoding="utf-8") as f:
        json.dump(entries[:10], f, indent=2, ensure_ascii=False)


def add_leaderboard_entry(name: str, score: int, distance: int, coins: int) -> None:
    """Add a new entry, keep only the top 10."""
    entries = load_leaderboard()
    entries.append({"name": name, "score": score, "distance": distance, "coins": coins})
    entries = sorted(entries, key=lambda e: e["score"], reverse=True)[:10]
    save_leaderboard(entries)


# ── Settings ─────────────────────────────────────────────────────────────────

def load_settings() -> dict:
    """Load settings from disk; fall back to defaults for missing keys."""
    base = dict(DEFAULT_SETTINGS)
    if not os.path.exists(SETTINGS_FILE):
        return base
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        try:
            stored = json.load(f)
        except json.JSONDecodeError:
            stored = {}
    base.update(stored)
    return base


def save_settings(settings: dict) -> None:
    """Persist settings to disk."""
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
