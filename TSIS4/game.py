# game.py — Вся игровая логика и отрисовка.
# Содержит: классы данных Food, PowerUp, Button, Snake и главный класс SnakeApp.

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import random
import sys

import pygame

# Импортируем все константы из config.py (цвета, размеры, таймеры и т.д.)
from config import (
    ACCENT, BACKGROUND, BASE_SPEED, BORDER_COLOR, CELL, COLS,
    DEFAULT_SETTINGS, EAT_SOUND_FILE, FOODS_PER_LEVEL, GRID_COLOR,
    HUD_COLOR, HUD_HEIGHT, MAX_USERNAME_LEN, MUTED_TEXT, OBSTACLE_COLOR,
    POISON_COLOR, POISON_HIGHLIGHT, POISON_RESPAWN_MS, POWERUP_DURATION_MS,
    POWERUP_FIELD_MS, POWERUP_RESPAWN_RANGE_MS, ROWS, SCREEN_HEIGHT,
    SCREEN_WIDTH, SETTINGS_FILE, SPEED_STEP, SUCCESS, TEXT_COLOR,
    TOP_LEADERBOARD_LIMIT,
)
from db import DatabaseManager


# ---------------------------------------------------------------------------
# Константы направлений
# (dx, dy) — смещение головы за один шаг
# ---------------------------------------------------------------------------
UP    = (0, -1)
DOWN  = (0,  1)
LEFT  = (-1, 0)
RIGHT = (1,  0)
# Словарь «противоположных» направлений — чтобы запретить разворот на 180°
OPPOSITE = {UP: DOWN, DOWN: UP, LEFT: RIGHT, RIGHT: LEFT}


# ---------------------------------------------------------------------------
# Данные о типах еды
# weight — вес при взвешенном случайном выборе (50+30+20 = 100)
# lifespan_ms — сколько миллисекунд еда живёт на поле
# ---------------------------------------------------------------------------
FOOD_TYPES = [
    {"label": "Common", "color": (240, 70,  70),  "highlight": (255, 150, 150),
     "value": 10, "lifespan_ms": 8000, "weight": 50},
    {"label": "Rare",   "color": (100, 180, 255), "highlight": (185, 225, 255),
     "value": 25, "lifespan_ms": 5000, "weight": 30},
    {"label": "Legend", "color": (255, 215,   0), "highlight": (255, 245, 150),
     "value": 50, "lifespan_ms": 3000, "weight": 20},
]

# Три вида бустеров: ускорение, замедление, щит
POWERUP_TYPES = [
    {"name": "speed",  "label": "Speed Boost",  "color": (255, 130,  40), "symbol": ">>"},
    {"name": "slow",   "label": "Slow Motion",  "color": ( 70, 160, 255), "symbol": "<<"},
    {"name": "shield", "label": "Shield",       "color": (130, 255, 180), "symbol": "S"},
]


# ---------------------------------------------------------------------------
# Класс Food — единица еды на поле
# @dataclass автоматически генерирует __init__, __repr__, __eq__
# ---------------------------------------------------------------------------
@dataclass
class Food:
    pos: tuple[int, int]           # Позиция в клетках (col, row)
    value: int                     # Очки за поедание (до умножения на уровень)
    color: tuple[int, int, int]
    highlight: tuple[int, int, int]
    lifespan_ms: int               # Время жизни в миллисекундах
    spawned_at: int                # pygame.time.get_ticks() в момент спавна
    label: str                     # "Common" / "Rare" / "Legend"

    def expired(self, now: int) -> bool:
        """Возвращает True, если еда «протухла» и должна быть заменена."""
        return now - self.spawned_at >= self.lifespan_ms

    def fraction_left(self, now: int) -> float:
        """
        Доля оставшегося времени жизни (от 1.0 до 0.0).
        Используется для плавного угасания цвета при отрисовке.
        """
        age = min(self.lifespan_ms, max(0, now - self.spawned_at))
        return 1.0 - age / self.lifespan_ms


# ---------------------------------------------------------------------------
# Класс PowerUp — бустер на поле
# ---------------------------------------------------------------------------
@dataclass
class PowerUp:
    pos: tuple[int, int]
    kind: str                    # "speed" | "slow" | "shield"
    color: tuple[int, int, int]
    label: str
    symbol: str                  # Символ на иконке бустера (">>" / "<<" / "S")
    spawned_at: int

    def expired(self, now: int) -> bool:
        """Бустер исчезает с поля через POWERUP_FIELD_MS мс, если не подобран."""
        return now - self.spawned_at >= POWERUP_FIELD_MS


# ---------------------------------------------------------------------------
# Класс Button — кнопка интерфейса
# ---------------------------------------------------------------------------
class Button:
    def __init__(self, x: int, y: int, width: int, height: int, text: str) -> None:
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text

    def draw(self, surface, font, hovered: bool = False) -> None:
        """Рисует кнопку: подсвечивает при наведении курсора."""
        fill = (68, 87, 114) if hovered else (44, 57, 76)
        pygame.draw.rect(surface, fill, self.rect, border_radius=12)
        pygame.draw.rect(surface, BORDER_COLOR, self.rect, 2, border_radius=12)
        label = font.render(self.text, True, TEXT_COLOR)
        surface.blit(label, label.get_rect(center=self.rect.center))

    def contains(self, position: tuple[int, int]) -> bool:
        """Возвращает True, если точка position находится внутри кнопки."""
        return self.rect.collidepoint(position)


