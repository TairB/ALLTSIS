"""
ui.py  –  All non-gameplay screens drawn with pure Pygame (no external UI libs).

Screens:
    main_menu()      → "play" | "leaderboard" | "settings" | "quit"
    name_entry()     → str  (player name)
    settings_screen()→ modifies and saves settings dict in-place
    leaderboard_screen()
    game_over_screen()→ "retry" | "menu"
"""
import pygame, sys
from pygame.locals import *
from persistence import load_leaderboard, load_settings, save_settings

# ── Shared palette ────────────────────────────────────────────────────────────
BLACK   = (  0,   0,   0)
WHITE   = (255, 255, 255)
YELLOW  = (255, 215,   0)
RED     = (220,  40,  40)
GREEN   = ( 50, 200,  50)
BLUE    = ( 30, 144, 255)
DARK    = ( 20,  20,  30)
PANEL   = ( 35,  35,  55)
GREY    = (120, 120, 120)
SILVER  = (192, 192, 192)
ORANGE  = (255, 140,   0)

SW = 400
SH = 600


# ── Tiny helpers ──────────────────────────────────────────────────────────────

def _fnt(size, bold=True):
    return pygame.font.SysFont("Verdana", size, bold=bold)


def _text(surf, text, fnt, colour, cx, cy):
    s = fnt.render(str(text), True, colour)
    surf.blit(s, s.get_rect(center=(cx, cy)))
    return s.get_rect(center=(cx, cy))


def _draw_bg(surf, bg_img, bg_y):
    """Scrolling background helper; returns next bg_y."""
    surf.blit(bg_img, (0, bg_y))
    surf.blit(bg_img, (0, bg_y - SH))
    return (bg_y + 2) % SH


def _overlay(surf, alpha=180):
    ov = pygame.Surface((SW, SH), pygame.SRCALPHA)
    ov.fill((0, 0, 0, alpha))
    surf.blit(ov, (0, 0))


# ── Button class ──────────────────────────────────────────────────────────────

class Button:
    def __init__(self, cx, cy, w, h, label, colour=BLUE, hover_col=None):
        self.rect      = pygame.Rect(0, 0, w, h)
        self.rect.center = (cx, cy)
        self.label     = label
        self.colour    = colour
        self.hover_col = hover_col or tuple(min(c + 40, 255) for c in colour)
        self._fnt      = _fnt(18)

    def draw(self, surf):
        mx, my = pygame.mouse.get_pos()
        col = self.hover_col if self.rect.collidepoint(mx, my) else self.colour
        pygame.draw.rect(surf, col, self.rect, border_radius=8)
        pygame.draw.rect(surf, WHITE, self.rect, 2, border_radius=8)
        _text(surf, self.label, self._fnt, WHITE,
              self.rect.centerx, self.rect.centery)

    def clicked(self, event):
        return (event.type == MOUSEBUTTONDOWN and event.button == 1
                and self.rect.collidepoint(event.pos))


# ── Main Menu ─────────────────────────────────────────────────────────────────

