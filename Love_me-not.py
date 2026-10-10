import ctypes
import math
import random
import sys
from functools import lru_cache

import pygame


BACKGROUND = (246, 246, 243)  
TRANSPARENT = (255, 0, 128)   
CARD_COLOR = (12, 18, 34)      

CLIP_START = 2 * 60 + 49         
CLIP_END = 3 * 60 + 22           
CLIP_LENGTH = CLIP_END - CLIP_START   
LEAD_IN = 2.0                    

LINE_DELAYS = [0.3, 0.9, 0.8, 0.7, 0.35, 0.8, 0.7, 0.6]

LYRIC_LINES = [
    "You're gonna say that you're sorry at the end of the night",
    "Wake up in the morning, everything's alright",
    "At the end of the story, you're holdin' me tight",
    "I don't need to worry, am I out of my mind?",
    "And, oh, it's hard to see you, but I wish you were right here (I'm losing my mind) ",
    "Oh, it's hard to leave you when I get you everywhere",
    "All this time I'm thinking, I'm strong enough to sink it",
    "Oh, no, I don't need you, but I miss you, come here",
]


def build_timeline():
    """Returns [(text, start_second, duration)] that fills exactly CLIP_LENGTH seconds."""
    weights = [len(line) + 12 for line in LYRIC_LINES]
    total = sum(weights)
    timeline, start = [], 0.0
    for line, w in zip(LYRIC_LINES, weights):
        duration = CLIP_LENGTH * w / total
        timeline.append((line, start, duration))
        start += duration
    return timeline


TIMELINE = build_timeline()
SONG_DURATION = CLIP_LENGTH

NOTE_COLORS = [
    (255, 120, 170), (120, 220, 255), (255, 215, 90),
    (170, 140, 255), (120, 255, 190), (255, 160, 90),
]


def make_window_transparent(always_on_top=True):
    """Make every pixel painted with TRANSPARENT invisible and click-through."""
    hwnd = pygame.display.get_wm_info()["window"]
    user32 = ctypes.windll.user32

    GWL_EXSTYLE = -20
    WS_EX_LAYERED = 0x00080000
    LWA_COLORKEY = 0x00000001
    HWND_TOPMOST = -1
    SWP_NOSIZE, SWP_NOMOVE = 0x0001, 0x0002

    # 64-bit safe argument/return types
    user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
    user32.SetLayeredWindowAttributes.argtypes = [
        ctypes.c_void_p, ctypes.c_uint, ctypes.c_ubyte, ctypes.c_uint]
    user32.SetWindowPos.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_uint]

    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)

    r, g, b = TRANSPARENT
    colorref = r | (g << 8) | (b << 16)   # Windows uses BGR order
    user32.SetLayeredWindowAttributes(hwnd, colorref, 0, LWA_COLORKEY)

    if always_on_top:
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)


@lru_cache(maxsize=16)
def get_font(size):
    """Fonts are cached so they are not rebuilt every frame."""
    return pygame.font.SysFont("georgia", size, bold=True)


def mix(a, b, t):
    """Blend color a toward color b by t (0..1)."""
    return (int(a[0] * (1 - t) + b[0] * t),
            int(a[1] * (1 - t) + b[1] * t),
            int(a[2] * (1 - t) + b[2] * t))


def fill_gradient_rounded(surface, rect, radius, top_color, bottom_color):
    """Vertical gradient inside a rounded rect, drawn line by line (hard edges, no alpha)."""
    for i in range(rect.height):
        t = i / max(1, rect.height - 1)
        color = mix(top_color, bottom_color, t)
        if i < radius:
            dy = radius - i - 0.5
        elif i >= rect.height - radius:
            dy = i - (rect.height - radius) + 0.5
        else:
            dy = 0
        inset = int(radius - math.sqrt(max(0.0, radius * radius - dy * dy))) if dy else 0
        y = rect.top + i
        pygame.draw.line(surface, color, (rect.left + inset, y), (rect.right - 1 - inset, y))


def sparkle(surface, x, y, size, color):
    """Little 4-point twinkle star."""
    s = max(1, size)
    points = [
        (x, y - s), (x + s * 0.28, y - s * 0.28), (x + s, y), (x + s * 0.28, y + s * 0.28),
        (x, y + s), (x - s * 0.28, y + s * 0.28), (x - s, y), (x - s * 0.28, y - s * 0.28),
    ]
    pygame.draw.polygon(surface, color, points)


