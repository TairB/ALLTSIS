"""
racer.py  –  TSIS 3 Game Engine

Sprites used:
    traffic_imgs[0]  Enemy.png      (red car)
    traffic_imgs[1]  yellowcar.jpeg
    traffic_imgs[2]  greencar.jpeg
    nitro_img        nitro.png      (NOS canister)
    barrier_img      barrier.png    (road barrier)
    player_img       Player.png / Player_<color>.png
"""

import pygame, sys, random
from pygame.locals import *
from persistence import add_leaderboard_entry

# ── Constants ─────────────────────────────────────────────────────────────────
FPS               = 60
SW                = 400
SH                = 600
LANE_XS           = [70, 160, 240, 330]
ROAD_LEFT         = 30
ROAD_RIGHT        = 370
RACE_DISTANCE     = 3000
ENEMY_BOOST_EVERY = 5

# Colours
BLACK  = (  0,   0,   0)
WHITE  = (255, 255, 255)
YELLOW = (255, 215,   0)
RED    = (220,  40,  40)
GREEN  = ( 50, 200,  50)
BLUE   = ( 30, 144, 255)
GREY   = ( 50,  50,  50)
ORANGE = (255, 140,   0)
SILVER = (192, 192, 192)
BRONZE = (205, 127,  50)
TEAL   = (  0, 200, 180)

# ── Difficulty presets ────────────────────────────────────────────────────────
DIFF = {
    "easy":   {"base_speed": 4,  "enemy_count": 1, "obs_interval": 4000,
               "coin_interval": 1500, "hazard_count": 1, "traffic_max": 2},
    "normal": {"base_speed": 5,  "enemy_count": 2, "obs_interval": 2800,
               "coin_interval": 2000, "hazard_count": 2, "traffic_max": 3},
    "hard":   {"base_speed": 7,  "enemy_count": 3, "obs_interval": 1800,
               "coin_interval": 2500, "hazard_count": 3, "traffic_max": 5},
}

# ── Coin types (from Practice 11) ─────────────────────────────────────────────
COIN_TYPES = [
    ("B", BRONZE, (140, 80, 20),   1, 50),
    ("S", SILVER, (120, 120, 120), 3, 30),
    ("G", YELLOW, (180, 140,  0),  5, 20),
]
_TOTAL_COIN_W = sum(t[4] for t in COIN_TYPES)

POWERUP_COLORS = {"nitro": ORANGE, "shield": TEAL, "repair": GREEN}
POWERUP_ICONS  = {"nitro": "⚡", "shield": "🛡", "repair": "🔧"}
POWERUP_DUR    = {"nitro": 4000}
POWERUP_LIFETIME = 8000


def _random_coin_type():
    roll, cumul = random.randint(1, _TOTAL_COIN_W), 0
    for ct in COIN_TYPES:
        cumul += ct[4]
        if roll <= cumul:
            return ct
    return COIN_TYPES[0]


def _random_lane():
    return random.choice(LANE_XS)


# ── ScrollingBackground ───────────────────────────────────────────────────────
# ЗАЧЕМ: создаёт иллюзию движущейся дороги.
# Используются ДВЕ копии картинки фона — одна за другой.
# Когда первая уходит вниз за экран — она прыгает наверх.
# Так получается бесконечный скролл без "дырок".
class ScrollingBackground:
    def __init__(self, image):
        self.img = image
        self.y1, self.y2 = 0, -SH  # y2 начинается выше экрана (над y1)

    def update(self, speed):
        # Каждый кадр обе копии двигаются вниз на speed пикселей
        self.y1 += speed
        self.y2 += speed
        # Если копия ушла за нижний край — перебрасываем её наверх
        if self.y1 >= SH: self.y1 = -SH
        if self.y2 >= SH: self.y2 = -SH

    def draw(self, surf):
        # Рисуем обе копии — одна видна, вторая "заходит" сверху
        surf.blit(self.img, (0, self.y1))
        surf.blit(self.img, (0, self.y2))


