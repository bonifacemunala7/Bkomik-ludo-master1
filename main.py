"""
LUDO MASTER - single-file Kivy game (made for Pydroid 3 on Android)

Modes : Local (human / computer per colour), LAN 2-player (Host = RED, Guest = GREEN)
Run   : install Kivy in Pydroid (Menu > Pip > kivy) and press Play.
"""

import json
import math
import os
import random
import socket
import struct
import tempfile
import threading
import time
import wave

from kivy.app import App
from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, Line, Rectangle, Triangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

try:  # audio is optional - the game must still run without it
    from kivy.core.audio import SoundLoader
except Exception:
    SoundLoader = None


# ============================ GAME CONSTANTS ============================
# Board is a 15x15 grid. Cell = (column, row), row 0 is the TOP row.
# Yards: RED top-left, GREEN top-right, YELLOW bottom-right, BLUE bottom-left.
# Turn order is clockwise: RED -> GREEN -> YELLOW -> BLUE.

def _build_track():
    t = []
    t += [(x, 6) for x in range(1, 6)]          # red start (1,6) -> right
    t += [(6, y) for y in range(5, -1, -1)]     # up the top-left column
    t += [(7, 0), (8, 0)]                       # across the top
    t += [(8, y) for y in range(1, 6)]          # green start (8,1) -> down
    t += [(x, 6) for x in range(9, 15)]         # right along row 6
    t += [(14, 7), (14, 8)]                     # across the right edge
    t += [(x, 8) for x in range(13, 8, -1)]     # yellow start (13,8) -> left
    t += [(8, y) for y in range(9, 15)]         # down the bottom-right column
    t += [(7, 14), (6, 14)]                     # across the bottom
    t += [(6, y) for y in range(13, 8, -1)]     # blue start (6,13) -> up
    t += [(x, 8) for x in range(5, -1, -1)]     # left along row 8
    t += [(0, 7), (0, 6)]                       # across the left edge
    return t


TRACK = _build_track()
assert len(TRACK) == 52 and len(set(TRACK)) == 52

TRACK_LENGTH = 52
START_POSITIONS = [0, 13, 26, 39]
SAFE_SQUARES = {0, 8, 13, 21, 26, 34, 39, 47}

# A token's own progress: -1 = in yard, 0..50 = on the track (51 squares),
# 51..55 = home lane (5 squares), 56 = finished (centre).
HOME_ENTRY = 51
FINISH_POSITION = 56

PLAYER_NAMES = ["RED", "GREEN", "YELLOW", "BLUE"]
PLAYER_COLORS = [(0.88, 0.12, 0.12), (0.12, 0.65, 0.20),
                 (0.95, 0.72, 0.05), (0.12, 0.35, 0.88)]

YARDS = [(0, 0), (9, 0), (9, 9), (0, 9)]   # top-left corner cell of each 6x6 yard

BASE_POSITIONS = [
    [(1, 1), (4, 1), (1, 4), (4, 4)],
    [(10, 1), (13, 1), (10, 4), (13, 4)],
    [(10, 10), (13, 10), (10, 13), (13, 13)],
    [(1, 10), (4, 10), (1, 13), (4, 13)],
]

HOME_LANES = [
    [(1, 7), (2, 7), (3, 7), (4, 7), (5, 7)],
    [(7, 1), (7, 2), (7, 3), (7, 4), (7, 5)],
    [(13, 7), (12, 7), (11, 7), (10, 7), (9, 7)],
    [(7, 13), (7, 12), (7, 11), (7, 10), (7, 9)],
]

FINISH_CELLS = [(6.2, 7.0), (7.0, 6.2), (7.8, 7.0), (7.0, 7.8)]


# ============================ HELPERS ============================

def get_data_dir(app):
    """Return a writable folder, or None if nothing is writable."""
    candidates = []
    try:
        candidates.append(app.user_data_dir)
    except Exception:
        pass
    candidates.append(os.path.join(os.path.expanduser("~"), ".ludo_master"))
    candidates.append(os.path.join(tempfile.gettempdir(), "ludo_master"))
    for d in candidates:
        try:
            os.makedirs(d, exist_ok=True)
            probe = os.path.join(d, ".probe")
            with open(probe, "w") as f:
                f.write("x")
            return d
        except Exception:
            continue
    return None


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "unknown (check your Wi-Fi settings)"


def empty_stats():
    return {"games": 0, "wins": [0, 0, 0, 0], "captures": [0, 0, 0, 0],
            "sixes": 0, "history": [], "players": {}, "daily": {}}