# ---------------------------------------------------------------------------
# Класс Snake — змейка игрока
# ---------------------------------------------------------------------------
class Snake:
    def __init__(self, color: tuple[int, int, int]) -> None:
        # Стартовая позиция — три клетки горизонтально в центре поля
        center_col = COLS // 2
        center_row = ROWS // 2
        self.body = [
            (center_col,     center_row),   # Голова
            (center_col - 1, center_row),   # Тело
            (center_col - 2, center_row),   # Хвост
        ]
        self.direction = RIGHT       # Начальное направление — вправо
        self.pending_growth = 0      # Сколько клеток ещё нужно добавить при движении
        self.color = color

    @property
    def head(self) -> tuple[int, int]:
        """Координаты головы (первый элемент списка тела)."""
        return self.body[0]

    @property
    def body_cells(self) -> set[tuple[int, int]]:
        """Множество всех клеток тела — для быстрой проверки столкновений."""
        return set(self.body)

    def turn(self, direction: tuple[int, int]) -> None:
        """
        Меняет направление движения.
        Разворот на 180° запрещён — проверяем через словарь OPPOSITE.
        """
        if direction != OPPOSITE[self.direction]:
            self.direction = direction

    def move(self) -> tuple[int, int]:
        """
        Делает один шаг: добавляет новую голову в начало списка,
        убирает хвост (если нет ожидающего роста).
        Возвращает координаты новой головы.
        """
        dx, dy = self.direction
        new_head = (self.head[0] + dx, self.head[1] + dy)
        self.body.insert(0, new_head)
        if self.pending_growth > 0:
            self.pending_growth -= 1   # Расходуем «кредит» роста
        else:
            self.body.pop()            # Убираем хвост — длина не меняется
        return new_head

    def grow(self, amount: int = 1) -> None:
        """Запланировать рост на amount клеток (выполняется при следующих шагах)."""
        self.pending_growth += amount

    def shrink(self, amount: int) -> None:
        """Уменьшить змейку на amount клеток (эффект яда). Сбрасывает pending_growth."""
        for _ in range(amount):
            if len(self.body) > 0:
                self.body.pop()
        self.pending_growth = 0

    def self_collision(self) -> bool:
        """Возвращает True, если голова пересеклась с телом (смерть)."""
        return self.head in self.body[1:]

    def draw(self, surface: pygame.Surface) -> None:
        """
        Рисует змейку:
        - Голова — основной цвет, с двумя «глазами».
        - Тело — чуть темнее (каждый канал уменьшен на 38).
        - inflate(-2, -2) создаёт небольшой зазор между клетками.
        """
        body_color = tuple(max(20, channel - 38) for channel in self.color)
        for index, (col, row) in enumerate(self.body):
            rect = pygame.Rect(col * CELL, row * CELL + HUD_HEIGHT, CELL, CELL).inflate(-2, -2)
            pygame.draw.rect(
                surface,
                self.color if index == 0 else body_color,
                rect,
                border_radius=5,
            )
            # Рисуем глаза только на голове (index == 0)
            if index == 0:
                for offset in (-4, 4):
                    eye = (rect.centerx + offset, rect.centery - 3)
                    pygame.draw.circle(surface, TEXT_COLOR, eye, 3)   # Белок
                    pygame.draw.circle(surface, BACKGROUND, eye, 1)   # Зрачок


