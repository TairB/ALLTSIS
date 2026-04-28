from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import random
import sys

import pygame

from config import (
    ACCENT,
    BACKGROUND,
    BASE_SPEED,
    BORDER_COLOR,
    CELL,
    COLS,
    DEFAULT_SETTINGS,
    EAT_SOUND_FILE,
    FOODS_PER_LEVEL,
    GRID_COLOR,
    HUD_COLOR,
    HUD_HEIGHT,
    MAX_USERNAME_LEN,
    MUTED_TEXT,
    OBSTACLE_COLOR,
    POISON_COLOR,
    POISON_HIGHLIGHT,
    POISON_RESPAWN_MS,
    POWERUP_DURATION_MS,
    POWERUP_FIELD_MS,
    POWERUP_RESPAWN_RANGE_MS,
    ROWS,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    SETTINGS_FILE,
    SPEED_STEP,
    SUCCESS,
    TEXT_COLOR,
    TOP_LEADERBOARD_LIMIT,
)
from db import DatabaseManager


UP = (0, -1)
DOWN = (0, 1)
LEFT = (-1, 0)
RIGHT = (1, 0)
OPPOSITE = {UP: DOWN, DOWN: UP, LEFT: RIGHT, RIGHT: LEFT}

FOOD_TYPES = [
    {
        "label": "Common",
        "color": (240, 70, 70),
        "highlight": (255, 150, 150),
        "value": 10,
        "lifespan_ms": 8000,
        "weight": 50,
    },
    {
        "label": "Rare",
        "color": (100, 180, 255),
        "highlight": (185, 225, 255),
        "value": 25,
        "lifespan_ms": 5000,
        "weight": 30,
    },
    {
        "label": "Legend",
        "color": (255, 215, 0),
        "highlight": (255, 245, 150),
        "value": 50,
        "lifespan_ms": 3000,
        "weight": 20,
    },
]

POWERUP_TYPES = [
    {"name": "speed", "label": "Speed Boost", "color": (255, 130, 40), "symbol": ">>"},
    {"name": "slow", "label": "Slow Motion", "color": (70, 160, 255), "symbol": "<<"},
    {"name": "shield", "label": "Shield", "color": (130, 255, 180), "symbol": "S"},
]


@dataclass
class Food:
    pos: tuple[int, int]
    value: int
    color: tuple[int, int, int]
    highlight: tuple[int, int, int]
    lifespan_ms: int
    spawned_at: int
    label: str

    def expired(self, now: int) -> bool:
        return now - self.spawned_at >= self.lifespan_ms

    def fraction_left(self, now: int) -> float:
        age = min(self.lifespan_ms, max(0, now - self.spawned_at))
        return 1.0 - age / self.lifespan_ms


@dataclass
class PowerUp:
    pos: tuple[int, int]
    kind: str
    color: tuple[int, int, int]
    label: str
    symbol: str
    spawned_at: int

    def expired(self, now: int) -> bool:
        return now - self.spawned_at >= POWERUP_FIELD_MS


class Button:
    def __init__(self, x: int, y: int, width: int, height: int, text: str) -> None:
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text

    def draw(self, surface, font, hovered: bool = False) -> None:
        fill = (68, 87, 114) if hovered else (44, 57, 76)
        pygame.draw.rect(surface, fill, self.rect, border_radius=12)
        pygame.draw.rect(surface, BORDER_COLOR, self.rect, 2, border_radius=12)
        label = font.render(self.text, True, TEXT_COLOR)
        surface.blit(label, label.get_rect(center=self.rect.center))

    def contains(self, position: tuple[int, int]) -> bool:
        return self.rect.collidepoint(position)