def main_menu(surface, bg_img) -> str:
    clock  = pygame.time.Clock()
    bg_y   = 0
    title  = _fnt(48)
    sub    = _fnt(16, bold=False)
    btns   = [
        Button(SW//2, 270, 220, 46, "▶  Play",        GREEN),
        Button(SW//2, 330, 220, 46, "🏆  Leaderboard", (80, 60, 160)),
        Button(SW//2, 390, 220, 46, "⚙  Settings",    (60, 100, 160)),
        Button(SW//2, 450, 220, 46, "✖  Quit",         (160, 40, 40)),
    ]
    actions = ["play", "leaderboard", "settings", "quit"]

    while True:
        for event in pygame.event.get():
            if event.type == QUIT:
                pygame.quit(); sys.exit()
            if event.type == KEYDOWN and event.key == K_ESCAPE:
                pygame.quit(); sys.exit()
            for btn, action in zip(btns, actions):
                if btn.clicked(event):
                    return action

        bg_y = _draw_bg(surface, bg_img, bg_y)
        _overlay(surface, 160)

        _text(surface, "🏎  RACER",   title, YELLOW, SW//2, 130)
        _text(surface, "TSIS 3 Edition", sub, SILVER, SW//2, 185)

        for btn in btns:
            btn.draw(surface)

        _text(surface, "ESC – quit", _fnt(13, False), GREY, SW//2, 570)
        pygame.display.flip()
        clock.tick(60)


# ── Name Entry ────────────────────────────────────────────────────────────────

def name_entry(surface, bg_img) -> str:
    clock  = pygame.time.Clock()
    bg_y   = 0
    name   = ""
    f_big  = _fnt(26)
    f_med  = _fnt(20)
    f_sml  = _fnt(15, False)
    blink  = True
    blink_t = 0

    while True:
        dt = clock.tick(60)
        blink_t += dt
        if blink_t > 500:
            blink = not blink
            blink_t = 0

        for event in pygame.event.get():
            if event.type == QUIT:
                pygame.quit(); sys.exit()
            if event.type == KEYDOWN:
                if event.key == K_RETURN and name.strip():
                    return name.strip()
                elif event.key == K_BACKSPACE:
                    name = name[:-1]
                elif event.unicode.isprintable() and len(name) < 16:
                    name += event.unicode

        bg_y = _draw_bg(surface, bg_img, bg_y)
        _overlay(surface, 170)

        _text(surface, "Enter Your Name", f_big, YELLOW, SW//2, 220)
        _text(surface, "─" * 22, f_sml, SILVER, SW//2, 260)

        display = name + ("|" if blink else " ")
        box = pygame.Rect(SW//2 - 130, 278, 260, 44)
        pygame.draw.rect(surface, PANEL, box, border_radius=6)
        pygame.draw.rect(surface, YELLOW if name else GREY, box, 2, border_radius=6)
        _text(surface, display, f_med, WHITE, SW//2, 300)

        _text(surface, "ENTER to confirm", f_sml, GREEN, SW//2, 350)
        pygame.display.flip()


# ── Settings Screen ───────────────────────────────────────────────────────────

def settings_screen(surface, bg_img) -> None:
    settings = load_settings()
    clock    = pygame.time.Clock()
    bg_y     = 0
    f_title  = _fnt(30)
    f_lbl    = _fnt(18)
    f_val    = _fnt(18, False)
    back_btn = Button(SW//2, 530, 160, 40, "← Back", (60, 60, 80))

    # Toggle / cycle buttons per option
    sound_btn = Button(SW//2 + 90, 220, 110, 36, "", GREEN)
    color_btn = Button(SW//2 + 90, 290, 110, 36, "", (60, 80, 160))
    diff_btn  = Button(SW//2 + 90, 360, 110, 36, "", (120, 60, 30))

    while True:
        # Update dynamic labels
        sound_btn.label  = "ON"  if settings["sound"]      else "OFF"
        sound_btn.colour = GREEN if settings["sound"]       else (160, 40, 40)
        color_btn.label  = settings["car_color"].capitalize()
        diff_btn.label   = settings["difficulty"].capitalize()

        for event in pygame.event.get():
            if event.type == QUIT:
                pygame.quit(); sys.exit()
            if event.type == KEYDOWN and event.key == K_ESCAPE:
                save_settings(settings); return
            if sound_btn.clicked(event):
                settings["sound"] = not settings["sound"]
            if color_btn.clicked(event):
                colors = ["blue", "red"]
                idx = colors.index(settings["car_color"])
                settings["car_color"] = colors[(idx + 1) % len(colors)]
            if diff_btn.clicked(event):
                diffs = ["easy", "normal", "hard"]
                idx = diffs.index(settings["difficulty"])
                settings["difficulty"] = diffs[(idx + 1) % len(diffs)]
            if back_btn.clicked(event):
                save_settings(settings); return

        bg_y = _draw_bg(surface, bg_img, bg_y)
        _overlay(surface, 170)

        _text(surface, "Settings", f_title, YELLOW, SW//2, 120)

        # Sound
        _text(surface, "Sound:", f_lbl, WHITE, SW//2 - 70, 220)
        sound_btn.draw(surface)

        # Car colour
        _text(surface, "Car Color:", f_lbl, WHITE, SW//2 - 60, 290)
        color_btn.draw(surface)

        # Difficulty
        _text(surface, "Difficulty:", f_lbl, WHITE, SW//2 - 60, 360)
        diff_btn.draw(surface)

        # Difficulty hints
        hints = {"easy": "Slower traffic, fewer obstacles",
                 "normal": "Balanced challenge",
                 "hard": "Fast traffic, many obstacles"}
        _text(surface, hints[settings["difficulty"]], _fnt(13, False),
              GREY, SW//2, 400)

        back_btn.draw(surface)
        pygame.display.flip()
        clock.tick(60)


# ── Leaderboard Screen ────────────────────────────────────────────────────────

def leaderboard_screen(surface, bg_img) -> None:
    entries  = load_leaderboard()
    clock    = pygame.time.Clock()
    bg_y     = 0
    f_title  = _fnt(28)
    f_hdr    = _fnt(14)
    f_row    = _fnt(14, False)
    back_btn = Button(SW//2, 565, 160, 38, "← Back", (60, 60, 80))

    while True:
        for event in pygame.event.get():
            if event.type == QUIT:
                pygame.quit(); sys.exit()
            if event.type == KEYDOWN and event.key == K_ESCAPE:
                return
            if back_btn.clicked(event):
                return

        bg_y = _draw_bg(surface, bg_img, bg_y)
        _overlay(surface, 175)

        _text(surface, "🏆 Leaderboard", f_title, YELLOW, SW//2, 50)

        # Header
        hdr_y = 95
        pygame.draw.rect(surface, PANEL, (10, hdr_y - 14, SW - 20, 28))
        _text(surface, "#",        f_hdr, SILVER,  35,       hdr_y)
        _text(surface, "Name",     f_hdr, SILVER, 120,       hdr_y)
        _text(surface, "Score",    f_hdr, SILVER, 230,       hdr_y)
        _text(surface, "Dist(m)",  f_hdr, SILVER, 310,       hdr_y)
        _text(surface, "Coins",    f_hdr, SILVER, 375,       hdr_y)

        # Rows
        row_colors = [YELLOW, SILVER, (205, 127, 50)]  # gold / silver / bronze
        for i, e in enumerate(entries):
            ry = 130 + i * 38
            bg_col = (30, 30, 50) if i % 2 == 0 else (40, 40, 65)
            pygame.draw.rect(surface, bg_col, (10, ry - 14, SW - 20, 34),
                             border_radius=4)
            rank_col = row_colors[i] if i < 3 else WHITE
            _text(surface, f"{i+1}",          f_row, rank_col, 35,  ry)
            # Truncate long names
            name_str = e.get("name", "?")[:12]
            _text(surface, name_str,           f_row, WHITE,  120,  ry)
            _text(surface, e.get("score", 0),  f_row, GREEN,  230,  ry)
            _text(surface, e.get("distance",0), f_row, BLUE,  310,  ry)
            _text(surface, e.get("coins", 0),  f_row, YELLOW, 375,  ry)

        if not entries:
            _text(surface, "No scores yet – play the game!",
                  _fnt(16, False), GREY, SW//2, 280)

        back_btn.draw(surface)
        pygame.display.flip()
        clock.tick(60)


# ── Game Over Screen ──────────────────────────────────────────────────────────

def game_over_screen(surface, bg_img, score, distance, coins,
                     crash_sound=None) -> str:
    """Returns 'retry' or 'menu'."""
    if crash_sound:
        crash_sound.play()
    clock    = pygame.time.Clock()
    bg_y     = 0
    f_big    = _fnt(42)
    f_med    = _fnt(20)
    f_sml    = _fnt(15, False)
    retry_btn = Button(SW//2 - 80, 440, 140, 44, "↺  Retry",     GREEN)
    menu_btn  = Button(SW//2 + 80, 440, 140, 44, "⌂  Main Menu", (60, 60, 80))

    while True:
        for event in pygame.event.get():
            if event.type == QUIT:
                pygame.quit(); sys.exit()
            if event.type == KEYDOWN:
                if event.key == K_r:      return "retry"
                if event.key == K_ESCAPE: return "menu"
            if retry_btn.clicked(event): return "retry"
            if menu_btn.clicked(event):  return "menu"

        bg_y = _draw_bg(surface, bg_img, bg_y)
        _overlay(surface, 185)

        _text(surface, "GAME OVER", f_big, RED, SW//2, 150)

        # Stats panel
        panel = pygame.Rect(SW//2 - 145, 215, 290, 180)
        pygame.draw.rect(surface, PANEL, panel, border_radius=10)
        pygame.draw.rect(surface, GREY,  panel, 2, border_radius=10)
        _text(surface, f"Score    {score}",    f_med, WHITE,  SW//2, 250)
        _text(surface, f"Distance {distance}m",f_med, BLUE,   SW//2, 285)
        _text(surface, f"Coins    {coins}",    f_med, YELLOW, SW//2, 320)

        retry_btn.draw(surface)
        menu_btn.draw(surface)

        _text(surface, "R – Retry   ESC – Menu", f_sml, GREY, SW//2, 510)
        pygame.display.flip()
        clock.tick(60)