def format_time(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


@lru_cache(maxsize=16)
def get_mono_font(size):
    return pygame.font.SysFont("consolas", size, bold=True)


def speaker_icon(surface, x, y, size, body_color, wave_color, elapsed, playing=True):
    """Pro equalizer badge: rounded dark chip with animated bars.
    Bars bounce while the song plays and go flat when it stops."""
    s = size
    chip = pygame.Rect(x, y, int(s * 1.25), s)
    pygame.draw.rect(surface, mix(wave_color, (0, 0, 0), 0.7), chip, border_radius=s // 4)
    pygame.draw.rect(surface, wave_color, chip, width=2, border_radius=s // 4)

    bars = 5
    pad = int(s * 0.2)
    gap = max(2, s // 14)
    bar_w = max(3, (chip.width - 2 * pad - gap * (bars - 1)) // bars)
    max_h = chip.height - 2 * pad
    total_w = bars * bar_w + gap * (bars - 1)
    left = chip.left + (chip.width - total_w) // 2
    for i in range(bars):
        if playing:
            wave = 0.5 + 0.5 * math.sin(elapsed * (5.5 + i * 1.3) + i * 1.9)
            h = int(max_h * (0.25 + 0.75 * wave))
        else:
            h = max(2, int(max_h * 0.18))
        bx = left + i * (bar_w + gap)
        by = chip.bottom - pad - h
        pygame.draw.rect(surface, body_color, (bx, by, bar_w, h), border_radius=bar_w // 2)


def lyric_state(elapsed):
    """Returns (text, line index, progress 0..1, finished)."""
    if elapsed < LEAD_IN:
        return "Ready?", 0, min(1.0, elapsed / LEAD_IN), False

    song_elapsed = elapsed - LEAD_IN
    if song_elapsed >= CLIP_LENGTH:
        return TIMELINE[-1][0], len(TIMELINE) - 1, 1.0, True

    t = song_elapsed % CLIP_LENGTH      # loops every 33 s

    for index, (line, start, duration) in enumerate(TIMELINE):
        if t < start + duration:
            local = t - start
            typing_time = max(0.2, duration - LINE_DELAYS[index])
            visible = min(len(line), int(local / typing_time * len(line)) + 1)
            return line[:visible], index, local / duration, False

    return TIMELINE[-1][0], len(TIMELINE) - 1, 1.0, False


class Star:
    def __init__(self, width, height):
        self.x = random.uniform(0, width)
        self.y = random.uniform(0, height)
        self.radius = random.choice((1, 1, 1, 2))
        self.phase = random.uniform(0, math.tau)
        self.speed = random.uniform(0.7, 2.0)
        self.brightness = random.randint(105, 220)

    def draw(self, surface, elapsed):
        shimmer = (math.sin(elapsed * self.speed + self.phase) + 1) * 0.5
        value = int(self.brightness * (0.55 + shimmer * 0.45))
        pygame.draw.circle(surface, (value, value, min(255, value + 4)),
                           (int(self.x), int(self.y)), self.radius)


class FloatingQuoteCard:
    def __init__(self, quote, center_x, width_ratio, height_ratio, phase,
                 accent, text_color, lane_y=0.5):
        self.quote = quote
        self.center_x = center_x
        self.width_ratio = width_ratio
        self.height_ratio = height_ratio
        self.phase = phase
        self.accent = accent            
        self.text_color = text_color
        self.lane_y = lane_y           

        self.accent_dark = mix(accent, (0, 0, 0), 0.62)         # hard shadow, text shadow
        self.body_top = mix(CARD_COLOR, accent, 0.16)           # gradient top
        self.body_bottom = mix(CARD_COLOR, accent, 0.04)        # gradient bottom
        self.inner_line = mix(CARD_COLOR, accent, 0.45)         # thin inner border

    def draw(self, surface, size, elapsed, font, progress, playing=True, full_text=None):
        width, height = size
        full_text = full_text if full_text is not None else self.quote
        is_ready_card = self.center_x == 0.5

        card_width = min(int(width * self.width_ratio), width - 32)
        base_height = min(int(height * self.height_ratio), height - 32)
        progress = max(0.0, min(1.0, progress))

        text_max_width = card_width * 0.78
        lines = wrap_text(full_text, font, text_max_width)
        line_height = font.get_linesize()
        text_height = len(lines) * line_height

        icon_size = max(26, min(44, base_height // 6))
        top_pad = icon_size + 36        
        bottom_pad = 48                 
        needed_height = text_height + top_pad + bottom_pad
        card_height = min(max(base_height, needed_height), height - 32)

        if is_ready_card:
            center = (width // 2, height // 2)
        else:
            # Slide from the left side to the right side as the line plays.
            margin = 16
            start_x = margin + card_width // 2              # left side
            end_x = width - margin - card_width // 2        # right side
            center_x = int(start_x + (end_x - start_x) * progress)

            # Gentle floating bob so it still feels alive.
            center_y = int(height * self.lane_y + 8 * math.sin(elapsed * 2 + self.phase))
            half_h = card_height // 2 + 16
            center_y = max(half_h, min(height - half_h, center_y))

            center = (center_x, center_y)

        rect = pygame.Rect(0, 0, card_width, card_height)
        rect.center = center

        radius = max(12, min(card_height // 5, 40))
        pulse = 0.5 + 0.5 * math.sin(elapsed * 2.5 + self.phase)
        border_color = mix(self.accent, (255, 255, 255), 0.22 * pulse)   # gentle shimmer

        # Neon glow rings (hard-edged, fading outward) that breathe with the beat.
        for i, shade in ((3, 0.80), (2, 0.68), (1, 0.52)):
            grow = int(i * 6 + 2 * pulse)
            pygame.draw.rect(surface, mix(self.accent, (0, 0, 0), shade),
                             rect.inflate(grow * 2, grow * 2), width=2,
                             border_radius=radius + grow)

        offset = 9 + (4 * math.sin(elapsed * 5) if is_ready_card else 0)
        pygame.draw.rect(surface, self.accent_dark, rect.move(int(offset), int(offset)),
                         border_radius=radius)

        pygame.draw.rect(surface, CARD_COLOR, rect, border_radius=radius)
        fill_gradient_rounded(surface, rect.inflate(-4, -4), max(6, radius - 2),
                              self.body_top, self.body_bottom)
        pygame.draw.rect(surface, border_color, rect, width=5 if is_ready_card else 4,
                         border_radius=radius)
        pygame.draw.rect(surface, self.inner_line, rect.inflate(-22, -22), width=1,
                         border_radius=max(6, radius - 10))

        shine = mix(self.accent, (255, 255, 255), 0.55)
        pygame.draw.line(surface, shine, (rect.left + radius, rect.top + 9),
                         (rect.right - radius, rect.top + 9), 2)
        bracket = rect.inflate(26, 26)
        arm = max(14, min(card_height // 6, 40))
        for cx, cy, dx, dy in ((bracket.left, bracket.top, 1, 1),
                               (bracket.right - 1, bracket.top, -1, 1),
                               (bracket.left, bracket.bottom - 1, 1, -1),
                               (bracket.right - 1, bracket.bottom - 1, -1, -1)):
            pygame.draw.line(surface, shine, (cx, cy), (cx + dx * arm, cy), 3)
            pygame.draw.line(surface, shine, (cx, cy), (cx, cy + dy * arm), 3)

        body_color = self.text_color if playing else mix(self.accent, (0, 0, 0), 0.4)
        speaker_icon(surface, rect.left + 24, rect.top + 22, icon_size,
                     body_color, self.accent, elapsed, playing)

        if is_ready_card:
            # Twinkles + a loading bar that fills as "Ready?" counts down.
            for i, (sx, sy) in enumerate((
                    (rect.right - 40, rect.top + 40),
                    (rect.right - 70, rect.bottom - 60),
                    (rect.left + 60, rect.bottom - 60))):
                twinkle = 9 + 7 * math.sin(elapsed * 4 + i * 2)
                sparkle(surface, sx, sy, int(twinkle), self.accent)

            bar_width = int(card_width * 0.5)
            bar_rect = pygame.Rect(0, 0, bar_width, 8)
            bar_rect.center = (center[0], rect.bottom - 38)
            pygame.draw.rect(surface, self.accent_dark, bar_rect, border_radius=4)
            fill = pygame.Rect(bar_rect.x, bar_rect.y, int(bar_width * progress), bar_rect.height)
            if fill.width > 0:
                pygame.draw.rect(surface, self.accent, fill, border_radius=4)
        else:
 
            ly = rect.bottom - 26
            half = int(card_width * 0.11)
            pygame.draw.line(surface, self.accent, (center[0] - half, ly), (center[0] + half, ly), 3)
            pygame.draw.circle(surface, self.accent, (center[0] - half - 10, ly), 3)
            pygame.draw.circle(surface, self.accent, (center[0] + half + 10, ly), 3)

        if is_ready_card:
            text_y = center[1] - text_height // 2 - 10
        else:
            area_top = rect.top + top_pad
            area_height = card_height - top_pad - bottom_pad
            text_y = area_top + (area_height - text_height) // 2

        remaining = len(self.quote)
        for line in lines:
            shown = line[:max(0, remaining)]
            remaining -= len(line) + 1        
            if shown:
                left_x = center[0] - font.size(line)[0] // 2
                shadow = font.render(shown, True, self.accent_dark)
                surface.blit(shadow, (left_x + 3, text_y + 3))
                rendered = font.render(shown, True, self.text_color)
                surface.blit(rendered, (left_x, text_y))
            text_y += line_height


def wrap_text(text, font, max_width):
    words = text.split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and font.size(candidate)[0] > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def snowflake(surface, x, y, radius, color):
    x, y, radius = int(x), int(y), int(radius)
    for angle in (0, math.pi / 3, 2 * math.pi / 3):
        dx, dy = math.cos(angle) * radius, math.sin(angle) * radius
        pygame.draw.line(surface, color, (x - dx, y - dy), (x + dx, y + dy), 2)
        for direction in (-1, 1):
            tip_x, tip_y = x + direction * dx * 0.58, y + direction * dy * 0.58
            for branch_angle in (angle + math.pi / 3, angle - math.pi / 3):
                branch_x = tip_x - direction * math.cos(branch_angle) * radius * 0.24
                branch_y = tip_y - direction * math.sin(branch_angle) * radius * 0.24
                pygame.draw.line(surface, color, (int(tip_x), int(tip_y)),
                                 (int(branch_x), int(branch_y)), 1)


def music_note(surface, x, y, scale=1.0, color=(191, 190, 185)):
    x, y = int(x), int(y)
    pygame.draw.line(surface, color, (x + int(13 * scale), y),
                     (x + int(13 * scale), y + int(25 * scale)), max(1, int(2 * scale)))
    pygame.draw.line(surface, color, (x + int(13 * scale), y),
                     (x + int(25 * scale), y - int(4 * scale)), max(1, int(2 * scale)))
    pygame.draw.line(surface, color, (x + int(25 * scale), y - int(4 * scale)),
                     (x + int(25 * scale), y + int(20 * scale)), max(1, int(2 * scale)))
    pygame.draw.ellipse(surface, color, (x, y + int(20 * scale), int(13 * scale), int(8 * scale)))
    pygame.draw.ellipse(surface, color, (x + int(12 * scale), y + int(15 * scale), int(13 * scale), int(8 * scale)))


def beamed_note(surface, x, y, scale, color):
    """Double eighth note."""
    x, y = int(x), int(y)
    w = max(2, int(2.5 * scale))
    head_w, head_h = int(13 * scale), int(9 * scale)
    gap = int(20 * scale)
    stem_h = int(30 * scale)
    # heads
    pygame.draw.ellipse(surface, color, (x, y + stem_h - head_h // 2, head_w, head_h))
    pygame.draw.ellipse(surface, color, (x + gap, y + stem_h - head_h // 2, head_w, head_h))
    # stems
    sx1, sx2 = x + head_w - w, x + gap + head_w - w
    pygame.draw.line(surface, color, (sx1, y + stem_h), (sx1, y), w)
    pygame.draw.line(surface, color, (sx2, y + stem_h), (sx2, y - int(3 * scale)), w)
    # beam
    pygame.draw.polygon(surface, color, [
        (sx1, y), (sx2 + w, y - int(3 * scale)),
        (sx2 + w, y + int(4 * scale)), (sx1, y + int(7 * scale))])


class FloatingNote:
    """A music note that drifts upward and sways. Position depends only on time."""

    def __init__(self):
        self.x0 = random.random()
        self.y0 = random.random() * 1.2
        self.speed = random.uniform(0.04, 0.12)         
        self.sway = random.uniform(0.012, 0.035)
        self.sway_speed = random.uniform(0.6, 1.6)
        self.phase = random.uniform(0, math.tau)
        self.scale = random.uniform(0.8, 1.9)
        self.color = random.choice(NOTE_COLORS)
        self.double = random.random() < 0.4

    def draw(self, surface, size, elapsed):
        width, height = size
        y_norm = 1.1 - ((self.y0 + self.speed * elapsed) % 1.2)   # bottom -> top, then wraps
        x_norm = self.x0 + self.sway * math.sin(elapsed * self.sway_speed + self.phase)
        x, y = x_norm * width, y_norm * height
        pulse = 1 + 0.12 * math.sin(elapsed * 3 + self.phase)      # little "beat"
        s = self.scale * pulse * max(0.7, min(width, height) / 800)
        shadow = mix(self.color, (0, 0, 0), 0.65)
        draw_note = beamed_note if self.double else music_note
        draw_note(surface, x + 3 * s, y + 3 * s, s, shadow)    
        draw_note(surface, x, y, s, self.color)
        twinkle = 3 + 3 * math.sin(elapsed * 4 + self.phase * 2)
        if twinkle > 1:
            sparkle(surface, x - 8 * s, y - 6 * s, int(twinkle * s), (255, 244, 214))


def make_notes(count=26):
    return [FloatingNote() for _ in range(count)]


def draw_pixel_landscape(surface, width, height, elapsed):
    unit = max(3, min(width, height) // 130)
    left, bottom = int(width * 0.025), height - int(height * 0.035)
    blocks = [
        (0, 0, 10, 6, (67, 108, 120)), (10, 2, 9, 5, (88, 133, 144)),
        (4, 6, 13, 4, (107, 148, 153)), (17, 5, 12, 7, (53, 89, 111)),
        (26, 7, 11, 5, (83, 122, 141)), (3, 10, 10, 4, (29, 47, 64)),
        (13, 11, 12, 5, (42, 67, 86)), (25, 12, 13, 4, (30, 48, 64)),
        (0, 14, 14, 6, (18, 29, 42)), (14, 16, 13, 5, (26, 38, 49)),
        (27, 16, 13, 6, (19, 30, 42)),
    ]
    for column, row, block_width, block_height, color in blocks:
        pygame.draw.rect(surface, color,
                         (left + column * unit, bottom - (row + block_height) * unit,
                          block_width * unit, block_height * unit))

    px, py = left + 8 * unit, bottom - 14 * unit
    person = [
        (1, 0, 3, 2, (224, 190, 145)), (0, 2, 5, 3, (56, 47, 47)),
        (1, 5, 4, 3, (139, 77, 62)), (0, 8, 3, 2, (32, 36, 42)),
        (4, 8, 3, 2, (32, 36, 42)), (2, 2, 1, 1, (25, 25, 27)),
    ]
    for column, row, block_width, block_height, color in person:
        pygame.draw.rect(surface, color,
                         (px + column * unit, py + row * unit,
                          block_width * unit, block_height * unit))
    glow = 0.5 + 0.5 * math.sin(elapsed * 1.3)
    snowflake(surface, left + 33 * unit, bottom - 20 * unit, unit * (1.2 + glow * 0.25), (147, 187, 192))


def make_stars(width, height, count=430):
    return [Star(width, height) for _ in range(count)]


def main():
    pygame.init()
    window_flags = pygame.RESIZABLE | pygame.NOFRAME
    screen = pygame.display.set_mode((0, 0), window_flags)
    make_window_transparent()
    clock = pygame.time.Clock()
    started_at = pygame.time.get_ticks() / 1000
    size = screen.get_size()
    cards = [
  
        FloatingQuoteCard("Ready?", 0.5, 0.62, 0.48, 0,
                          accent=(170, 120, 255), text_color=(240, 230, 255)),
      
        FloatingQuoteCard("", 0.27, 0.37, 0.24, 0,
                          accent=(0, 215, 255), text_color=(190, 250, 255),
                          lane_y=0.30),
     
        FloatingQuoteCard("", 0.73, 0.37, 0.24, 1.5,
                          accent=(255, 80, 190), text_color=(255, 205, 240),
                          lane_y=0.68),
    ]
    notes = make_notes()
    fullscreen = False
    window_size = size
    running = True

    while running:
        elapsed = pygame.time.get_ticks() / 1000 - started_at
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_r:
                    started_at = pygame.time.get_ticks() / 1000   # R = restart the song
                elif event.key == pygame.K_F11:
                    fullscreen = not fullscreen
                    if fullscreen:
                        window_size = screen.get_size()
                        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                    else:
                        screen = pygame.display.set_mode(window_size, window_flags)
                    make_window_transparent()
            elif event.type == pygame.VIDEORESIZE and not fullscreen:
                window_size = (max(480, event.w), max(320, event.h))
                screen = pygame.display.set_mode(window_size, window_flags)
                make_window_transparent()

        width, height = screen.get_size()
        lyric_size = max(21, min(40, int(min(width, height) * 0.044)))
        card_font = get_font(lyric_size)
        ready_font = get_font(int(lyric_size * 1.9))   

        screen.fill(TRANSPARENT)

    
        for note in notes:
            note.draw(screen, (width, height), elapsed)

        current_lyric, lyric_index, progress, finished = lyric_state(elapsed)
        is_ready = elapsed < LEAD_IN
        active_card = cards[0] if is_ready else cards[1 + lyric_index % 2]
        active_card.quote = current_lyric
        full_text = "Ready?" if is_ready else TIMELINE[lyric_index][0]
        font = ready_font if is_ready else card_font
        active_card.draw(screen, (width, height), elapsed, font, progress,
                         playing=not finished, full_text=full_text)

        if finished:
            running = False

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())    