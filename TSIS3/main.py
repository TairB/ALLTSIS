"""
main.py  –  TSIS 3 Entry Point

Assets in assets/ folder:
    AnimatedStreet.png   road background
    Player.png           player car (blue)
    Enemy.png            enemy car (red)
    yellowcar.jpeg       traffic car variant 1
    greencar.jpeg        traffic car variant 2
    nitro.png            nitro power-up sprite
    barrier.png          barrier road event sprite
    background.wav       looping music
    crash.wav            crash sound effect
"""

import pygame, sys, os
from pygame.locals import *

import ui
from racer import run_game
from persistence import load_settings

pygame.init()
pygame.mixer.init()

SW, SH = 400, 600
DISPLAYSURF = pygame.display.set_mode((SW, SH))
pygame.display.set_caption("RACER  –  TSIS 3")


# ── Asset loader helper ───────────────────────────────────────────────────────
def _load(name):
    for path in [os.path.join("assets", name), name]:
        if os.path.exists(path):
            return path
    raise FileNotFoundError(f"Asset not found: {name}")


def _scale_car(img, target_w=52):
    ratio = target_w / img.get_width()
    new_h = int(img.get_height() * ratio)
    return pygame.transform.scale(img, (target_w, new_h))


def _to_alpha(img):
    """Convert any surface (e.g. JPEG) to SRCALPHA surface."""
    result = pygame.Surface(img.get_size(), pygame.SRCALPHA)
    result.blit(img, (0, 0))
    return result


def load_assets():
    # Road background
    bg_img = pygame.image.load(_load("AnimatedStreet.png")).convert()
    bg_img = pygame.transform.scale(bg_img, (SW, SH))

    # Primary enemy car (red, from P11)
    enemy_img = pygame.image.load(_load("Enemy.png")).convert_alpha()
    enemy_img = _scale_car(enemy_img, 52)

    # Traffic car variants: yellow + green (JPEG → alpha surface)
    yellow_raw = pygame.image.load(_load("yellowcar.jpeg")).convert()
    green_raw  = pygame.image.load(_load("greencar.jpeg")).convert()
    yellow_car = _scale_car(_to_alpha(yellow_raw), 52)
    green_car  = _scale_car(_to_alpha(green_raw),  52)

    # All traffic images (cycled randomly among enemies)
    traffic_imgs = [enemy_img, yellow_car, green_car]

    # Nitro power-up sprite
    nitro_raw = pygame.image.load(_load("nitro.png")).convert_alpha()
    nitro_img = pygame.transform.scale(nitro_raw, (38, 38))

    # Barrier road-event sprite
    barrier_raw = pygame.image.load(_load("barrier.png")).convert_alpha()
    barrier_img = pygame.transform.scale(barrier_raw, (72, 48))

    # Sounds
    crash_snd = pygame.mixer.Sound(_load("crash.wav"))
    bg_music  = _load("background.wav")

    return bg_img, traffic_imgs, nitro_img, barrier_img, crash_snd, bg_music


def load_player_img(settings):
    color = settings.get("car_color", "blue")
    candidates = [f"Player_{color}.png", "Player.png"]
    for name in candidates:
        for path in [os.path.join("assets", name), name]:
            if os.path.exists(path):
                img = pygame.image.load(path).convert_alpha()
                return _scale_car(img, 52)
    raise FileNotFoundError("Player.png not found")


# ── Main loop ─────────────────────────────────────────────────────────────────
def main():
    try:
        bg_img, traffic_imgs, nitro_img, barrier_img, crash_snd, bg_music = load_assets()
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        pygame.quit()
        sys.exit(1)

    player_name = ""

    while True:
        settings = load_settings()
        action   = ui.main_menu(DISPLAYSURF, bg_img)

        if action == "quit":
            pygame.quit(); sys.exit()
        elif action == "leaderboard":
            ui.leaderboard_screen(DISPLAYSURF, bg_img)
        elif action == "settings":
            ui.settings_screen(DISPLAYSURF, bg_img)
        elif action == "play":
            if not player_name:
                player_name = ui.name_entry(DISPLAYSURF, bg_img)

            settings   = load_settings()
            player_img = load_player_img(settings)

            while True:
                result, score, distance, coins = run_game(
                    DISPLAYSURF, bg_img,
                    traffic_imgs,
                    nitro_img,
                    barrier_img,
                    player_img,
                    crash_snd, bg_music,
                    player_name, settings
                )

                choice = ui.game_over_screen(
                    DISPLAYSURF, bg_img, score, distance, coins,
                    crash_snd if settings.get("sound") else None
                )

                if choice == "retry":
                    settings   = load_settings()
                    player_img = load_player_img(settings)
                else:
                    break


if __name__ == "__main__":
    main()