class Snake:
    def __init__(self, color: tuple[int, int, int]) -> None:
        center_col = COLS // 2
        center_row = ROWS // 2
        self.body = [
            (center_col, center_row),
            (center_col - 1, center_row),
            (center_col - 2, center_row),
        ]
        self.direction = RIGHT
        self.pending_growth = 0
        self.color = color

    @property
    def head(self) -> tuple[int, int]:
        return self.body[0]

    @property
    def body_cells(self) -> set[tuple[int, int]]:
        return set(self.body)

    def turn(self, direction: tuple[int, int]) -> None:
        if direction != OPPOSITE[self.direction]:
            self.direction = direction

    def move(self) -> tuple[int, int]:
        dx, dy = self.direction
        new_head = (self.head[0] + dx, self.head[1] + dy)
        self.body.insert(0, new_head)
        if self.pending_growth > 0:
            self.pending_growth -= 1
        else:
            self.body.pop()
        return new_head

    def grow(self, amount: int = 1) -> None:
        self.pending_growth += amount

    def shrink(self, amount: int) -> None:
        for _ in range(amount):
            if len(self.body) > 0:
                self.body.pop()
        self.pending_growth = 0

    def self_collision(self) -> bool:
        return self.head in self.body[1:]

    def draw(self, surface: pygame.Surface) -> None:
        body_color = tuple(max(20, channel - 38) for channel in self.color)
        for index, (col, row) in enumerate(self.body):
            rect = pygame.Rect(col * CELL, row * CELL + HUD_HEIGHT, CELL, CELL).inflate(-2, -2)
            pygame.draw.rect(
                surface,
                self.color if index == 0 else body_color,
                rect,
                border_radius=5,
            )
            if index == 0:
                for offset in (-4, 4):
                    eye = (rect.centerx + offset, rect.centery - 3)
                    pygame.draw.circle(surface, TEXT_COLOR, eye, 3)
                    pygame.draw.circle(surface, BACKGROUND, eye, 1)


