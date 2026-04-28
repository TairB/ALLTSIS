"""
tools.py — логика всех инструментов рисования.

Каждый инструмент — отдельная функция или класс.
paint.py импортирует отсюда всё что нужно.
"""

import pygame
import math
import sys
from collections import deque


# ─── Константы инструментов ───────────────────────────────────────────────────
TOOL_PENCIL  = "pencil"
TOOL_LINE    = "line"
TOOL_RECT    = "rect"
TOOL_CIRCLE  = "circle"
TOOL_SQUARE  = "square"
TOOL_RTRI    = "right_tri"
TOOL_ETRI    = "equil_tri"
TOOL_RHOMBUS = "rhombus"
TOOL_ERASER  = "eraser"
TOOL_FILL    = "fill"
TOOL_TEXT    = "text"

ALL_TOOLS = [
    TOOL_PENCIL, TOOL_LINE, TOOL_RECT, TOOL_CIRCLE,
    TOOL_SQUARE, TOOL_RTRI, TOOL_ETRI, TOOL_RHOMBUS,
    TOOL_ERASER, TOOL_FILL, TOOL_TEXT,
]

TOOL_LABELS = {
    TOOL_PENCIL:  "Pencil [P]",
    TOOL_LINE:    "Line [L]",
    TOOL_RECT:    "Rect [R]",
    TOOL_CIRCLE:  "Circle [C]",
    TOOL_SQUARE:  "Square [Q]",
    TOOL_RTRI:    "R.Tri [T]",
    TOOL_ETRI:    "Eq.Tri [Y]",
    TOOL_RHOMBUS: "Rhombus [H]",
    TOOL_ERASER:  "Eraser [E]",
    TOOL_FILL:    "Fill [G]",
    TOOL_TEXT:    "Text [X]",
}

# Три уровня кисти (клавиши 1, 2, 3)
BRUSH_SIZES = {1: 2, 2: 5, 3: 10}


# ─── Вспомогательные функции рисования ───────────────────────────────────────

def draw_smooth_line(surface, colour, start, end, width):
    """
    Рисует плавную линию между двумя точками.
    Используется карандашом и ластиком при движении мыши.

    Интерполируем шаги между start и end и рисуем круги —
    это даёт плавную непрерывную линию без пробелов.
    """
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    steps = max(abs(dx), abs(dy), 1)
    for i in range(steps + 1):
        t = i / steps
        pygame.draw.circle(
            surface, colour,
            (int(start[0] + t * dx), int(start[1] + t * dy)),
            width
        )


def polygon_shape(surface, colour, points, fill, brush_size=2):
    """
    Рисует полигон — закрашенный или контурный.

    fill=True  → pygame.draw.polygon с width=0 (залитый)
    fill=False → pygame.draw.polygon с width=brush_size (контур)
    """
    if len(points) < 2:
        return
    width = 0 if fill else max(1, brush_size)
    pygame.draw.polygon(surface, colour, points, width)


# ─── Функции построения фигур ─────────────────────────────────────────────────

def make_square_points(x0, y0, x1, y1):
    """
    Квадрат — берём меньшую из сторон как размер.
    Сторона квадрата = min(|dx|, |dy|), направление сохраняется.
    """
    dx = x1 - x0
    dy = y1 - y0
    side = min(abs(dx), abs(dy))
    sx = side if dx >= 0 else -side
    sy = side if dy >= 0 else -side
    return [(x0, y0), (x0 + sx, y0), (x0 + sx, y0 + sy), (x0, y0 + sy)]


def make_right_triangle_points(x0, y0, x1, y1):
    """
    Прямоугольный треугольник.
    Прямой угол — в точке (x0, y1).
    Вертикальный катет: x0, y0 → x0, y1
    Горизонтальный катет: x0, y1 → x1, y1
    """
    return [(x0, y1), (x0, y0), (x1, y1)]


