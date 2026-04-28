"""
tools.py — All drawing tools, geometry helpers, and UI classes for the Paint app.
Imported by paint.py; contains no entry point of its own.
"""

import math
import collections
import pygame

# ---------------------------------------------------------------------------
# Tool ID constants — used as the active_tool value in Toolbar
# ---------------------------------------------------------------------------
TOOL_PENCIL  = "pencil"
TOOL_LINE    = "line"
TOOL_RECT    = "rect"
TOOL_CIRCLE  = "circle"
TOOL_SQUARE  = "square"
TOOL_RTRI    = "rtri"    # Right triangle
TOOL_ETRI    = "etri"    # Equilateral triangle
TOOL_RHOMBUS = "rhombus"
TOOL_ERASER  = "eraser"
TOOL_FILL    = "fill"
TOOL_TEXT    = "text"

# Brush size presets accessed by keyboard keys 1 / 2 / 3
BRUSH_SIZES = {1: 2, 2: 5, 3: 10}

# Toolbar button order — determines left-to-right display order
TOOL_ORDER = [
    TOOL_PENCIL, TOOL_LINE, TOOL_RECT, TOOL_CIRCLE,
    TOOL_SQUARE, TOOL_RTRI, TOOL_ETRI, TOOL_RHOMBUS,
    TOOL_ERASER, TOOL_FILL, TOOL_TEXT,
]

# Short labels shown on toolbar buttons
TOOL_LABELS = {
    TOOL_PENCIL:  "P Pencil",
    TOOL_LINE:    "L Line",
    TOOL_RECT:    "R Rect",
    TOOL_CIRCLE:  "C Circle",
    TOOL_SQUARE:  "Q Square",
    TOOL_RTRI:    "T RightTri",
    TOOL_ETRI:    "Y EqTri",
    TOOL_RHOMBUS: "H Rhombus",
    TOOL_ERASER:  "E Eraser",
    TOOL_FILL:    "G Fill",
    TOOL_TEXT:    "X Text",
}

# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def draw_smooth_line(surface, colour, p1, p2, radius):
    """
    Draw a smooth thick stroke between two points.
    Interpolates intermediate circles along the segment so fast mouse
    movement doesn't leave gaps (unlike a single pygame.draw.line call).
    """
    x1, y1 = p1
    x2, y2 = p2
    dx, dy = x2 - x1, y2 - y1
    dist = max(1, int(math.hypot(dx, dy)))
    for i in range(dist + 1):
        t = i / dist
        x = int(x1 + dx * t)
        y = int(y1 + dy * t)
        pygame.draw.circle(surface, colour, (x, y), radius)


def polygon_shape(surface, colour, points, fill, brush_size):
    """
    Draw a filled or outlined polygon.
    fill=True  → width=0 (solid fill)
    fill=False → width=brush_size (outline only)
    Skips drawing if fewer than 3 points are provided.
    """
    if len(points) < 3:
        return
    width = 0 if fill else max(1, brush_size)
    pygame.draw.polygon(surface, colour, points, width)


# ---------------------------------------------------------------------------
# Geometry helpers — each returns a list of (x, y) vertex tuples
# ---------------------------------------------------------------------------

def make_square_points(x0, y0, x1, y1):
    """
    Return 4 corners of an axis-aligned square.
    Side length = min of width/height drag distance, anchored at (x0, y0).
    """
    side = min(abs(x1 - x0), abs(y1 - y0))
    sx = side if x1 >= x0 else -side
    sy = side if y1 >= y0 else -side
    return [(x0, y0), (x0 + sx, y0), (x0 + sx, y0 + sy), (x0, y0 + sy)]


def make_right_triangle_points(x0, y0, x1, y1):
    """
    Return 3 corners of a right-angle triangle.
    Right angle is at bottom-left; hypotenuse goes from top-left to bottom-right.
    """
    return [(x0, y0), (x0, y1), (x1, y1)]


def make_equilateral_triangle_points(x0, y0, x1, y1):
    """
    Return 3 corners of an equilateral triangle.
    Base runs from (x0,y1) to (x1,y1); apex is centred above the base.
    """
    base = x1 - x0
    height = base * math.sqrt(3) / 2
    apex_x = x0 + base / 2
    apex_y = y1 - height
    return [(x0, y1), (x1, y1), (int(apex_x), int(apex_y))]


def make_rhombus_points(x0, y0, x1, y1):
    """
    Return 4 corners of a rhombus (diamond) whose bounding box is (x0,y0)-(x1,y1).
    """
    mx = (x0 + x1) // 2
    my = (y0 + y1) // 2
    return [(mx, y0), (x1, my), (mx, y1), (x0, my)]


# ---------------------------------------------------------------------------
# Flood fill (BFS)
# ---------------------------------------------------------------------------

def flood_fill(surface, start_pos, fill_colour):
    """
    Fill a contiguous region of the same colour using BFS.
    Reads pixels with surface.get_at() and writes with surface.set_at().
    Stops at any pixel whose colour differs from the seed colour.
    Does nothing if the seed pixel already has the fill colour.
    """
    sx, sy = start_pos
    w, h = surface.get_size()

    # Clamp start position to surface bounds
    sx = max(0, min(sx, w - 1))
    sy = max(0, min(sy, h - 1))

    target_colour = surface.get_at((sx, sy))[:3]   # Ignore alpha
    fill_rgb = fill_colour[:3]

    if target_colour == fill_rgb:
        return  # Already the right colour — nothing to do

    queue = collections.deque()
    queue.append((sx, sy))
    visited = set()
    visited.add((sx, sy))

    while queue:
        x, y = queue.popleft()
        if surface.get_at((x, y))[:3] != target_colour:
            continue
        surface.set_at((x, y), fill_colour)
        for nx, ny in ((x+1, y), (x-1, y), (x, y+1), (x, y-1)):
            if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in visited:
                visited.add((nx, ny))
                queue.append((nx, ny))