# ── Player ────────────────────────────────────────────────────────────────────
# ЗАЧЕМ: класс игрока. Хранит картинку, позицию и состояния (щит, замедление).
# Наследуется от pygame.sprite.Sprite — это даёт встроенные методы коллизий.
class Player(pygame.sprite.Sprite):
    BASE_SPEED = 5

    def __init__(self, img):
        super().__init__()
        self.image      = img
        # Начальная позиция — по центру экрана, внизу (y=500)
        self.rect       = self.image.get_rect(center=(SW // 2, 500))
        self.shielded   = False  # активен ли щит
        self.slow_timer = 0      # сколько мс осталось замедления

    def move(self, dt):
        keys = pygame.key.get_pressed()
        # Если замедлен — скорость падает с 5 до 2
        spd  = max(2, self.BASE_SPEED - (2 if self.slow_timer > 0 else 0))
        if self.slow_timer > 0:
            self.slow_timer = max(0, self.slow_timer - dt)  # уменьшаем таймер каждый кадр
        # Движение по стрелкам с ограничением по краям дороги
        if keys[K_LEFT]  and self.rect.left   > ROAD_LEFT:    self.rect.x -= spd
        if keys[K_RIGHT] and self.rect.right  < ROAD_RIGHT:   self.rect.x += spd
        # Вертикальное движение — только в нижней половине экрана
        if keys[K_UP]    and self.rect.top    > SH // 2:      self.rect.y -= spd
        if keys[K_DOWN]  and self.rect.bottom < SH - 10:      self.rect.y += spd

    def apply_slow(self, ms):  self.slow_timer = max(self.slow_timer, ms)  # берём максимум — не сбрасываем если уже дольше
    def apply_shield(self):    self.shielded = True
    def remove_shield(self):   self.shielded = False


# ── Enemy / Traffic ───────────────────────────────────────────────────────────
# ЗАЧЕМ: вражеские машины, едущие сверху вниз.
# Случайно выбирают картинку из пула (красная/жёлтая/зелёная машина).
# _respawn() — перемещает машину обратно наверх когда она уходит за экран.
class Enemy(pygame.sprite.Sprite):
    def __init__(self, traffic_imgs, player_rect, extra_speed=0):
        super().__init__()
        # Случайно выбираем одну из картинок (Enemy.png, yellowcar, greencar)
        self.image       = random.choice(traffic_imgs)
        self.extra_speed = extra_speed  # дополнительная скорость (растёт с уровнем)
        self.rect        = self.image.get_rect()
        self._respawn(player_rect)

    def _respawn(self, player_rect):
        # Пытаемся 20 раз найти полосу, которая не совпадает с позицией игрока
        for _ in range(20):
            self.rect.centerx = _random_lane()
            self.rect.bottom  = random.randint(-140, -20)  # появляется выше экрана
            if abs(self.rect.centerx - player_rect.centerx) > 50:  # не прямо на игроке
                break

    def update(self, speed, player_rect):
        self.rect.y += speed + self.extra_speed  # двигается вниз каждый кадр
        if self.rect.top > SH:  # ушла за нижний край — возрождаем наверху
            self._respawn(player_rect)

    def boost(self, amt=0.5):
        # Вызывается когда игрок собирает каждые 5 монет — враги ускоряются
        self.extra_speed += amt


# ── Coin ──────────────────────────────────────────────────────────────────────
class Coin(pygame.sprite.Sprite):
    R = 14

    def __init__(self):
        super().__init__()
        label, col, ring, self.value, _ = _random_coin_type()
        size       = self.R * 2 + 2
        self.image = pygame.Surface((size, size), pygame.SRCALPHA)
        cx = cy    = self.R + 1
        pygame.draw.circle(self.image, col,  (cx, cy), self.R)
        pygame.draw.circle(self.image, ring, (cx, cy), self.R - 4)
        lbl = pygame.font.SysFont("arial", 14, bold=True).render(label, True, WHITE)
        self.image.blit(lbl, lbl.get_rect(center=(cx, cy)))
        self.rect = self.image.get_rect(center=(_random_lane(), -self.R))

    def update(self, speed):
        self.rect.y += speed


# ── Power-up ─────────────────────────────────────────────────────────────────
class PowerUp(pygame.sprite.Sprite):
    FALLBACK_SIZE = 36

    def __init__(self, kind, nitro_img=None):
        super().__init__()
        self.kind  = kind
        self.birth = pygame.time.get_ticks()

        if kind == "nitro" and nitro_img is not None:
            # Use real nitro.png sprite
            self.image = nitro_img.copy()
        else:
            # Draw shield / repair as coloured circles with emoji
            sz         = self.FALLBACK_SIZE
            self.image = pygame.Surface((sz, sz), pygame.SRCALPHA)
            col        = POWERUP_COLORS[kind]
            pygame.draw.circle(self.image, col,   (sz // 2, sz // 2), sz // 2)
            pygame.draw.circle(self.image, WHITE, (sz // 2, sz // 2), sz // 2, 2)
            fnt = pygame.font.SysFont("segoe ui emoji", 16)
            lbl = fnt.render(POWERUP_ICONS[kind], True, WHITE)
            self.image.blit(lbl, lbl.get_rect(center=(sz // 2, sz // 2)))

        self.rect = self.image.get_rect(center=(_random_lane(), -self.image.get_height()))

    def update(self, speed):
        self.rect.y += speed

    def expired(self):
        return pygame.time.get_ticks() - self.birth > POWERUP_LIFETIME


# ── Lane Hazard ───────────────────────────────────────────────────────────────
class LaneHazard(pygame.sprite.Sprite):
    KINDS = {
        "oil":  {"col": (30, 30, 60, 180),   "w": 60, "h": 30, "slow_ms": 2000},
        "slow": {"col": (200, 200, 0, 140),  "w": 80, "h": 20, "slow_ms": 1500},
    }

    def __init__(self, kind=None):
        super().__init__()
        self.kind    = kind or random.choice(list(self.KINDS))
        cfg          = self.KINDS[self.kind]
        self.slow_ms = cfg["slow_ms"]
        w, h         = cfg["w"], cfg["h"]
        self.image   = pygame.Surface((w, h), pygame.SRCALPHA)
        self.image.fill(cfg["col"])
        fnt = pygame.font.SysFont("arial", 11, bold=True)
        lbl = fnt.render("OIL" if self.kind == "oil" else "SLOW", True, WHITE)
        self.image.blit(lbl, lbl.get_rect(center=(w // 2, h // 2)))
        self.rect = self.image.get_rect(center=(_random_lane(), -h))

    def update(self, speed):
        self.rect.y += speed


# ── Road Event ────────────────────────────────────────────────────────────────
class RoadEvent(pygame.sprite.Sprite):
    KINDS = {
        "barrier":     {"w": 72, "h": 48, "effect": "stop"},
        "speedbump":   {"w": 80, "h": 14, "effect": "slow"},
        "nitro_strip": {"w": 80, "h": 14, "effect": "boost"},
    }

    def __init__(self, kind=None, barrier_img=None):
        super().__init__()
        self.kind   = kind or random.choice(list(self.KINDS))
        cfg         = self.KINDS[self.kind]
        self.effect = cfg["effect"]

        if self.kind == "barrier" and barrier_img is not None:
            self.image = barrier_img.copy()
        else:
            w, h       = cfg["w"], cfg["h"]
            col        = {"stop": (220, 50, 50), "slow": (180, 130, 20),
                          "boost": (50, 200, 200)}[self.effect]
            self.image = pygame.Surface((w, h), pygame.SRCALPHA)
            self.image.fill(col)
            fnt  = pygame.font.SysFont("arial", 10, bold=True)
            lbl_map = {"stop": "BARRIER", "slow": "BUMP", "boost": "NITRO"}
            lbl  = fnt.render(lbl_map[self.effect], True, WHITE)
            self.image.blit(lbl, lbl.get_rect(center=(w // 2, h // 2)))

        cx = _random_lane() if self.kind == "barrier" else SW // 2
        self.rect  = self.image.get_rect(center=(cx, -self.image.get_height()))
        self.drift = random.choice([-1, 0, 1]) if self.kind == "barrier" else 0

    def update(self, speed):
        self.rect.y += speed
        if self.drift:
            self.rect.x += self.drift
            self.rect.x  = max(ROAD_LEFT, min(ROAD_RIGHT - self.rect.w, self.rect.x))


# ── Obstacle ──────────────────────────────────────────────────────────────────
class Obstacle(pygame.sprite.Sprite):
    def __init__(self):
        super().__init__()
        kind       = random.choice(["pothole", "debris"])
        w, h       = (36, 18) if kind == "pothole" else (28, 28)
        self.image = pygame.Surface((w, h), pygame.SRCALPHA)
        if kind == "pothole":
            pygame.draw.ellipse(self.image, (40, 30, 20, 200), (0, 0, w, h))
            fnt = pygame.font.SysFont("arial", 10)
            self.image.blit(fnt.render("hole", True, (180, 160, 120)),
                            (4, 3))
        else:
            pygame.draw.rect(self.image, (160, 80, 20, 200), (0, 0, w, h))
        self.rect = self.image.get_rect(center=(_random_lane(), -h))

    def update(self, speed):
        self.rect.y += speed


# ── HUD ───────────────────────────────────────────────────────────────────────
def draw_hud(surf, score, coins, distance, active_pu, pu_ms_left,
             shielded, speed, nitro_active):
    fs = pygame.font.SysFont("Verdana", 14)
    fm = pygame.font.SysFont("Verdana", 17, bold=True)
    ft = pygame.font.SysFont("Verdana", 13)

    surf.blit(fs.render(f"Score: {score}", True, BLACK), (8, 6))

    cs = fm.render(f"Coins: {coins}", True, YELLOW)
    surf.blit(cs, (SW - cs.get_width() - 8, 6))

    spd_col = ORANGE if nitro_active else WHITE
    surf.blit(ft.render(f"Spd {speed:.1f}", True, spd_col), (8, 26))

    # Distance bar
    bx, by, bw, bh = 10, SH - 20, SW - 20, 8
    frac = min(1.0, distance / RACE_DISTANCE)
    pygame.draw.rect(surf, GREY,  (bx, by, bw, bh), border_radius=4)
    pygame.draw.rect(surf, GREEN, (bx, by, int(bw * frac), bh), border_radius=4)
    dl = ft.render(f"{distance}m / {RACE_DISTANCE}m", True, WHITE)
    surf.blit(dl, dl.get_rect(centerx=SW // 2, bottom=by - 2))

    # Power-up badge
    if active_pu:
        col   = POWERUP_COLORS[active_pu]
        badge = pygame.Rect(SW // 2 - 70, 26, 140, 26)
        pygame.draw.rect(surf, col, badge, border_radius=6)
        pygame.draw.rect(surf, WHITE, badge, 1, border_radius=6)
        txt = (f"{POWERUP_ICONS[active_pu]} {active_pu.upper()} {pu_ms_left//1000+1}s"
               if pu_ms_left > 0 else
               f"{POWERUP_ICONS[active_pu]} {active_pu.upper()}")
        lbl = ft.render(txt, True, WHITE)
        surf.blit(lbl, lbl.get_rect(center=badge.center))

    # Shield ring
    if shielded:
        pygame.draw.circle(surf, TEAL, (SW - 22, 42), 12, 3)
        surf.blit(ft.render("SHD", True, TEAL), (SW - 50, 36))


# ── Main game session ─────────────────────────────────────────────────────────
# ЗАЧЕМ: главная функция одной игровой сессии.
# Принимает все ресурсы (картинки, звуки, настройки) и запускает игровой цикл.
# Возвращает (action, score, distance, coins) когда игра заканчивается.
def run_game(surface, bg_img, traffic_imgs, nitro_img, barrier_img,
             player_img, crash_snd, bg_music,
             player_name: str, settings: dict):
    """
    Run one game session.
    Returns (action, score, distance, coins)
    """
    diff_key = settings.get("difficulty", "normal")
    dcfg     = DIFF[diff_key]
    sound_on = settings.get("sound", True)

    speed             = float(dcfg["base_speed"])
    score             = 0
    coins             = 0
    distance          = 0
    coins_since_boost = 0

    active_pu     = None
    pu_end_time   = 0
    nitro_active  = False
    shield_active = False
    crashes       = 0
    MAX_CRASHES   = 1

    bg  = ScrollingBackground(bg_img)
    clk = pygame.time.Clock()

    P1 = Player(player_img)

    enemies = pygame.sprite.Group()
    for _ in range(dcfg["enemy_count"]):
        enemies.add(Enemy(traffic_imgs, P1.rect))

    coins_grp     = pygame.sprite.Group()
    powerups_grp  = pygame.sprite.Group()
    hazards_grp   = pygame.sprite.Group()
    events_grp    = pygame.sprite.Group()
    obstacles_grp = pygame.sprite.Group()

    EV_SPEED    = USEREVENT + 1
    EV_COIN     = USEREVENT + 2
    EV_POWERUP  = USEREVENT + 3
    EV_HAZARD   = USEREVENT + 4
    EV_EVENT    = USEREVENT + 5
    EV_OBSTACLE = USEREVENT + 6
    EV_TRAFFIC  = USEREVENT + 7

    pygame.time.set_timer(EV_SPEED,    1200)
    pygame.time.set_timer(EV_COIN,     dcfg["coin_interval"])
    pygame.time.set_timer(EV_POWERUP,  6000)
    pygame.time.set_timer(EV_HAZARD,   3500)
    pygame.time.set_timer(EV_EVENT,    5000)
    pygame.time.set_timer(EV_OBSTACLE, dcfg["obs_interval"])
    pygame.time.set_timer(EV_TRAFFIC,  4000)

    if sound_on:
        pygame.mixer.music.load(bg_music)
        pygame.mixer.music.play(-1)

    # Seed initial hazards
    for _ in range(dcfg["hazard_count"]):
        h = LaneHazard()
        h.rect.y = random.randint(-SH, -50)
        hazards_grp.add(h)

    running = True
    while running:
        dt = clk.tick(FPS)

        # ── Events ───────────────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == QUIT:
                pygame.quit(); sys.exit()
            if event.type == KEYDOWN and event.key == K_ESCAPE:
                _stop_timers(EV_SPEED, EV_COIN, EV_POWERUP,
                             EV_HAZARD, EV_EVENT, EV_OBSTACLE, EV_TRAFFIC)
                pygame.mixer.music.stop()
                return ("menu", score, distance, coins)

            if event.type == EV_SPEED:
                speed = min(speed + 0.4, 18)
                if len(enemies) < dcfg["traffic_max"]:
                    enemies.add(Enemy(traffic_imgs, P1.rect,
                                      extra_speed=speed * 0.1))
            if event.type == EV_COIN:
                coins_grp.add(Coin())
            if event.type == EV_POWERUP:
                if len(powerups_grp) < 2:
                    kind = random.choice(["nitro", "shield", "repair"])
                    powerups_grp.add(PowerUp(kind,
                        nitro_img if kind == "nitro" else None))
            if event.type == EV_HAZARD:
                hazards_grp.add(LaneHazard())
            if event.type == EV_EVENT:
                events_grp.add(RoadEvent(barrier_img=barrier_img))
            if event.type == EV_OBSTACLE:
                obstacles_grp.add(Obstacle())
            if event.type == EV_TRAFFIC:
                if len(enemies) < dcfg["traffic_max"]:
                    enemies.add(Enemy(traffic_imgs, P1.rect))

        # ── Speed with nitro ──────────────────────────────────────────────────
        eff_speed = speed
        if nitro_active:
            if pygame.time.get_ticks() < pu_end_time:
                eff_speed = speed * 1.7
            else:
                nitro_active = False
                active_pu    = None

        # ── Move ─────────────────────────────────────────────────────────────
        bg.update(eff_speed)
        P1.move(dt)

        for e in enemies:
            e.update(eff_speed, P1.rect)
        for grp in (coins_grp, powerups_grp, hazards_grp, events_grp, obstacles_grp):
            for spr in list(grp):
                spr.update(eff_speed)
                if spr.rect.top > SH:
                    spr.kill()

        for pu in list(powerups_grp):
            if pu.expired():
                pu.kill()

        distance = min(RACE_DISTANCE, distance + int(eff_speed * dt / 600))

        # ── Coin collection ───────────────────────────────────────────────────
        for coin in pygame.sprite.spritecollide(P1, coins_grp, dokill=True):
            coins             += coin.value
            coins_since_boost += coin.value
            if coins_since_boost >= ENEMY_BOOST_EVERY:
                for e in enemies: e.boost(0.6)
                coins_since_boost -= ENEMY_BOOST_EVERY

        # ── Power-up collection ───────────────────────────────────────────────
        for pu in pygame.sprite.spritecollide(P1, powerups_grp, dokill=True):
            if pu.kind == "nitro" and not nitro_active:
                active_pu    = "nitro"
                nitro_active = True
                pu_end_time  = pygame.time.get_ticks() + POWERUP_DUR["nitro"]
            elif pu.kind == "shield" and not shield_active:
                active_pu     = "shield"
                shield_active = True
                P1.apply_shield()
            elif pu.kind == "repair" and crashes > 0:
                crashes  -= 1
                active_pu = "repair"

        # ── Hazards ───────────────────────────────────────────────────────────
        for h in pygame.sprite.spritecollide(P1, hazards_grp, dokill=False):
            P1.apply_slow(h.slow_ms)

        # ── Road events ───────────────────────────────────────────────────────
        for ev in pygame.sprite.spritecollide(P1, events_grp, dokill=True):
            if ev.effect == "boost" and not nitro_active:
                nitro_active = True
                active_pu    = "nitro"
                pu_end_time  = pygame.time.get_ticks() + 2500
            elif ev.effect == "slow":
                P1.apply_slow(1200)
            elif ev.effect == "stop":
                if shield_active:
                    shield_active = False; P1.remove_shield(); active_pu = None
                else:
                    crashes += 1
                    if crashes > MAX_CRASHES: running = False

        # ── Obstacles ─────────────────────────────────────────────────────────
        if pygame.sprite.spritecollide(P1, obstacles_grp, dokill=True):
            if shield_active:
                shield_active = False; P1.remove_shield(); active_pu = None
            else:
                crashes += 1
                if crashes > MAX_CRASHES: running = False

        # ── Enemy collision ───────────────────────────────────────────────────
        if pygame.sprite.spritecollideany(P1, enemies):
            if shield_active:
                shield_active = False; P1.remove_shield(); active_pu = None
                for e in list(enemies):
                    if pygame.sprite.collide_rect(P1, e):
                        e._respawn(P1.rect)
            else:
                running = False

        if distance >= RACE_DISTANCE:
            score += 500; running = False

        # Формула очков: каждая монета = 10 очков + каждые 5 метров = 1 очко
        score = coins * 10 + distance // 5

        # ── Render ────────────────────────────────────────────────────────────
        bg.draw(surface)

        for grp in (hazards_grp, events_grp, obstacles_grp, coins_grp, powerups_grp):
            for spr in grp:
                surface.blit(spr.image, spr.rect)

        # Player shield glow
        if shield_active:
            glow = pygame.Surface((P1.rect.w + 14, P1.rect.h + 14), pygame.SRCALPHA)
            pygame.draw.ellipse(glow, (0, 200, 200, 80), glow.get_rect())
            surface.blit(glow, (P1.rect.x - 7, P1.rect.y - 7))

        surface.blit(P1.image, P1.rect)
        for e in enemies:
            surface.blit(e.image, e.rect)

        draw_hud(surface, score, coins, distance,
                 active_pu,
                 max(0, pu_end_time - pygame.time.get_ticks()) if nitro_active else 0,
                 shield_active, eff_speed, nitro_active)

        pygame.display.flip()

    # ── Session end ───────────────────────────────────────────────────────────
    _stop_timers(EV_SPEED, EV_COIN, EV_POWERUP,
                 EV_HAZARD, EV_EVENT, EV_OBSTACLE, EV_TRAFFIC)
    pygame.mixer.music.stop()
    add_leaderboard_entry(player_name, score, distance, coins)
    return ("dead", score, distance, coins)


def _stop_timers(*events):
    for ev in events:
        pygame.time.set_timer(ev, 0)