# ---------------------------------------------------------------------------
# Главный класс приложения
# ---------------------------------------------------------------------------
class SnakeApp:
    """
    Управляет всеми экранами (меню, игра, таблица рекордов, настройки, game over)
    через простой конечный автомат: self.state = "menu" | "play" | "leaderboard" |
    "settings" | "game_over".
    """

    def __init__(self, database: DatabaseManager) -> None:
        pygame.init()

        # Пытаемся инициализировать аудио; если устройство недоступно — продолжаем без звука
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

        # Шрифты разных размеров для разных нужд UI
        self.font_title    = pygame.font.SysFont("Verdana", 38, bold=True)
        self.font_subtitle = pygame.font.SysFont("Verdana", 24, bold=True)
        self.font_body     = pygame.font.SysFont("Verdana", 18)
        self.font_small    = pygame.font.SysFont("Verdana", 15)
        self.font_hud      = pygame.font.SysFont("Verdana", 16, bold=True)

        self.running = True
        self.state = "menu"          # Начальный экран — главное меню
        self.username = ""
        self.menu_message = "Enter a username to start."
        self.last_game: dict[str, int | str] | None = None   # Данные последней сессии для game_over
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        self.audio_message = ""
        self.load_sounds()

    # ------------------------------------------------------------------
    # Главный цикл приложения — конечный автомат состояний
    # ------------------------------------------------------------------

    def run(self) -> None:
        """
        Диспетчер экранов. Каждый экран реализован в отдельном методе-цикле.
        Когда метод возвращает управление, run() снова проверяет self.state
        и вызывает нужный экран.
        """
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

    # ------------------------------------------------------------------
    # Загрузка и сохранение настроек
    # ------------------------------------------------------------------

    def load_settings(self) -> dict:
        """
        Читает settings.json. При ошибке или отсутствии файла
        возвращает DEFAULT_SETTINGS.
        Затем валидирует значения: цвет — зажимаем в [0, 255],
        булевы поля — принудительно bool().
        """
        if SETTINGS_FILE.exists():
            try:
                data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}
        else:
            data = {}

        merged = DEFAULT_SETTINGS.copy()
        merged.update(data)  # Пользовательские значения перекрывают дефолты
        # Зажимаем каждый канал RGB в диапазон [0, 255]
        merged["snake_color"] = [
            max(0, min(255, int(value)))
            for value in merged.get("snake_color", DEFAULT_SETTINGS["snake_color"])
        ]
        merged["grid_overlay"] = bool(merged.get("grid_overlay", True))
        merged["sound"]        = bool(merged.get("sound", False))
        return merged

    def save_settings(self) -> None:
        """Записывает текущие настройки в settings.json (с отступами для читаемости)."""
        SETTINGS_FILE.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # Звук
    # ------------------------------------------------------------------

    def load_sounds(self) -> None:
        """
        Загружает звуковой файл eats.mp3.
        Если аудио недоступно или файл не найден — устанавливает
        информационное сообщение (отображается в настройках).
        """
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
        """Воспроизводит звук по имени, если звук включён в настройках."""
        if not self.settings.get("sound", False):
            return
        sound = self.sounds.get(name)
        if sound is not None:
            sound.play()

    # ------------------------------------------------------------------
    # Экран: Главное меню
    # ------------------------------------------------------------------

    def menu_loop(self) -> None:
        """
        Рисует главное меню с полем ввода имени и четырьмя кнопками.
        Ввод имени обрабатывается напрямую через KEYDOWN-события.
        Нажатие Enter или кнопки Play → start_game_from_menu().
        """
        play_button         = Button(200, 250, 200, 44, "Play")
        leaderboard_button  = Button(200, 308, 200, 44, "Leaderboard")
        settings_button     = Button(200, 366, 200, 44, "Settings")
        quit_button         = Button(200, 424, 200, 44, "Quit")
        input_rect = pygame.Rect(160, 170, 280, 46)  # Поле ввода имени

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
                        self.username = self.username[:-1]   # Удаляем последний символ
                    elif event.unicode.isprintable() and len(self.username) < MAX_USERNAME_LEN:
                        if event.unicode not in "\r\t":
                            self.username += event.unicode   # Добавляем введённый символ
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if play_button.contains(event.pos):
                        self.start_game_from_menu()
                    elif leaderboard_button.contains(event.pos):
                        self.state = "leaderboard"
                    elif settings_button.contains(event.pos):
                        self.state = "settings"
                    elif quit_button.contains(event.pos):
                        self.running = False

            # --- Отрисовка ---
            self.screen.fill(BACKGROUND)
            self.draw_title("TSIS 4 Snake", "Database, power-ups, poison, obstacles")

            # Поле ввода имени
            label = self.font_body.render("Username", True, TEXT_COLOR)
            self.screen.blit(label, (input_rect.x, input_rect.y - 26))
            pygame.draw.rect(self.screen, (28, 34, 48), input_rect, border_radius=10)
            pygame.draw.rect(self.screen, BORDER_COLOR, input_rect, 2, border_radius=10)
            # Плейсхолдер серым, реальный текст — белым
            text = self.font_body.render(
                self.username or "Type here...",
                True,
                TEXT_COLOR if self.username else MUTED_TEXT,
            )
            self.screen.blit(text, (input_rect.x + 12, input_rect.y + 12))

            for button in (play_button, leaderboard_button, settings_button, quit_button):
                button.draw(self.screen, self.font_body, button.contains(mouse_pos))

            # В нижнем колонтитуле — сообщение меню и статус БД
            db_line = self.database.status_message
            if self.database.last_error:
                db_line = f"{db_line} Check PostgreSQL config in config.py or env vars."
            self.draw_footer(self.menu_message, db_line)

            pygame.display.flip()
            self.clock.tick(60)   # 60 FPS для UI достаточно

    def start_game_from_menu(self) -> None:
        """
        Валидирует имя перед стартом игры.
        Если имя пустое — показывает сообщение об ошибке, игру не запускает.
        """
        cleaned = self.username.strip()
        if not cleaned:
            self.menu_message = "Username is required."
            return
        self.username = cleaned[:MAX_USERNAME_LEN]
        self.state = "play"
        self.menu_message = "Enter a username to start."

    # ------------------------------------------------------------------
    # Экран: Таблица рекордов
    # ------------------------------------------------------------------

    def leaderboard_loop(self) -> None:
        """
        Загружает топ-10 из БД и отображает в виде таблицы.
        Если БД недоступна — показывает соответствующее сообщение.
        """
        back_button  = Button(220, 518, 160, 42, "Back")
        leaderboard  = self.database.get_leaderboard(TOP_LEADERBOARD_LIMIT)

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

            # Фоновая карточка таблицы
            table_rect = pygame.Rect(48, 130, 504, 360)
            pygame.draw.rect(self.screen, (24, 30, 42), table_rect, border_radius=16)
            pygame.draw.rect(self.screen, BORDER_COLOR, table_rect, 2, border_radius=16)

            # Заголовки столбцов
            headers = ["Rank", "Username", "Score", "Level", "Date"]
            columns = [68, 170, 90, 80, 140]   # Ширина каждого столбца в пикселях
            x = table_rect.x + 16
            for header, width in zip(headers, columns):
                header_text = self.font_small.render(header, True, ACCENT)
                self.screen.blit(header_text, (x, table_rect.y + 18))
                x += width

            if leaderboard:
                for index, row in enumerate(leaderboard, start=1):
                    y = table_rect.y + 52 + (index - 1) * 28
                    # Форматируем дату: datetime → "YYYY-MM-DD", строка → первые 10 символов
                    played_at = row["played_at"]
                    date_text = (
                        played_at.strftime("%Y-%m-%d")
                        if isinstance(played_at, datetime)
                        else str(played_at)[:10]
                    )
                    values = [
                        str(index),
                        str(row["username"])[:14],    # Обрезаем длинные имена
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
                # Если данных нет — показываем причину по центру таблицы
                message = "No data yet." if self.database.available else "Database unavailable."
                text = self.font_subtitle.render(message, True, MUTED_TEXT)
                self.screen.blit(text, text.get_rect(center=table_rect.center))

            back_button.draw(self.screen, self.font_body, back_button.contains(mouse_pos))
            self.draw_footer("Scores are saved automatically after game over.", self.database.status_message)
            pygame.display.flip()
            self.clock.tick(60)

    # ------------------------------------------------------------------
    # Экран: Настройки
    # ------------------------------------------------------------------

    def settings_loop(self) -> None:
        """
        Позволяет переключить сетку и звук, а также настроить цвет змейки
        по каналам R, G, B (кнопки +/- с шагом 15).
        Изменения сохраняются в settings.json по кнопке «Save & Back».
        """
        save_button   = Button(198, 508, 204, 42, "Save & Back")
        toggle_grid   = Button(350, 170, 130, 40, "Toggle")
        toggle_sound  = Button(350, 232, 130, 40, "Toggle")
        # Кнопки +/- для трёх каналов цвета змейки
        color_buttons = {
            "r_minus": Button(310, 314, 52, 38, "-"),
            "r_plus":  Button(428, 314, 52, 38, "+"),
            "g_minus": Button(310, 366, 52, 38, "-"),
            "g_plus":  Button(428, 366, 52, 38, "+"),
            "b_minus": Button(310, 418, 52, 38, "-"),
            "b_plus":  Button(428, 418, 52, 38, "+"),
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

            # --- Отрисовка ---
            self.screen.fill(BACKGROUND)
            self.draw_title("Settings", "Saved to settings.json")

            grid_text  = f"Grid Overlay: {'On' if self.settings['grid_overlay'] else 'Off'}"
            sound_text = f"Sound: {'On' if self.settings['sound'] else 'Off'}"
            self.screen.blit(self.font_body.render(grid_text,  True, TEXT_COLOR), (120, 180))
            self.screen.blit(self.font_body.render(sound_text, True, TEXT_COLOR), (120, 242))
            toggle_grid.draw(self.screen,  self.font_small, toggle_grid.contains(mouse_pos))
            toggle_sound.draw(self.screen, self.font_small, toggle_sound.contains(mouse_pos))

            # Показываем текущие значения R, G, B
            channels = self.settings["snake_color"]
            for label, value, y in [("R", channels[0], 320), ("G", channels[1], 372), ("B", channels[2], 424)]:
                text = self.font_body.render(f"{label}: {value}", True, TEXT_COLOR)
                self.screen.blit(text, (120, y))

            for button in color_buttons.values():
                button.draw(self.screen, self.font_small, button.contains(mouse_pos))

            # Превью цвета змейки
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
        """
        При нажатии на кнопку +/- изменяет соответствующий канал цвета змейки
        на ±15 и зажимает значение в [0, 255].
        delta_map связывает имя кнопки с (индекс_канала, изменение).
        """
        delta_map = {
            "r_minus": (0, -15), "r_plus": (0,  15),
            "g_minus": (1, -15), "g_plus": (1,  15),
            "b_minus": (2, -15), "b_plus": (2,  15),
        }
        for key, button in buttons.items():
            if button.contains(position):
                index, delta = delta_map[key]
                self.settings["snake_color"][index] = max(
                    0, min(255, self.settings["snake_color"][index] + delta)
                )
                break

    # ------------------------------------------------------------------
    # Экран: Игра
    # ------------------------------------------------------------------

    def play_loop(self) -> None:
        """
        Основной игровой цикл. Структура:
          1. Обработка событий (клавиши направления, Escape).
          2. Тайм-менеджмент: обновление еды, яда, бустеров, эффектов.
          3. Движение змейки (раз в 1000/speed мс).
          4. Проверка столкновений → game over или щит.
          5. Проверка подбора еды / яда / бустера.
          6. Отрисовка кадра.
        """
        # --- Инициализация переменных сессии ---
        personal_best = self.database.get_personal_best(self.username)
        snake = Snake(tuple(self.settings["snake_color"]))
        score = 0
        level = 1
        foods_this_level = 0       # Счётчик съеденного на текущем уровне
        level_message = ""         # Всплывающее сообщение в нижней части экрана
        shield_ready = False       # Активен ли щит
        effect_name  = ""          # Название активного эффекта ("Speed Boost" / "Slow Motion" / "Shield")
        effect_ends_at = 0         # Время (ticks) окончания эффекта

        powerup: PowerUp | None = None
        # Бустер появляется через случайное время после старта
        powerup_next_spawn = pygame.time.get_ticks() + random.randint(*POWERUP_RESPAWN_RANGE_MS)

        poison_pos: tuple[int, int] | None = None
        # Яд появляется через 3 секунды после старта
        poison_next_spawn = pygame.time.get_ticks() + 3000

        obstacles: set[tuple[int, int]] = set()   # Препятствия (активны с 3-го уровня)
        last_move_at = pygame.time.get_ticks()
        food = self.spawn_food(snake, obstacles)

        while self.running and self.state == "play":
            now = pygame.time.get_ticks()   # Текущее время в миллисекундах

            # --- Обработка событий ---
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.state = "menu"
                        return
                    # WASD и стрелки управляют направлением
                    if event.key in (pygame.K_UP,    pygame.K_w): snake.turn(UP)
                    elif event.key in (pygame.K_DOWN,  pygame.K_s): snake.turn(DOWN)
                    elif event.key in (pygame.K_LEFT,  pygame.K_a): snake.turn(LEFT)
                    elif event.key in (pygame.K_RIGHT, pygame.K_d): snake.turn(RIGHT)

            occupied = self.occupied_cells(food, poison_pos, powerup)

            # --- Обновление состояния объектов ---

            # Еда «протухла» → заменяем новой
            if food.expired(now):
                food = self.spawn_food(snake, obstacles, self.occupied_cells(None, poison_pos, powerup))
                occupied = self.occupied_cells(food, poison_pos, powerup)

            # Яд: пора спавнить → ищем свободную клетку
            if poison_pos is None and now >= poison_next_spawn:
                poison_pos = self.random_free_cell(
                    snake, obstacles, self.occupied_cells(food, None, powerup), exclude_radius=1
                )
                poison_next_spawn = now + POISON_RESPAWN_MS
                occupied = self.occupied_cells(food, poison_pos, powerup)

            # Бустер истёк на поле → удаляем, планируем следующий
            if powerup and powerup.expired(now):
                powerup = None
                powerup_next_spawn = now + random.randint(*POWERUP_RESPAWN_RANGE_MS)
                occupied = self.occupied_cells(food, poison_pos, powerup)

            # Пора спавнить следующий бустер
            if powerup is None and now >= powerup_next_spawn:
                powerup = self.spawn_powerup(snake, obstacles, self.occupied_cells(food, poison_pos, None))
                occupied = self.occupied_cells(food, poison_pos, powerup)

            # Эффект скорости/замедления закончился (щит не имеет таймера)
            if effect_name and now >= effect_ends_at and effect_name != "Shield":
                effect_name    = ""
                effect_ends_at = 0

            # --- Движение змейки (rate-limited) ---
            speed      = self.current_speed(level, effect_name)   # клеток/сек
            move_delay = int(1000 / speed)                        # мс между шагами

            if now - last_move_at >= move_delay:
                previous_body = snake.body[:]   # Сохраняем тело для отката при щите
                new_head = snake.move()
                last_move_at = now

                # --- Проверка столкновений ---
                collision = self.detect_collision(new_head, snake, obstacles)
                if collision:
                    if shield_ready:
                        # Щит поглощает удар: откатываем тело, сбрасываем эффект
                        shield_ready  = False
                        effect_name   = ""
                        snake.body    = previous_body
                        level_message = "Shield absorbed the collision."
                    else:
                        # Смерть: сохраняем результат и переходим на экран game_over
                        saved = self.database.save_session(self.username, score, level)
                        personal_best = max(personal_best, score)
                        self.last_game = {
                            "username":      self.username,
                            "score":         score,
                            "level":         level,
                            "personal_best": personal_best,
                            "saved":         "yes" if saved else "no",
                        }
                        self.state = "game_over"
                        return
                else:
                    # --- Подбор еды ---
                    if new_head == food.pos:
                        snake.grow()
                        score += food.value * level           # Очки масштабируются с уровнем
                        foods_this_level += 1
                        personal_best = max(personal_best, score)
                        self.play_sound("eat")
                        level_message = f"+{food.value * level} from {food.label.lower()} food"
                        food = self.spawn_food(snake, obstacles, self.occupied_cells(None, poison_pos, powerup))

                        # Проверяем переход на следующий уровень
                        if foods_this_level >= FOODS_PER_LEVEL:
                            level += 1
                            foods_this_level = 0
                            level_message = f"Level {level}"
                            if level >= 3:
                                # С 3-го уровня добавляем/обновляем препятствия
                                obstacles = self.generate_obstacles(level, snake)
                                # Если яд или бустер попали в препятствие — убираем их
                                if poison_pos in obstacles:
                                    poison_pos = None
                                    poison_next_spawn = now + POISON_RESPAWN_MS
                                if powerup and powerup.pos in obstacles:
                                    powerup = None
                                    powerup_next_spawn = now + random.randint(*POWERUP_RESPAWN_RANGE_MS)
                                food = self.spawn_food(snake, obstacles, self.occupied_cells(None, poison_pos, powerup))

                    # --- Подбор яда ---
                    if poison_pos and new_head == poison_pos:
                        snake.shrink(2)   # Змейка уменьшается на 2 клетки
                        poison_pos = None
                        poison_next_spawn = now + POISON_RESPAWN_MS
                        level_message = "Poison food: -2 segments"
                        # Если змейка стала слишком маленькой — смерть
                        if len(snake.body) <= 1:
                            saved = self.database.save_session(self.username, score, level)
                            personal_best = max(personal_best, score)
                            self.last_game = {
                                "username": self.username, "score": score, "level": level,
                                "personal_best": personal_best, "saved": "yes" if saved else "no",
                            }
                            self.state = "game_over"
                            return

                    # --- Подбор бустера ---
                    if powerup and new_head == powerup.pos:
                        powerup_name, shield_ready, effect_ends_at, level_message = self.activate_powerup(
                            powerup.kind, now, shield_ready
                        )
                        effect_name = powerup_name
                        powerup = None
                        powerup_next_spawn = now + random.randint(*POWERUP_RESPAWN_RANGE_MS)

            # --- Отрисовка кадра ---
            self.draw_game(
                snake=snake, food=food, poison_pos=poison_pos, powerup=powerup,
                obstacles=obstacles, score=score, level=level,
                foods_this_level=foods_this_level, personal_best=personal_best,
                effect_name=effect_name, shield_ready=shield_ready,
                message=level_message, now=now,
            )
            pygame.display.flip()
            self.clock.tick(60)

    # ------------------------------------------------------------------
    # Экран: Game Over
    # ------------------------------------------------------------------

    def game_over_loop(self) -> None:
        """
        Показывает итоги игры: очки, уровень, личный рекорд, статус сохранения.
        Кнопки: Retry (сразу в play с тем же именем) и Main Menu.
        """
        retry_button = Button(175, 380, 110, 44, "Retry")
        menu_button  = Button(315, 380, 110, 44, "Main Menu")

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

            # Карточка с результатами
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
            menu_button.draw(self.screen,  self.font_body,  menu_button.contains(mouse_pos))
            self.draw_footer("Retry uses the same username.", self.database.status_message)
            pygame.display.flip()
            self.clock.tick(60)

    # ------------------------------------------------------------------
    # Вспомогательные методы: спавн объектов
    # ------------------------------------------------------------------

    def spawn_food(
        self,
        snake: Snake,
        obstacles: set[tuple[int, int]],
        occupied: set[tuple[int, int]] | None = None,
    ) -> Food:
        """
        Спавнит новую еду на случайной свободной клетке.
        Тип выбирается взвешенным случайным выбором (Common 50%, Rare 30%, Legend 20%).
        """
        occupied = occupied or set()
        cell = self.random_free_cell(snake, obstacles, occupied)
        spec = random.choices(FOOD_TYPES, weights=[item["weight"] for item in FOOD_TYPES], k=1)[0]
        return Food(
            pos=cell, value=spec["value"], color=spec["color"],
            highlight=spec["highlight"], lifespan_ms=spec["lifespan_ms"],
            spawned_at=pygame.time.get_ticks(), label=spec["label"],
        )

    def spawn_powerup(
        self,
        snake: Snake,
        obstacles: set[tuple[int, int]],
        occupied: set[tuple[int, int]],
    ) -> PowerUp:
        """
        Спавнит случайный бустер. exclude_radius=1 — не ставим бустер
        вплотную к голове змейки (чтоб не подобрать случайно).
        """
        spec = random.choice(POWERUP_TYPES)
        cell = self.random_free_cell(snake, obstacles, occupied, exclude_radius=1)
        return PowerUp(
            pos=cell, kind=spec["name"], color=spec["color"],
            label=spec["label"], symbol=spec["symbol"],
            spawned_at=pygame.time.get_ticks(),
        )

    def random_free_cell(
        self,
        snake: Snake,
        obstacles: set[tuple[int, int]],
        occupied: set[tuple[int, int]] | None = None,
        exclude_radius: int = 0,
    ) -> tuple[int, int]:
        """
        Возвращает случайную клетку, которая не занята змейкой,
        препятствием, другим объектом или зоной вокруг головы (exclude_radius).
        Работает через цикл с rejection sampling — пробует случайные клетки,
        пока не найдёт подходящую.
        """
        occupied   = occupied or set()
        snake_cells = snake.body_cells
        head        = snake.head
        while True:
            pos = (random.randint(1, COLS - 2), random.randint(1, ROWS - 2))
            if pos in snake_cells or pos in obstacles or pos in occupied:
                continue
            if exclude_radius and abs(pos[0] - head[0]) + abs(pos[1] - head[1]) <= exclude_radius:
                continue
            return pos

    def occupied_cells(
        self,
        food: "Food | None",
        poison_pos: tuple[int, int] | None,
        powerup: "PowerUp | None",
    ) -> set[tuple[int, int]]:
        """
        Собирает множество клеток, уже занятых едой, ядом и бустером.
        Используется при спавне новых объектов, чтобы они не перекрывались.
        """
        occupied: set[tuple[int, int]] = set()
        if food:
            occupied.add(food.pos)
        if poison_pos:
            occupied.add(poison_pos)
        if powerup:
            occupied.add(powerup.pos)
        return occupied

    # ------------------------------------------------------------------
    # Вспомогательные методы: логика игры
    # ------------------------------------------------------------------

    def detect_collision(
        self,
        head: tuple[int, int],
        snake: Snake,
        obstacles: set[tuple[int, int]],
    ) -> bool:
        """
        Проверяет три вида столкновений:
        1. Выход за границы поля (крайние клетки — стены).
        2. Наезд на препятствие.
        3. Самостолкновение (голова попала в тело).
        """
        if head[0] <= 0 or head[0] >= COLS - 1 or head[1] <= 0 or head[1] >= ROWS - 1:
            return True
        if head in obstacles:
            return True
        return snake.self_collision()

    def current_speed(self, level: int, effect_name: str) -> int:
        """
        Вычисляет текущую скорость (клеток/сек):
        base + (level-1)*step ± бонус бустера.
        """
        speed = BASE_SPEED + (level - 1) * SPEED_STEP
        if effect_name == "Speed Boost":
            speed += 4
        elif effect_name == "Slow Motion":
            speed = max(4, speed - 4)   # Минимум 4, чтобы не остановиться
        return speed

    def activate_powerup(
        self,
        powerup_type: str,
        now: int,
        shield_ready: bool,
    ) -> tuple[str, bool, int, str]:
        """
        Активирует подобранный бустер.
        Возвращает: (имя_эффекта, shield_ready, effect_ends_at, сообщение).
        Для щита effect_ends_at=0 — он не имеет таймера, действует до удара.
        """
        if powerup_type == "speed":
            return "Speed Boost", shield_ready, now + POWERUP_DURATION_MS, "Speed boost for 5 seconds"
        if powerup_type == "slow":
            return "Slow Motion", shield_ready, now + POWERUP_DURATION_MS, "Slow motion for 5 seconds"
        return "Shield", True, 0, "Shield will block the next collision"

    def generate_obstacles(self, level: int, snake: Snake) -> set[tuple[int, int]]:
        """
        Генерирует препятствия для уровня ≥ 3.
        Количество: от 8 до 24, растёт с уровнем.
        Защитная зона вокруг головы (5×5) никогда не блокируется.
        До 250 попыток найти безопасную расстановку через obstacles_are_safe().
        """
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
        return set()   # Если не нашли — возвращаем пустое множество (лучше, чем тупик)

    def obstacles_are_safe(self, obstacles: set[tuple[int, int]], snake: Snake) -> bool:
        """
        Проверяет, что расстановка препятствий не блокирует змейку.
        Два условия:
        1. У головы должно быть минимум 2 свободных соседних клетки.
        2. BFS из головы должен достигать достаточно большой области
           (минимум 45 клеток или 4 × длина тела — чтобы было место для манёвра).
        """
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

        # BFS (поиск в ширину) для оценки доступного пространства
        frontier = [snake.head]
        seen     = {snake.head}
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

    # ------------------------------------------------------------------
    # Методы отрисовки
    # ------------------------------------------------------------------

    def draw_game(
        self, *, snake, food, poison_pos, powerup, obstacles,
        score, level, foods_this_level, personal_best,
        effect_name, shield_ready, message, now,
    ) -> None:
        """
        Рисует полный игровой кадр:
        HUD (верхняя панель) → сетка → граница → препятствия →
        еда → яд → бустер → змейка → текстовые метки.
        """
        self.screen.fill(BACKGROUND)
        # HUD-панель
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

        # Текстовые метки в HUD
        self.screen.blit(self.font_hud.render(f"Score: {score}",  True, TEXT_COLOR), (12,  10))
        self.screen.blit(self.font_hud.render(f"Level: {level}",  True, ACCENT),     (12,  30))
        self.screen.blit(self.font_hud.render(f"Best: {personal_best}", True, SUCCESS), (110, 10))

        # Прогресс-бар уровня
        bar_x, bar_y, bar_w = 240, 16, 130
        fill = int(bar_w * foods_this_level / FOODS_PER_LEVEL)
        pygame.draw.rect(self.screen, (55, 67, 86), (bar_x, bar_y, bar_w, 12), border_radius=6)
        pygame.draw.rect(self.screen, ACCENT,       (bar_x, bar_y, fill,  12), border_radius=6)
        pygame.draw.rect(self.screen, TEXT_COLOR,   (bar_x, bar_y, bar_w, 12), 1, border_radius=6)
        self.screen.blit(self.font_small.render("Level progress", True, MUTED_TEXT), (bar_x, 34))

        # Правый блок: эффект, щит, имя игрока
        effect_text = effect_name if effect_name else "None"
        shield_text = "Ready" if shield_ready else "Off"
        for index, line in enumerate([f"Effect: {effect_text}", f"Shield: {shield_text}", f"Player: {self.username}"]):
            label = self.font_small.render(line, True, TEXT_COLOR if index == 0 else MUTED_TEXT)
            self.screen.blit(label, (410, 10 + index * 18))

        if message:
            msg = self.font_small.render(message, True, TEXT_COLOR)
            self.screen.blit(msg, msg.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 14)))

    def draw_grid(self) -> None:
        """Рисует тонкую сетку по всему игровому полю (если включена в настройках)."""
        for col in range(COLS):
            for row in range(ROWS):
                rect = pygame.Rect(col * CELL, row * CELL + HUD_HEIGHT, CELL, CELL)
                pygame.draw.rect(self.screen, GRID_COLOR, rect, 1)

    def draw_border(self) -> None:
        """Закрашивает крайние клетки поля — они являются стенами (смерть при касании)."""
        for col in range(COLS):
            self.draw_block((col, 0),        BORDER_COLOR)
            self.draw_block((col, ROWS - 1), BORDER_COLOR)
        for row in range(ROWS):
            self.draw_block((0,        row), BORDER_COLOR)
            self.draw_block((COLS - 1, row), BORDER_COLOR)

    def draw_obstacles(self, obstacles: set[tuple[int, int]]) -> None:
        """Рисует все препятствия."""
        for cell in obstacles:
            self.draw_block(cell, OBSTACLE_COLOR)

    def draw_block(self, pos: tuple[int, int], color: tuple[int, int, int]) -> None:
        """
        Рисует одну закрашенную клетку.
        Тонкая обводка цветом BACKGROUND создаёт визуальный зазор между блоками.
        """
        rect = pygame.Rect(pos[0] * CELL, pos[1] * CELL + HUD_HEIGHT, CELL, CELL)
        pygame.draw.rect(self.screen, color,      rect)
        pygame.draw.rect(self.screen, BACKGROUND, rect, 1)

    def draw_food(self, food: Food, now: int) -> None:
        """
        Рисует еду с пульсирующим радиусом и угасающим цветом.
        pulse — синусоидальное колебание на основе pygame.math.Vector2.rotate.
        fraction — доля оставшегося времени жизни, используется для интерполяции цвета.
        """
        center = (food.pos[0] * CELL + CELL // 2, food.pos[1] * CELL + CELL // 2 + HUD_HEIGHT)
        pulse   = abs(pygame.math.Vector2(1, 0).rotate(now / 7).x)
        radius  = int(CELL // 2 - 2 + 2 * pulse)
        fraction = max(0.0, food.fraction_left(now))
        faded     = self.interpolate((90, 90, 90),   food.color,      fraction)
        highlight = self.interpolate((120, 120, 120), food.highlight,  fraction)
        pygame.draw.circle(self.screen, faded,     center, radius)
        pygame.draw.circle(self.screen, highlight, (center[0] - 3, center[1] - 3), max(2, radius // 3))
        ring = max(0, int((CELL // 2 + 2) * fraction))
        if ring > 0:
            pygame.draw.circle(self.screen, faded, center, ring, 2)

    def draw_poison(self, pos: tuple[int, int], now: int) -> None:
        """Рисует яд — аналогично еде, но с фиксированными тёмно-красными цветами."""
        center = (pos[0] * CELL + CELL // 2, pos[1] * CELL + CELL // 2 + HUD_HEIGHT)
        pulse  = abs(pygame.math.Vector2(1, 0).rotate(now / 6).x)
        radius = int(CELL // 2 - 3 + 2 * pulse)
        pygame.draw.circle(self.screen, POISON_COLOR,     center, radius)
        pygame.draw.circle(self.screen, POISON_HIGHLIGHT, (center[0] - 2, center[1] - 2), max(2, radius // 3))

    def draw_powerup(self, powerup: PowerUp) -> None:
        """Рисует бустер: цветной квадрат с символом (>>, <<, S) по центру."""
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
        """
        Линейная интерполяция между двумя RGB-цветами.
        factor=0.0 → low (серый), factor=1.0 → high (яркий цвет).
        Используется для плавного угасания еды.
        """
        return tuple(int(low[i] + (high[i] - low[i]) * factor) for i in range(3))

    def draw_title(self, title: str, subtitle: str) -> None:
        """Рисует заголовок и подзаголовок по центру верхней части экрана."""
        title_text    = self.font_title.render(title,    True, TEXT_COLOR)
        subtitle_text = self.font_small.render(subtitle, True, MUTED_TEXT)
        self.screen.blit(title_text,    title_text.get_rect(center=(SCREEN_WIDTH // 2, 60)))
        self.screen.blit(subtitle_text, subtitle_text.get_rect(center=(SCREEN_WIDTH // 2, 96)))

    def draw_footer(self, line_one: str, line_two: str) -> None:
        """Рисует две строки текста в нижней части экрана (колонтитул меню)."""
        top    = self.font_small.render(line_one, True, MUTED_TEXT)
        bottom = self.font_small.render(line_two, True, MUTED_TEXT)
        self.screen.blit(top,    top.get_rect(center=(SCREEN_WIDTH // 2,    SCREEN_HEIGHT - 34)))
        self.screen.blit(bottom, bottom.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 16)))