def make_equilateral_triangle_points(x0, y0, x1, y1):
    """
    Равносторонний треугольник.
    Основание — от x0 до x1 на высоте y0.
    Вершина рассчитывается через высоту = (√3 / 2) * сторона.
    """
    base_mid_x = (x0 + x1) / 2
    base_len   = abs(x1 - x0)
    height     = (math.sqrt(3) / 2) * base_len
    apex_y     = y0 - height if y1 <= y0 else y0 + height
    return [(x0, y0), (x1, y0), (int(base_mid_x), int(apex_y))]


def make_rhombus_points(x0, y0, x1, y1):
    """
    Ромб. Центр в точке (x0, y0).
    Полуширина = |x1-x0|, полувысота = |y1-y0|.
    """
    cx = x0
    cy = y0
    hw = abs(x1 - x0)
    hh = abs(y1 - y0)
    return [
        (cx,      cy - hh),
        (cx + hw, cy),
        (cx,      cy + hh),
        (cx - hw, cy),
    ]


# ─── Flood Fill ───────────────────────────────────────────────────────────────

def flood_fill(surface, pos, fill_colour):
    """
    Заливка области одним цветом (алгоритм BFS).

    Как работает:
      1. Берём цвет пикселя в точке pos (target_colour)
      2. Если fill_colour == target_colour — ничего не делаем (уже залито)
      3. Используем очередь (deque) для обхода соседних пикселей
      4. Для каждого пикселя: если его цвет == target_colour → перекрашиваем
         и добавляем 4 соседей в очередь

    get_at(x, y) — возвращает цвет пикселя (R, G, B, A)
    set_at(x, y, colour) — устанавливает цвет пикселя

    Ограничение: работает по точному совпадению цвета.
    """
    x, y = pos
    w, h = surface.get_size()

    # Проверяем что клик внутри поверхности
    if not (0 <= x < w and 0 <= y < h):
        return

    target_colour = surface.get_at((x, y))[:3]  # берём RGB без альфа
    fill_rgb       = fill_colour[:3]

    # Если цвет уже такой — ничего не делаем
    if target_colour == fill_rgb:
        return

    # BFS — обходим пиксели в ширину
    queue = deque()
    queue.append((x, y))
    visited = set()
    visited.add((x, y))

    while queue:
        cx, cy = queue.popleft()

        # Проверяем цвет текущего пикселя
        if surface.get_at((cx, cy))[:3] != target_colour:
            continue

        # Перекрашиваем
        surface.set_at((cx, cy), fill_colour)

        # Добавляем 4 соседей (вверх, вниз, влево, вправо)
        for nx, ny in [(cx+1, cy), (cx-1, cy), (cx, cy+1), (cx, cy-1)]:
            if (0 <= nx < w and 0 <= ny < h) and (nx, ny) not in visited:
                visited.add((nx, ny))
                queue.append((nx, ny))


# ─── Text Tool ────────────────────────────────────────────────────────────────

