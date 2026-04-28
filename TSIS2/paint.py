"""
paint.py — расширенный Paint на Pygame (TSIS 2)

Управление:
  Левая кнопка мыши   Рисовать / выбрать инструмент / цвет
  Колёсико / + / -    Размер кисти
  1 / 2 / 3           Размер кисти: маленький(2) / средний(5) / большой(10)
  P                   Карандаш
  L                   Прямая линия (с превью)
  R                   Прямоугольник
  C                   Круг
  Q                   Квадрат
  T                   Прямоугольный треугольник
  Y                   Равносторонний треугольник
  H                   Ромб
  E                   Ластик
  G                   Заливка (Flood Fill)
  X                   Текст (кликни → печатай → Enter)
  F                   Переключить Fill / Outline
  N / BACKSPACE       Очистить холст
  Ctrl+S              Сохранить холст как PNG
  ESC / Ctrl+W        Выход
"""

import pygame
import sys
import datetime

from tools import (
    TOOL_PENCIL, TOOL_LINE, TOOL_RECT, TOOL_CIRCLE,
    TOOL_SQUARE, TOOL_RTRI, TOOL_ETRI, TOOL_RHOMBUS,
    TOOL_ERASER, TOOL_FILL, TOOL_TEXT,
    draw_smooth_line, polygon_shape, flood_fill,
    make_square_points, make_right_triangle_points,
    make_equilateral_triangle_points, make_rhombus_points,
    Toolbar, TextTool,
    BRUSH_SIZES,
)

pygame.init()

SCREEN_W      = 1100
SCREEN_H      = 680
CANVAS_TOP    = 42
PALETTE_H     = 45
CANVAS_BOTTOM = SCREEN_H - PALETTE_H

WHITE      = (255, 255, 255)
BLACK      = (0,   0,   0)
DARK       = (30,  30,  30)
MID_GREY   = (100, 100, 100)
PALETTE_BG = (35,  35,  45)

PALETTE_COLOURS = [
    (0,   0,   0),   (255, 255, 255), (220, 50,  50),  (255, 140, 0),
    (255, 215, 0),   (50,  200, 50),  (30,  144, 255), (138, 43,  226),
    (255, 105, 180), (0,   206, 209), (139, 69,  19),  (128, 128, 128),
    (255, 69,  0),   (0,   128, 128), (75,  0,   130), (240, 230, 140),
]

DISPLAYSURF = pygame.display.set_mode((SCREEN_W, SCREEN_H))
pygame.display.set_caption("Paint — TSIS 2")

font = pygame.font.SysFont("arial", 11, bold=True)


class ColourPalette:
    SWATCH_W = SCREEN_W // len(PALETTE_COLOURS)

    def __init__(self):
        self.rects = [
            (pygame.Rect(i * self.SWATCH_W, CANVAS_BOTTOM, self.SWATCH_W, PALETTE_H), c)
            for i, c in enumerate(PALETTE_COLOURS)
        ]

    def handle_click(self, pos):
        for rect, colour in self.rects:
            if rect.collidepoint(pos):
                return colour
        return None

    def draw(self, surface, active_colour):
        pygame.draw.rect(surface, PALETTE_BG, (0, CANVAS_BOTTOM, SCREEN_W, PALETTE_H))
        pygame.draw.line(surface, MID_GREY, (0, CANVAS_BOTTOM), (SCREEN_W, CANVAS_BOTTOM), 2)
        for rect, colour in self.rects:
            pygame.draw.rect(surface, colour, rect)
            pygame.draw.rect(
                surface,
                WHITE if colour == active_colour else DARK,
                rect, 3 if colour == active_colour else 1
            )


def save_canvas(canvas):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename  = f"canvas_{timestamp}.png"
    pygame.image.save(canvas, filename)
    print(f"[Сохранено] {filename}")
    return filename