class SnakeApp:
    def __init__(self, database: DatabaseManager) -> None:
        pygame.init()
        self.audio_available = False
        try:
            pygame.mixer.init()
            self.audio_available = True
        except pygame.error:
            self.audio_available = False

        self.database = database
        self.settings = self.load_settings()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("TSIS 4 Snake")
        self.clock = pygame.time.Clock()

        self.font_title = pygame.font.SysFont("Verdana", 38, bold=True)
        self.font_subtitle = pygame.font.SysFont("Verdana", 24, bold=True)
        self.font_body = pygame.font.SysFont("Verdana", 18)
        self.font_small = pygame.font.SysFont("Verdana", 15)
        self.font_hud = pygame.font.SysFont("Verdana", 16, bold=True)

        self.running = True
        self.state = "menu"
        self.username = ""
        self.menu_message = "Enter a username to start."
        self.last_game: dict[str, int | str] | None = None
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        self.audio_message = ""
        self.load_sounds()

    def run(self) -> None:
        while self.running:
            if self.state == "menu":
                self.menu_loop()
            elif self.state == "leaderboard":
                self.leaderboard_loop()
            elif self.state == "settings":
                self.settings_loop()
            elif self.state == "play":
                self.play_loop()
            elif self.state == "game_over":
                self.game_over_loop()
            else:
                self.running = False
        pygame.quit()
        sys.exit()

    def load_settings(self) -> dict:
        if SETTINGS_FILE.exists():
            try:
                data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}
        else:
            data = {}

        merged = DEFAULT_SETTINGS.copy()
        merged.update(data)
        merged["snake_color"] = [
            max(0, min(255, int(value)))
            for value in merged.get("snake_color", DEFAULT_SETTINGS["snake_color"])
        ]
        merged["grid_overlay"] = bool(merged.get("grid_overlay", True))
        merged["sound"] = bool(merged.get("sound", False))
        return merged

    def save_settings(self) -> None:
        SETTINGS_FILE.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")

    def load_sounds(self) -> None:
        if not self.audio_available:
            self.audio_message = "Audio device unavailable."
            return
        if not EAT_SOUND_FILE.exists():
            self.audio_message = f"Missing sound file: {EAT_SOUND_FILE.name}"
            return

        try:
            eat_sound = pygame.mixer.Sound(str(EAT_SOUND_FILE))
            eat_sound.set_volume(0.55)
            self.sounds["eat"] = eat_sound
            self.audio_message = "Eat sound loaded."
        except pygame.error:
            self.audio_message = "Could not load eats.mp3."

    def play_sound(self, name: str) -> None:
        if not self.settings.get("sound", False):
            return
        sound = self.sounds.get(name)
        if sound is not None:
            sound.play()

    def menu_loop(self) -> None:
        play_button = Button(200, 250, 200, 44, "Play")
        leaderboard_button = Button(200, 308, 200, 44, "Leaderboard")
        settings_button = Button(200, 366, 200, 44, "Settings")
        quit_button = Button(200, 424, 200, 44, "Quit")
        input_rect = pygame.Rect(160, 170, 280, 46)

        while self.running and self.state == "menu":
            mouse_pos = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                    elif event.key == pygame.K_RETURN:
                        self.start_game_from_menu()
                    elif event.key == pygame.K_BACKSPACE:
                        self.username = self.username[:-1]
                    elif event.unicode.isprintable() and len(self.username) < MAX_USERNAME_LEN:
                        if event.unicode not in "\r\t":
                            self.username += event.unicode
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if play_button.contains(event.pos):
                        self.start_game_from_menu()
                    elif leaderboard_button.contains(event.pos):
                        self.state = "leaderboard"
                    elif settings_button.contains(event.pos):
                        self.state = "settings"
                    elif quit_button.contains(event.pos):
                        self.running = False

            self.screen.fill(BACKGROUND)
            self.draw_title("TSIS 4 Snake", "Database, power-ups, poison, obstacles")

            label = self.font_body.render("Username", True, TEXT_COLOR)
            self.screen.blit(label, (input_rect.x, input_rect.y - 26))
            pygame.draw.rect(self.screen, (28, 34, 48), input_rect, border_radius=10)
            pygame.draw.rect(self.screen, BORDER_COLOR, input_rect, 2, border_radius=10)
            text = self.font_body.render(self.username or "Type here...", True, TEXT_COLOR if self.username else MUTED_TEXT)
            self.screen.blit(text, (input_rect.x + 12, input_rect.y + 12))

            for button in (play_button, leaderboard_button, settings_button, quit_button):
                button.draw(self.screen, self.font_body, button.contains(mouse_pos))

            db_line = self.database.status_message
            if self.database.last_error:
                db_line = f"{db_line} Check PostgreSQL config in config.py or env vars."
            self.draw_footer(self.menu_message, db_line)

            pygame.display.flip()
            self.clock.tick(60)

    def start_game_from_menu(self) -> None:
        cleaned = self.username.strip()
        if not cleaned:
            self.menu_message = "Username is required."
            return
        self.username = cleaned[:MAX_USERNAME_LEN]
        self.state = "play"
        self.menu_message = "Enter a username to start."

    def leaderboard_loop(self) -> None:
        back_button = Button(220, 518, 160, 42, "Back")
        leaderboard = self.database.get_leaderboard(TOP_LEADERBOARD_LIMIT)

        while self.running and self.state == "leaderboard":
            mouse_pos = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                    self.state = "menu"
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if back_button.contains(event.pos):
                        self.state = "menu"

            self.screen.fill(BACKGROUND)
            self.draw_title("Leaderboard", "Top 10 all-time scores")

            table_rect = pygame.Rect(48, 130, 504, 360)
            pygame.draw.rect(self.screen, (24, 30, 42), table_rect, border_radius=16)
            pygame.draw.rect(self.screen, BORDER_COLOR, table_rect, 2, border_radius=16)

            headers = ["Rank", "Username", "Score", "Level", "Date"]
            columns = [68, 170, 90, 80, 140]
            x = table_rect.x + 16
            for header, width in zip(headers, columns):
                header_text = self.font_small.render(header, True, ACCENT)
                self.screen.blit(header_text, (x, table_rect.y + 18))
                x += width

            if leaderboard:
                for index, row in enumerate(leaderboard, start=1):
                    y = table_rect.y + 52 + (index - 1) * 28
                    played_at = row["played_at"]
                    if isinstance(played_at, datetime):
                        date_text = played_at.strftime("%Y-%m-%d")
                    else:
                        date_text = str(played_at)[:10]
                    values = [
                        str(index),
                        str(row["username"])[:14],
                        str(row["score"]),
                        str(row["level_reached"]),
                        date_text,
                    ]
                    x = table_rect.x + 16
                    for value, width in zip(values, columns):
                        cell = self.font_small.render(value, True, TEXT_COLOR)
                        self.screen.blit(cell, (x, y))
                        x += width
            else:
                message = "No data yet." if self.database.available else "Database unavailable."
                text = self.font_subtitle.render(message, True, MUTED_TEXT)
                self.screen.blit(text, text.get_rect(center=table_rect.center))

            back_button.draw(self.screen, self.font_body, back_button.contains(mouse_pos))
            self.draw_footer("Scores are saved automatically after game over.", self.database.status_message)
            pygame.display.flip()
            self.clock.tick(60)

    def settings_loop(self) -> None:
        save_button = Button(198, 508, 204, 42, "Save & Back")
        toggle_grid = Button(350, 170, 130, 40, "Toggle")
        toggle_sound = Button(350, 232, 130, 40, "Toggle")
        color_buttons = {
            "r_minus": Button(310, 314, 52, 38, "-"),
            "r_plus": Button(428, 314, 52, 38, "+"),
            "g_minus": Button(310, 366, 52, 38, "-"),
            "g_plus": Button(428, 366, 52, 38, "+"),
            "b_minus": Button(310, 418, 52, 38, "-"),
            "b_plus": Button(428, 418, 52, 38, "+"),
        }

        while self.running and self.state == "settings":
            mouse_pos = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self.state = "menu"
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if toggle_grid.contains(event.pos):
                        self.settings["grid_overlay"] = not self.settings["grid_overlay"]
                    elif toggle_sound.contains(event.pos):
                        self.settings["sound"] = not self.settings["sound"]
                    elif save_button.contains(event.pos):
                        self.save_settings()
                        self.state = "menu"
                    else:
                        self.adjust_color_buttons(event.pos, color_buttons)

            self.screen.fill(BACKGROUND)
            self.draw_title("Settings", "Saved to settings.json")

            grid_text = f"Grid Overlay: {'On' if self.settings['grid_overlay'] else 'Off'}"
            sound_text = f"Sound: {'On' if self.settings['sound'] else 'Off'}"
            self.screen.blit(self.font_body.render(grid_text, True, TEXT_COLOR), (120, 180))
            self.screen.blit(self.font_body.render(sound_text, True, TEXT_COLOR), (120, 242))
            toggle_grid.draw(self.screen, self.font_small, toggle_grid.contains(mouse_pos))
            toggle_sound.draw(self.screen, self.font_small, toggle_sound.contains(mouse_pos))

            channels = self.settings["snake_color"]
            labels = [("R", channels[0], 320), ("G", channels[1], 372), ("B", channels[2], 424)]
            for label, value, y in labels:
                text = self.font_body.render(f"{label}: {value}", True, TEXT_COLOR)
                self.screen.blit(text, (120, y))

            for button in color_buttons.values():
                button.draw(self.screen, self.font_small, button.contains(mouse_pos))

            preview_rect = pygame.Rect(120, 470, 120, 42)
            pygame.draw.rect(self.screen, tuple(channels), preview_rect, border_radius=10)
            pygame.draw.rect(self.screen, BORDER_COLOR, preview_rect, 2, border_radius=10)
            preview_label = self.font_small.render("Snake Color Preview", True, MUTED_TEXT)
            self.screen.blit(preview_label, (250, 482))

            save_button.draw(self.screen, self.font_body, save_button.contains(mouse_pos))
            self.draw_footer(
                "Use +/- to change RGB in steps of 15.",
                f"Sound toggle controls eats.mp3. {self.audio_message}",
            )
            pygame.display.flip()
            self.clock.tick(60)

    def adjust_color_buttons(self, position: tuple[int, int], buttons: dict[str, Button]) -> None:
        delta_map = {
            "r_minus": (0, -15),
            "r_plus": (0, 15),
            "g_minus": (1, -15),
            "g_plus": (1, 15),
            "b_minus": (2, -15),
            "b_plus": (2, 15),
        }
        for key, button in buttons.items():
            if button.contains(position):
                index, delta = delta_map[key]
                self.settings["snake_color"][index] = max(
                    0,
                    min(255, self.settings["snake_color"][index] + delta),
                )
                break

    def play_loop(self) -> None:
        personal_best = self.database.get_personal_best(self.username)
        snake = Snake(tuple(self.settings["snake_color"]))
        score = 0
        level = 1
        foods_this_level = 0
        level_message = ""
        shield_ready = False
        effect_name = ""
        effect_ends_at = 0
        powerup: PowerUp | None = None
        powerup_next_spawn = pygame.time.get_ticks() + random.randint(*POWERUP_RESPAWN_RANGE_MS)
        poison_pos: tuple[int, int] | None = None
        poison_next_spawn = pygame.time.get_ticks() + 3000
        obstacles: set[tuple[int, int]] = set()
        last_move_at = pygame.time.get_ticks()
        food = self.spawn_food(snake, obstacles)

        while self.running and self.state == "play":
            now = pygame.time.get_ticks()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.state = "menu"
                        return
                    if event.key in (pygame.K_UP, pygame.K_w):
                        snake.turn(UP)
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        snake.turn(DOWN)
                    elif event.key in (pygame.K_LEFT, pygame.K_a):
                        snake.turn(LEFT)
                    elif event.key in (pygame.K_RIGHT, pygame.K_d):
                        snake.turn(RIGHT)

            occupied = self.occupied_cells(food, poison_pos, powerup)

            if food.expired(now):
                food = self.spawn_food(
                    snake,
                    obstacles,
                    self.occupied_cells(None, poison_pos, powerup),
                )
                occupied = self.occupied_cells(food, poison_pos, powerup)

            if poison_pos is None and now >= poison_next_spawn:
                poison_pos = self.random_free_cell(
                    snake,
                    obstacles,
                    self.occupied_cells(food, None, powerup),
                    exclude_radius=1,
                )
                poison_next_spawn = now + POISON_RESPAWN_MS
                occupied = self.occupied_cells(food, poison_pos, powerup)

            if powerup and powerup.expired(now):
                powerup = None
                powerup_next_spawn = now + random.randint(*POWERUP_RESPAWN_RANGE_MS)
                occupied = self.occupied_cells(food, poison_pos, powerup)

            if powerup is None and now >= powerup_next_spawn:
                powerup = self.spawn_powerup(snake, obstacles, self.occupied_cells(food, poison_pos, None))
                occupied = self.occupied_cells(food, poison_pos, powerup)

            if effect_name and now >= effect_ends_at and effect_name != "Shield":
                effect_name = ""
                effect_ends_at = 0

            speed = self.current_speed(level, effect_name)
            move_delay = int(1000 / speed)

            if now - last_move_at >= move_delay:
                previous_body = snake.body[:]
                new_head = snake.move()
                last_move_at = now

                collision = self.detect_collision(new_head, snake, obstacles)
                if collision:
                    if shield_ready:
                        shield_ready = False
                        effect_name = ""
                        snake.body = previous_body
                        level_message = "Shield absorbed the collision."
                    else:
                        saved = self.database.save_session(self.username, score, level)
                        personal_best = max(personal_best, score)
                        self.last_game = {
                            "username": self.username,
                            "score": score,
                            "level": level,
                            "personal_best": personal_best,
                            "saved": "yes" if saved else "no",
                        }
                        self.state = "game_over"
                        return
                else:
                    if new_head == food.pos:
                        snake.grow()
                        score += food.value * level
                        foods_this_level += 1
                        personal_best = max(personal_best, score)
                        self.play_sound("eat")
                        level_message = f"+{food.value * level} from {food.label.lower()} food"
                        food = self.spawn_food(
                            snake,
                            obstacles,
                            self.occupied_cells(None, poison_pos, powerup),
                        )
                        if foods_this_level >= FOODS_PER_LEVEL:
                            level += 1
                            foods_this_level = 0
                            level_message = f"Level {level}"
                            if level >= 3:
                                obstacles = self.generate_obstacles(level, snake)
                                if poison_pos in obstacles:
                                    poison_pos = None
                                    poison_next_spawn = now + POISON_RESPAWN_MS
                                if powerup and powerup.pos in obstacles:
                                    powerup = None
                                    powerup_next_spawn = now + random.randint(*POWERUP_RESPAWN_RANGE_MS)
                                food = self.spawn_food(
                                    snake,
                                    obstacles,
                                    self.occupied_cells(None, poison_pos, powerup),
                                )

                    if poison_pos and new_head == poison_pos:
                        snake.shrink(2)
                        poison_pos = None
                        poison_next_spawn = now + POISON_RESPAWN_MS
                        level_message = "Poison food: -2 segments"
                        if len(snake.body) <= 1:
                            saved = self.database.save_session(self.username, score, level)
                            personal_best = max(personal_best, score)
                            self.last_game = {
                                "username": self.username,
                                "score": score,
                                "level": level,
                                "personal_best": personal_best,
                                "saved": "yes" if saved else "no",
                            }
                            self.state = "game_over"
                            return

                    if powerup and new_head == powerup.pos:
                        powerup_name, shield_ready, effect_ends_at, level_message = self.activate_powerup(
                            powerup.kind,
                            now,
                            shield_ready,
                        )
                        effect_name = powerup_name
                        powerup = None
                        powerup_next_spawn = now + random.randint(*POWERUP_RESPAWN_RANGE_MS)

            self.draw_game(
                snake=snake,
                food=food,
                poison_pos=poison_pos,
                powerup=powerup,
                obstacles=obstacles,
                score=score,
                level=level,
                foods_this_level=foods_this_level,
                personal_best=personal_best,
                effect_name=effect_name,
                shield_ready=shield_ready,
                message=level_message,
                now=now,
            )
            pygame.display.flip()
            self.clock.tick(60)

    def game_over_loop(self) -> None:
        retry_button = Button(175, 380, 110, 44, "Retry")
        menu_button = Button(315, 380, 110, 44, "Main Menu")

        while self.running and self.state == "game_over":
            mouse_pos = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.state = "menu"
                    elif event.key == pygame.K_RETURN:
                        self.state = "play"
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if retry_button.contains(event.pos):
                        self.state = "play"
                    elif menu_button.contains(event.pos):
                        self.state = "menu"

            result = self.last_game or {}
            self.screen.fill(BACKGROUND)
            self.draw_title("Game Over", "Result saved automatically after the run")
            box = pygame.Rect(120, 170, 360, 170)
            pygame.draw.rect(self.screen, (24, 30, 42), box, border_radius=16)
            pygame.draw.rect(self.screen, BORDER_COLOR, box, 2, border_radius=16)

            lines = [
                f"Player: {result.get('username', self.username)}",
                f"Score: {result.get('score', 0)}",
                f"Level reached: {result.get('level', 1)}",
                f"Personal best: {result.get('personal_best', 0)}",
                f"Saved to DB: {result.get('saved', 'no')}",
            ]
            for index, line in enumerate(lines):
                label = self.font_body.render(line, True, TEXT_COLOR)
                self.screen.blit(label, (150, 200 + index * 28))

            retry_button.draw(self.screen, self.font_body, retry_button.contains(mouse_pos))
            menu_button.draw(self.screen, self.font_body, menu_button.contains(mouse_pos))
            self.draw_footer("Retry uses the same username.", self.database.status_message)
            pygame.display.flip()
            self.clock.tick(60)

    def spawn_food(
        self,
        snake: Snake,
        obstacles: set[tuple[int, int]],
        occupied: set[tuple[int, int]] | None = None,
    ) -> Food:
        occupied = occupied or set()
        cell = self.random_free_cell(snake, obstacles, occupied)
        spec = random.choices(FOOD_TYPES, weights=[item["weight"] for item in FOOD_TYPES], k=1)[0]
        return Food(
            pos=cell,
            value=spec["value"],
            color=spec["color"],
            highlight=spec["highlight"],
            lifespan_ms=spec["lifespan_ms"],
            spawned_at=pygame.time.get_ticks(),
            label=spec["label"],
        )

    def spawn_powerup(
        self,
        snake: Snake,
        obstacles: set[tuple[int, int]],
        occupied: set[tuple[int, int]],
    ) -> PowerUp:
        spec = random.choice(POWERUP_TYPES)
        cell = self.random_free_cell(snake, obstacles, occupied, exclude_radius=1)
        return PowerUp(
            pos=cell,
            kind=spec["name"],
            color=spec["color"],
            label=spec["label"],
            symbol=spec["symbol"],
            spawned_at=pygame.time.get_ticks(),
        )

    def random_free_cell(
        self,
        snake: Snake,
        obstacles: set[tuple[int, int]],
        occupied: set[tuple[int, int]] | None = None,
        exclude_radius: int = 0,
    ) -> tuple[int, int]:
        occupied = occupied or set()
        snake_cells = snake.body_cells
        head = snake.head
        while True:
            pos = (random.randint(1, COLS - 2), random.randint(1, ROWS - 2))
            if pos in snake_cells or pos in obstacles or pos in occupied:
                continue
            if exclude_radius and abs(pos[0] - head[0]) + abs(pos[1] - head[1]) <= exclude_radius:
                continue
            return pos

    def occupied_cells(
        self,
        food: Food | None,
        poison_pos: tuple[int, int] | None,
        powerup: PowerUp | None,
    ) -> set[tuple[int, int]]:
        occupied: set[tuple[int, int]] = set()
        if food:
            occupied.add(food.pos)
        if poison_pos:
            occupied.add(poison_pos)
        if powerup:
            occupied.add(powerup.pos)
        return occupied

    def detect_collision(
        self,
        head: tuple[int, int],
        snake: Snake,
        obstacles: set[tuple[int, int]],
    ) -> bool:
        if head[0] <= 0 or head[0] >= COLS - 1 or head[1] <= 0 or head[1] >= ROWS - 1:
            return True
        if head in obstacles:
            return True
        return snake.self_collision()

    def current_speed(self, level: int, effect_name: str) -> int:
        speed = BASE_SPEED + (level - 1) * SPEED_STEP
        if effect_name == "Speed Boost":
            speed += 4
        elif effect_name == "Slow Motion":
            speed = max(4, speed - 4)
        return speed

    def activate_powerup(
        self,
        powerup_type: str,
        now: int,
        shield_ready: bool,
    ) -> tuple[str, bool, int, str]:
        if powerup_type == "speed":
            return "Speed Boost", shield_ready, now + POWERUP_DURATION_MS, "Speed boost for 5 seconds"
        if powerup_type == "slow":
            return "Slow Motion", shield_ready, now + POWERUP_DURATION_MS, "Slow motion for 5 seconds"
        return "Shield", True, 0, "Shield will block the next collision"

    def generate_obstacles(self, level: int, snake: Snake) -> set[tuple[int, int]]:
        count = min(6 + (level - 3) * 2, 24)
        protected = set()
        for col in range(snake.head[0] - 2, snake.head[0] + 3):
            for row in range(snake.head[1] - 2, snake.head[1] + 3):
                if 0 < col < COLS - 1 and 0 < row < ROWS - 1:
                    protected.add((col, row))

        candidates = [
            (col, row)
            for col in range(1, COLS - 1)
            for row in range(1, ROWS - 1)
            if (col, row) not in snake.body_cells and (col, row) not in protected
        ]

        for _ in range(250):
            sample = set(random.sample(candidates, k=min(count, len(candidates))))
            if self.obstacles_are_safe(sample, snake):
                return sample
        return set()

    def obstacles_are_safe(self, obstacles: set[tuple[int, int]], snake: Snake) -> bool:
        neighbors = [
            (snake.head[0] + dx, snake.head[1] + dy)
            for dx, dy in (UP, DOWN, LEFT, RIGHT)
        ]
        free_neighbors = 0
        blocked = snake.body_cells | obstacles
        for col, row in neighbors:
            if 0 < col < COLS - 1 and 0 < row < ROWS - 1 and (col, row) not in blocked:
                free_neighbors += 1
        if free_neighbors < 2:
            return False

        frontier = [snake.head]
        seen = {snake.head}
        while frontier:
            cell = frontier.pop()
            for dx, dy in (UP, DOWN, LEFT, RIGHT):
                nxt = (cell[0] + dx, cell[1] + dy)
                if nxt in seen or nxt in blocked:
                    continue
                if not (0 < nxt[0] < COLS - 1 and 0 < nxt[1] < ROWS - 1):
                    continue
                seen.add(nxt)
                frontier.append(nxt)
        return len(seen) >= max(45, len(snake.body) * 4)

    def draw_game(
        self,
        *,
        snake: Snake,
        food: Food,
        poison_pos: tuple[int, int] | None,
        powerup: PowerUp | None,
        obstacles: set[tuple[int, int]],
        score: int,
        level: int,
        foods_this_level: int,
        personal_best: int,
        effect_name: str,
        shield_ready: bool,
        message: str,
        now: int,
    ) -> None:
        self.screen.fill(BACKGROUND)
        pygame.draw.rect(self.screen, HUD_COLOR, (0, 0, SCREEN_WIDTH, HUD_HEIGHT))
        pygame.draw.line(self.screen, BORDER_COLOR, (0, HUD_HEIGHT), (SCREEN_WIDTH, HUD_HEIGHT), 2)

        if self.settings["grid_overlay"]:
            self.draw_grid()
        self.draw_border()
        self.draw_obstacles(obstacles)
        self.draw_food(food, now)
        if poison_pos:
            self.draw_poison(poison_pos, now)
        if powerup:
            self.draw_powerup(powerup)
        snake.draw(self.screen)

        score_text = self.font_hud.render(f"Score: {score}", True, TEXT_COLOR)
        level_text = self.font_hud.render(f"Level: {level}", True, ACCENT)
        best_text = self.font_hud.render(f"Best: {personal_best}", True, SUCCESS)
        self.screen.blit(score_text, (12, 10))
        self.screen.blit(level_text, (12, 30))
        self.screen.blit(best_text, (110, 10))

        bar_x = 240
        bar_y = 16
        bar_w = 130
        fill = int(bar_w * foods_this_level / FOODS_PER_LEVEL)
        pygame.draw.rect(self.screen, (55, 67, 86), (bar_x, bar_y, bar_w, 12), border_radius=6)
        pygame.draw.rect(self.screen, ACCENT, (bar_x, bar_y, fill, 12), border_radius=6)
        pygame.draw.rect(self.screen, TEXT_COLOR, (bar_x, bar_y, bar_w, 12), 1, border_radius=6)
        prog_text = self.font_small.render("Level progress", True, MUTED_TEXT)
        self.screen.blit(prog_text, (bar_x, 34))

        effect_text = effect_name if effect_name else "None"
        shield_text = "Ready" if shield_ready else "Off"
        right_block = [
            f"Effect: {effect_text}",
            f"Shield: {shield_text}",
            f"Player: {self.username}",
        ]
        for index, line in enumerate(right_block):
            label = self.font_small.render(line, True, TEXT_COLOR if index == 0 else MUTED_TEXT)
            self.screen.blit(label, (410, 10 + index * 18))

        if message:
            msg = self.font_small.render(message, True, TEXT_COLOR)
            self.screen.blit(msg, msg.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 14)))

    def draw_grid(self) -> None:
        for col in range(COLS):
            for row in range(ROWS):
                rect = pygame.Rect(col * CELL, row * CELL + HUD_HEIGHT, CELL, CELL)
                pygame.draw.rect(self.screen, GRID_COLOR, rect, 1)

    def draw_border(self) -> None:
        for col in range(COLS):
            self.draw_block((col, 0), BORDER_COLOR)
            self.draw_block((col, ROWS - 1), BORDER_COLOR)
        for row in range(ROWS):
            self.draw_block((0, row), BORDER_COLOR)
            self.draw_block((COLS - 1, row), BORDER_COLOR)

    def draw_obstacles(self, obstacles: set[tuple[int, int]]) -> None:
        for cell in obstacles:
            self.draw_block(cell, OBSTACLE_COLOR)

    def draw_block(self, pos: tuple[int, int], color: tuple[int, int, int]) -> None:
        rect = pygame.Rect(pos[0] * CELL, pos[1] * CELL + HUD_HEIGHT, CELL, CELL)
        pygame.draw.rect(self.screen, color, rect)
        pygame.draw.rect(self.screen, BACKGROUND, rect, 1)

    def draw_food(self, food: Food, now: int) -> None:
        center = (
            food.pos[0] * CELL + CELL // 2,
            food.pos[1] * CELL + CELL // 2 + HUD_HEIGHT,
        )
        pulse = abs(pygame.math.Vector2(1, 0).rotate(now / 7).x)
        radius = int(CELL // 2 - 2 + 2 * pulse)
        fraction = max(0.0, food.fraction_left(now))
        faded = self.interpolate((90, 90, 90), food.color, fraction)
        highlight = self.interpolate((120, 120, 120), food.highlight, fraction)
        pygame.draw.circle(self.screen, faded, center, radius)
        pygame.draw.circle(self.screen, highlight, (center[0] - 3, center[1] - 3), max(2, radius // 3))
        ring = max(0, int((CELL // 2 + 2) * fraction))
        if ring > 0:
            pygame.draw.circle(self.screen, faded, center, ring, 2)

    def draw_poison(self, pos: tuple[int, int], now: int) -> None:
        center = (pos[0] * CELL + CELL // 2, pos[1] * CELL + CELL // 2 + HUD_HEIGHT)
        pulse = abs(pygame.math.Vector2(1, 0).rotate(now / 6).x)
        radius = int(CELL // 2 - 3 + 2 * pulse)
        pygame.draw.circle(self.screen, POISON_COLOR, center, radius)
        pygame.draw.circle(self.screen, POISON_HIGHLIGHT, (center[0] - 2, center[1] - 2), max(2, radius // 3))

    def draw_powerup(self, powerup: PowerUp) -> None:
        rect = pygame.Rect(powerup.pos[0] * CELL, powerup.pos[1] * CELL + HUD_HEIGHT, CELL, CELL).inflate(-3, -3)
        pygame.draw.rect(self.screen, powerup.color, rect, border_radius=6)
        label = self.font_small.render(powerup.symbol, True, BACKGROUND)
        self.screen.blit(label, label.get_rect(center=rect.center))

    def interpolate(
        self,
        low: tuple[int, int, int],
        high: tuple[int, int, int],
        factor: float,
    ) -> tuple[int, int, int]:
        return tuple(int(low[index] + (high[index] - low[index]) * factor) for index in range(3))

    def draw_title(self, title: str, subtitle: str) -> None:
        title_text = self.font_title.render(title, True, TEXT_COLOR)
        subtitle_text = self.font_small.render(subtitle, True, MUTED_TEXT)
        self.screen.blit(title_text, title_text.get_rect(center=(SCREEN_WIDTH // 2, 60)))
        self.screen.blit(subtitle_text, subtitle_text.get_rect(center=(SCREEN_WIDTH // 2, 96)))

    def draw_footer(self, line_one: str, line_two: str) -> None:
        top = self.font_small.render(line_one, True, MUTED_TEXT)
        bottom = self.font_small.render(line_two, True, MUTED_TEXT)
        self.screen.blit(top, top.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 34)))
        self.screen.blit(bottom, bottom.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 16)))