class TextTool:
    """
    Инструмент ввода текста.

    Состояния:
      active=False — ждём клика
      active=True  — пользователь печатает

    Использование:
      1. Клик на холст → устанавливает позицию курсора
      2. Печатаем — текст появляется в реальном времени
      3. Enter → текст записывается на холст permanently
      4. Escape → отмена
    """

    def __init__(self):
        self.active   = False   # режим ввода активен?
        self.text     = ""      # текущий вводимый текст
        self.pos      = (0, 0)  # позиция на холсте (относительно canvas)
        self.font     = pygame.font.SysFont("arial", 20)
        self.cursor_visible = True
        self.cursor_timer   = 0

    def start(self, pos):
        """Активирует ввод в указанной позиции."""
        self.active  = True
        self.text    = ""
        self.pos     = pos

    def cancel(self):
        """Отменяет ввод."""
        self.active = False
        self.text   = ""

    def handle_keydown(self, event, canvas, colour):
        """
        Обрабатывает нажатие клавиш во время ввода текста.

        Возвращает True если текст подтверждён (Enter нажат).
        """
        if not self.active:
            return False

        if event.key == pygame.K_RETURN:
            # Enter — записываем текст на холст
            self.commit(canvas, colour)
            return True

        elif event.key == pygame.K_ESCAPE:
            # Escape — отмена
            self.cancel()
            return False

        elif event.key == pygame.K_BACKSPACE:
            # Удаляем последний символ
            self.text = self.text[:-1]

        else:
            # Добавляем введённый символ
            if event.unicode and event.unicode.isprintable():
                self.text += event.unicode

        return False

    def commit(self, canvas, colour):
        """Рисует текст на холсте и деактивирует инструмент."""
        if self.text.strip():
            text_surface = self.font.render(self.text, True, colour)
            canvas.blit(text_surface, self.pos)
        self.cancel()

    def draw_preview(self, display_surface, colour, canvas_top=0):
        """
        Рисует превью текста прямо на DISPLAYSURF (не на холсте!).

        Это ключевое исправление — рисуем на экране, а не на canvas.
        Так текст не "запекается" на холст до нажатия Enter.

        display_surface — DISPLAYSURF (экран)
        canvas_top      — отступ сверху (высота тулбара)
        """
        if not self.active:
            return

        # Мигание курсора (каждые 30 кадров)
        self.cursor_timer += 1
        if self.cursor_timer > 30:
            self.cursor_visible = not self.cursor_visible
            self.cursor_timer   = 0

        # Текст + мигающий курсор
        display_text = self.text + ("|" if self.cursor_visible else " ")
        text_surface = self.font.render(display_text, True, colour)

        # Позиция на экране = позиция на холсте + отступ тулбара
        screen_pos = (self.pos[0], self.pos[1] + canvas_top)
        display_surface.blit(text_surface, screen_pos)


# ─── Toolbar ──────────────────────────────────────────────────────────────────

WHITE      = (255, 255, 255)
MID_GREY   = (100, 100, 100)
LIGHT_GREY = (200, 200, 200)
TOOLBAR_BG = (45, 45, 55)


class Toolbar:
    """
    Панель инструментов вверху экрана.

    Содержит:
      - кнопки инструментов
      - кнопки размера кисти (1, 2, 3)
      - превью цвета
      - индикатор Fill/Outline
    """

    BTN_W  = 72
    BTN_H  = 30
    BTN_Y  = 5
    BTN_X0 = 4

    def __init__(self, font):
        self.font        = font
        self.active_tool = TOOL_PENCIL
        self.buttons     = {}

        # Кнопки инструментов
        for i, tool in enumerate(ALL_TOOLS):
            self.buttons[tool] = pygame.Rect(
                self.BTN_X0 + i * (self.BTN_W + 2),
                self.BTN_Y,
                self.BTN_W,
                self.BTN_H
            )

    def handle_click(self, pos):
        for tool, rect in self.buttons.items():
            if rect.collidepoint(pos):
                self.active_tool = tool
                return tool
        return None

    def draw(self, surface, draw_colour, brush_size, fill_mode, screen_w, canvas_top):
        # Фон тулбара
        pygame.draw.rect(surface, TOOLBAR_BG, (0, 0, screen_w, canvas_top))
        pygame.draw.line(surface, MID_GREY, (0, canvas_top - 1), (screen_w, canvas_top - 1), 2)

        # Кнопки инструментов
        for tool, rect in self.buttons.items():
            active = (tool == self.active_tool)
            pygame.draw.rect(
                surface,
                (80, 120, 200) if active else (60, 60, 75),
                rect, border_radius=4
            )
            pygame.draw.rect(
                surface,
                LIGHT_GREY if active else MID_GREY,
                rect, 1, border_radius=4
            )
            lbl = self.font.render(TOOL_LABELS[tool], True, WHITE)
            surface.blit(lbl, lbl.get_rect(center=rect.center))

        # Превью цвета
        sw = pygame.Rect(screen_w - 90, 5, 30, 30)
        pygame.draw.rect(surface, draw_colour, sw, border_radius=4)
        pygame.draw.rect(surface, LIGHT_GREY, sw, 1, border_radius=4)

        # Размер кисти и fill/outline
        info = f"Size:{brush_size}  {'[Fill]' if fill_mode else '[Outline]'}"
        surface.blit(
            self.font.render(info, True, (150, 200, 150) if fill_mode else (200, 150, 80)),
            (screen_w - 220, canvas_top - 14)
        )