def main():
    global FILL_MODE
    FILL_MODE = True

    clock     = pygame.time.Clock()
    toolbar   = Toolbar(font)
    palette   = ColourPalette()
    text_tool = TextTool()

    canvas_h = CANVAS_BOTTOM - CANVAS_TOP

    def new_canvas():
        c = pygame.Surface((SCREEN_W, canvas_h))
        c.fill(WHITE)
        return c

    canvas          = new_canvas()
    canvas_snapshot = canvas.copy()

    draw_colour    = BLACK
    brush_size     = 5
    is_drawing     = False
    last_pos       = None
    shape_start    = None
    save_msg       = ""
    save_msg_timer = 0

    while True:
        pressed   = pygame.key.get_pressed()
        ctrl_held = pressed[pygame.K_LCTRL] or pressed[pygame.K_RCTRL]
        alt_held  = pressed[pygame.K_LALT]  or pressed[pygame.K_RALT]

        for event in pygame.event.get():

            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()

            if event.type == pygame.KEYDOWN:

                # ── Текстовый режим — весь ввод идёт в text_tool ─────────────
                if text_tool.active:
                    text_tool.handle_keydown(event, canvas, draw_colour)
                    continue

                # Выход
                if event.key == pygame.K_ESCAPE:    pygame.quit(); sys.exit()
                if event.key == pygame.K_w and ctrl_held: pygame.quit(); sys.exit()
                if event.key == pygame.K_F4 and alt_held: pygame.quit(); sys.exit()

                # Ctrl+S — сохранить
                if event.key == pygame.K_s and ctrl_held:
                    filename       = save_canvas(canvas)
                    save_msg       = f"Сохранено: {filename}"
                    save_msg_timer = 180

                # Инструменты
                if event.key == pygame.K_p: toolbar.active_tool = TOOL_PENCIL
                if event.key == pygame.K_l: toolbar.active_tool = TOOL_LINE
                if event.key == pygame.K_r: toolbar.active_tool = TOOL_RECT
                if event.key == pygame.K_c: toolbar.active_tool = TOOL_CIRCLE
                if event.key == pygame.K_q: toolbar.active_tool = TOOL_SQUARE
                if event.key == pygame.K_t: toolbar.active_tool = TOOL_RTRI
                if event.key == pygame.K_y: toolbar.active_tool = TOOL_ETRI
                if event.key == pygame.K_h: toolbar.active_tool = TOOL_RHOMBUS
                if event.key == pygame.K_e: toolbar.active_tool = TOOL_ERASER
                if event.key == pygame.K_g: toolbar.active_tool = TOOL_FILL
                if event.key == pygame.K_x: toolbar.active_tool = TOOL_TEXT

                if event.key == pygame.K_f: FILL_MODE = not FILL_MODE

                # Размер кисти
                if event.key == pygame.K_1: brush_size = BRUSH_SIZES[1]
                if event.key == pygame.K_2: brush_size = BRUSH_SIZES[2]
                if event.key == pygame.K_3: brush_size = BRUSH_SIZES[3]
                if event.key in (pygame.K_PLUS, pygame.K_EQUALS):
                    brush_size = min(60, brush_size + 1)
                if event.key == pygame.K_MINUS:
                    brush_size = max(1, brush_size - 1)

                # Очистить
                if event.key in (pygame.K_DELETE, pygame.K_BACKSPACE, pygame.K_n):
                    canvas = new_canvas()

            if event.type == pygame.MOUSEWHEEL:
                brush_size = max(1, min(60, brush_size + event.y))

            # ── Нажатие мыши ─────────────────────────────────────────────────
            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos

                if my < CANVAS_TOP:
                    toolbar.handle_click((mx, my)); continue

                if my >= CANVAS_BOTTOM:
                    col = palette.handle_click((mx, my))
                    if col: draw_colour = col
                    continue

                if event.button == 1:
                    cx = max(0, min(mx, SCREEN_W - 1))
                    cy = max(0, min(my - CANVAS_TOP, canvas_h - 1))
                    tool = toolbar.active_tool

                    if tool == TOOL_TEXT:
                        # Активируем текстовый режим — запоминаем позицию
                        text_tool.start((cx, cy))
                        continue

                    if tool == TOOL_FILL:
                        flood_fill(canvas, (cx, cy), draw_colour)
                        continue

                    if tool in (TOOL_RECT, TOOL_CIRCLE, TOOL_SQUARE,
                                TOOL_RTRI, TOOL_ETRI, TOOL_RHOMBUS, TOOL_LINE):
                        shape_start     = (cx, cy)
                        canvas_snapshot = canvas.copy()

                    elif tool == TOOL_PENCIL:
                        last_pos = (cx, cy)
                        pygame.draw.circle(canvas, draw_colour, (cx, cy), brush_size)

                    elif tool == TOOL_ERASER:
                        last_pos = (cx, cy)
                        pygame.draw.circle(canvas, WHITE, (cx, cy), brush_size * 2)

                    is_drawing = True

            # ── Движение мыши ────────────────────────────────────────────────
            if event.type == pygame.MOUSEMOTION and is_drawing:
                mx, my = event.pos
                if CANVAS_TOP <= my < CANVAS_BOTTOM:
                    cx   = mx
                    cy   = my - CANVAS_TOP
                    tool = toolbar.active_tool

                    if tool == TOOL_PENCIL and last_pos:
                        draw_smooth_line(canvas, draw_colour, last_pos, (cx, cy), brush_size)
                        last_pos = (cx, cy)

                    elif tool == TOOL_ERASER and last_pos:
                        draw_smooth_line(canvas, WHITE, last_pos, (cx, cy), brush_size * 2)
                        last_pos = (cx, cy)

                    elif tool == TOOL_LINE and shape_start:
                        canvas.blit(canvas_snapshot, (0, 0))
                        pygame.draw.line(canvas, draw_colour, shape_start, (cx, cy), max(1, brush_size))

                    elif tool == TOOL_RECT and shape_start:
                        canvas.blit(canvas_snapshot, (0, 0))
                        x0, y0 = shape_start
                        r = pygame.Rect(min(x0,cx), min(y0,cy), abs(cx-x0), abs(cy-y0))
                        pygame.draw.rect(canvas, draw_colour, r, 0 if FILL_MODE else max(1, brush_size))

                    elif tool == TOOL_CIRCLE and shape_start:
                        canvas.blit(canvas_snapshot, (0, 0))
                        x0, y0 = shape_start
                        radius = int(((cx-x0)**2 + (cy-y0)**2)**0.5)
                        if radius > 0:
                            pygame.draw.circle(canvas, draw_colour, (x0,y0), radius,
                                               0 if FILL_MODE else max(1, brush_size))

                    elif tool == TOOL_SQUARE and shape_start:
                        canvas.blit(canvas_snapshot, (0, 0))
                        polygon_shape(canvas, draw_colour, make_square_points(*shape_start, cx, cy), FILL_MODE, brush_size)

                    elif tool == TOOL_RTRI and shape_start:
                        canvas.blit(canvas_snapshot, (0, 0))
                        polygon_shape(canvas, draw_colour, make_right_triangle_points(*shape_start, cx, cy), FILL_MODE, brush_size)

                    elif tool == TOOL_ETRI and shape_start:
                        canvas.blit(canvas_snapshot, (0, 0))
                        polygon_shape(canvas, draw_colour, make_equilateral_triangle_points(*shape_start, cx, cy), FILL_MODE, brush_size)

                    elif tool == TOOL_RHOMBUS and shape_start:
                        canvas.blit(canvas_snapshot, (0, 0))
                        polygon_shape(canvas, draw_colour, make_rhombus_points(*shape_start, cx, cy), FILL_MODE, brush_size)

            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                is_drawing  = False
                last_pos    = None
                shape_start = None

        # ── Отрисовка ─────────────────────────────────────────────────────────
        DISPLAYSURF.fill(DARK)

        # Рисуем холст
        DISPLAYSURF.blit(canvas, (0, CANVAS_TOP))

        # Превью текста рисуем ПРЯМО НА DISPLAYSURF — холст не трогаем!
        # Так текст не "записывается" на холст до нажатия Enter
        if text_tool.active:
            text_tool.draw_preview(DISPLAYSURF, draw_colour, CANVAS_TOP)
            hint = font.render("Enter = подтвердить  |  Escape = отмена", True, (255, 220, 50))
            DISPLAYSURF.blit(hint, (10, CANVAS_TOP + 5))

        toolbar.draw(DISPLAYSURF, draw_colour, brush_size, FILL_MODE, SCREEN_W, CANVAS_TOP)
        palette.draw(DISPLAYSURF, draw_colour)

        if save_msg_timer > 0:
            save_msg_timer -= 1
            DISPLAYSURF.blit(font.render(save_msg, True, (50, 220, 50)),
                             (10, SCREEN_H - PALETTE_H - 20))

        pygame.display.flip()
        clock.tick(60)


if __name__ == "__main__":
    main()