def load_stats(app):
    """Load statistics defensively and repair malformed older save files."""
    defaults = empty_stats()
    if not app.data_dir:
        return defaults

    path = os.path.join(app.data_dir, "stats.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return defaults

        result = defaults.copy()
        for key in ("games", "sixes"):
            value = data.get(key, 0)
            result[key] = max(0, value) if type(value) is int else 0

        for key in ("wins", "captures"):
            values = data.get(key, [])
            if isinstance(values, list) and len(values) == 4:
                result[key] = [max(0, x) if type(x) is int else 0 for x in values]

        history = data.get("history", [])
        if isinstance(history, list):
            result["history"] = [x for x in history if isinstance(x, dict)][-50:]

        players = data.get("players", {})
        if isinstance(players, dict):
            clean_players = {}
            for name, record in players.items():
                if not isinstance(name, str) or not isinstance(record, dict):
                    continue
                clean_players[name[:20]] = {
                    key: max(0, record.get(key, 0)) if type(record.get(key, 0)) is int else 0
                    for key in ("wins", "captures", "games_won")
                }
            result["players"] = clean_players

        daily = data.get("daily", {})
        if isinstance(daily, dict):
            result["daily"] = {
                "date": daily.get("date", "") if isinstance(daily.get("date", ""), str) else "",
                "wins": max(0, daily.get("wins", 0)) if type(daily.get("wins", 0)) is int else 0,
                "completed": daily.get("completed", False) is True,
            }
        return result
    except (OSError, ValueError, TypeError):
        return defaults


def write_stats_safely(app, data):
    """Atomically replace stats.json so an interrupted write cannot truncate it."""
    if not app.data_dir:
        return False
    path = os.path.join(app.data_dir, "stats.json")
    temp_path = path + ".tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)
        return True
    except (OSError, TypeError, ValueError):
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass
        return False


# ============================ AUDIO ============================

class SoundManager:
    def __init__(self, app):
        self.app = app
        self.enabled = True
        self.sounds = {}

    def make_beep(self, name, freq, duration=0.10):
        folder = self.app.data_dir
        if not folder or SoundLoader is None:
            return
        path = os.path.join(folder, name + ".wav")
        if not os.path.exists(path):
            rate = 22050
            n = int(rate * duration)
            fade = max(1, int(rate * 0.01))
            buf = bytearray()
            for i in range(n):
                env = min(1.0, i / fade, (n - i) / fade)
                v = int(9000 * env * math.sin(2 * math.pi * freq * i / rate))
                buf += struct.pack("<h", v)
            with wave.open(path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(rate)
                wf.writeframes(bytes(buf))
        self.sounds[name] = SoundLoader.load(path)

    def setup(self):
        for name, freq, dur in (("dice", 520, .13), ("move", 720, .07),
                                ("capture", 260, .18), ("win", 880, .30)):
            try:
                self.make_beep(name, freq, dur)
            except Exception:
                self.sounds[name] = None

    def play(self, name):
        if not self.enabled:
            return
        s = self.sounds.get(name)
        if not s:
            return
        try:
            s.stop()
            s.play()
        except Exception:
            pass


# ============================ BOARD WIDGET ============================

class LudoBoard(Widget):
    def __init__(self, game, **kwargs):
        super().__init__(**kwargs)
        self.game = game
        self.selected_token = None
        self.animating = False
        self.bind(pos=self.redraw, size=self.redraw)

    # ---- geometry ----
    def metrics(self):
        side = min(self.width, self.height) / 15.0
        ox = self.x + (self.width - side * 15) / 2
        oy = self.y + (self.height - side * 15) / 2
        return side, ox, oy

    def cell_center(self, cell):
        side, ox, oy = self.metrics()
        x, y = cell
        return ox + (x + .5) * side, oy + (14 - y + .5) * side

    def cell_rect(self, x, y, w, h):
        side, ox, oy = self.metrics()
        return ox + x * side, oy + (15 - y - h) * side, w * side, h * side

    # ---- drawing ----
    def redraw(self, *args):
        self.canvas.clear()
        with self.canvas:
            Color(.96, .96, .96)
            Rectangle(pos=self.pos, size=self.size)
            self.draw_yards()
            self.draw_track()
            self.draw_home_lanes()
            self.draw_center()
            self.draw_tokens()

    def draw_yards(self):
        side = self.metrics()[0]
        for i, (x, y) in enumerate(YARDS):
            px, py, pw, ph = self.cell_rect(x, y, 6, 6)
            Color(*PLAYER_COLORS[i], .25)
            Rectangle(pos=(px, py), size=(pw, ph))
            Color(*PLAYER_COLORS[i], .85)
            Line(rectangle=(px, py, pw, ph), width=1.5)
            for cell in BASE_POSITIONS[i]:
                cx, cy = self.cell_center(cell)
                Color(1, 1, 1, .85)
                Ellipse(pos=(cx - side * .42, cy - side * .42), size=(side * .84, side * .84))

    def draw_track(self):
        side = self.metrics()[0]
        for idx, cell in enumerate(TRACK):
            cx, cy = self.cell_center(cell)
            Color(1, 1, 1)
            Rectangle(pos=(cx - side / 2, cy - side / 2), size=(side, side))
            if idx in START_POSITIONS:
                Color(*PLAYER_COLORS[START_POSITIONS.index(idx)], .6)
                Rectangle(pos=(cx - side / 2, cy - side / 2), size=(side, side))
            elif idx in SAFE_SQUARES:
                Color(.98, .85, .18, .9)
                Ellipse(pos=(cx - side * .25, cy - side * .25), size=(side * .5, side * .5))
            Color(.65, .65, .65)
            Line(rectangle=(cx - side / 2, cy - side / 2, side, side), width=.7)

    def draw_home_lanes(self):
        side = self.metrics()[0]
        for p, lane in enumerate(HOME_LANES):
            for cell in lane:
                cx, cy = self.cell_center(cell)
                Color(*PLAYER_COLORS[p], .55)
                Rectangle(pos=(cx - side / 2, cy - side / 2), size=(side, side))
                Color(.5, .5, .5)
                Line(rectangle=(cx - side / 2, cy - side / 2, side, side), width=.7)

    def draw_center(self):
        px, py, pw, ph = self.cell_rect(6, 6, 3, 3)
        tl, tr = (px, py + ph), (px + pw, py + ph)
        bl, br = (px, py), (px + pw, py)
        c = (px + pw / 2, py + ph / 2)
        for color, pts in ((PLAYER_COLORS[0], (tl, bl, c)),
                           (PLAYER_COLORS[1], (tl, tr, c)),
                           (PLAYER_COLORS[2], (tr, br, c)),
                           (PLAYER_COLORS[3], (bl, br, c))):
            Color(*color)
            Triangle(points=[pts[0][0], pts[0][1], pts[1][0], pts[1][1], pts[2][0], pts[2][1]])

    def token_cell(self, player, token, position=None):
        pos = self.game.tokens[player][token] if position is None else position
        if pos == -1:
            return BASE_POSITIONS[player][token]
        if pos >= FINISH_POSITION:
            fx, fy = FINISH_CELLS[player]
            return (fx + ((token % 2) - .5) * .3, fy + ((token // 2) - .5) * .3)
        if pos >= HOME_ENTRY:
            return HOME_LANES[player][pos - HOME_ENTRY]
        return TRACK[(START_POSITIONS[player] + pos) % TRACK_LENGTH]

    def token_draw_positions(self):
        """Return the exact on-screen token centres used by drawing and hit-testing."""
        g = self.game
        side = self.metrics()[0]
        groups = {}
        for p in range(4):
            if g.kinds[p] == "off":
                continue
            for t in range(4):
                groups.setdefault(self.token_cell(p, t), []).append((p, t))

        positions = {}
        for cell, members in groups.items():
            cx, cy = self.cell_center(cell)
            n = len(members)
            for k, key in enumerate(members):
                if n > 1:
                    ang = 2 * math.pi * k / n
                    x = cx + math.cos(ang) * side * .2
                    y = cy + math.sin(ang) * side * .2
                    radius = side * .24
                else:
                    x, y, radius = cx, cy, side * .29
                positions[key] = (x, y, radius)
        return positions

    def draw_tokens(self):
        g = self.game
        side = self.metrics()[0]
        positions = self.token_draw_positions()
        for (p, t), (x, y, r) in positions.items():
                legal = (p == g.current_player and g.is_human(p) and
                         t in g.legal_moves and not self.animating)
                if legal:
                    Color(1, 1, 1, .95)
                    Ellipse(pos=(x - r - side * .09, y - r - side * .09),
                            size=((r + side * .09) * 2, (r + side * .09) * 2))
                    Color(0, 0, 0, .9)
                    Line(circle=(x, y, r + side * .09), width=1.2)
                Color(*PLAYER_COLORS[p])
                Ellipse(pos=(x - r, y - r), size=(r * 2, r * 2))
                Color(1, 1, 1, .8)
                Line(circle=(x, y, r), width=1.1)
                if p == g.current_player and t == self.selected_token:
                    Color(0, 0, 0)
                    Line(circle=(x, y, r + side * .07), width=2)

    # ---- input ----
    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        g = self.game
        if not g.can_human_act() or g.dice_value is None:
            return True
        side = self.metrics()[0]
        positions = self.token_draw_positions()
        # Match the visible token offsets so stacked tokens can be selected individually.
        for t in g.legal_moves:
            centre = positions.get((g.current_player, t))
            if centre is None:
                continue
            cx, cy, token_radius = centre
            radius = max(dp(18), token_radius + side * .09)
            if (touch.x - cx) ** 2 + (touch.y - cy) ** 2 <= radius ** 2:
                self.selected_token = t
                g.start_move(t)
                return True
        return True


# ============================ GAME ENGINE ============================

class LudoGame:
    """kinds[p] is one of: 'human', 'ai', 'remote' (other device), 'off'."""

    def __init__(self, app, kinds, ai_difficulty="Medium", names=None, online=False, host=False):
        self.app = app
        self.kinds = list(kinds)
        self.ai_difficulty = ai_difficulty
        self.names = list(names) if names else PLAYER_NAMES[:]
        self.online = online
        self.host = host
        self.alive = True
        self.events = []
        self.anim_event = None
        self.current_player = next((i for i, k in enumerate(self.kinds) if k != "off"), 0)
        self.dice_value = None
        self.legal_moves = []
        self.game_over = False
        self.winner = None
        self.animating = False
        self.saved = False
        self.tokens = [[-1] * 4 for _ in range(4)]
        self.captures = [0] * 4
        self.stats = {"moves": 0, "sixes": 0, "captures": 0, "started": time.time()}
        self.board = LudoBoard(self)
        self.build_ui()

    # ---- lifecycle ----
    def schedule(self, fn, delay):
        def cb(dt):
            if self.alive:
                fn()
        ev = Clock.schedule_once(cb, delay)
        self.events.append(ev)
        return ev

    def destroy(self):
        self.alive = False
        for ev in self.events:
            try:
                ev.cancel()
            except Exception:
                pass
        self.events = []
        if self.anim_event is not None:
            try:
                self.anim_event.cancel()
            except Exception:
                pass
            self.anim_event = None

    # ---- who controls what ----
    def is_ai(self, p):
        return self.kinds[p] == "ai"

    def is_human(self, p):
        return self.kinds[p] == "human"

    def can_human_act(self):
        if not self.alive or self.game_over or self.animating:
            return False
        if not self.is_human(self.current_player):
            return False
        if self.online and not self.app.network.connected:
            return False
        return True

    # ---- UI ----
    def build_ui(self):
        self.root = BoxLayout(orientation="vertical", spacing=dp(5), padding=dp(5))
        self.info = Label(text="", size_hint_y=None, height=dp(46),
                          font_size=dp(16), halign="center", valign="middle")
        self.info.bind(size=lambda w, *_: setattr(w, "text_size", w.size))
        self.root.add_widget(self.info)
        self.root.add_widget(self.board)
        bottom = BoxLayout(size_hint_y=None, height=dp(58), spacing=dp(6))
        self.roll_button = Button(text="ROLL DICE", font_size=dp(17), bold=True,
                                  background_normal="", background_color=(.12, .58, .22, 1))
        self.roll_button.bind(on_release=lambda *_: self.roll_dice())
        bottom.add_widget(self.roll_button)
        menu = Button(text="MENU", background_normal="", background_color=(.20, .28, .40, 1))
        menu.bind(on_release=lambda *_: self.app.show_menu())
        bottom.add_widget(menu)
        self.root.add_widget(bottom)
        self.update_turn_display()
        self.schedule(self.auto_turn, .4)

    def update_turn_display(self):
        cur = self.current_player
        if self.game_over:
            text = "GAME OVER"
        elif self.online and not self.app.network.connected:
            text = "Waiting for opponent..."
        else:
            who = "COMPUTER" if self.is_ai(cur) else self.names[cur]
            dice = "-" if self.dice_value is None else str(self.dice_value)
            text = f"{who}  |  {PLAYER_NAMES[cur]}  |  Dice: {dice}"
        self.info.text = text
        self.info.color = tuple(PLAYER_COLORS[cur]) + (1,)
        self.roll_button.disabled = not (self.can_human_act() and self.dice_value is None)

    # ---- rules ----
    def get_legal_moves(self):
        if self.dice_value is None or self.game_over:
            return []
        result = []
        for t, pos in enumerate(self.tokens[self.current_player]):
            if pos == -1:
                if self.dice_value == 6:
                    result.append(t)
            elif pos + self.dice_value <= FINISH_POSITION:
                result.append(t)
        return result

    def roll_dice(self):
        if not self.can_human_act() or self.dice_value is not None:
            return
        self._roll()

    def _roll(self):
        self.dice_value = random.randint(1, 6)
        self.stats["moves"] += 1
        if self.dice_value == 6:
            self.stats["sixes"] += 1
        self.legal_moves = self.get_legal_moves()
        self.app.sounds.play("dice")
        self.update_turn_display()
        self.board.redraw()
        if self.online:
            self.app.network_send({"type": "roll", "value": self.dice_value})
        if not self.legal_moves:
            self.schedule(self.end_turn, .9)
        elif len(self.legal_moves) == 1 and self.is_human(self.current_player):
            # No choice is available: automatically move the only legal token.
            self.schedule(lambda: self.start_move(self.legal_moves[0])
                          if len(self.legal_moves) == 1 and self.dice_value is not None
                          else None, .45)

    def on_remote_roll(self, value):
        """Display the other device's roll; never execute its turn locally.

        The device that owns the active player performs the move (or passes)
        and then sends the authoritative state to its opponent.
        """
        if not self.alive or self.game_over:
            return
        if self.kinds[self.current_player] != "remote" or self.dice_value is not None:
            return
        if type(value) is not int or not 1 <= value <= 6:
            return
        self.dice_value = value
        self.legal_moves = self.get_legal_moves()
        self.app.sounds.play("dice")
        self.update_turn_display()
        self.board.redraw()
        # Do not move a remote token or call end_turn() here. The owning
        # device will send the updated state after its move/pass completes.

    def ai_choose_move(self):
        moves = self.legal_moves[:]
        if not moves:
            return None
        best, best_score = None, -10 ** 9
        for t in moves:
            old = self.tokens[self.current_player][t]
            new = 0 if old == -1 else old + self.dice_value
            score = 0
            if old == -1:
                score += 40
            score += new * 2
            if new == FINISH_POSITION:
                score += 180
            if self.would_capture(t):
                score += 100
            if self.ai_difficulty == "Easy":
                score = random.randint(0, 80)
            elif self.ai_difficulty == "Medium":
                score += random.randint(0, 25)
            else:
                score += random.randint(0, 8)
            if score > best_score:
                best_score, best = score, t
        return best

    def would_capture(self, t):
        old = self.tokens[self.current_player][t]
        new = 0 if old == -1 else old + self.dice_value
        if new >= HOME_ENTRY:
            return False
        g = (START_POSITIONS[self.current_player] + new) % TRACK_LENGTH
        if g in SAFE_SQUARES:
            return False
        for p in range(4):
            if p == self.current_player or self.kinds[p] == "off":
                continue
            for op in self.tokens[p]:
                if 0 <= op < HOME_ENTRY and (START_POSITIONS[p] + op) % TRACK_LENGTH == g:
                    return True
        return False

    def start_move(self, t):
        if (not self.alive or self.game_over or self.animating or
                t not in self.legal_moves or self.dice_value is None):
            return
        old = self.tokens[self.current_player][t]
        new = 0 if old == -1 else old + self.dice_value
        self.legal_moves = []
        self.animating = True
        self.board.selected_token = t
        self.board.animating = True
        self.update_turn_display()
        self.board.redraw()
        self.animate_token(self.current_player, t, old, new)

    def animate_token(self, p, t, old, new):
        start = max(0, old)
        total = 1 if old == -1 else max(1, new - old)
        state = {"step": 0}

        def tick(dt):
            if not self.alive:
                return False
            state["step"] += 1
            step = state["step"]
            self.tokens[p][t] = 0 if old == -1 else min(new, start + step)
            self.board.redraw()
            if step >= total:
                self.tokens[p][t] = new
                self.anim_event = None
                self.finish_move(p, t, new)
                return False
            return True

        self.anim_event = Clock.schedule_interval(tick, .12)

    def finish_move(self, p, t, new):
        self.tokens[p][t] = new
        self.animating = False
        self.board.animating = False
        self.board.selected_token = None
        self.app.sounds.play("move")
        if new < HOME_ENTRY:
            self.capture_opponents(p, t)
        if self.player_has_won(p):
            self.game_over = True
            self.winner = p
            self.app.sounds.play("win")
            self.save_stats(p)
            self.update_turn_display()
            self.board.redraw()
            self.sync_state()
            self.show_winner(p)
            return
        extra = (self.dice_value == 6)
        self.dice_value = None
        self.legal_moves = []
        self.update_turn_display()
        self.board.redraw()
        if extra:
            self.sync_state()
            self.schedule(self.auto_turn, .45)
        else:
            self.end_turn()

    def capture_opponents(self, p, t):
        pos = self.tokens[p][t]
        if pos < 0 or pos >= HOME_ENTRY:
            return
        g = (START_POSITIONS[p] + pos) % TRACK_LENGTH
        if g in SAFE_SQUARES:
            return
        for op in range(4):
            if op == p or self.kinds[op] == "off":
                continue
            for ot in range(4):
                opos = self.tokens[op][ot]
                if 0 <= opos < HOME_ENTRY and (START_POSITIONS[op] + opos) % TRACK_LENGTH == g:
                    self.tokens[op][ot] = -1
                    self.captures[p] += 1
                    self.stats["captures"] += 1
                    self.app.sounds.play("capture")

    def player_has_won(self, p):
        return all(x == FINISH_POSITION for x in self.tokens[p])

    def end_turn(self):
        if self.game_over or not self.alive:
            return
        self.dice_value = None
        self.legal_moves = []
        nxt = (self.current_player + 1) % 4
        while self.kinds[nxt] == "off":
            nxt = (nxt + 1) % 4
        self.current_player = nxt
        self.update_turn_display()
        self.board.redraw()
        self.sync_state()
        self.schedule(self.auto_turn, .35)

    def auto_turn(self):
        if self.game_over or not self.alive or self.dice_value is not None:
            return
        if self.is_ai(self.current_player):
            self._roll()
            if self.legal_moves:
                self.schedule(self.ai_move, .6)

    def ai_move(self):
        if self.game_over or not self.is_ai(self.current_player):
            return
        move = self.ai_choose_move()
        if move is not None:
            self.start_move(move)

    # ---- online sync ----
    def serialize(self):
        return {"tokens": self.tokens, "current": self.current_player,
                "dice": self.dice_value, "game_over": self.game_over,
                "winner": self.winner, "captures": self.captures}

    def sync_state(self):
        if self.online:
            self.app.network_send({"type": "state", "state": self.serialize()})

    def load_state(self, s):
        if not self.alive or self.animating:
            return
        try:
            if not isinstance(s, dict):
                return
            raw_tokens = s.get("tokens")
            if not isinstance(raw_tokens, list) or len(raw_tokens) != 4:
                return
            if any(not isinstance(row, list) or len(row) != 4 for row in raw_tokens):
                return
            if any(type(pos) is not int or pos < -1 or pos > FINISH_POSITION
                   for row in raw_tokens for pos in row):
                return
            tokens = [row[:] for row in raw_tokens]
            current = s.get("current")
            if type(current) is not int or not 0 <= current < 4:
                return
            dice = s.get("dice")
            if dice is not None and (type(dice) is not int or not 1 <= dice <= 6):
                return
            raw_captures = s.get("captures", [0] * 4)
            if (not isinstance(raw_captures, list) or len(raw_captures) != 4
                    or any(type(x) is not int or x < 0 for x in raw_captures)):
                return
            captures = raw_captures[:]
            winner = s.get("winner")
            if winner is not None and (type(winner) is not int or not 0 <= winner < 4):
                return
            game_over = s.get("game_over", False)
            if type(game_over) is not bool:
                return
            if game_over and winner is None:
                return
            if not game_over and winner is not None:
                return
            if self.kinds[current] == "off":
                return
            if game_over and not all(pos == FINISH_POSITION for pos in tokens[winner]):
                return
            self.tokens = tokens
            self.current_player = current
            self.dice_value = dice
            self.captures = captures
            self.legal_moves = self.get_legal_moves()
            was_over = self.game_over
            self.game_over = game_over
            self.winner = winner
        except Exception:
            return
        self.update_turn_display()
        self.board.redraw()
        if self.game_over and not was_over and self.winner is not None:
            self.app.sounds.play("win")
            self.save_stats(self.winner)
            self.show_winner(self.winner)

    # ---- end of game ----
    def show_winner(self, p):
        who = "COMPUTER" if self.is_ai(p) else self.names[p]
        box = BoxLayout(orientation="vertical", padding=dp(15), spacing=dp(10))
        box.add_widget(Label(text=f"{who} WINS!", font_size=dp(28)))
        box.add_widget(Label(text=f"Captures: {self.captures[p]}"))
        if not self.online:
            again = Button(text="PLAY AGAIN")
            again.bind(on_release=lambda *_: self.app.play_again())
            box.add_widget(again)
        menu = Button(text="MAIN MENU")
        menu.bind(on_release=lambda *_: self.app.show_menu())
        box.add_widget(menu)
        self.app.open_popup("GAME OVER", box, (.85, .55), auto_dismiss=False)

    def save_stats(self, winner):
        if self.saved or not self.app.data_dir:
            return
        self.saved = True
        try:
            data = load_stats(self.app)
            data["games"] += 1
            data["wins"][winner] += 1
            data["captures"][winner] += self.captures[winner]
            data["sixes"] += self.stats["sixes"]
            winner_name = "COMPUTER" if self.is_ai(winner) else str(self.names[winner])[:20]
            duration = max(0, int(time.time() - self.stats.get("started", time.time())))
            record = {"date": time.strftime("%Y-%m-%d %H:%M"),
                      "winner": winner_name, "colour": PLAYER_NAMES[winner],
                      "captures": int(self.captures[winner]),
                      "difficulty": self.ai_difficulty, "duration_seconds": duration,
                      "mode": "LAN" if self.online else "LOCAL"}
            data["history"].insert(0, record)
            data["history"] = data["history"][:50]
            # Human victories count toward player rankings and challenges; AI wins do not.
            if self.kinds[winner] != "ai":
                player = data["players"].setdefault(winner_name,
                    {"wins": 0, "captures": 0, "games_won": 0})
                player["wins"] = int(player.get("wins", 0)) + 1
                player["captures"] = int(player.get("captures", 0)) + int(self.captures[winner])
                player["games_won"] = int(player.get("games_won", 0)) + 1
                today = time.strftime("%Y-%m-%d")
                daily = data["daily"]
                if daily.get("date") != today:
                    daily.clear()
                    daily.update({"date": today, "wins": 0, "completed": False})
                daily["wins"] = int(daily.get("wins", 0)) + 1
                daily["completed"] = True  # Daily challenge: win at least one game today.
            write_stats_safely(self.app, data)
        except Exception:
            pass


# ============================ NETWORK (LAN, 2 players) ============================

class Network:
    PORT = 5050

    def __init__(self, app):
        self.app = app
        self.sock = None
        self.server = None
        self.running = False
        self.connected = False
        self.gen = 0   # bumped on close() so stale threads stop quietly
        self.room_code = None
        self.send_lock = threading.Lock()

    def host_game(self, room_code, port=PORT):
        self.close()
        gen = self.gen
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("0.0.0.0", port))
            srv.listen(1)
        except Exception:
            srv.close()
            raise
        srv.settimeout(1.0)
        self.server = srv
        self.room_code = str(room_code)
        self.running = True
        threading.Thread(target=self._accept, args=(srv, gen), daemon=True).start()

    def _read_handshake(self, conn):
        conn.settimeout(12)
        data = bytearray()
        while len(data) <= 4096:
            chunk = conn.recv(1)
            if not chunk:
                raise ConnectionError("Connection closed before room verification")
            if chunk == b"\n":
                break
            data.extend(chunk)
        else:
            raise ValueError("Room invitation is too large")
        obj = json.loads(data.decode("utf-8"))
        if not isinstance(obj, dict) or obj.get("type") != "join":
            raise ValueError("Invalid room invitation")
        if str(obj.get("code", "")) != str(self.room_code):
            raise ValueError("Incorrect room code")
        name = obj.get("name", "Guest")
        if not isinstance(name, str):
            name = "Guest"
        return name.strip()[:20] or "Guest"

    def _accept(self, srv, gen):
        # Keep listening after a bad room code or malformed handshake so the
        # intended guest can retry without restarting the host's room.
        while self.running and gen == self.gen:
            conn = None
            try:
                conn, _ = srv.accept()
                if gen != self.gen:
                    conn.close()
                    return
                guest_name = self._read_handshake(conn)
                conn.settimeout(None)
            except socket.timeout:
                continue
            except Exception as e:
                if conn is not None:
                    try:
                        conn.close()
                    except OSError:
                        pass
                if gen == self.gen:
                    Clock.schedule_once(
                        lambda dt, m=str(e): self.app.network_error("Room join failed: " + m), 0)
                continue

            self.sock = conn
            self.connected = True
            Clock.schedule_once(
                lambda dt, n=guest_name: self.app.network_message(
                    {"type": "profile", "player": 1, "name": n}), 0)
            Clock.schedule_once(lambda dt: self.app.network_connected(), 0)
            self._read_loop(conn, gen)
            # Keep the room listener alive after a guest disconnects. A guest
            # can reconnect by joining again with the same IP and room code.
            if gen != self.gen or not self.running:
                return

    def join_game(self, host, room_code, player_name, port=PORT):
        self.close()
        gen = self.gen
        self.running = True

        def run():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(8)
                s.connect((host, port))
                join_packet = {"type": "join", "code": str(room_code),
                               "name": str(player_name).strip()[:20] or "Guest"}
                s.sendall((json.dumps(join_packet) + "\n").encode("utf-8"))
                s.settimeout(None)
            except Exception as e:
                msg = str(e)
                if gen == self.gen:
                    Clock.schedule_once(
                        lambda dt, m=msg: self.app.network_error("Could not connect: " + m), 0)
                return
            if gen != self.gen:
                try:
                    s.close()
                except Exception:
                    pass
                return
            self.sock = s
            self.connected = True
            Clock.schedule_once(lambda dt: self.app.network_connected(), 0)
            self._read_loop(s, gen)

        threading.Thread(target=run, daemon=True).start()

    def send(self, obj):
        sock = self.sock
        if not sock or not self.connected:
            return False
        try:
            packet = (json.dumps(obj, separators=(",", ":")) + "\n").encode("utf-8")
            if len(packet) > 65536:
                return False
            with self.send_lock:
                if sock is not self.sock or not self.connected:
                    return False
                sock.sendall(packet)
            return True
        except OSError:
            self.connected = False
            Clock.schedule_once(lambda dt: self.app.network_lost(), 0)
            return False

    def _read_loop(self, sock, gen):
        buf = ""
        try:
            while self.running and gen == self.gen:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk.decode("utf-8", "strict")
                if len(buf) > 65536 and "\n" not in buf:
                    raise ValueError("Incoming network message is too large")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    if not line.strip():
                        continue
                    if len(line) > 65536:
                        raise ValueError("Incoming network message is too large")
                    try:
                        obj = json.loads(line)
                    except (json.JSONDecodeError, UnicodeError):
                        continue
                    if isinstance(obj, dict):
                        Clock.schedule_once(lambda dt, o=obj: self.app.network_message(o), 0)
        except (OSError, UnicodeError, ValueError):
            pass
        if self.running and gen == self.gen:
            self.connected = False
            Clock.schedule_once(lambda dt: self.app.network_lost(), 0)

    def close(self):
        self.gen += 1
        self.running = False
        self.connected = False
        for s in (self.sock, self.server):
            if s is None:
                continue
            try:
                s.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                s.close()
            except Exception:
                pass
        self.sock = None
        self.server = None


# ============================ SCREENS ============================

class MenuScreen(Screen):
    """Responsive, scrollable branded menu for narrow and tall Android screens."""
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        box = BoxLayout(orientation="vertical", padding=[dp(18), dp(18)],
                        spacing=dp(9), size_hint_y=None)
        box.bind(minimum_height=box.setter("height"))

        title = Label(text="[b][color=FFD54A]BKOMIK[/color] [color=FFFFFF]LUDO[/color][/b]",
                      markup=True, font_size=dp(32), size_hint_y=None,
                      height=dp(58), halign="center", valign="middle")
        title.bind(size=lambda w, *_: setattr(w, "text_size", w.size))
        box.add_widget(title)
        subtitle = Label(text="MASTER  •  PLAY  •  CHALLENGE  •  WIN",
                         font_size=dp(14), size_hint_y=None, height=dp(30),
                         color=(.75, .88, 1, 1))
        box.add_widget(subtitle)

        actions = [
            ("LOCAL GAME", app.show_setup, (0.12, .58, .22, 1)),
            ("LAN MULTIPLAYER - HOST", app.lan_host, (.10, .32, .78, 1)),
            ("LAN MULTIPLAYER - JOIN", app.lan_join, (.10, .32, .78, 1)),
            ("LEADERBOARD & ACHIEVEMENTS", app.show_progress, (.48, .20, .68, 1)),
            ("STATISTICS & HISTORY", app.show_stats, (.08, .48, .62, 1)),
            ("SETTINGS", app.show_settings, (.25, .31, .42, 1)),
        ]
        for caption, callback, tint in actions:
            button = Button(text=caption, font_size=dp(16), bold=True,
                            size_hint_y=None, height=dp(54),
                            background_normal="", background_down="",
                            background_color=tint, color=(1, 1, 1, 1))
            button.bind(on_release=lambda *_args, fn=callback: fn())
            box.add_widget(button)

        footer = Label(text="[color=FFD54A]BKOMIK[/color]  |  Game on. Anytime. Anywhere.",
                       markup=True, font_size=dp(12), size_hint_y=None,
                       height=dp(34), color=(.85, .9, 1, 1))
        box.add_widget(footer)
        scroll.add_widget(box)
        self.add_widget(scroll)


class SetupScreen(Screen):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.human = [True, False, False, False]
        self.diff = "Medium"
        box = BoxLayout(orientation="vertical", padding=dp(15), spacing=dp(8))
        box.add_widget(Label(text="LOCAL GAME SETUP", font_size=dp(26), size_hint_y=.12))
        grid = GridLayout(cols=2, size_hint_y=.32, spacing=dp(5))
        self.player_buttons = []
        for i in range(4):
            btn = Button(text=self.player_text(i))
            btn.bind(on_release=lambda b, i=i: self.toggle_player(b, i))
            self.player_buttons.append(btn)
            grid.add_widget(btn)
        box.add_widget(grid)
        self.difficulty = Button(text="AI DIFFICULTY: MEDIUM")
        self.difficulty.bind(on_release=self.cycle_difficulty)
        box.add_widget(self.difficulty)
        self.name_input = TextInput(text="Player", hint_text="Your name", multiline=False,
                                    size_hint_y=.12)
        box.add_widget(self.name_input)
        start = Button(text="START GAME", font_size=dp(20))
        start.bind(on_release=lambda *_: self.start())
        box.add_widget(start)
        back = Button(text="BACK")
        back.bind(on_release=lambda *_: app.show_menu())
        box.add_widget(back)
        self.add_widget(box)

    def player_text(self, i):
        return f"{PLAYER_NAMES[i]}: {'HUMAN' if self.human[i] else 'COMPUTER'}"

    def toggle_player(self, b, i):
        self.human[i] = not self.human[i]
        b.text = self.player_text(i)

    def cycle_difficulty(self, *_):
        self.diff = {"Easy": "Medium", "Medium": "Hard", "Hard": "Easy"}[self.diff]
        self.difficulty.text = f"AI DIFFICULTY: {self.diff.upper()}"

    def start(self):
        kinds = ["human" if h else "ai" for h in self.human]
        names = PLAYER_NAMES[:]
        typed = self.name_input.text.strip() or "Player"
        first_human = next((i for i, k in enumerate(kinds) if k == "human"), None)
        if first_human is not None:
            names[first_human] = typed
        self.app.start_game(kinds, self.diff, names)


class GameScreen(Screen):
    def set_game(self, game):
        self.clear_widgets()
        self.add_widget(game.root)


# ============================ APP ============================

class LudoApp(App):
    def build(self):
        self.title = "BKOMIK Ludo Master"
        self.icon = os.path.join(os.path.dirname(__file__), "bkomik_ludo_icon.png")
        self.popup = None
        self.game = None
        self.last_setup = None
        self.data_dir = get_data_dir(self)
        self.local_player_name = "Player"
        self.room_code = None
        self.sounds = SoundManager(self)
        try:
            self.sounds.setup()
        except Exception:
            pass
        self.network = Network(self)
        self.manager = ScreenManager()
        self.menu = MenuScreen(self, name="menu")
        self.setup = SetupScreen(self, name="setup")
        self.game_screen = GameScreen(name="game")
        self.manager.add_widget(self.menu)
        self.manager.add_widget(self.setup)
        self.manager.add_widget(self.game_screen)
        return self.manager

    def on_pause(self):
        return True   # keep the app alive when Android pauses it

    def on_resume(self):
        pass

    def on_stop(self):
        self.network.close()

    # ---- navigation ----
    def show_menu(self):
        self.close_popup()
        self.network.close()
        if self.game:
            self.game.destroy()
            self.game = None
        self.manager.current = "menu"

    def show_setup(self):
        self.manager.current = "setup"

    def start_game(self, kinds, difficulty="Medium", names=None, online=False, host=False):
        self.close_popup()
        self.network.close()
        if self.game:
            self.game.destroy()
        if not online:
            self.last_setup = (list(kinds), difficulty, list(names) if names else None)
        self.game = LudoGame(self, kinds, difficulty, names, online, host)
        self.game_screen.set_game(self.game)
        self.manager.current = "game"

    def play_again(self):
        if self.last_setup:
            kinds, diff, names = self.last_setup
            self.start_game(kinds, diff, names)
        else:
            self.show_menu()

    # ---- popups ----
    def close_popup(self):
        if self.popup:
            try:
                self.popup.dismiss()
            except Exception:
                pass
            self.popup = None

    def open_popup(self, title, content, size_hint, auto_dismiss=True):
        self.close_popup()
        self.popup = Popup(title=title, content=content, size_hint=size_hint,
                           auto_dismiss=auto_dismiss)
        self.popup.open()

    def show_message(self, title, text):
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        box.add_widget(Label(text=text, halign="center"))
        b = Button(text="OK", size_hint_y=None, height=dp(48))
        b.bind(on_release=lambda *_: self.close_popup())
        box.add_widget(b)
        self.open_popup(title, box, (.88, .5))

    def show_settings(self):
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        sound = Button(text=f"SOUND: {'ON' if self.sounds.enabled else 'OFF'}")
        sound.bind(on_release=lambda b: self.toggle_sound(b))
        box.add_widget(sound)
        close = Button(text="CLOSE")
        close.bind(on_release=lambda *_: self.close_popup())
        box.add_widget(close)
        self.open_popup("SETTINGS", box, (.8, .4))

    def toggle_sound(self, b):
        self.sounds.enabled = not self.sounds.enabled
        b.text = f"SOUND: {'ON' if self.sounds.enabled else 'OFF'}"

    def show_stats(self):
        data = load_stats(self)
        text = (f"Games: {data['games']}\n"
                f"Red wins: {data['wins'][0]}\nGreen wins: {data['wins'][1]}\n"
                f"Yellow wins: {data['wins'][2]}\nBlue wins: {data['wins'][3]}\n"
                f"Total captures: {sum(data['captures'])}\nSixes rolled: {data['sixes']}")
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        box.add_widget(Label(text=text, font_size=dp(17)))
        close = Button(text="CLOSE", size_hint_y=None, height=dp(48))
        close.bind(on_release=lambda *_: self.close_popup())
        box.add_widget(close)
        self.open_popup("STATISTICS", box, (.8, .65))

    def show_progress(self):
        data = load_stats(self)
        players = data.get("players", {})
        ranked = sorted(players.items(),
                        key=lambda item: (int(item[1].get("wins", 0)),
                                          int(item[1].get("captures", 0))), reverse=True)
        leaderboard = ["LOCAL LEADERBOARD (this device)"]
        if ranked:
            for rank, (name, values) in enumerate(ranked[:10], 1):
                leaderboard.append(f"{rank}. {name} — {values.get('wins', 0)} wins, {values.get('captures', 0)} captures")
        else:
            leaderboard.append("No completed games yet.")

        today = time.strftime("%Y-%m-%d")
        daily = data.get("daily", {})
        completed = daily.get("date") == today and daily.get("completed", False)
        challenge = "DAILY CHALLENGE: Win one game today.\n" + ("Completed!" if completed else "Progress: 0/1 wins")
        games = data.get("history", [])[:8]
        history = ["RECENT GAME HISTORY"]
        if games:
            for item in games:
                history.append(f"{item.get('date', '?')} | {item.get('winner', '?')} ({item.get('colour', '?')}) | {item.get('mode', 'LOCAL')} | {item.get('difficulty', 'Medium')}")
        else:
            history.append("No game history yet.")

        total_wins = sum(int(v.get("wins", 0)) for v in players.values())
        total_captures = sum(int(v.get("captures", 0)) for v in players.values())
        achievements = ["ACHIEVEMENTS"]
        checks = [("First Victory", total_wins >= 1),
                  ("Five Victories", total_wins >= 5),
                  ("Ten Victories", total_wins >= 10),
                  ("Capture Specialist (10 captures)", total_captures >= 10),
                  ("Capture Master (50 captures)", total_captures >= 50),
                  ("Daily Champion", completed)]
        achievements.extend(("[UNLOCKED] " if ok else "[LOCKED] ") + title for title, ok in checks)
        content = "\n\n".join((challenge, "\n".join(leaderboard),
                                  "\n".join(achievements), "\n".join(history)))
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        from kivy.uix.scrollview import ScrollView
        scroll = ScrollView()
        label = Label(text=content, font_size=dp(14), halign="left", valign="top",
                      size_hint_y=None)
        label.bind(texture_size=lambda inst, size: setattr(inst, "height", size[1] + dp(20)))
        label.text_size = (dp(310), None)
        scroll.add_widget(label)
        box.add_widget(scroll)
        close = Button(text="CLOSE", size_hint_y=None, height=dp(46))
        close.bind(on_release=lambda *_: self.close_popup())
        box.add_widget(close)
        self.open_popup("PLAYER PROGRESS", box, (.94, .88))

    # ---- LAN rooms ----
    def lan_host(self):
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        name_input = TextInput(text=self.local_player_name, hint_text="Your player name", multiline=False)
        box.add_widget(Label(text="Choose your player name (RED):"))
        box.add_widget(name_input)
        start = Button(text="CREATE PRIVATE WI-FI ROOM")
        box.add_widget(start)
        cancel = Button(text="CANCEL")
        cancel.bind(on_release=lambda *_: self.close_popup())
        box.add_widget(cancel)

        def create_room(*_):
            self.local_player_name = name_input.text.strip()[:20] or "Host"
            self.room_code = str(random.randint(100000, 999999))
            try:
                self.start_game(["human", "remote", "off", "off"], "Medium",
                                [self.local_player_name, "Guest", "", ""], online=True, host=True)
                self.network.host_game(self.room_code)
            except Exception as e:
                self.show_menu()
                self.show_message("LAN ERROR", f"Could not start hosting:\n{e}")
                return
            self.show_message("PRIVATE WI-FI ROOM",
                              f"Room code: {self.room_code}\n\n"
                              f"Host address: {get_local_ip()}\nPort: {Network.PORT}\n\n"
                              f"Give the other player BOTH the IP address and room code.\n"
                              f"Both phones must be on the same Wi-Fi.")

        start.bind(on_release=create_room)
        self.open_popup("CREATE ROOM", box, (.9, .55))

    def lan_join(self):
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        name_input = TextInput(text="Guest", hint_text="Your player name", multiline=False)
        ip_input = TextInput(hint_text="Host IP, e.g. 192.168.1.5", multiline=False)
        code_input = TextInput(hint_text="6-digit room code", multiline=False, input_filter="int")
        box.add_widget(name_input)
        box.add_widget(ip_input)
        box.add_widget(code_input)
        join = Button(text="JOIN PRIVATE ROOM")

        def do_join(*_):
            host = ip_input.text.strip()
            code = code_input.text.strip()
            if not host or len(code) != 6:
                self.show_message("ROOM DETAILS", "Enter the host IP address and the 6-digit room code.")
                return
            self.local_player_name = name_input.text.strip()[:20] or "Guest"
            self.start_game(["remote", "human", "off", "off"], "Medium",
                            ["Host", self.local_player_name, "", ""], online=True, host=False)
            self.network.join_game(host, code, self.local_player_name)
            self.show_message("CONNECTING", f"Joining private room at {host} ...")

        join.bind(on_release=do_join)
        box.add_widget(join)
        close = Button(text="CANCEL")
        close.bind(on_release=lambda *_: self.close_popup())
        box.add_widget(close)
        self.open_popup("JOIN WI-FI ROOM", box, (.9, .68))

    def network_send(self, obj):
        self.network.send(obj)

    def network_connected(self):
        if not self.game or not self.game.online:
            return
        self.close_popup()
        local_index = 0 if self.game.host else 1
        self.network_send({"type": "profile", "player": local_index,
                           "name": self.local_player_name})
        self.game.update_turn_display()
        if self.game.host:
            self.game.sync_state()

    def network_message(self, obj):
        g = self.game
        if not g or not g.online or not isinstance(obj, dict):
            return
        kind = obj.get("type")
        if kind == "profile":
            # Each peer may update only the other peer's player slot.
            remote_index = 1 if g.host else 0
            player = obj.get("player")
            name = obj.get("name")
            if type(player) is int and player == remote_index and isinstance(name, str):
                g.names[player] = name.strip()[:20] or "Player"
                g.update_turn_display()
        elif kind == "roll":
            g.on_remote_roll(obj.get("value"))
        elif kind == "state":
            state = obj.get("state")
            if isinstance(state, dict):
                g.load_state(state)

    def network_error(self, msg):
        if self.game:
            self.game.update_turn_display()
        self.show_message("NETWORK ERROR", msg)

    def network_lost(self):
        if self.game:
            self.game.update_turn_display()
        self.show_message("DISCONNECTED", "The other player disconnected.")


if __name__ == "__main__":
    LudoApp().run()
