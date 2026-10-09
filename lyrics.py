import ctypes
import math
import random
import sys
from functools import lru_cache

import pygame


BACKGROUND = (246, 246, 243)   # no longer used for the window, kept for reference
TRANSPARENT = (255, 0, 128)    # color key: this color becomes invisible
CARD_COLOR = (16, 14, 32)      # dark navy card body

lyrics = [
    ("Oh, ooh", 4.6, 0.49),
    ("Mamamatay akong nakangiti", 1.22, 0.13),  
    ("Kapag ikaw ang nasa aking tabi", 1.21, 0.13),
    ("Mabubuhay akong nagsisisi", 1.15, 0.12),
    ("Kapag isang araw hindi kita mapapangiti", 1.13, 0.10),
    ("Kalapastangan ang 'di ka ibigin", 1.13, 0.10),
    ("Kalokohan ang 'di ka isipin", 1.13, 0.10),
    ("Kung ang mundo ay biglang gugunawin", 1.12, 0.10),
    ("Ikaw ang una kong hahanapin", 1.12, 0.10),
]

SONG_DURATION = sum(len(line) * char_delay + line_delay
                    for line, line_delay, char_delay in lyrics)


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


def speaker_icon(surface, x, y, size, body_color, wave_color, elapsed, playing=True):
    """Speaker emoji drawn with shapes. While playing, sound waves appear one by one.
    When the song ends, the waves disappear (sound stopped)."""
    s = size
    pygame.draw.rect(surface, body_color, (x, y + int(s * 0.34), int(s * 0.2), int(s * 0.32)))
    pygame.draw.polygon(surface, body_color, [
        (x + int(s * 0.2), y + int(s * 0.34)),
        (x + int(s * 0.52), y + int(s * 0.08)),
        (x + int(s * 0.52), y + int(s * 0.92)),
        (x + int(s * 0.2), y + int(s * 0.66)),
    ])
    if not playing:
        return
    cx, cy = x + int(s * 0.58), y + s // 2
    visible_waves = int(elapsed * 3.2) % 4          # 0, 1, 2, 3 waves, then repeat
    thickness = max(2, s // 11)
    for i in range(visible_waves):
        r = int(s * (0.28 + 0.22 * i))
        arc_rect = pygame.Rect(cx - r, cy - r, r * 2, r * 2)
        pygame.draw.arc(surface, wave_color, arc_rect, -0.85, 0.85, thickness)


def lyric_state(elapsed):
    """Returns (text, line index, progress 0..1, finished)."""
    if elapsed < 2.0:
        return "Ready?", 0, min(1.0, elapsed / 2.0), False

    time_in_song = elapsed - 2.0
    time_in_song %= SONG_DURATION

    for index, (line, line_delay, char_delay) in enumerate(lyrics):
        typing_duration = len(line) * char_delay
        line_duration = typing_duration + line_delay
        if time_in_song < line_duration:
            visible_chars = min(len(line), int(time_in_song / char_delay) + 1)
            progress = time_in_song / line_duration
            return line[:visible_chars], index, progress, False
        time_in_song -= line_duration

    return lyrics[-1][0], len(lyrics) - 1, 1.0, False


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
    def __init__(self, quote, center_x, width_ratio, height_ratio, phase, accent, text_color):
        self.quote = quote
        self.center_x = center_x
        self.width_ratio = width_ratio
        self.height_ratio = height_ratio
        self.phase = phase
        self.accent = accent            # border / icon / ornaments
        self.text_color = text_color

        # Fixed palette derived from the accent (no color cycling).
        self.accent_dark = mix(accent, (0, 0, 0), 0.62)         # hard shadow, text shadow
        self.body_top = mix(CARD_COLOR, accent, 0.16)           # gradient top
        self.body_bottom = mix(CARD_COLOR, accent, 0.04)        # gradient bottom
        self.inner_line = mix(CARD_COLOR, accent, 0.45)         # thin inner border

    def draw(self, surface, size, elapsed, font, progress, playing=True):
        width, height = size
        card_width = min(int(width * self.width_ratio), width - 32)
        card_height = min(int(height * self.height_ratio), height - 32)
        progress = max(0.0, min(1.0, progress))
        is_ready_card = self.center_x == 0.5

        if is_ready_card:
            center = (width // 2, height // 2)
        else:
            center_x = int(width * self.center_x)
            start_y = int(height * 0.96)
            end_y = int(height * 0.38)
            center_y = int(start_y + (end_y - start_y) * progress * 1.5)
            rest_y = card_height // 2 + 24          # stops just below the top edge
            center = (center_x, max(rest_y, center_y))

        rect = pygame.Rect(0, 0, card_width, card_height)
        rect.center = center

        # Everything is hard-edged (no alpha, no anti-aliasing),
        # so the transparent color key leaves no pink fringe.
        radius = max(12, min(card_height // 5, 40))
        pulse = 0.5 + 0.5 * math.sin(elapsed * 2.5 + self.phase)
        border_color = mix(self.accent, (255, 255, 255), 0.22 * pulse)   # gentle shimmer

        # Hard retro shadow (the Ready card pulses it).
        offset = 9 + (4 * math.sin(elapsed * 5) if is_ready_card else 0)
        pygame.draw.rect(surface, self.accent_dark, rect.move(int(offset), int(offset)),
                         border_radius=radius)

        # Body: solid base, soft gradient on top, bright border, thin inner line.
        pygame.draw.rect(surface, CARD_COLOR, rect, border_radius=radius)
        fill_gradient_rounded(surface, rect.inflate(-4, -4), max(6, radius - 2),
                              self.body_top, self.body_bottom)
        pygame.draw.rect(surface, border_color, rect, width=5 if is_ready_card else 4,
                         border_radius=radius)
        pygame.draw.rect(surface, self.inner_line, rect.inflate(-22, -22), width=1,
                         border_radius=max(6, radius - 10))

        # Animated speaker in the top-left corner; it goes silent when the song ends.
        icon_size = max(26, min(44, card_height // 6))
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
            # Small ornament under the lyric: line with a dot on each end.
            ly = rect.bottom - 26
            half = int(card_width * 0.11)
            pygame.draw.line(surface, self.accent, (center[0] - half, ly), (center[0] + half, ly), 3)
            pygame.draw.circle(surface, self.accent, (center[0] - half - 10, ly), 3)
            pygame.draw.circle(surface, self.accent, (center[0] + half + 10, ly), 3)

        # Text: colored drop shadow first, then the main text on top.
        text_max_width = card_width * 0.78
        lines = wrap_text(self.quote, font, text_max_width)
        line_height = font.get_linesize()
        text_height = len(lines) * line_height
        text_y = center[1] - text_height // 2 - (10 if is_ready_card else 0)
        for line in lines:
            x = center[0]
            shadow = font.render(line, True, self.accent_dark)
            surface.blit(shadow, (x - shadow.get_width() // 2 + 3, text_y + 3))
            rendered = font.render(line, True, self.text_color)
            surface.blit(rendered, (x - rendered.get_width() // 2, text_y))
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

    # A tiny traveler gives the corner scene the same pixel-art scale as the reference.
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
        # Ready: gold + cream
        FloatingQuoteCard("Ready?", 0.5, 0.62, 0.48, 0,
                          accent=(255, 200, 70), text_color=(255, 244, 214)),
        # Left lyric card: red
        FloatingQuoteCard("", 0.27, 0.30, 0.18, 0,
                          accent=(255, 70, 80), text_color=(255, 45, 45)),
        # Right lyric card: yellow
        FloatingQuoteCard("", 0.73, 0.30, 0.18, 1.5,
                          accent=(255, 215, 60), text_color=(255, 225, 45)),
    ]
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
        lyric_size = max(19, min(35, int(min(width, height) * 0.039)))
        card_font = get_font(lyric_size)
        ready_font = get_font(int(lyric_size * 1.9))   # bigger text for "Ready?"

        screen.fill(TRANSPARENT)   # was: screen.fill(BACKGROUND)

        current_lyric, lyric_index, progress, finished = lyric_state(elapsed)
        is_ready = elapsed < 2.0
        active_card = cards[0] if is_ready else cards[1 + lyric_index % 2]
        active_card.quote = current_lyric
        font = ready_font if is_ready else card_font
        active_card.draw(screen, (width, height), elapsed, font, progress,
                         playing=not finished)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())