# ---------------------------------------------------------------------------
# Text tool
# ---------------------------------------------------------------------------

class TextTool:
    """
    Two-phase text input:
      1. User clicks the canvas  → start() records the position.
      2. User types characters   → handle_keydown() builds the string.
      3. Enter confirms          → text is rendered permanently onto the canvas.
         Escape cancels          → state is reset with no changes.
    draw_preview() renders the current buffer onto the display surface each
    frame WITHOUT touching the canvas, so nothing is committed until Enter.
    """

    FONT_SIZE = 22

    def __init__(self):
        self.active   = False
        self.pos      = (0, 0)   # Canvas-space position (relative to canvas top)
        self.buffer   = ""       # Characters typed so far
        self._font    = None     # Lazy-loaded on first use

    def _get_font(self):
        """Load font once and cache it."""
        if self._font is None:
            self._font = pygame.font.SysFont("arial", self.FONT_SIZE)
        return self._font

    def start(self, pos):
        """Activate text input at canvas position pos."""
        self.active = True
        self.pos    = pos
        self.buffer = ""

    def handle_keydown(self, event, canvas, colour):
        """
        Process a key press while text mode is active.
        Enter  → render buffer onto canvas and deactivate.
        Escape → cancel without drawing.
        Backspace → delete last character.
        Printable → append to buffer.
        """
        if event.key == pygame.K_RETURN:
            self._commit(canvas, colour)
        elif event.key == pygame.K_ESCAPE:
            self.active = False
            self.buffer = ""
        elif event.key == pygame.K_BACKSPACE:
            self.buffer = self.buffer[:-1]
        elif event.unicode and event.unicode.isprintable():
            self.buffer += event.unicode

    def _commit(self, canvas, colour):
        """Render the buffer string onto the canvas surface at self.pos."""
        if self.buffer:
            font   = self._get_font()
            text   = font.render(self.buffer, True, colour)
            canvas.blit(text, self.pos)
        self.active = False
        self.buffer = ""

    def draw_preview(self, display_surface, colour, canvas_top):
        """
        Draw a live preview of the typed text onto the display surface.
        canvas_top is added to convert canvas-space Y to screen-space Y.
        A blinking cursor '|' is appended to show the insertion point.
        """
        font  = self._get_font()
        x, y  = self.pos
        preview = font.render(self.buffer + "|", True, colour)
        display_surface.blit(preview, (x, y + canvas_top))


# ---------------------------------------------------------------------------
# Toolbar
# ---------------------------------------------------------------------------

class Toolbar:
    """
    Horizontal strip of tool buttons rendered at the top of the window.
    Tracks the currently active tool and draws a highlighted border around it.
    Also shows the active colour swatch, brush size, and fill/outline mode.
    """

    BTN_W = 78    # Button width in pixels
    BTN_H = 30    # Button height in pixels
    PAD   = 4     # Gap between buttons

    # Colours used for toolbar rendering
    BG       = (45,  45,  60)
    ACTIVE   = (90,  140, 220)
    INACTIVE = (60,  60,  80)
    BORDER   = (80,  80,  100)
    TEXT_CLR = (230, 230, 230)

    def __init__(self, font):
        self.font        = font
        self.active_tool = TOOL_PENCIL
        self._buttons    = []   # List of (Rect, tool_id) built on first draw

    def _build_buttons(self, screen_w, toolbar_h):
        """Compute button rects based on current screen width (called once)."""
        self._buttons = []
        x = self.PAD
        for tool in TOOL_ORDER:
            rect = pygame.Rect(x, (toolbar_h - self.BTN_H) // 2, self.BTN_W, self.BTN_H)
            self._buttons.append((rect, tool))
            x += self.BTN_W + self.PAD

    def handle_click(self, pos):
        """Switch active tool if pos lands inside a button rect."""
        for rect, tool in self._buttons:
            if rect.collidepoint(pos):
                self.active_tool = tool
                return

    def draw(self, surface, active_colour, brush_size, fill_mode, screen_w, toolbar_h):
        """
        Render the toolbar background, all tool buttons, and status indicators
        (colour swatch, brush size, fill/outline toggle).
        """
        # Build button layout on first call
        if not self._buttons:
            self._build_buttons(screen_w, toolbar_h)

        # Toolbar background
        pygame.draw.rect(surface, self.BG, (0, 0, screen_w, toolbar_h))

        # Tool buttons
        for rect, tool in self._buttons:
            is_active = (tool == self.active_tool)
            bg_colour = self.ACTIVE if is_active else self.INACTIVE
            pygame.draw.rect(surface, bg_colour, rect, border_radius=4)
            pygame.draw.rect(surface, self.BORDER, rect, 1, border_radius=4)
            label = self.font.render(TOOL_LABELS[tool], True, self.TEXT_CLR)
            surface.blit(label, label.get_rect(center=rect.center))

        # Active colour swatch — small square on the right side of toolbar
        swatch_x = screen_w - 120
        swatch_rect = pygame.Rect(swatch_x, 6, 28, 28)
        pygame.draw.rect(surface, active_colour, swatch_rect)
        pygame.draw.rect(surface, (200, 200, 200), swatch_rect, 1)

        # Brush size indicator
        size_label = self.font.render(f"Size: {brush_size}", True, self.TEXT_CLR)
        surface.blit(size_label, (swatch_x + 34, 8))

        # Fill / Outline mode indicator
        mode_text  = "Fill" if fill_mode else "Outline"
        mode_label = self.font.render(f"[F] {mode_text}", True, self.TEXT_CLR)
        surface.blit(mode_label, (swatch_x + 34, 20))