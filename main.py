import ctypes
import ctypes.wintypes
import difflib
import glob
import hashlib
import io
import json
import os
import platform
import queue
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import tkinter as tk
import tkinter.colorchooser
import tkinter.filedialog
import tkinter.font
import urllib.error
import urllib.request
import zipfile
import zlib

from PIL import Image, ImageEnhance, ImageTk

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

IS_WINDOWS = os.name == "nt"
FROZEN = getattr(sys, "frozen", False)
APP_DIR = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.abspath(__file__))
RESOURCE_DIR = getattr(sys, "_MEIPASS", APP_DIR)
SETTINGS_PATH = os.path.join(APP_DIR, "settings.json")
STATUSBAR_PATH = os.path.join(APP_DIR, "statusbar.json")
PRESETS_PATH = os.path.join(APP_DIR, "presets.json")
NETCONFIG_PATH = os.path.join(APP_DIR, "netconfig.json")
INSTALL_DIR = os.path.join(APP_DIR, "installed")

DEFAULT_SETTINGS = {
    "font": "Terminal",
    "size": 12,
    "fg": "#ff0000",
    "bg": "#000000",
    "background_image": "",
    "dim": 0.6,
    "margin": 16,
    "icon": "",
}

SPEED_SERVERS = [
    ("Cloudflare", "https://speed.cloudflare.com/__down?bytes=25000000"),
    ("Hetzner", "https://speed.hetzner.de/100MB.bin"),
    ("OVH", "http://proof.ovh.net/files/10Mb.dat"),
    ("Tele2", "http://speedtest.tele2.net/10MB.zip"),
]

DEFAULT_STATUSBAR = {
    "enabled": True,
    "server": "auto",
    "interval": 2.0,
    "scroll_speed": 2,
    "items": ["down", "ping", "server", "ip", "host", "time"],
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".ico"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".oga", ".opus", ".m4a", ".aac", ".wma", ".aiff", ".aif"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".flv", ".m4v", ".mpg", ".mpeg", ".ts"}
TEXT_EXTENSIONS = {".txt", ".log", ".md", ".json", ".xml", ".csv", ".ini", ".cfg", ".py", ".bat", ".cmd", ".ps1",
                   ".html", ".htm", ".css", ".js", ".yml", ".yaml", ".toml", ".c", ".h", ".cpp", ".java", ".sh", ".conf"}
COVER_NAMES = ("cover", "folder", "front", "album", "albumart", "albumartsmall", "thumb")
COVER_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
AUDIO_CHUNK_SECONDS = 180.0


class JsonStore:
    def __init__(self, path, defaults):
        self.path = path
        self.defaults = defaults
        self.data = json.loads(json.dumps(defaults))
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, dict):
                self.data.update(loaded)
        except (OSError, ValueError):
            pass

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as handle:
                json.dump(self.data, handle, indent=2)
        except OSError:
            pass


def blend_colors(first, second, ratio):
    try:
        r1, g1, b1 = [value // 256 for value in tk._default_root.winfo_rgb(first)]
        r2, g2, b2 = [value // 256 for value in tk._default_root.winfo_rgb(second)]
    except (tk.TclError, AttributeError):
        return first
    mixed = (
        int(r1 + (r2 - r1) * ratio),
        int(g1 + (g2 - g1) * ratio),
        int(b1 + (b2 - b1) * ratio),
    )
    return "#%02x%02x%02x" % mixed


def format_duration(seconds):
    if seconds is None or seconds != seconds:
        return "--:--"
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return "%d:%02d:%02d" % (hours, minutes, secs)
    return "%02d:%02d" % (minutes, secs)


def format_size(number_of_bytes):
    value = float(number_of_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return "%d %s" % (value, unit) if unit == "B" else "%.2f %s" % (value, unit)
        value /= 1024


def hidden_process_flags():
    return subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0


def decode_output(raw):
    encodings = ["utf-8"]
    if IS_WINDOWS:
        encodings = ["oem", "utf-8"]
    for encoding in encodings:
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def run_command(arguments, timeout=25):
    try:
        completed = subprocess.run(
            arguments, capture_output=True, timeout=timeout, creationflags=hidden_process_flags()
        )
    except FileNotFoundError:
        return "Command not available: %s" % arguments[0]
    except subprocess.TimeoutExpired:
        return "Command timed out: %s" % " ".join(arguments)
    except OSError as error:
        return "Command failed: %s" % error
    text = decode_output(completed.stdout) + decode_output(completed.stderr)
    return text.strip() or "(no output)"


def find_binary(name):
    return shutil.which(name)


def local_ip_address(family=socket.AF_INET):
    target = "8.8.8.8" if family == socket.AF_INET else "2001:4860:4860::8888"
    probe = socket.socket(family, socket.SOCK_DGRAM)
    try:
        probe.connect((target, 80))
        return probe.getsockname()[0]
    except OSError:
        return "unavailable"
    finally:
        probe.close()


def detect_file_kind(path):
    extension = os.path.splitext(path)[1].lower()
    if extension in IMAGE_EXTENSIONS:
        return "image"
    if extension in VIDEO_EXTENSIONS:
        return "video"
    if extension in AUDIO_EXTENSIONS:
        return "audio"
    if extension in TEXT_EXTENSIONS:
        return "text"
    try:
        with open(path, "rb") as handle:
            sample = handle.read(4096)
    except OSError:
        return "hex"
    if sample and b"\x00" not in sample:
        try:
            sample.decode("utf-8")
            return "text"
        except UnicodeDecodeError:
            return "hex"
    return "hex" if sample else "text"


def default_icon_bytes():
    size = 64
    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            border = x < 3 or y < 3 or x >= size - 3 or y >= size - 3
            stem = 14 <= x < 22 and 12 <= y < 52
            bowl_top = 14 <= x < 46 and 12 <= y < 20
            bowl_right = 38 <= x < 46 and 12 <= y < 36
            bowl_bottom = 14 <= x < 46 and 28 <= y < 36
            lit = border or stem or bowl_top or bowl_right or bowl_bottom
            rows.extend((255, 0, 0, 255) if lit else (0, 0, 0, 255))

    def chunk(tag, payload):
        body = tag + payload
        return len(payload).to_bytes(4, "big") + body + (zlib.crc32(body) & 0xFFFFFFFF).to_bytes(4, "big")

    header = size.to_bytes(4, "big") * 2 + bytes([8, 6, 0, 0, 0])
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(bytes(rows))) + chunk(b"IEND", b"")


def locate_icon(custom_path):
    candidates = [custom_path, os.path.join(APP_DIR, "icon.png"), os.path.join(RESOURCE_DIR, "icon.png")]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def work_area():
    if IS_WINDOWS:
        rect = ctypes.wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0):
            return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
    return None


class Theme:
    def __init__(self, store):
        self.store = store
        self.control_x_handler = None

    def value(self, key):
        return self.store.data.get(key, DEFAULT_SETTINGS[key])

    @property
    def fg(self):
        return self.value("fg")

    @property
    def bg(self):
        return self.value("bg")

    @property
    def dim_color(self):
        return blend_colors(self.fg, self.bg, 0.55)

    def font(self, delta=0, weight="normal"):
        return (self.value("font"), max(6, int(self.value("size")) + delta), weight)

    def style_widget(self, widget):
        if getattr(widget, "skip_theme", False):
            return
        if hasattr(widget, "apply_theme"):
            widget.apply_theme(self)
            return
        fg, bg = self.fg, self.bg
        kind = widget.winfo_class()
        try:
            if kind in ("Frame", "Toplevel"):
                widget.configure(bg=bg)
                if kind == "Frame" and getattr(widget, "outlined", False):
                    widget.configure(highlightbackground=fg, highlightcolor=fg, highlightthickness=1)
            elif kind == "Label":
                widget.configure(bg=bg, fg=fg, font=self.font())
            elif kind in ("Button", "Menubutton"):
                widget.configure(
                    bg=bg, fg=fg, activebackground=fg, activeforeground=bg, relief="flat", bd=0,
                    highlightthickness=1, highlightbackground=fg, highlightcolor=fg, font=self.font(),
                    padx=8, pady=2, cursor="hand2",
                )
            elif kind in ("Entry", "Text"):
                if self.control_x_handler:
                    widget.bind("<Control-x>", self.control_x_handler)
                widget.configure(
                    bg=bg, fg=fg, insertbackground=fg, selectbackground=fg, selectforeground=bg,
                    highlightthickness=1, highlightbackground=self.dim_color, highlightcolor=fg,
                    relief="flat", font=self.font(),
                )
            elif kind == "Listbox":
                widget.configure(
                    bg=bg, fg=fg, selectbackground=fg, selectforeground=bg, highlightthickness=1,
                    highlightbackground=self.dim_color, highlightcolor=fg, relief="flat", font=self.font(),
                )
            elif kind in ("Checkbutton", "Radiobutton"):
                widget.configure(
                    bg=bg, fg=fg, selectcolor=bg, activebackground=bg, activeforeground=fg,
                    highlightthickness=0, font=self.font(),
                )
            elif kind == "Scale":
                widget.configure(
                    bg=bg, fg=fg, troughcolor=self.dim_color, activebackground=fg,
                    highlightthickness=0, bd=0, font=self.font(-2),
                )
            elif kind == "Scrollbar":
                widget.configure(
                    bg=fg, troughcolor=bg, activebackground=fg, highlightthickness=0, bd=0, relief="flat",
                )
            elif kind == "Canvas":
                widget.configure(bg=bg, highlightthickness=0)
            elif kind == "Menu":
                widget.configure(bg=bg, fg=fg, activebackground=fg, activeforeground=bg, font=self.font())
        except tk.TclError:
            pass

    def style_tree(self, root):
        self.style_widget(root)
        if getattr(root, "skip_children", False) or hasattr(root, "apply_theme"):
            return
        for child in root.winfo_children():
            self.style_tree(child)


class LoadingBar(tk.Canvas):
    def __init__(self, master):
        super().__init__(master, height=5, highlightthickness=0, bd=0)
        self.skip_theme = True
        self.busy_count = 0
        self.fraction = None
        self.phase = 0.0
        self.running = False
        self.bar_color = "#ff0000"
        self.bind("<Configure>", lambda event: self.redraw())

    def apply_theme(self, theme):
        self.bar_color = theme.fg
        self.configure(bg=theme.bg)
        self.redraw()

    def begin(self):
        self.busy_count += 1
        if not self.running:
            self.running = True
            self.animate()

    def end(self):
        self.busy_count = max(0, self.busy_count - 1)
        if self.busy_count == 0:
            self.running = False
            self.fraction = None
            self.redraw()

    def set_fraction(self, fraction):
        self.fraction = fraction
        self.redraw()

    def animate(self):
        if not self.running:
            return
        self.phase = (self.phase + 0.03) % 1.0
        self.redraw()
        self.after(30, self.animate)

    def redraw(self):
        self.delete("all")
        width = max(1, self.winfo_width())
        if self.fraction is not None and self.running:
            self.create_rectangle(0, 0, int(width * self.fraction), 5, fill=self.bar_color, width=0)
        elif self.running:
            block = width * 0.25
            start = (width + block) * self.phase - block
            self.create_rectangle(max(0, start), 0, min(width, start + block), 5, fill=self.bar_color, width=0)


class TextView(tk.Frame):
    def __init__(self, master, app, wrap="word"):
        super().__init__(master)
        self.app = app
        self.zoom = 0
        self.matches = []
        self.match_index = -1
        self.text = tk.Text(self, wrap=wrap, state="disabled", cursor="arrow", undo=False, padx=6, pady=4)
        self.scrollbar = tk.Scrollbar(self, command=self.text.yview, width=12)
        self.text.configure(yscrollcommand=self.scrollbar.set)
        self.search_bar = tk.Frame(self)
        self.search_var = tk.StringVar()
        tk.Label(self.search_bar, text="Find:").pack(side="left", padx=4)
        self.search_entry = tk.Entry(self.search_bar, textvariable=self.search_var, width=28)
        self.search_entry.pack(side="left", padx=4, pady=2)
        self.search_info = tk.Label(self.search_bar, text="")
        self.search_info.pack(side="left", padx=6)
        tk.Button(self.search_bar, text="Prev", command=lambda: self.step_match(-1)).pack(side="left", padx=2)
        tk.Button(self.search_bar, text="Next", command=lambda: self.step_match(1)).pack(side="left", padx=2)
        tk.Button(self.search_bar, text="X", command=self.close_search).pack(side="left", padx=2)
        self.scrollbar.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.search_var.trace_add("write", lambda *args: self.find_all())
        self.search_entry.bind("<Return>", lambda event: self.step_match(1) or "break")
        self.search_entry.bind("<Shift-Return>", lambda event: self.step_match(-1) or "break")
        self.search_entry.bind("<Escape>", lambda event: self.close_search() or "break")
        self.text.bind("<Shift-MouseWheel>", self.on_zoom_wheel)
        self.text.bind("<Shift-Button-4>", lambda event: self.change_zoom(1) or "break")
        self.text.bind("<Shift-Button-5>", lambda event: self.change_zoom(-1) or "break")
        self.text.bind("<Button-1>", lambda event: self.text.focus_set())

    def apply_theme(self, theme):
        self.configure(bg=theme.bg)
        self.search_bar.configure(bg=theme.bg)
        for child in self.search_bar.winfo_children():
            theme.style_widget(child)
        theme.style_widget(self.text)
        theme.style_widget(self.scrollbar)
        self.text.configure(font=theme.font(self.zoom), cursor="arrow", insertwidth=0)
        self.text.tag_configure("head", background=theme.fg, foreground=theme.bg)
        self.text.tag_configure("dim", foreground=theme.dim_color)
        self.text.tag_configure("match", background=theme.dim_color, foreground=theme.bg)
        self.text.tag_configure("current", background=theme.fg, foreground=theme.bg)
        self.text.tag_raise("match")
        self.text.tag_raise("current")
        for window_name in self.text.window_names():
            try:
                theme.style_widget(self.text.nametowidget(window_name))
            except KeyError:
                pass

    def write(self, content, tag=None, follow=True):
        self.text.configure(state="normal")
        if tag:
            self.text.insert("end", content, tag)
        else:
            self.text.insert("end", content)
        self.text.configure(state="disabled")
        if follow:
            self.text.see("end")

    def replace(self, content):
        self.clear()
        self.write(content, follow=False)
        self.text.see("1.0")

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        self.matches = []

    def add_button(self, label, command):
        button = tk.Button(self.text, text=label, command=command)
        self.app.theme.style_widget(button)
        self.text.configure(state="normal")
        self.text.window_create("end", window=button)
        self.text.insert("end", "\n")
        self.text.configure(state="disabled")
        self.text.see("end")
        return button

    def on_zoom_wheel(self, event):
        self.change_zoom(1 if event.delta > 0 else -1)
        return "break"

    def change_zoom(self, step):
        self.zoom = max(-6, min(40, self.zoom + step))
        self.text.configure(font=self.app.theme.font(self.zoom))
        return "break"

    def select_all(self):
        self.text.tag_add("sel", "1.0", "end-1c")
        return "break"

    def open_search(self):
        if not self.search_bar.winfo_ismapped():
            self.search_bar.pack(side="top", fill="x", before=self.scrollbar)
        self.search_entry.focus_set()
        self.search_entry.select_range(0, "end")
        self.find_all()

    def close_search(self):
        self.search_bar.pack_forget()
        self.text.tag_remove("match", "1.0", "end")
        self.text.tag_remove("current", "1.0", "end")
        self.text.focus_set()

    def find_all(self):
        self.text.tag_remove("match", "1.0", "end")
        self.text.tag_remove("current", "1.0", "end")
        self.matches = []
        self.match_index = -1
        needle = self.search_var.get()
        if not needle:
            self.search_info.configure(text="")
            return
        position = "1.0"
        length = tk.IntVar()
        while len(self.matches) < 5000:
            position = self.text.search(needle, position, stopindex="end", nocase=True, count=length)
            if not position:
                break
            end = "%s+%dc" % (position, length.get())
            self.text.tag_add("match", position, end)
            self.matches.append((position, end))
            position = end
        self.search_info.configure(text="%d found" % len(self.matches))
        if self.matches:
            self.step_match(1)

    def step_match(self, direction):
        if not self.matches:
            return
        self.text.tag_remove("current", "1.0", "end")
        self.match_index = (self.match_index + direction) % len(self.matches)
        start, end = self.matches[self.match_index]
        self.text.tag_add("current", start, end)
        self.text.see(start)
        self.search_info.configure(text="%d/%d" % (self.match_index + 1, len(self.matches)))


class StatusBar(tk.Canvas):
    def __init__(self, master, app):
        super().__init__(master, height=22, highlightthickness=0, bd=0)
        self.skip_theme = True
        self.app = app
        self.text_color = "#ff0000"
        self.font = ("Terminal", 10)
        self.offset = 0.0
        self.text_ids = []
        self.last_text = None
        self.after(100, self.tick)

    def apply_theme(self, theme):
        self.text_color = theme.fg
        self.font = theme.font(-2)
        self.configure(bg=theme.bg)
        self.last_text = None

    def compose(self):
        return "   |   ".join(self.app.status_items()) + "   |   "

    def tick(self):
        if not self.winfo_exists():
            return
        text = self.compose()
        if text != self.last_text or not self.text_ids:
            self.last_text = text
            self.delete("all")
            self.text_ids = []
            probe = self.create_text(0, 11, text=text, anchor="w", fill=self.text_color, font=self.font)
            self.text_ids.append(probe)
            bounds = self.bbox(probe)
            self.text_width = max(1, bounds[2] - bounds[0]) if bounds else 1
            repeats = int(self.winfo_width() / self.text_width) + 2
            for index in range(1, repeats + 1):
                self.text_ids.append(
                    self.create_text(index * self.text_width, 11, text=text, anchor="w", fill=self.text_color, font=self.font)
                )
        speed = self.app.statusbar_store.data.get("scroll_speed", 2)
        self.offset = (self.offset + speed) % self.text_width
        for index, item in enumerate(self.text_ids):
            self.coords(item, index * self.text_width - self.offset, 11)
        self.after(40, self.tick)


class SeekBar(tk.Canvas):
    def __init__(self, master, app, on_seek, height=80):
        super().__init__(master, height=height, highlightthickness=0, bd=0, cursor="hand2")
        self.skip_theme = True
        self.app = app
        self.on_seek = on_seek
        self.peaks = None
        self.duration = 0.0
        self.fraction = 0.0
        self.dragging = False
        self.fg = "#ff0000"
        self.dim = "#550000"
        self.bind("<Configure>", lambda event: self.redraw())
        self.bind("<Motion>", self.on_hover)
        self.bind("<Leave>", lambda event: self.delete("hover"))
        self.bind("<ButtonPress-1>", self.on_press)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<ButtonRelease-1>", self.on_release)

    def apply_theme(self, theme):
        self.fg = theme.fg
        self.dim = theme.dim_color
        self.configure(bg=theme.bg)
        self.redraw()

    def set_peaks(self, peaks):
        self.peaks = peaks
        self.redraw()

    def set_duration(self, duration):
        self.duration = duration or 0.0

    def set_fraction(self, fraction):
        if self.dragging:
            return
        self.fraction = max(0.0, min(1.0, fraction))
        self.move_playhead()

    def fraction_at(self, x):
        return max(0.0, min(1.0, x / max(1, self.winfo_width())))

    def on_press(self, event):
        self.dragging = True
        self.fraction = self.fraction_at(event.x)
        self.move_playhead()

    def on_drag(self, event):
        self.fraction = self.fraction_at(event.x)
        self.move_playhead()
        self.on_hover(event)

    def on_release(self, event):
        self.dragging = False
        self.fraction = self.fraction_at(event.x)
        self.move_playhead()
        self.on_seek(self.fraction)

    def on_hover(self, event):
        self.delete("hover")
        width = max(1, self.winfo_width())
        x = max(0, min(width, event.x))
        label = format_duration(self.fraction_at(x) * self.duration)
        self.create_line(x, 0, x, self.winfo_height(), fill=self.dim, tags="hover")
        anchor = "ne" if x > width - 60 else "nw"
        self.create_text(x + (-4 if anchor == "ne" else 4), 2, text=label, anchor=anchor, fill=self.fg, font=("Terminal", 10), tags="hover")

    def move_playhead(self):
        x = self.fraction * max(1, self.winfo_width())
        self.delete("playhead")
        self.create_line(x, 0, x, self.winfo_height(), fill=self.fg, width=2, tags="playhead")

    def redraw(self):
        self.delete("wave")
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        middle = height / 2
        if self.peaks is None or len(self.peaks) == 0:
            self.create_line(0, middle, width, middle, fill=self.dim, tags="wave")
        else:
            total = len(self.peaks)
            for x in range(0, width, 2):
                start = int(x * total / width)
                end = max(start + 1, int((x + 2) * total / width))
                peak = float(self.peaks[start:end].max())
                extent = max(1.0, peak * (height / 2 - 2))
                self.create_line(x, middle - extent, x, middle + extent, fill=self.dim, width=2, tags="wave")
        self.tag_lower("wave")
        self.move_playhead()


class ThemedWindow(tk.Toplevel):
    cascade_offset = 0

    def __init__(self, app, title, width=820, height=540, min_size=(360, 220), show_status_bar=True):
        super().__init__(app.root)
        self.app = app
        self.window_title = title
        self.min_size = min_size
        self.is_maximized = False
        self.is_fullscreen = False
        self.restore_geometry = None
        self.minimized = False
        self.search_target = None
        self.background_photo = None
        self.background_size = None
        self.background_job = None
        self.drag_origin = None
        self.resize_origin = None
        self.overrideredirect(True)
        self.title(title)
        self.withdraw()
        offset = ThemedWindow.cascade_offset
        ThemedWindow.cascade_offset = (offset + 28) % 140
        left = max(0, (self.winfo_screenwidth() - width) // 2 - 70 + offset)
        top = max(0, (self.winfo_screenheight() - height) // 2 - 70 + offset)
        self.geometry("%dx%d+%d+%d" % (width, height, left, top))
        self.outer = tk.Frame(self)
        self.outer.outlined = True
        self.outer.pack(fill="both", expand=True)
        self.build_title_bar()
        self.loading = LoadingBar(self.outer)
        self.loading.pack(side="top", fill="x")
        self.status_bar = StatusBar(self.outer, app)
        if show_status_bar:
            self.status_bar.pack(side="bottom", fill="x")
        self.stage = tk.Frame(self.outer)
        self.stage.pack(side="top", fill="both", expand=True)
        self.background_label = tk.Label(self.stage, bd=0)
        self.background_label.skip_theme = True
        self.background_label.place(x=0, y=0, relwidth=1, relheight=1)
        self.client = tk.Frame(self.stage)
        self.build_grips()
        self.stage.bind("<Configure>", self.schedule_background)
        self.bind("<Map>", self.on_map)
        self.bind("<Control-f>", self.on_find)
        self.protocol("WM_DELETE_WINDOW", self.close)
        app.register_window(self)
        self.iconphoto(False, app.icon_photo) if app.icon_photo else None
        self.refresh_theme()
        self.after(10, self.reveal)

    def build_title_bar(self):
        self.title_bar = tk.Frame(self.outer)
        self.title_bar.pack(side="top", fill="x")
        self.title_icon = tk.Label(self.title_bar, image=self.app.icon_small) if self.app.icon_small else tk.Label(self.title_bar, text="#")
        self.title_icon.pack(side="left", padx=(6, 2))
        self.title_label = tk.Label(self.title_bar, text=self.window_title, anchor="w")
        self.title_label.pack(side="left", padx=4)
        self.close_button = tk.Button(self.title_bar, text="X", command=self.close, width=3)
        self.maximize_button = tk.Button(self.title_bar, text="[]", command=self.toggle_maximize, width=3)
        self.minimize_button = tk.Button(self.title_bar, text="_", command=self.minimize, width=3)
        for button in (self.close_button, self.maximize_button, self.minimize_button):
            button.pack(side="right", padx=2, pady=2)
        self.coordinates = tk.StringVar(value="X:0 Y:0")
        self.coordinate_label = tk.Label(self.title_bar, textvariable=self.coordinates)
        self.coordinate_label.pack(side="right", padx=8)
        for widget in (self.title_bar, self.title_label, self.title_icon, self.coordinate_label):
            widget.bind("<ButtonPress-1>", self.start_drag)
            widget.bind("<B1-Motion>", self.do_drag)
            widget.bind("<Double-Button-1>", lambda event: self.toggle_maximize())

    def build_grips(self):
        specs = {
            "top_side": dict(x=8, y=0, relwidth=1, width=-16, height=4),
            "bottom_side": dict(x=8, rely=1, y=-4, relwidth=1, width=-16, height=4),
            "left_side": dict(x=0, y=8, width=4, relheight=1, height=-16),
            "right_side": dict(relx=1, x=-4, y=8, width=4, relheight=1, height=-16),
            "top_left_corner": dict(x=0, y=0, width=8, height=8),
            "top_right_corner": dict(relx=1, x=-8, y=0, width=8, height=8),
            "bottom_left_corner": dict(x=0, rely=1, y=-8, width=8, height=8),
            "bottom_right_corner": dict(relx=1, x=-8, rely=1, y=-8, width=8, height=8),
        }
        self.grips = []
        for cursor, placement in specs.items():
            grip = tk.Frame(self, cursor=cursor)
            grip.skip_theme = True
            grip.place(**placement)
            grip.configure(bg=self.app.theme.bg)
            grip.bind("<ButtonPress-1>", lambda event, edge=cursor: self.start_resize(event, edge))
            grip.bind("<B1-Motion>", self.do_resize)
            self.grips.append(grip)

    def reveal(self):
        self.apply_taskbar_style()
        self.deiconify()
        self.lift()
        self.focus_force()

    def apply_taskbar_style(self):
        if not IS_WINDOWS:
            return
        try:
            user32 = ctypes.windll.user32
            user32.GetParent.argtypes = [ctypes.wintypes.HWND]
            user32.GetParent.restype = ctypes.wintypes.HWND
            user32.GetWindowLongW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
            user32.GetWindowLongW.restype = ctypes.c_long
            user32.SetWindowLongW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int, ctypes.c_long]
            user32.SetWindowLongW.restype = ctypes.c_long
            handle = user32.GetParent(self.winfo_id()) or self.winfo_id()
            style = user32.GetWindowLongW(handle, -20)
            style = (style & ~0x00000080) | 0x00040000
            user32.SetWindowLongW(handle, -20, style)
            self.withdraw()
            self.after(10, self.deiconify)
        except (OSError, AttributeError, ctypes.ArgumentError):
            pass

    def on_map(self, event):
        if event.widget is self and self.minimized:
            self.minimized = False
            self.after(20, self.restore_borderless)

    def restore_borderless(self):
        self.overrideredirect(True)
        self.apply_taskbar_style()

    def minimize(self):
        self.update_idletasks()
        self.minimized = True
        self.overrideredirect(False)
        self.iconify()

    def toggle_maximize(self):
        if self.is_fullscreen:
            return
        if self.is_maximized:
            self.geometry(self.restore_geometry)
            self.is_maximized = False
            return
        self.restore_geometry = self.geometry()
        area = work_area() or (0, 0, self.winfo_screenwidth(), self.winfo_screenheight())
        self.geometry("%dx%d+%d+%d" % (area[2], area[3], area[0], area[1]))
        self.is_maximized = True

    def set_fullscreen(self, enabled):
        if enabled == self.is_fullscreen:
            return
        self.is_fullscreen = enabled
        if enabled:
            self.restore_geometry = self.geometry()
            self.title_bar.pack_forget()
            self.loading.pack_forget()
            self.status_bar.pack_forget()
            for grip in self.grips:
                grip.destroy()
            self.grips = []
            self.geometry("%dx%d+0+0" % (self.winfo_screenwidth(), self.winfo_screenheight()))
        else:
            self.title_bar.pack(side="top", fill="x", before=self.stage)
            self.loading.pack(side="top", fill="x", before=self.stage)
            self.status_bar.pack(side="bottom", fill="x", before=self.stage)
            self.build_grips()
            self.geometry(self.restore_geometry)

    def start_drag(self, event):
        if self.is_maximized:
            return
        self.drag_origin = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())

    def do_drag(self, event):
        if self.drag_origin:
            self.geometry("+%d+%d" % (event.x_root - self.drag_origin[0], event.y_root - self.drag_origin[1]))

    def start_resize(self, event, edge):
        self.resize_origin = (edge, event.x_root, event.y_root, self.winfo_x(), self.winfo_y(), self.winfo_width(), self.winfo_height())

    def do_resize(self, event):
        if not self.resize_origin or self.is_maximized:
            return
        edge, start_x, start_y, left, top, width, height = self.resize_origin
        delta_x, delta_y = event.x_root - start_x, event.y_root - start_y
        if "left" in edge:
            delta_x = min(delta_x, width - self.min_size[0])
            left, width = left + delta_x, width - delta_x
        if "right" in edge:
            width = max(self.min_size[0], width + delta_x)
        if "top" in edge:
            delta_y = min(delta_y, height - self.min_size[1])
            top, height = top + delta_y, height - delta_y
        if "bottom" in edge:
            height = max(self.min_size[1], height + delta_y)
        self.geometry("%dx%d+%d+%d" % (width, height, left, top))

    def set_title(self, text):
        self.window_title = text
        self.title_label.configure(text=text)
        self.title(text)

    def on_find(self, event=None):
        target = self.search_target
        focused = self.focus_get()
        while focused is not None:
            if isinstance(focused, TextView):
                target = focused
                break
            focused = getattr(focused, "master", None)
        if target is not None:
            target.open_search()
        return "break"

    def schedule_background(self, event=None):
        if self.background_job:
            self.after_cancel(self.background_job)
        self.background_job = self.after(120, self.update_background)

    def place_client(self):
        margin = self.app.theme.value("margin") if self.app.theme.value("background_image") else 0
        self.client.place(x=margin, y=margin, relwidth=1, relheight=1, width=-2 * margin, height=-2 * margin)

    def update_background(self):
        self.background_job = None
        path = self.app.theme.value("background_image")
        width, height = self.stage.winfo_width(), self.stage.winfo_height()
        if not path or not os.path.isfile(path) or width < 4 or height < 4:
            self.background_label.configure(image="", bg=self.app.theme.bg)
            self.background_photo = None
            return
        try:
            with Image.open(path) as source:
                picture = source.convert("RGB")
        except (OSError, ValueError):
            return
        scale = max(width / picture.width, height / picture.height)
        picture = picture.resize((max(1, int(picture.width * scale)), max(1, int(picture.height * scale))))
        left, top = (picture.width - width) // 2, (picture.height - height) // 2
        picture = picture.crop((left, top, left + width, top + height))
        picture = ImageEnhance.Brightness(picture).enhance(max(0.0, 1.0 - float(self.app.theme.value("dim"))))
        self.background_photo = ImageTk.PhotoImage(picture)
        self.background_label.configure(image=self.background_photo)

    def refresh_theme(self):
        theme = self.app.theme
        self.configure(bg=theme.bg)
        theme.style_tree(self)
        self.title_label.configure(fg=theme.bg, bg=theme.fg)
        self.title_bar.configure(bg=theme.fg)
        self.title_icon.configure(bg=theme.fg)
        self.coordinate_label.configure(fg=theme.bg, bg=theme.fg)
        for button in (self.close_button, self.maximize_button, self.minimize_button):
            button.configure(bg=theme.fg, fg=theme.bg, activebackground=theme.bg, activeforeground=theme.fg, highlightthickness=0)
        for grip in self.grips:
            grip.configure(bg=theme.bg)
        self.loading.apply_theme(theme)
        self.status_bar.apply_theme(theme)
        self.place_client()
        self.update_background()

    def style_new(self, widget=None):
        self.app.theme.style_tree(widget or self.client)

    def close(self):
        self.app.unregister_window(self)
        self.on_close()
        self.destroy()

    def on_close(self):
        pass


class MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("length", ctypes.c_ulong),
        ("load", ctypes.c_ulong),
        ("total_physical", ctypes.c_ulonglong),
        ("available_physical", ctypes.c_ulonglong),
        ("total_page", ctypes.c_ulonglong),
        ("available_page", ctypes.c_ulonglong),
        ("total_virtual", ctypes.c_ulonglong),
        ("available_virtual", ctypes.c_ulonglong),
        ("available_extended", ctypes.c_ulonglong),
    ]


def run_ping(protocol, port, host, count, ip_version, emit, cancel):
    families = {4: socket.AF_INET, 6: socket.AF_INET6, 0: socket.AF_UNSPEC}
    socket_type = socket.SOCK_STREAM if protocol == "TCP" else socket.SOCK_DGRAM
    try:
        infos = socket.getaddrinfo(host, port, families[ip_version], socket_type)
    except socket.gaierror as error:
        emit("Cannot resolve %s: %s\n" % (host, error))
        return
    family, kind, proto, _, address = infos[0]
    emit("PING %s %s (%s) port %d, %d packets\n" % (protocol, host, address[0], port, count), "head")
    timings = []
    replies = closed = silent = errors = sent = 0
    for sequence in range(1, count + 1):
        if cancel.is_set():
            emit("Cancelled.\n")
            break
        sent += 1
        started = time.perf_counter()
        probe = socket.socket(family, kind, proto)
        outcome = ""
        try:
            if protocol == "TCP":
                probe.settimeout(3)
                probe.connect(address)
                outcome = "open"
                replies += 1
                timings.append((time.perf_counter() - started) * 1000)
            else:
                probe.settimeout(2)
                probe.connect(address)
                probe.send(b"\x00")
                try:
                    probe.recv(2048)
                    outcome = "reply received"
                    replies += 1
                    timings.append((time.perf_counter() - started) * 1000)
                except socket.timeout:
                    outcome = "no reply (open|filtered)"
                    silent += 1
                except (ConnectionResetError, ConnectionRefusedError):
                    outcome = "closed (ICMP port unreachable)"
                    closed += 1
        except socket.timeout:
            outcome = "timeout"
            silent += 1
        except ConnectionRefusedError:
            outcome = "closed (connection refused)"
            closed += 1
        except OSError as error:
            outcome = "error: %s" % error
            errors += 1
        finally:
            probe.close()
        elapsed = (time.perf_counter() - started) * 1000
        emit("packet %d: %s:%d %s time=%.2f ms\n" % (sequence, address[0], port, outcome, elapsed))
        if sequence < count and cancel.wait(max(0.0, 1.0 - elapsed / 1000)):
            emit("Cancelled.\n")
            break
    emit("\n--- %s %s ping statistics ---\n" % (host, protocol), "head")
    emit("sent=%d responded=%d closed=%d no-response=%d errors=%d\n" % (sent, replies, closed, silent, errors))
    if sent:
        emit("unanswered: %.0f%%\n" % (100.0 * (sent - replies) / sent))
    if timings:
        emit("min/avg/max = %.2f/%.2f/%.2f ms\n" % (min(timings), sum(timings) / len(timings), max(timings)))


def section_os():
    return "\n".join([
        "System: %s %s" % (platform.system(), platform.release()),
        "Version: %s" % platform.version(),
        "Machine: %s" % platform.machine(),
        "Platform: %s" % platform.platform(),
    ])


def section_python():
    return "\n".join([
        "Python: %s" % sys.version.replace("\n", " "),
        "Executable: %s" % sys.executable,
        "Frozen: %s" % FROZEN,
        "Working directory: %s" % os.getcwd(),
    ])


def section_cpu():
    name = platform.processor() or "unknown"
    if IS_WINDOWS:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                name = winreg.QueryValueEx(key, "ProcessorNameString")[0]
        except OSError:
            pass
    elif os.path.exists("/proc/cpuinfo"):
        with open("/proc/cpuinfo", "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.lower().startswith("model name"):
                    name = line.split(":", 1)[1].strip()
                    break
    return "Processor: %s\nLogical cores: %s\nArchitecture: %s" % (name, os.cpu_count(), platform.architecture()[0])


def section_memory():
    if IS_WINDOWS:
        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        return "\n".join([
            "Memory load: %d%%" % status.load,
            "Physical total: %s" % format_size(status.total_physical),
            "Physical available: %s" % format_size(status.available_physical),
            "Page file total: %s" % format_size(status.total_page),
            "Page file available: %s" % format_size(status.available_page),
        ])
    lines = []
    if os.path.exists("/proc/meminfo"):
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.split(":")[0] in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
                    lines.append(line.strip())
    return "\n".join(lines) or "Memory information unavailable"


def section_disks():
    lines = []
    if IS_WINDOWS:
        roots = ["%s:\\" % letter for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.exists("%s:\\" % letter)]
    else:
        roots = ["/"]
    for root in roots:
        try:
            usage = shutil.disk_usage(root)
            lines.append("%s total %s, used %s, free %s" % (root, format_size(usage.total), format_size(usage.used), format_size(usage.free)))
        except OSError:
            lines.append("%s not ready" % root)
    return "\n".join(lines)


def section_host():
    return "\n".join([
        "Host name: %s" % socket.gethostname(),
        "FQDN: %s" % socket.getfqdn(),
        "User: %s" % (os.environ.get("USERNAME") or os.environ.get("USER", "unknown")),
        "Domain: %s" % os.environ.get("USERDOMAIN", "n/a"),
    ])


def section_adapters():
    return run_command(["ipconfig", "/all"] if IS_WINDOWS else ["ip", "addr"])


def section_addresses():
    lines = ["Primary IPv4: %s" % local_ip_address(socket.AF_INET), "Primary IPv6: %s" % local_ip_address(socket.AF_INET6)]
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            lines.append("Host address: %s" % info[4][0])
    except socket.gaierror:
        pass
    return "\n".join(dict.fromkeys(lines))


def section_dns():
    if IS_WINDOWS:
        text = run_command(["ipconfig", "/all"])
        selected = [line for line in text.splitlines() if "DNS" in line or line.startswith("   ") and line.strip()[:1].isdigit()]
        return "\n".join(selected) or text
    try:
        with open("/etc/resolv.conf", "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return "DNS configuration unavailable"


def section_dns_test():
    lines = []
    for name in ("example.com", "google.com", "cloudflare.com"):
        started = time.perf_counter()
        try:
            address = socket.getaddrinfo(name, 443)[0][4][0]
            lines.append("%s -> %s (%.1f ms)" % (name, address, (time.perf_counter() - started) * 1000))
        except socket.gaierror as error:
            lines.append("%s -> failed (%s)" % (name, error))
    return "\n".join(lines)


def section_routes():
    return run_command(["route", "print"] if IS_WINDOWS else ["ip", "route"])


def section_arp():
    return run_command(["arp", "-a"] if IS_WINDOWS else ["ip", "neigh"])


def section_listening():
    if IS_WINDOWS:
        text = run_command(["netstat", "-an"])
        return "\n".join(line for line in text.splitlines() if "LISTENING" in line or line.strip().startswith("UDP") or "Proto" in line)
    return run_command(["ss", "-tuln"])


def section_connections():
    text = run_command(["netstat", "-an"] if IS_WINDOWS else ["ss", "-tun"])
    lines = text.splitlines()
    return "\n".join(lines[:80] + (["... %d more lines" % (len(lines) - 80)] if len(lines) > 80 else []))


def section_wifi():
    if IS_WINDOWS:
        return run_command(["netsh", "wlan", "show", "interfaces"])
    return "Wi-Fi report is available on Windows only"


def section_proxy():
    lines = ["%s=%s" % (key, os.environ[key]) for key in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy") if key in os.environ]
    if IS_WINDOWS:
        lines.append(run_command(["netsh", "winhttp", "show", "proxy"]))
    return "\n".join(lines) or "No proxy configured in environment"


def section_firewall():
    if IS_WINDOWS:
        return run_command(["netsh", "advfirewall", "show", "allprofiles", "state"])
    return "Firewall profile report is available on Windows only"


def section_hosts_file():
    path = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "drivers", "etc", "hosts") if IS_WINDOWS else "/etc/hosts"
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            lines = [line.rstrip() for line in handle if line.strip() and not line.lstrip().startswith("#")]
        return "\n".join(lines) or "(no active entries)"
    except OSError as error:
        return "Cannot read hosts file: %s" % error


def section_connectivity():
    lines = []
    for host, port in (("1.1.1.1", 443), ("8.8.8.8", 53), ("example.com", 80)):
        started = time.perf_counter()
        try:
            with socket.create_connection((host, port), timeout=3):
                lines.append("TCP %s:%d reachable (%.1f ms)" % (host, port, (time.perf_counter() - started) * 1000))
        except OSError as error:
            lines.append("TCP %s:%d failed (%s)" % (host, port, error))
    return "\n".join(lines)


def section_media_tools():
    lines = ["ffmpeg: %s" % (find_binary("ffmpeg") or "not found on PATH"), "ffprobe: %s" % (find_binary("ffprobe") or "not found on PATH")]
    for module_name in ("pygame", "numpy", "PIL"):
        try:
            module = __import__(module_name)
            lines.append("%s: %s" % (module_name, getattr(module, "__version__", getattr(module, "ver", "installed"))))
        except ImportError:
            lines.append("%s: not installed" % module_name)
    return "\n".join(lines)


STATUS_SECTIONS = [
    ("Operating system", section_os),
    ("Python runtime", section_python),
    ("CPU", section_cpu),
    ("Memory", section_memory),
    ("Disks", section_disks),
    ("Host and user", section_host),
    ("Network adapters", section_adapters),
    ("IP addresses", section_addresses),
    ("DNS configuration", section_dns),
    ("DNS resolution test", section_dns_test),
    ("Routing table", section_routes),
    ("ARP cache", section_arp),
    ("Open ports (listening)", section_listening),
    ("Active connections", section_connections),
    ("Wi-Fi", section_wifi),
    ("Proxy settings", section_proxy),
    ("Firewall profiles", section_firewall),
    ("Hosts file", section_hosts_file),
    ("Internet connectivity", section_connectivity),
    ("Media tools and libraries", section_media_tools),
]


class SpeedMonitor(threading.Thread):
    def __init__(self, app):
        super().__init__(daemon=True)
        self.app = app
        self.server = None
        self.server_checked = 0.0

    def pick_server(self, configured):
        if configured != "auto":
            return configured, configured.split("//")[-1].split("/")[0]
        if self.server and time.time() - self.server_checked < 600:
            return self.server
        best = None
        for name, url in SPEED_SERVERS:
            started = time.perf_counter()
            try:
                request = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
                with urllib.request.urlopen(request, timeout=4):
                    pass
            except (urllib.error.URLError, OSError, ValueError):
                continue
            elapsed = time.perf_counter() - started
            if best is None or elapsed < best[0]:
                best = (elapsed, url, name)
        self.server_checked = time.time()
        self.server = (best[1], best[2]) if best else None
        return self.server

    def run(self):
        values = self.app.status_values
        while True:
            config = self.app.statusbar_store.data
            values["ip"] = "IP: %s" % local_ip_address()
            values["host"] = "HOST: %s" % socket.gethostname()
            if not config.get("enabled", True):
                values["down"] = "DOWN: monitor off"
                values["ping"] = "PING: --"
                values["server"] = "SERVER: --"
                time.sleep(1.0)
                continue
            try:
                chosen = self.pick_server(str(config.get("server", "auto")))
            except Exception:
                chosen = None
            if not chosen:
                values["down"] = "DOWN: offline"
                values["ping"] = "PING: --"
                values["server"] = "SERVER: none reachable"
                time.sleep(3.0)
                continue
            url, name = chosen
            values["server"] = "SERVER: %s" % name
            self.measure(url, values)
            time.sleep(max(0.2, float(config.get("interval", 2.0))))

    def measure(self, url, values):
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(url, timeout=8) as response:
                values["ping"] = "PING: %.0f ms" % ((time.perf_counter() - started) * 1000)
                window_start = time.perf_counter()
                window_bytes = 0
                test_start = window_start
                while time.perf_counter() - test_start < 3.0:
                    block = response.read(65536)
                    if not block:
                        break
                    window_bytes += len(block)
                    now = time.perf_counter()
                    if now - window_start >= 0.5:
                        values["down"] = "DOWN: %.2f Mbit/s" % (window_bytes * 8 / (now - window_start) / 1e6)
                        window_start, window_bytes = now, 0
        except (urllib.error.URLError, OSError, ValueError):
            values["down"] = "DOWN: error"
            values["ping"] = "PING: --"


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("Program")
        self.settings = JsonStore(SETTINGS_PATH, DEFAULT_SETTINGS)
        self.statusbar_store = JsonStore(STATUSBAR_PATH, DEFAULT_STATUSBAR)
        self.theme = Theme(self.settings)
        self.theme.control_x_handler = self.on_control_x
        self.windows = []
        self.active_tasks = []
        self.post_queue = queue.Queue()
        self.status_values = {"down": "DOWN: measuring...", "ping": "PING: --", "server": "SERVER: --", "ip": "IP: --", "host": "HOST: --"}
        self.icon_photo = None
        self.icon_small = None
        self.load_icon()
        self.root.bind_all("<Motion>", self.on_motion, add="+")
        self.root.bind_all("<Control-x>", self.on_control_x, add="+")
        self.root.bind_all("<Control-a>", self.on_select_all, add="+")
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.pump()
        self.monitor = SpeedMonitor(self)
        self.monitor.start()

    def load_icon(self):
        path = locate_icon(self.settings.data.get("icon", ""))
        try:
            source = Image.open(path).convert("RGBA") if path else Image.open(io.BytesIO(default_icon_bytes())).convert("RGBA")
        except (OSError, ValueError):
            source = Image.open(io.BytesIO(default_icon_bytes())).convert("RGBA")
        self.icon_photo = ImageTk.PhotoImage(source.resize((64, 64)))
        self.icon_small = ImageTk.PhotoImage(source.resize((16, 16)))
        self.root.iconphoto(True, self.icon_photo)
        for window in self.windows:
            window.iconphoto(False, self.icon_photo)
            window.title_icon.configure(image=self.icon_small)

    def status_items(self):
        config = self.statusbar_store.data
        items = []
        for key in config.get("items", DEFAULT_STATUSBAR["items"]):
            if key == "time":
                items.append("TIME: %s" % time.strftime("%H:%M:%S"))
            elif key in self.status_values:
                items.append(self.status_values[key])
        return items or ["Program"]

    def register_window(self, window):
        self.windows.append(window)

    def unregister_window(self, window):
        if window in self.windows:
            self.windows.remove(window)
        for entry in list(self.active_tasks):
            if entry["window"] is window:
                entry["cancel"].set()

    def refresh_all_themes(self):
        for window in list(self.windows):
            window.refresh_theme()

    def post(self, callback):
        self.post_queue.put(callback)

    def pump(self):
        try:
            while True:
                callback = self.post_queue.get_nowait()
                try:
                    callback()
                except tk.TclError:
                    pass
        except queue.Empty:
            pass
        self.root.after(20, self.pump)

    def run_task(self, window, work, done=None, failed=None):
        cancel = threading.Event()
        entry = {"cancel": cancel, "window": window}
        self.active_tasks.append(entry)
        window.loading.begin()

        def runner():
            try:
                outcome = (True, work(cancel))
            except Exception as error:
                outcome = (False, error)
            self.post(lambda: self.finish_task(entry, outcome, done, failed))

        threading.Thread(target=runner, daemon=True).start()
        return cancel

    def finish_task(self, entry, outcome, done, failed):
        if entry in self.active_tasks:
            self.active_tasks.remove(entry)
        window = entry["window"]
        if not window.winfo_exists():
            return
        window.loading.end()
        if outcome[0] and done:
            done(outcome[1])
        elif not outcome[0] and failed:
            failed(outcome[1])

    def thread_safe(self, widget, function):
        def wrapper(*arguments):
            self.post(lambda: function(*arguments) if widget.winfo_exists() else None)
        return wrapper

    def focused_window(self):
        widget = self.root.focus_get()
        while widget is not None and not isinstance(widget, ThemedWindow):
            widget = getattr(widget, "master", None)
        if widget is None and self.windows:
            widget = self.windows[-1]
        return widget

    def on_control_x(self, event=None):
        window = self.focused_window()
        if window is None:
            return "break"
        running = [entry for entry in self.active_tasks if entry["window"] is window]
        if running:
            for entry in running:
                entry["cancel"].set()
            if hasattr(window, "announce"):
                window.announce("Cancelling current command...")
            return "break"
        window.close()
        return "break"

    def on_select_all(self, event):
        widget = event.widget
        if isinstance(widget, tk.Text):
            widget.tag_add("sel", "1.0", "end-1c")
        elif isinstance(widget, tk.Entry):
            widget.select_range(0, "end")
            widget.icursor("end")
        return "break"

    def on_motion(self, event):
        try:
            top = event.widget.winfo_toplevel()
        except (AttributeError, KeyError, tk.TclError):
            return
        if isinstance(top, ThemedWindow):
            top.coordinates.set("X:%d Y:%d" % (event.x_root - top.winfo_rootx(), event.y_root - top.winfo_rooty()))

    def notify(self, parent, message, title="Program"):
        window = ThemedWindow(self, title, 460, 180, min_size=(300, 140), show_status_bar=False)
        window.place_client()
        tk.Label(window.client, text=message, wraplength=400, justify="left").pack(padx=14, pady=14, fill="x")
        tk.Button(window.client, text="OK", command=window.close, width=10).pack(pady=6)
        window.style_new()
        return window

    def open_file(self, path=None, parent=None):
        if not path:
            path = tkinter.filedialog.askopenfilename(title="Open file", parent=parent or self.root)
        if not path:
            return
        path = os.path.abspath(os.path.expanduser(path.strip('"')))
        if not os.path.isfile(path):
            self.notify(parent, "File not found:\n%s" % path)
            return
        kind = detect_file_kind(path)
        if kind == "image":
            ImageWindow(self, path)
        elif kind in ("audio", "video"):
            PlayerWindow(self, path, kind)
        elif kind == "text":
            TextFileWindow(self, path)
        else:
            HexWindow(self, path)

    def quit(self):
        for window in list(self.windows):
            window.on_close()
        self.root.destroy()

    def run(self):
        MainWindow(self)
        self.root.mainloop()


COMMAND_NAMES = ["help", "status", "ping", "ofile", "netconf", "custom", "clear", "exit"]

HELP_LINES = [
    ("help", "Show this help"),
    ("status", "System and network status report"),
    ("ping TCP|UDP PORT HOST [COUNT] [-4|-6]", "Ping a host and port"),
    ("ping", "Open the ping tool window"),
    ("ofile [PATH]", "Open a file in the right viewer"),
    ("netconf", "Network configuration catalog"),
    ("custom", "Customize fonts, colors and background"),
    ("clear", "Clear this screen"),
    ("exit", "Close the program"),
]


class MainWindow(ThemedWindow):
    def __init__(self, app):
        super().__init__(app, "Program", 900, 580, min_size=(520, 320))
        self.history = []
        self.history_index = 0
        self.place_client()
        menu = tk.Frame(self.client)
        menu.pack(side="top", fill="x", pady=(2, 4))
        entries = [
            ("Ping", self.cmd_ping), ("Status", self.cmd_status), ("Open file", self.cmd_ofile),
            ("Net config", self.cmd_netconf), ("Customize", self.cmd_custom), ("Help", self.cmd_help),
            ("Clear", self.cmd_clear), ("Exit", self.cmd_exit),
        ]
        for label, handler in entries:
            tk.Button(menu, text=label, command=lambda handler=handler: handler([])).pack(side="left", padx=3)
        prompt_row = tk.Frame(self.client)
        prompt_row.pack(side="bottom", fill="x", pady=(4, 0))
        tk.Label(prompt_row, text=">").pack(side="left", padx=(2, 4))
        self.entry = tk.Entry(prompt_row)
        self.entry.pack(side="left", fill="x", expand=True)
        self.output = TextView(self.client, app)
        self.output.pack(side="top", fill="both", expand=True)
        self.search_target = self.output
        self.entry.bind("<Return>", self.submit)
        self.entry.bind("<Tab>", self.on_tab)
        self.entry.bind("<Up>", lambda event: self.walk_history(-1))
        self.entry.bind("<Down>", lambda event: self.walk_history(1))
        self.style_new()
        self.output.write("PROGRAM - network diagnostics, file inspection and media playback\n", "head")
        self.output.write("Type 'help' for the list of commands, or use the menu above.\n\n")
        self.entry.focus_set()

    def announce(self, text):
        self.output.write(text + "\n", "dim")

    def fill_entry(self, text):
        self.entry.delete(0, "end")
        self.entry.insert(0, text)
        self.entry.focus_set()
        self.entry.icursor("end")

    def submit(self, event=None):
        line = self.entry.get().strip()
        self.entry.delete(0, "end")
        if not line:
            return "break"
        self.history.append(line)
        self.history_index = len(self.history)
        self.output.write("> %s\n" % line, "dim")
        self.execute(line)
        return "break"

    def execute(self, line):
        parts = line.split()
        name = parts[0].lower()
        if name not in COMMAND_NAMES:
            self.output.write("Unknown command: %s\n" % parts[0])
            guesses = difflib.get_close_matches(name, COMMAND_NAMES, n=1, cutoff=0.5)
            if guesses:
                corrected = guesses[0] + line[len(parts[0]):]
                self.output.add_button("did you mean %s?" % guesses[0], lambda: self.fill_entry(corrected))
            return
        arguments = parts[1:]
        if name == "ofile":
            arguments = [line[len(parts[0]):].strip().strip('"')] if arguments else []
        getattr(self, "cmd_" + name)(arguments)

    def walk_history(self, direction):
        if not self.history:
            return "break"
        self.history_index = max(0, min(len(self.history), self.history_index + direction))
        self.fill_entry(self.history[self.history_index] if self.history_index < len(self.history) else "")
        return "break"

    def on_tab(self, event):
        text = self.entry.get()
        parts = text.split(" ")
        head = parts[0].lower()
        options, prefix_length = [], len(parts[-1])
        if len(parts) == 1:
            options = [name for name in COMMAND_NAMES if name.startswith(head)]
        elif head == "ping" and len(parts) == 2:
            options = [name for name in ("TCP", "UDP") if name.startswith(parts[1].upper())]
        elif head == "ofile":
            typed = " ".join(parts[1:]).strip('"')
            prefix_length = len(" ".join(parts[1:]))
            options = [match + (os.sep if os.path.isdir(match) else "") for match in glob.glob(os.path.expanduser(typed) + "*")]
            parts = parts[:1] + [""]
        if not options:
            return "break"
        if len(options) == 1:
            replacement = options[0] + (" " if len(parts) == 1 else "")
        else:
            replacement = os.path.commonprefix(options)
            self.output.write("  ".join(options) + "\n", "dim")
        self.fill_entry(text[: len(text) - prefix_length] + replacement)
        return "break"

    def cmd_help(self, arguments):
        for usage, description in HELP_LINES:
            self.output.write("  %-40s %s\n" % (usage, description))
        self.output.write("\nTab completes, Up/Down walks history, Ctrl+F searches, Ctrl+X cancels or closes.\n", "dim")

    def cmd_clear(self, arguments):
        self.output.clear()

    def cmd_exit(self, arguments):
        self.close()

    def cmd_status(self, arguments):
        StatusWindow(self.app)

    def cmd_netconf(self, arguments):
        NetConfigWindow(self.app)

    def cmd_custom(self, arguments):
        CustomizeWindow(self.app)

    def cmd_ofile(self, arguments):
        self.app.open_file(arguments[0] if arguments else None, parent=self)

    def cmd_ping(self, arguments):
        if not arguments:
            PingWindow(self.app)
            return
        ip_version = 0
        remaining = []
        for argument in arguments:
            if argument in ("-4", "-6"):
                ip_version = int(argument[1])
            else:
                remaining.append(argument)
        usage = "Usage: ping TCP|UDP PORT HOST [COUNT] [-4|-6]\n"
        if len(remaining) < 3:
            self.output.write(usage)
            return
        protocol = remaining[0].upper()
        if protocol not in ("TCP", "UDP"):
            self.output.write("Unknown protocol: %s\n" % remaining[0])
            guesses = difflib.get_close_matches(protocol, ["TCP", "UDP"], n=1, cutoff=0.4)
            if guesses:
                corrected = "ping %s %s" % (guesses[0], " ".join(arguments[1:]))
                self.output.add_button("did you mean %s?" % guesses[0], lambda: self.fill_entry(corrected))
            return
        if not remaining[1].isdigit() or not 0 < int(remaining[1]) < 65536:
            self.output.write("Port must be a number between 1 and 65535.\n" + usage)
            return
        count = 4
        if len(remaining) > 3:
            if not remaining[3].isdigit() or int(remaining[3]) < 1:
                self.output.write("COUNT must be a positive number.\n" + usage)
                return
            count = min(int(remaining[3]), 1000)
        port, host = int(remaining[1]), remaining[2]
        emit = self.app.thread_safe(self.output, self.output.write)
        self.app.run_task(
            self, lambda cancel: run_ping(protocol, port, host, count, ip_version, emit, cancel),
            failed=lambda error: self.output.write("Ping failed: %s\n" % error),
        )

    def close(self):
        self.app.quit()


class PingWindow(ThemedWindow):
    def __init__(self, app):
        super().__init__(app, "Ping tool", 760, 520, min_size=(560, 340))
        self.place_client()
        self.protocol_var = tk.StringVar(value="TCP")
        self.version_var = tk.IntVar(value=0)
        self.port_var = tk.StringVar(value="443")
        self.count_var = tk.StringVar(value="4")
        self.host_var = tk.StringVar(value="example.com")
        form = tk.Frame(self.client)
        form.pack(side="top", fill="x", pady=4)
        tk.Label(form, text="Protocol:").grid(row=0, column=0, sticky="w", padx=4)
        for column, value in enumerate(("TCP", "UDP")):
            tk.Radiobutton(form, text=value, value=value, variable=self.protocol_var).grid(row=0, column=1 + column, sticky="w")
        tk.Label(form, text="IP version:").grid(row=1, column=0, sticky="w", padx=4)
        for column, (label, value) in enumerate((("Auto", 0), ("IPv4", 4), ("IPv6", 6))):
            tk.Radiobutton(form, text=label, value=value, variable=self.version_var).grid(row=1, column=1 + column, sticky="w")
        tk.Label(form, text="Port:").grid(row=2, column=0, sticky="w", padx=4)
        tk.Entry(form, textvariable=self.port_var, width=8).grid(row=2, column=1, sticky="w", pady=2)
        tk.Label(form, text="Packets:").grid(row=2, column=2, sticky="e", padx=4)
        tk.Entry(form, textvariable=self.count_var, width=6).grid(row=2, column=3, sticky="w")
        tk.Label(form, text="Host or IP:").grid(row=3, column=0, sticky="w", padx=4)
        host_entry = tk.Entry(form, textvariable=self.host_var, width=40)
        host_entry.grid(row=3, column=1, columnspan=3, sticky="w", pady=2)
        host_entry.bind("<Return>", lambda event: self.start())
        buttons = tk.Frame(form)
        buttons.grid(row=4, column=0, columnspan=4, sticky="w", pady=4)
        tk.Button(buttons, text="Run", command=self.start).pack(side="left", padx=4)
        tk.Button(buttons, text="Cancel", command=self.cancel).pack(side="left", padx=4)
        tk.Button(buttons, text="Clear", command=lambda: self.output.clear()).pack(side="left", padx=4)
        self.output = TextView(self.client, app)
        self.output.pack(side="top", fill="both", expand=True)
        self.search_target = self.output
        self.style_new()
        self.running = None

    def announce(self, text):
        self.output.write(text + "\n", "dim")

    def cancel(self):
        for entry in self.app.active_tasks:
            if entry["window"] is self:
                entry["cancel"].set()

    def start(self):
        port_text, count_text = self.port_var.get().strip(), self.count_var.get().strip()
        host = self.host_var.get().strip()
        if not port_text.isdigit() or not 0 < int(port_text) < 65536:
            self.output.write("Port must be a number between 1 and 65535.\n")
            return
        if not count_text.isdigit() or not 0 < int(count_text) <= 1000:
            self.output.write("Packets must be a number between 1 and 1000.\n")
            return
        if not host:
            self.output.write("Enter a host name or IP address.\n")
            return
        protocol, version = self.protocol_var.get(), self.version_var.get()
        emit = self.app.thread_safe(self.output, self.output.write)
        self.app.run_task(
            self, lambda cancel: run_ping(protocol, int(port_text), host, int(count_text), version, emit, cancel),
            failed=lambda error: self.output.write("Ping failed: %s\n" % error),
        )


class StatusWindow(ThemedWindow):
    def __init__(self, app):
        super().__init__(app, "Status report", 900, 600, min_size=(520, 320))
        self.place_client()
        bar = tk.Frame(self.client)
        bar.pack(side="top", fill="x", pady=3)
        tk.Button(bar, text="Refresh", command=self.start).pack(side="left", padx=4)
        tk.Button(bar, text="Cancel", command=self.cancel).pack(side="left", padx=4)
        tk.Button(bar, text="Save report", command=self.save).pack(side="left", padx=4)
        self.progress_label = tk.Label(bar, text="")
        self.progress_label.pack(side="left", padx=10)
        self.output = TextView(self.client, app)
        self.output.pack(side="top", fill="both", expand=True)
        self.search_target = self.output
        self.style_new()
        self.start()

    def announce(self, text):
        self.progress_label.configure(text=text)

    def cancel(self):
        for entry in self.app.active_tasks:
            if entry["window"] is self:
                entry["cancel"].set()

    def start(self):
        if any(entry["window"] is self for entry in self.app.active_tasks):
            return
        self.output.clear()
        total = len(STATUS_SECTIONS)
        show = self.app.thread_safe(self.output, self.show_section)
        progress = self.app.thread_safe(self.output, self.update_progress)

        def work(cancel):
            for index, (title, collector) in enumerate(STATUS_SECTIONS):
                if cancel.is_set():
                    return False
                progress(index, total, title)
                try:
                    content = collector()
                except Exception as error:
                    content = "Section failed: %s" % error
                show(title, content)
            progress(total, total, "")
            return True

        self.app.run_task(self, work, done=self.finished)

    def show_section(self, title, content):
        self.output.write(" %s \n" % title.upper(), "head")
        self.output.write(content + "\n\n")

    def update_progress(self, index, total, title):
        self.loading.set_fraction(index / total)
        self.progress_label.configure(text="%d/%d %s" % (index, total, title) if title else "")

    def finished(self, completed):
        self.progress_label.configure(text="Report complete" if completed else "Report cancelled")

    def save(self):
        path = tkinter.filedialog.asksaveasfilename(parent=self, defaultextension=".txt", initialfile="status_report.txt")
        if path:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(self.output.text.get("1.0", "end-1c"))


def add_file_toolbar(window, path):
    bar = tk.Frame(window.client)
    bar.pack(side="bottom", fill="x", pady=(4, 0))
    tk.Button(bar, text="Hex view", command=lambda: HexWindow(window.app, path)).pack(side="left", padx=3)
    tk.Button(bar, text="Integrity check", command=lambda: IntegrityWindow(window.app, path)).pack(side="left", padx=3)
    tk.Button(bar, text="Open another file", command=lambda: window.app.open_file(parent=window)).pack(side="left", padx=3)
    tk.Label(bar, text=path, anchor="e").pack(side="right", padx=6)
    return bar


class ImageWindow(ThemedWindow):
    def __init__(self, app, path):
        super().__init__(app, "Image - " + os.path.basename(path), 860, 620, min_size=(320, 240))
        self.path = path
        self.photo = None
        self.render_job = None
        self.place_client()
        add_file_toolbar(self, path)
        self.canvas_label = tk.Label(self.client, bd=0)
        self.canvas_label.pack(side="top", fill="both", expand=True)
        self.canvas_label.skip_theme = False
        self.style_new()
        try:
            with Image.open(path) as source:
                self.source = source.convert("RGBA")
        except (OSError, ValueError) as error:
            self.source = None
            self.canvas_label.configure(text="Cannot open image: %s" % error)
            return
        self.set_title("Image - %s (%dx%d)" % (os.path.basename(path), self.source.width, self.source.height))
        self.canvas_label.bind("<Configure>", self.schedule_render)

    def schedule_render(self, event=None):
        if self.render_job:
            self.after_cancel(self.render_job)
        self.render_job = self.after(80, self.render)

    def render(self):
        self.render_job = None
        width, height = self.canvas_label.winfo_width(), self.canvas_label.winfo_height()
        if width < 4 or height < 4 or self.source is None:
            return
        scale = min(width / self.source.width, height / self.source.height)
        size = (max(1, int(self.source.width * scale)), max(1, int(self.source.height * scale)))
        self.photo = ImageTk.PhotoImage(self.source.resize(size))
        self.canvas_label.configure(image=self.photo)


class TextFileWindow(ThemedWindow):
    LIMIT = 8 * 1024 * 1024

    def __init__(self, app, path):
        super().__init__(app, "Text - " + os.path.basename(path), 860, 600, min_size=(360, 240))
        self.place_client()
        add_file_toolbar(self, path)
        self.view = TextView(self.client, app, wrap="none")
        self.view.pack(side="top", fill="both", expand=True)
        self.search_target = self.view
        self.style_new()
        with open(path, "rb") as handle:
            raw = handle.read(self.LIMIT + 1)
        content = None
        for encoding in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
            try:
                content = raw[: self.LIMIT].decode(encoding)
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
        self.view.replace(content or "")
        if len(raw) > self.LIMIT:
            self.view.write("\n[truncated at %s]\n" % format_size(self.LIMIT), "dim", follow=False)


class HexWindow(ThemedWindow):
    PAGE = 4096

    def __init__(self, app, path):
        super().__init__(app, "Hex - " + os.path.basename(path), 900, 600, min_size=(560, 260))
        self.path = path
        self.size = os.path.getsize(path)
        self.offset = 0
        self.place_client()
        bar = tk.Frame(self.client)
        bar.pack(side="top", fill="x", pady=3)
        tk.Button(bar, text="Prev", command=lambda: self.go(self.offset - self.PAGE)).pack(side="left", padx=3)
        tk.Button(bar, text="Next", command=lambda: self.go(self.offset + self.PAGE)).pack(side="left", padx=3)
        tk.Label(bar, text="Offset (hex):").pack(side="left", padx=(12, 3))
        self.goto_var = tk.StringVar(value="0")
        goto = tk.Entry(bar, textvariable=self.goto_var, width=12)
        goto.pack(side="left")
        goto.bind("<Return>", lambda event: self.jump())
        tk.Button(bar, text="Go", command=self.jump).pack(side="left", padx=3)
        self.info = tk.Label(bar, text="")
        self.info.pack(side="left", padx=10)
        add_file_toolbar(self, path)
        self.view = TextView(self.client, app, wrap="none")
        self.view.pack(side="top", fill="both", expand=True)
        self.search_target = self.view
        self.style_new()
        self.go(0)

    def jump(self):
        try:
            self.go(int(self.goto_var.get().strip() or "0", 16))
        except ValueError:
            self.info.configure(text="Invalid offset")

    def go(self, offset):
        self.offset = max(0, min(offset, max(0, self.size - 1)))
        self.offset -= self.offset % 16
        with open(self.path, "rb") as handle:
            handle.seek(self.offset)
            block = handle.read(self.PAGE)
        lines = []
        for start in range(0, len(block), 16):
            row = block[start:start + 16]
            hexed = " ".join("%02X" % value for value in row[:8]) + "  " + " ".join("%02X" % value for value in row[8:])
            text = "".join(chr(value) if 32 <= value < 127 else "." for value in row)
            lines.append("%08X  %-48s  %s" % (self.offset + start, hexed, text))
        self.view.replace("\n".join(lines) + "\n")
        self.info.configure(text="%s of %s" % (format_size(self.offset), format_size(self.size)))


def compute_hashes(path, progress, cancel):
    algorithms = {name: hashlib.new(name) for name in ("md5", "sha1", "sha256", "sha512")}
    crc = 0
    total = max(1, os.path.getsize(path))
    done = 0
    with open(path, "rb") as handle:
        while True:
            if cancel.is_set():
                return None
            block = handle.read(1024 * 1024)
            if not block:
                break
            for digest in algorithms.values():
                digest.update(block)
            crc = zlib.crc32(block, crc)
            done += len(block)
            progress(done / total)
    result = {name.upper(): digest.hexdigest() for name, digest in algorithms.items()}
    result["CRC32"] = "%08x" % (crc & 0xFFFFFFFF)
    return result


class IntegrityWindow(ThemedWindow):
    def __init__(self, app, path):
        super().__init__(app, "Integrity - " + os.path.basename(path), 800, 460, min_size=(520, 300))
        self.path = path
        self.hashes = None
        self.place_client()
        compare = tk.Frame(self.client)
        compare.pack(side="top", fill="x", pady=4)
        tk.Label(compare, text="Expected hash:").pack(side="left", padx=4)
        self.expected_var = tk.StringVar()
        expected = tk.Entry(compare, textvariable=self.expected_var)
        expected.pack(side="left", fill="x", expand=True, padx=4)
        tk.Button(compare, text="Compare", command=self.compare).pack(side="left", padx=4)
        self.verdict = tk.Label(self.client, text="", anchor="w")
        self.verdict.pack(side="top", fill="x", padx=6)
        self.output = TextView(self.client, app)
        self.output.pack(side="top", fill="both", expand=True)
        self.search_target = self.output
        self.style_new()
        stats = os.stat(path)
        self.output.write("File: %s\nSize: %s (%d bytes)\nModified: %s\n\n" % (
            path, format_size(stats.st_size), stats.st_size, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stats.st_mtime))))
        progress = app.thread_safe(self.output, self.loading.set_fraction)
        app.run_task(self, lambda cancel: compute_hashes(path, progress, cancel), done=self.show, failed=lambda error: self.output.write("Failed: %s\n" % error))

    def announce(self, text):
        self.verdict.configure(text=text)

    def show(self, hashes):
        if hashes is None:
            self.output.write("Cancelled.\n")
            return
        self.hashes = hashes
        for name, value in hashes.items():
            self.output.write("%-7s %s\n" % (name, value))

    def compare(self):
        expected = self.expected_var.get().strip().lower()
        if not self.hashes or not expected:
            self.verdict.configure(text="Enter an expected hash after the calculation finishes.")
            return
        for name, value in self.hashes.items():
            if value.lower() == expected:
                self.verdict.configure(text="MATCH: file is intact (%s)" % name)
                return
        self.verdict.configure(text="MISMATCH: no calculated hash equals the expected value")


def probe_media(path):
    ffprobe = find_binary("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe was not found on PATH. Install ffmpeg and add it to PATH.")
    completed = subprocess.run(
        [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
        capture_output=True, timeout=60, creationflags=hidden_process_flags(),
    )
    if completed.returncode != 0:
        raise RuntimeError(decode_output(completed.stderr).strip() or "ffprobe could not read the file")
    return json.loads(completed.stdout or b"{}")


def parse_frame_rate(text):
    try:
        numerator, denominator = str(text).split("/")
        value = float(numerator) / float(denominator)
        return value if 1.0 <= value <= 240.0 else 25.0
    except (ValueError, ZeroDivisionError):
        return 25.0


def describe_media(info):
    lines = []
    media_format = info.get("format", {})
    for key in ("filename", "format_long_name", "duration", "size", "bit_rate"):
        if key in media_format:
            lines.append("%-18s %s" % (key, media_format[key]))
    for key, value in media_format.get("tags", {}).items():
        lines.append("tag %-14s %s" % (key, value))
    for stream in info.get("streams", []):
        lines.append("")
        lines.append("stream #%s (%s)" % (stream.get("index"), stream.get("codec_type")))
        for key in ("codec_name", "profile", "width", "height", "avg_frame_rate", "sample_rate", "channels", "channel_layout", "bit_rate", "duration"):
            if key in stream:
                lines.append("  %-16s %s" % (key, stream[key]))
        for key, value in stream.get("tags", {}).items():
            lines.append("  tag %-12s %s" % (key, value))
    return "\n".join(lines)


def tempo_filter(speed, keep_pitch):
    if abs(speed - 1.0) < 0.001:
        return "anull"
    if not keep_pitch:
        return "aresample=44100,asetrate=%d,aresample=44100" % round(44100 * speed)
    parts = []
    remaining = speed
    while remaining < 0.5:
        parts.append("atempo=0.5")
        remaining /= 0.5
    while remaining > 2.0:
        parts.append("atempo=2.0")
        remaining /= 2.0
    parts.append("atempo=%.4f" % remaining)
    return ",".join(parts)


class AudioEngine:
    def __init__(self, app, path, duration, has_audio):
        self.app = app
        self.path = path
        self.duration = duration
        self.has_audio = has_audio
        self.error = ""
        self.pygame = None
        self.tempdir = tempfile.mkdtemp(prefix="program_audio_")
        self.speed = 1.0
        self.keep_pitch = True
        self.volume = 0.8
        self.muted = False
        self.token = 0
        self.counter = 0
        self.base = 0.0
        self.played_offset = 0
        self.chunk_end = 0.0
        self.next_file = None
        self.want_play = False
        self.ready = False
        self.running = False
        self.render_pending = False
        self.ended = False
        self.clock_start = 0.0
        if has_audio:
            try:
                import pygame
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
                self.pygame = pygame
            except Exception as error:
                self.error = "Audio output unavailable: %s" % error
                self.has_audio = False

    def position(self):
        if not self.running:
            return min(self.base, self.duration) if self.duration else self.base
        if not self.has_audio:
            return min(self.duration, self.base + (time.monotonic() - self.clock_start) * self.speed)
        played = max(0, self.pygame.mixer.music.get_pos())
        return min(self.duration, self.base + (played - self.played_offset) / 1000.0 * self.speed)

    def apply_volume(self):
        if self.pygame and self.pygame.mixer.get_init():
            self.pygame.mixer.music.set_volume(0.0 if self.muted else self.volume)

    def set_volume(self, volume, muted):
        self.volume = volume
        self.muted = muted
        self.apply_volume()

    def stop_output(self):
        if self.pygame and self.pygame.mixer.get_init():
            self.pygame.mixer.music.stop()

    def start(self, position, play):
        self.token += 1
        self.base = max(0.0, position)
        self.want_play = play
        self.ready = False
        self.running = False
        self.ended = False
        self.render_pending = False
        self.next_file = None
        self.played_offset = 0
        self.stop_output()
        if not self.has_audio:
            self.ready = True
            self.running = play
            self.clock_start = time.monotonic()
            return
        if play:
            self.begin_render()

    def begin_render(self):
        self.render_pending = True
        token, start, speed, keep = self.token, self.base, self.speed, self.keep_pitch
        index = self.next_index()
        post = self.app.post
        threading.Thread(
            target=lambda: post(lambda path=self.render_chunk(start, speed, keep, index): self.on_rendered(token, path)),
            daemon=True,
        ).start()

    def next_index(self):
        self.counter += 1
        return self.counter

    def render_chunk(self, start, speed, keep, index):
        ffmpeg = find_binary("ffmpeg")
        if not ffmpeg or start >= self.duration:
            return None
        output = os.path.join(self.tempdir, "chunk_%d.wav" % index)
        length = min(AUDIO_CHUNK_SECONDS, max(0.2, self.duration - start))
        command = [
            ffmpeg, "-v", "error", "-y", "-ss", "%.3f" % start, "-t", "%.3f" % length, "-i", self.path,
            "-vn", "-af", tempo_filter(speed, keep), "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", output,
        ]
        try:
            completed = subprocess.run(command, capture_output=True, timeout=300, creationflags=hidden_process_flags())
        except (OSError, subprocess.TimeoutExpired):
            return None
        if completed.returncode != 0 or not os.path.exists(output) or os.path.getsize(output) < 100:
            return None
        return output

    def on_rendered(self, token, path):
        if token != self.token:
            return
        self.render_pending = False
        if path is None:
            self.error = "No playable audio stream"
            self.has_audio = False
            self.ready = True
            self.running = self.want_play
            self.clock_start = time.monotonic()
            return
        music = self.pygame.mixer.music
        music.load(path)
        self.apply_volume()
        music.play()
        self.played_offset = 0
        self.chunk_end = self.base + AUDIO_CHUNK_SECONDS
        self.ready = True
        if self.want_play:
            self.running = True
        else:
            music.pause()
        self.prerender_next()

    def prerender_next(self):
        if self.chunk_end >= self.duration - 0.05:
            return
        token, start, speed, keep = self.token, self.chunk_end, self.speed, self.keep_pitch
        index = self.next_index()
        post = self.app.post

        def work():
            path = self.render_chunk(start, speed, keep, index)
            post(lambda: self.on_next_rendered(token, path))

        threading.Thread(target=work, daemon=True).start()

    def on_next_rendered(self, token, path):
        if token == self.token:
            self.next_file = path

    def pump(self):
        if not self.running:
            return
        if not self.has_audio:
            if self.position() >= self.duration - 0.02:
                self.finish()
            return
        position = self.position()
        music = self.pygame.mixer.music
        if position >= self.chunk_end - 0.04 or not music.get_busy():
            if self.chunk_end >= self.duration - 0.05:
                self.finish()
            elif self.next_file:
                music.load(self.next_file)
                self.apply_volume()
                music.play()
                self.base = self.chunk_end
                self.played_offset = 0
                self.chunk_end += AUDIO_CHUNK_SECONDS
                self.next_file = None
                self.prerender_next()

    def finish(self):
        self.base = self.duration
        self.running = False
        self.ended = True

    def pause(self):
        self.want_play = False
        if self.running:
            self.base = self.position()
            self.running = False
            if self.has_audio and self.ready:
                self.pygame.mixer.music.pause()

    def resume(self):
        self.want_play = True
        if self.running:
            return
        if not self.has_audio:
            self.running = True
            self.clock_start = time.monotonic()
        elif self.ready:
            self.pygame.mixer.music.unpause()
            self.played_offset = max(0, self.pygame.mixer.music.get_pos())
            self.running = True
        elif not self.render_pending:
            self.start(self.base, True)

    def hold_at(self, position):
        self.start(position, False)

    def close(self):
        self.token += 1
        if self.pygame and self.pygame.mixer.get_init():
            self.pygame.mixer.music.stop()
            try:
                self.pygame.mixer.music.unload()
            except (AttributeError, self.pygame.error):
                pass
        shutil.rmtree(self.tempdir, ignore_errors=True)


class VideoPipe:
    def __init__(self, path, start, width, height, fps):
        self.width = width
        self.height = height
        self.start = start
        self.fps = fps
        self.stop_flag = threading.Event()
        self.frames = queue.Queue(maxsize=10)
        command = [
            find_binary("ffmpeg"), "-v", "error", "-ss", "%.3f" % start, "-i", path, "-an", "-sn",
            "-vf", "scale=%d:%d:flags=fast_bilinear" % (width, height), "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
        ]
        self.process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            creationflags=hidden_process_flags(), bufsize=width * height * 3,
        )
        threading.Thread(target=self.read_frames, daemon=True).start()

    def put(self, item):
        while not self.stop_flag.is_set():
            try:
                self.frames.put(item, timeout=0.1)
                return
            except queue.Full:
                continue

    def read_frames(self):
        size = self.width * self.height * 3
        index = 0
        stream = self.process.stdout
        while not self.stop_flag.is_set():
            try:
                data = stream.read(size)
            except (OSError, ValueError):
                break
            if len(data) < size:
                self.put(None)
                break
            self.put((self.start + index / self.fps, data))
            index += 1

    def close(self):
        self.stop_flag.set()
        try:
            self.process.kill()
        except OSError:
            pass
        try:
            self.process.stdout.close()
        except (OSError, ValueError):
            pass


class MediaReportWindow(ThemedWindow):
    def __init__(self, app, path, info):
        super().__init__(app, "Report - " + os.path.basename(path), 800, 600, min_size=(420, 260))
        self.place_client()
        self.output = TextView(self.client, app)
        self.output.pack(fill="both", expand=True)
        self.search_target = self.output
        self.style_new()
        self.output.write(" METADATA \n", "head")
        self.output.write(describe_media(info) + "\n\n")
        self.output.write(" HASHES \n", "head")
        progress = app.thread_safe(self.output, self.loading.set_fraction)
        app.run_task(self, lambda cancel: compute_hashes(path, progress, cancel), done=self.show_hashes, failed=lambda error: self.output.write("Failed: %s\n" % error))

    def show_hashes(self, hashes):
        for name, value in (hashes or {}).items():
            self.output.write("%-7s %s\n" % (name, value))


class PlayerWindow(ThemedWindow):
    def __init__(self, app, path, kind):
        super().__init__(app, "Player - " + os.path.basename(path), 900, 640, min_size=(520, 360))
        self.path = path
        self.kind = kind
        self.info = None
        self.duration = 0.0
        self.engine = None
        self.pipe = None
        self.held_frame = None
        self.frame_photo = None
        self.cover_photo = None
        self.covers = []
        self.cover_index = 0
        self.speed = 1.0
        self.keep_pitch = True
        self.loop = False
        self.muted = False
        self.volume = 0.8
        self.paused = False
        self.finished = False
        self.closed = False
        self.fps = 25.0
        self.video_size = (640, 360)
        self.video_position = 0.0
        self.resize_job = None
        self.place_client()
        self.status_label = tk.Label(self.client, text="Loading media...")
        self.status_label.pack(expand=True)
        self.style_new()
        self.bind("<KeyPress>", self.on_key)
        self.bind("<MouseWheel>", self.on_wheel)
        self.bind("<Button-4>", lambda event: self.change_volume(0.05))
        self.bind("<Button-5>", lambda event: self.change_volume(-0.05))
        app.run_task(self, lambda cancel: probe_media(path), done=self.on_probed, failed=self.on_probe_failed)

    def announce(self, text):
        self.time_label.configure(text=text) if hasattr(self, "time_label") else None

    def on_probe_failed(self, error):
        self.status_label.configure(text="Cannot open media: %s" % error)

    def on_probed(self, info):
        self.info = info
        streams = info.get("streams", [])
        audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
        video_streams = [
            stream for stream in streams
            if stream.get("codec_type") == "video" and not stream.get("disposition", {}).get("attached_pic")
        ]
        try:
            self.duration = float(info.get("format", {}).get("duration") or 0.0)
        except ValueError:
            self.duration = 0.0
        if self.kind == "video" and not video_streams:
            self.kind = "audio"
        if self.kind == "audio" and not audio_streams:
            self.status_label.configure(text="No audio stream found in this file")
            return
        if self.kind == "video":
            stream = video_streams[0]
            self.video_size = (int(stream.get("width", 640)), int(stream.get("height", 360)))
            self.fps = parse_frame_rate(stream.get("avg_frame_rate", "25/1"))
            if not self.duration:
                try:
                    self.duration = float(stream.get("duration") or 0.0)
                except ValueError:
                    self.duration = 0.0
        self.status_label.destroy()
        self.build_ui()
        self.engine = AudioEngine(self.app, self.path, self.duration, bool(audio_streams))
        self.engine.set_volume(self.volume, self.muted)
        if self.engine.error:
            self.time_label.configure(text=self.engine.error)
        self.seekbar.set_duration(self.duration)
        self.start_waveform()
        if self.kind == "audio":
            self.start_covers()
        self.pause_other_players()
        self.engine.start(0.0, True)
        if self.kind == "video":
            self.after(150, lambda: self.start_video(0.0))
        self.tick()
        self.focus_force()

    def build_ui(self):
        self.controls = tk.Frame(self.client)
        self.controls.pack(side="bottom", fill="x")
        self.seek_frame = tk.Frame(self.client)
        self.seek_frame.pack(side="bottom", fill="x", pady=4)
        self.seekbar = SeekBar(self.seek_frame, self.app, self.on_seek)
        self.seekbar.pack(fill="x")
        self.time_label = tk.Label(self.seek_frame, anchor="w")
        self.time_label.pack(fill="x")
        row_one = tk.Frame(self.controls)
        row_one.pack(fill="x", pady=2)
        row_two = tk.Frame(self.controls)
        row_two.pack(fill="x", pady=2)
        self.play_button = tk.Button(row_one, text="Pause", width=7, command=self.toggle_pause, takefocus=0)
        self.loop_button = tk.Button(row_one, text="Loop: off", width=9, command=self.toggle_loop, takefocus=0)
        self.mute_button = tk.Button(row_one, text="Mute: off", width=9, command=self.toggle_mute, takefocus=0)
        for button in (self.play_button, self.loop_button, self.mute_button):
            button.pack(side="left", padx=3)
        tk.Label(row_one, text="Volume").pack(side="left", padx=(10, 2))
        self.volume_scale = tk.Scale(row_one, from_=0, to=100, orient="horizontal", length=120, showvalue=False, command=self.on_volume_scale, takefocus=0)
        self.volume_scale.set(int(self.volume * 100))
        self.volume_scale.pack(side="left")
        self.volume_scale.bind("<ButtonRelease-1>", lambda event: self.focus_set(), add="+")
        tk.Button(row_one, text="Report", command=lambda: MediaReportWindow(self.app, self.path, self.info), takefocus=0).pack(side="right", padx=3)
        tk.Button(row_one, text="Hex", command=lambda: HexWindow(self.app, self.path), takefocus=0).pack(side="right", padx=3)
        tk.Button(row_one, text="Integrity", command=lambda: IntegrityWindow(self.app, self.path), takefocus=0).pack(side="right", padx=3)
        tk.Label(row_two, text="Speed").pack(side="left", padx=(3, 2))
        self.speed_scale = tk.Scale(row_two, from_=0.25, to=2.0, resolution=0.05, orient="horizontal", length=220, showvalue=False, command=self.on_speed_scale, takefocus=0)
        self.speed_scale.set(1.0)
        self.speed_scale.pack(side="left")
        self.speed_scale.bind("<ButtonRelease-1>", lambda event: (self.apply_speed(), self.focus_set()))
        self.speed_label = tk.Label(row_two, text="1.00x", width=6)
        self.speed_label.pack(side="left")
        self.pitch_button = tk.Button(row_two, text="Pitch: keep", width=12, command=self.toggle_pitch, takefocus=0)
        self.pitch_button.pack(side="left", padx=6)
        tk.Button(row_two, text="1.0x", command=self.reset_speed, takefocus=0).pack(side="left", padx=3)
        if self.kind == "video":
            tk.Button(row_two, text="Fullscreen", command=self.toggle_fullscreen, takefocus=0).pack(side="right", padx=3)
            self.video_canvas = tk.Canvas(self.client, bg="#000000", highlightthickness=0, bd=0)
            self.video_canvas.skip_theme = True
            self.video_canvas.pack(side="top", fill="both", expand=True)
            self.image_item = self.video_canvas.create_image(0, 0, anchor="center")
            self.video_canvas.bind("<Double-Button-1>", lambda event: self.toggle_fullscreen())
            self.video_canvas.bind("<Configure>", self.schedule_video_restart)
        else:
            self.top_area = tk.Frame(self.client)
            self.top_area.pack(side="top", fill="both", expand=True)
            self.cover_label = tk.Label(self.top_area, text="No cover art", width=28, cursor="hand2")
            self.cover_label.pack(side="left", padx=8, pady=6)
            self.cover_label.bind("<Button-1>", lambda event: self.cycle_cover())
            self.info_label = tk.Label(self.top_area, text=self.audio_summary(), justify="left", anchor="nw", wraplength=420)
            self.info_label.pack(side="left", fill="both", expand=True, padx=8, pady=6)
        self.style_new()
        self.title_label.configure(fg=self.app.theme.bg, bg=self.app.theme.fg)

    def audio_summary(self):
        media_format = self.info.get("format", {})
        tags = {key.lower(): value for key, value in media_format.get("tags", {}).items()}
        lines = [os.path.basename(self.path)]
        for key in ("title", "artist", "album", "date", "genre"):
            if key in tags:
                lines.append("%s: %s" % (key.capitalize(), tags[key]))
        lines.append("Duration: %s" % format_duration(self.duration))
        lines.append("Format: %s" % media_format.get("format_long_name", "unknown"))
        lines.append("Size: %s" % format_size(int(media_format.get("size", 0) or 0)))
        return "\n".join(lines)

    def start_waveform(self):
        path, ffmpeg = self.path, find_binary("ffmpeg")
        post = self.app.post

        def work():
            peaks = None
            try:
                import numpy
                completed = subprocess.run(
                    [ffmpeg, "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                    capture_output=True, creationflags=hidden_process_flags(),
                )
                samples = numpy.abs(numpy.frombuffer(completed.stdout, dtype=numpy.int16).astype(numpy.int32))
                if len(samples):
                    bins = min(2000, len(samples))
                    usable = len(samples) // bins * bins
                    peaks = samples[:usable].reshape(bins, -1).max(axis=1).astype(numpy.float32)
                    peaks = peaks / max(float(peaks.max()), 1.0)
            except Exception:
                peaks = None
            post(lambda: self.seekbar.winfo_exists() and self.seekbar.set_peaks(peaks))

        threading.Thread(target=work, daemon=True).start()

    def start_covers(self):
        path, ffmpeg = self.path, find_binary("ffmpeg")
        post = self.app.post

        def work():
            found = []
            try:
                completed = subprocess.run(
                    [ffmpeg, "-v", "error", "-i", path, "-an", "-map", "0:v:0", "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
                    capture_output=True, timeout=30, creationflags=hidden_process_flags(),
                )
                if completed.returncode == 0 and completed.stdout:
                    found.append(("embedded", completed.stdout))
            except (OSError, subprocess.TimeoutExpired):
                pass
            folder = os.path.dirname(path)
            try:
                names = sorted(os.listdir(folder))
            except OSError:
                names = []
            for name in names:
                stem, extension = os.path.splitext(name)
                if stem.lower() in COVER_NAMES and extension.lower() in COVER_EXTENSIONS:
                    found.append(("file", os.path.join(folder, name)))
            post(lambda: self.cover_label.winfo_exists() and self.set_covers(found))

        threading.Thread(target=work, daemon=True).start()

    def set_covers(self, covers):
        self.covers = covers
        self.cover_index = 0
        self.show_cover()

    def cycle_cover(self):
        if len(self.covers) > 1:
            self.cover_index = (self.cover_index + 1) % len(self.covers)
            self.show_cover()

    def show_cover(self):
        if not self.covers:
            return
        kind, payload = self.covers[self.cover_index]
        try:
            picture = Image.open(io.BytesIO(payload) if kind == "embedded" else payload).convert("RGB")
        except (OSError, ValueError):
            self.cover_label.configure(image="", text="Cover unreadable")
            return
        picture.thumbnail((300, 300))
        self.cover_photo = ImageTk.PhotoImage(picture)
        self.cover_label.configure(image=self.cover_photo, text="", width=picture.width, height=picture.height)
        self.info_label.configure(text=self.audio_summary() + "\nCover %d/%d (%s) - click to cycle" % (self.cover_index + 1, len(self.covers), kind))

    def video_target_size(self):
        canvas_width = max(64, self.video_canvas.winfo_width())
        canvas_height = max(64, self.video_canvas.winfo_height())
        scale = min(canvas_width / self.video_size[0], canvas_height / self.video_size[1])
        width = max(2, int(self.video_size[0] * scale) // 2 * 2)
        height = max(2, int(self.video_size[1] * scale) // 2 * 2)
        return width, height

    def start_video(self, position):
        if self.closed or not find_binary("ffmpeg"):
            return
        if self.pipe:
            self.pipe.close()
        self.held_frame = None
        width, height = self.video_target_size()
        self.video_position = position
        try:
            self.pipe = VideoPipe(self.path, position, width, height, self.fps)
        except OSError:
            self.pipe = None

    def schedule_video_restart(self, event=None):
        if self.resize_job:
            self.after_cancel(self.resize_job)
        self.resize_job = self.after(250, self.restart_video_for_size)

    def restart_video_for_size(self):
        self.resize_job = None
        if self.engine and self.pipe and self.video_target_size() != (self.pipe.width, self.pipe.height):
            self.start_video(self.engine.position())
        center_x, center_y = self.video_canvas.winfo_width() // 2, self.video_canvas.winfo_height() // 2
        self.video_canvas.coords(self.image_item, center_x, center_y)

    def show_frame(self, frame_time, data):
        width, height = self.pipe.width, self.pipe.height
        picture = Image.frombuffer("RGB", (width, height), data, "raw", "RGB", 0, 1)
        self.frame_photo = ImageTk.PhotoImage(picture)
        self.video_canvas.itemconfigure(self.image_item, image=self.frame_photo)
        self.video_canvas.coords(self.image_item, self.video_canvas.winfo_width() // 2, self.video_canvas.winfo_height() // 2)
        self.video_position = frame_time

    def advance_video(self, position):
        if not self.pipe:
            return
        latest = None
        while True:
            if self.held_frame is None:
                try:
                    self.held_frame = self.pipe.frames.get_nowait()
                except queue.Empty:
                    break
            if self.held_frame is None:
                break
            if self.held_frame[0] <= position + 0.001:
                latest = self.held_frame
                self.held_frame = None
            else:
                break
        if latest:
            self.show_frame(*latest)

    def step_forward(self):
        if self.kind != "video" or not self.pipe:
            return
        if not self.paused:
            self.set_paused(True)
        frame = self.held_frame
        self.held_frame = None
        if frame is None:
            try:
                frame = self.pipe.frames.get(timeout=1.0)
            except queue.Empty:
                return
        if frame is None:
            return
        self.show_frame(*frame)
        self.engine.hold_at(frame[0])

    def step_backward(self):
        if self.kind != "video":
            return
        if not self.paused:
            self.set_paused(True)
        self.seek_to(max(0.0, self.video_position - 1.0 / self.fps), play=False)

    def tick(self):
        if self.closed or not self.winfo_exists():
            return
        self.engine.pump()
        position = self.engine.position()
        if self.duration:
            self.seekbar.set_fraction(position / self.duration)
        if self.engine.error and not self.engine.has_audio:
            note = "  [%s]" % self.engine.error
        else:
            note = ""
        self.time_label.configure(text="%s / %s   %.2fx %s   volume %d%%%s" % (
            format_duration(position), format_duration(self.duration), self.speed,
            "keep pitch" if self.keep_pitch else "shift pitch", int(self.volume * 100) if not self.muted else 0, note))
        if self.kind == "video":
            self.advance_video(position)
        if self.engine.ended and not self.finished:
            self.finished = True
            self.on_finished()
        self.after(15 if self.kind == "video" else 50, self.tick)

    def on_finished(self):
        if self.loop:
            self.seek_to(0.0, play=True)
        else:
            self.paused = True
            self.play_button.configure(text="Play")

    def seek_to(self, seconds, play=None):
        seconds = max(0.0, min(seconds, max(0.0, self.duration - 0.05)))
        self.finished = False
        if play is None:
            play = not self.paused
        self.paused = not play
        self.play_button.configure(text="Pause" if play else "Play")
        self.engine.start(seconds, play)
        if self.kind == "video":
            self.start_video(seconds)
        if self.duration:
            self.seekbar.set_fraction(seconds / self.duration)

    def on_seek(self, fraction):
        self.seek_to(fraction * self.duration)

    def pause_other_players(self):
        for window in self.app.windows:
            if isinstance(window, PlayerWindow) and window is not self and window.engine and not window.paused:
                window.set_paused(True)

    def set_paused(self, paused):
        if not paused:
            self.pause_other_players()
        self.paused = paused
        self.play_button.configure(text="Play" if paused else "Pause")
        if paused:
            self.engine.pause()
        else:
            self.engine.resume()

    def toggle_pause(self):
        if self.finished and not self.loop:
            self.seek_to(0.0, play=True)
            return
        self.set_paused(not self.paused)

    def toggle_loop(self):
        self.loop = not self.loop
        self.loop_button.configure(text="Loop: on" if self.loop else "Loop: off")

    def toggle_mute(self):
        self.muted = not self.muted
        self.mute_button.configure(text="Mute: on" if self.muted else "Mute: off")
        self.engine.set_volume(self.volume, self.muted)

    def on_volume_scale(self, value):
        self.volume = int(float(value)) / 100.0
        if self.engine:
            self.engine.set_volume(self.volume, self.muted)

    def change_volume(self, delta):
        self.volume = max(0.0, min(1.0, self.volume + delta))
        self.volume_scale.set(int(round(self.volume * 100)))
        self.engine.set_volume(self.volume, self.muted)

    def on_wheel(self, event):
        if not self.engine:
            return
        self.change_volume(0.05 if event.delta > 0 else -0.05)

    def on_speed_scale(self, value):
        self.speed_label.configure(text="%.2fx" % float(value))

    def apply_speed(self):
        self.speed = float(self.speed_scale.get())
        self.engine.speed = self.speed
        self.engine.keep_pitch = self.keep_pitch
        self.engine.start(self.engine.position(), not self.paused)

    def reset_speed(self):
        self.speed_scale.set(1.0)
        self.apply_speed()

    def toggle_pitch(self):
        self.keep_pitch = not self.keep_pitch
        self.pitch_button.configure(text="Pitch: keep" if self.keep_pitch else "Pitch: shift")
        self.apply_speed()

    def toggle_fullscreen(self):
        if self.kind != "video":
            return
        entering = not self.is_fullscreen
        self.set_fullscreen(entering)
        if entering:
            self.controls.pack_forget()
            self.seek_frame.pack_forget()
        else:
            self.controls.pack(side="bottom", fill="x", before=self.video_canvas)
            self.seek_frame.pack(side="bottom", fill="x", pady=4, before=self.video_canvas)

    def on_key(self, event):
        if not self.engine:
            return
        key = event.keysym
        position = self.engine.position()
        if key == "space":
            self.toggle_pause()
        elif key == "Left":
            self.seek_to(position - 5)
        elif key == "Right":
            self.seek_to(position + 5)
        elif key == "Up":
            self.change_volume(0.05)
        elif key == "Down":
            self.change_volume(-0.05)
        elif key in ("m", "M"):
            self.toggle_mute()
        elif key in ("l", "L"):
            self.toggle_loop()
        elif key == "Home":
            self.seek_to(0.0)
        elif key in ("f", "F"):
            self.toggle_fullscreen()
        elif key == "Escape" and self.is_fullscreen:
            self.toggle_fullscreen()
        elif key == "comma":
            self.step_backward()
        elif key == "period":
            self.step_forward()

    def on_close(self):
        self.closed = True
        if self.pipe:
            self.pipe.close()
            self.pipe = None
        if self.engine:
            self.engine.close()
            self.engine = None


NETCONFIG_SCOPES = [
    "Global", "Ethernet", "Wi-Fi", "Loopback", "VPN", "Tor", "I2P", "Hotspot", "Bluetooth", "Virtual", "IPv4 stack", "IPv6 stack", "Proxy chain",
]

NETCONFIG_PARAMETERS = {
    "TCP": """
Window scaling|bool|on|Enable RFC 1323 window scaling
Timestamps|bool|off|Enable RFC 1323 timestamps
Selective ACK|bool|on|Enable selective acknowledgements
Initial RTO (ms)|int|1000|Initial retransmission timeout
Max SYN retransmits|int|2|Connection attempts before giving up
Congestion provider|choice:cubic,ctcp,bbr2,newreno|cubic|Congestion control algorithm
Receive autotuning|choice:normal,restricted,highlyrestricted,experimental,disabled|normal|Receive window auto-tuning level
Keep-alive time (ms)|int|7200000|Idle time before keep-alive probes
Delayed ACK timeout (ms)|int|40|Delay before acknowledging
ECN capability|choice:disabled,enabled|disabled|Explicit congestion notification
""",
    "UDP": """
Receive buffer (KB)|int|64|Socket receive buffer size
Send buffer (KB)|int|64|Socket send buffer size
Max datagram size|int|1472|Largest datagram without fragmentation
Checksum offload|bool|on|Offload checksum to adapter
Broadcast allowed|bool|off|Permit broadcast sends
Multicast loopback|bool|on|Loop multicast to local sockets
Port range start|int|49152|First ephemeral port
Port range size|int|16384|Number of ephemeral ports
Reuse address|bool|off|Allow address reuse
Packet coalescing|bool|off|Receive segment coalescing
""",
    "IPv4": """
Default TTL|int|128|Default time to live
Forwarding|bool|off|Forward packets between interfaces
Source routing|choice:drop,forward,process|drop|Source routed packet policy
Path MTU discovery|bool|on|Discover path maximum transmission unit
Dead gateway detection|bool|on|Detect dead gateways
Fragment reassembly timeout (s)|int|60|Reassembly timeout
ICMP redirects|bool|off|Accept ICMP redirects
Neighbor stale time (s)|int|30|ARP cache stale time
Reachable time (ms)|int|30000|ARP reachable time
DHCP media sense|bool|on|React to link state changes
""",
    "IPv6": """
Privacy addresses|bool|on|Temporary random addresses
Router discovery|choice:enabled,disabled,dhcp|dhcp|Router discovery mode
Teredo|choice:default,disabled,client|disabled|Teredo tunnelling state
6to4|choice:default,disabled,enabled|disabled|6to4 tunnelling state
ISATAP|choice:default,disabled,enabled|disabled|ISATAP tunnelling state
Hop limit|int|128|Default hop limit
Random identifiers|bool|on|Randomize interface identifiers
Duplicate address detection|int|3|DAD transmits
Neighbor discovery retransmit (ms)|int|1000|NS retransmit timer
Prefer IPv4 over IPv6|bool|off|Address selection preference
""",
    "DNS": """
Primary server|text|auto|Primary DNS server address
Secondary server|text|auto|Secondary DNS server address
DNS over HTTPS|choice:off,auto,required|off|Encrypted DNS policy
Cache size|int|4096|Resolver cache entries
Negative cache time (s)|int|900|Cache time for failed lookups
Query timeout (s)|int|3|Per-query timeout
Retries|int|2|Query retries
Register adapter address|bool|on|Dynamic DNS registration
Suffix search list|text||Connection specific suffixes
Multicast name resolution|bool|on|LLMNR and mDNS queries
""",
    "Wi-Fi": """
Power saving|choice:off,low,medium,maximum|medium|Adapter power save mode
Preferred band|choice:auto,2.4GHz,5GHz,6GHz|auto|Preferred radio band
Roaming aggressiveness|choice:lowest,medium,highest|medium|Roaming threshold
Channel width|choice:auto,20MHz,40MHz,80MHz,160MHz|auto|Channel bandwidth
Fast roaming|bool|on|802.11r fast transition
Random hardware address|choice:off,on,daily|off|MAC address randomization
Auto connect|bool|on|Connect to known networks
Scan interval (s)|int|60|Background scan interval
Metered connection|bool|off|Treat network as metered
Minimum signal (%)|int|20|Weakest acceptable signal
""",
    "Proxy": """
Use system proxy|bool|off|Route through the system proxy
SOCKS host|text|127.0.0.1|SOCKS proxy host
SOCKS port|int|9050|SOCKS proxy port
HTTP proxy host|text||HTTP proxy host
HTTP proxy port|int|8080|HTTP proxy port
Proxy DNS lookups|bool|on|Resolve names through the proxy
Bypass local addresses|bool|on|Skip proxy for local addresses
Connection timeout (s)|int|30|Proxy connection timeout
Auto-detect script|bool|off|WPAD discovery
Failover to direct|bool|off|Fall back to direct connection
""",
    "Firewall": """
Default inbound action|choice:block,allow,prompt|block|Action for unsolicited inbound traffic
Default outbound action|choice:allow,block,prompt|allow|Action for outbound traffic
Stealth mode|bool|on|Do not answer unsolicited probes
Log dropped packets|bool|off|Write dropped packet log
Log successful connections|bool|off|Write allowed connection log
Respond to ping|bool|off|Answer ICMP echo requests
Block port scans|bool|on|Detect and block scans
Allow loopback|bool|on|Always permit loopback
Connection tracking size|int|65536|Tracked connection entries
Rule evaluation timeout (ms)|int|500|Per-rule timeout
""",
    "Routing": """
Interface metric|int|25|Automatic interface metric
Automatic metric|bool|on|Compute metric from link speed
Route cache lifetime (s)|int|600|Cached route lifetime
Persistent routes|bool|on|Keep routes across reboots
Strong host model|choice:weak,strong|weak|Host model for sends and receives
Multipath routes|int|1|Equal-cost route count
Default gateway probe|bool|on|Probe the default gateway
Gateway probe interval (s)|int|10|Probe interval
Blackhole detection|bool|on|Detect black hole routers
Reverse path filter|choice:off,loose,strict|loose|Source address validation
""",
    "QoS and offload": """
Large send offload|bool|on|Segmentation offload
Receive side scaling|bool|on|Spread receive load across CPUs
Receive segment coalescing|bool|on|Merge received segments
Interrupt moderation|choice:off,low,medium,high|medium|Interrupt coalescing level
Jumbo frame size|int|1514|Maximum frame size
Flow control|choice:off,rx,tx,both|both|Ethernet pause frames
Reserved bandwidth (%)|int|0|Bandwidth reserved for QoS
DSCP marking|int|0|Default DSCP value
Transmit buffers|int|256|Adapter transmit buffers
Receive buffers|int|256|Adapter receive buffers
""",
}


def build_netconfig_catalog():
    catalog = []
    for category, block in NETCONFIG_PARAMETERS.items():
        for line in block.strip().splitlines():
            name, kind, default, description = line.split("|")
            for scope in NETCONFIG_SCOPES:
                catalog.append({
                    "key": "%s/%s/%s" % (category, scope, name),
                    "category": category,
                    "scope": scope,
                    "name": name,
                    "kind": kind,
                    "default": default,
                    "description": "%s (%s)" % (description, scope),
                })
    return catalog


NETCONFIG_CATALOG = build_netconfig_catalog()


def latest_tor_url():
    base = "https://archive.torproject.org/tor-package-archive/torbrowser/"
    with urllib.request.urlopen(base, timeout=20) as response:
        listing = response.read().decode("utf-8", errors="replace")
    versions = sorted(set(re.findall(r'href="(\d+\.\d+(?:\.\d+)?)/"', listing)), key=lambda text: [int(part) for part in text.split(".")])
    if not versions:
        raise RuntimeError("Could not find a Tor release")
    version = versions[-1]
    return "%s%s/tor-expert-bundle-windows-x86_64-%s.tar.gz" % (base, version, version)


def latest_i2p_url():
    request = urllib.request.Request("https://api.github.com/repos/PurpleI2P/i2pd/releases/latest", headers={"User-Agent": "Program"})
    with urllib.request.urlopen(request, timeout=20) as response:
        release = json.loads(response.read().decode("utf-8"))
    for asset in release.get("assets", []):
        if re.search(r"win64_mingw\.zip$", asset.get("name", "")):
            return asset["browser_download_url"]
    raise RuntimeError("Could not find an i2pd Windows build")


def download_and_extract(url, target_dir, progress, cancel):
    os.makedirs(target_dir, exist_ok=True)
    archive = os.path.join(target_dir, "download.tmp")
    request = urllib.request.Request(url, headers={"User-Agent": "Program"})
    with urllib.request.urlopen(request, timeout=30) as response, open(archive, "wb") as handle:
        total = int(response.headers.get("Content-Length") or 0)
        received = 0
        while True:
            if cancel.is_set():
                handle.close()
                os.remove(archive)
                return False
            block = response.read(65536)
            if not block:
                break
            handle.write(block)
            received += len(block)
            if total:
                progress(received / total)
    base = os.path.realpath(target_dir)
    if url.endswith(".zip"):
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.namelist():
                if not os.path.realpath(os.path.join(base, member)).startswith(base):
                    raise RuntimeError("Unsafe path in archive")
            bundle.extractall(base)
    else:
        with tarfile.open(archive) as bundle:
            for member in bundle.getmembers():
                if not os.path.realpath(os.path.join(base, member.name)).startswith(base):
                    raise RuntimeError("Unsafe path in archive")
            bundle.extractall(base)
    os.remove(archive)
    return True


class NetConfigWindow(ThemedWindow):
    def __init__(self, app):
        super().__init__(app, "Network configuration", 1040, 660, min_size=(700, 420))
        self.store = JsonStore(NETCONFIG_PATH, {"values": {}, "active_preset": ""})
        self.presets = JsonStore(PRESETS_PATH, {})
        self.visible = []
        self.helper_processes = {}
        self.place_client()
        top = tk.Frame(self.client)
        top.pack(side="top", fill="x", pady=3)
        tk.Label(top, text="Search:").pack(side="left", padx=4)
        self.search_var = tk.StringVar()
        search = tk.Entry(top, textvariable=self.search_var, width=26)
        search.pack(side="left")
        self.search_entry = search
        self.category_var = tk.StringVar(value="All categories")
        categories = ["All categories"] + list(NETCONFIG_PARAMETERS)
        self.category_menu = tk.OptionMenu(top, self.category_var, *categories, command=lambda value: self.refresh())
        self.category_menu.pack(side="left", padx=8)
        self.changed_var = tk.IntVar(value=0)
        tk.Checkbutton(top, text="Changed only", variable=self.changed_var, command=self.refresh).pack(side="left", padx=4)
        self.count_label = tk.Label(top, text="")
        self.count_label.pack(side="left", padx=10)
        presets = tk.Frame(self.client)
        presets.pack(side="top", fill="x", pady=3)
        tk.Label(presets, text="Preset:").pack(side="left", padx=4)
        self.preset_var = tk.StringVar()
        preset_entry = tk.Entry(presets, textvariable=self.preset_var, width=20)
        preset_entry.pack(side="left")
        for label, handler in (("Save", self.save_preset), ("Select", self.select_preset), ("Delete", self.delete_preset), ("Reset all", self.reset_all)):
            tk.Button(presets, text=label, command=handler).pack(side="left", padx=3)
        self.preset_list_label = tk.Label(presets, text="")
        self.preset_list_label.pack(side="left", padx=8)
        helpers = tk.Frame(self.client)
        helpers.pack(side="bottom", fill="x", pady=3)
        for label, handler in (
            ("Install Tor", lambda: self.install_helper("tor")), ("Start Tor", lambda: self.start_helper("tor")),
            ("Install I2P", lambda: self.install_helper("i2p")), ("Start I2P", lambda: self.start_helper("i2p")),
            ("Stop helpers", self.stop_helpers),
        ):
            tk.Button(helpers, text=label, command=handler).pack(side="left", padx=3)
        self.helper_label = tk.Label(helpers, text="", anchor="w")
        self.helper_label.pack(side="left", padx=8)
        editor = tk.Frame(self.client)
        editor.pack(side="bottom", fill="x", pady=3)
        self.selected_label = tk.Label(editor, text="Select a setting", anchor="w")
        self.selected_label.pack(side="top", fill="x", padx=4)
        edit_row = tk.Frame(editor)
        edit_row.pack(side="top", fill="x")
        tk.Label(edit_row, text="Value:").pack(side="left", padx=4)
        self.value_var = tk.StringVar()
        value_entry = tk.Entry(edit_row, textvariable=self.value_var, width=30)
        value_entry.pack(side="left")
        value_entry.bind("<Return>", lambda event: self.apply_value())
        tk.Button(edit_row, text="Set", command=self.apply_value).pack(side="left", padx=3)
        tk.Button(edit_row, text="Restore default", command=self.restore_default).pack(side="left", padx=3)
        self.choices_label = tk.Label(edit_row, text="", anchor="w")
        self.choices_label.pack(side="left", padx=8)
        list_frame = tk.Frame(self.client)
        list_frame.pack(side="top", fill="both", expand=True)
        self.listbox = tk.Listbox(list_frame, activestyle="none", exportselection=False)
        scrollbar = tk.Scrollbar(list_frame, command=self.listbox.yview, width=12)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.listbox.pack(side="left", fill="both", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        self.search_var.trace_add("write", lambda *args: self.refresh())
        self.style_new()
        self.refresh()
        self.refresh_preset_list()
        search.focus_set()

    def on_find(self, event=None):
        self.search_entry.focus_set()
        self.search_entry.select_range(0, "end")
        return "break"

    def announce(self, text):
        self.helper_label.configure(text=text)

    def current_value(self, item):
        return self.store.data["values"].get(item["key"], item["default"])

    def refresh(self):
        needle = self.search_var.get().strip().lower()
        category = self.category_var.get()
        changed_only = bool(self.changed_var.get())
        self.visible = []
        self.listbox.delete(0, "end")
        for item in NETCONFIG_CATALOG:
            if category != "All categories" and item["category"] != category:
                continue
            if changed_only and item["key"] not in self.store.data["values"]:
                continue
            if needle and needle not in (item["key"] + " " + item["description"]).lower():
                continue
            self.visible.append(item)
            marker = "*" if item["key"] in self.store.data["values"] else " "
            self.listbox.insert("end", "%s %-52s = %s" % (marker, "%s > %s > %s" % (item["category"], item["scope"], item["name"]), self.current_value(item)))
        self.count_label.configure(text="%d of %d settings, %d changed" % (len(self.visible), len(NETCONFIG_CATALOG), len(self.store.data["values"])))

    def selected_item(self):
        selection = self.listbox.curselection()
        return self.visible[selection[0]] if selection else None

    def on_select(self, event=None):
        item = self.selected_item()
        if not item:
            return
        self.selected_label.configure(text="%s - %s" % (item["key"], item["description"]))
        self.value_var.set(self.current_value(item))
        kind = item["kind"]
        self.choices_label.configure(text="Options: %s" % kind[7:].replace(",", " | ") if kind.startswith("choice:") else "Type: %s" % kind)

    def apply_value(self):
        item = self.selected_item()
        if not item:
            return
        value = self.value_var.get().strip()
        kind = item["kind"]
        if kind == "bool" and value.lower() not in ("on", "off"):
            self.choices_label.configure(text="Enter on or off")
            return
        if kind == "int" and not re.fullmatch(r"-?\d+", value):
            self.choices_label.configure(text="Enter a whole number")
            return
        if kind.startswith("choice:") and value not in kind[7:].split(","):
            self.choices_label.configure(text="Options: %s" % kind[7:].replace(",", " | "))
            return
        self.set_value(item, value)

    def set_value(self, item, value):
        if value == item["default"]:
            self.store.data["values"].pop(item["key"], None)
        else:
            self.store.data["values"][item["key"]] = value
        self.store.save()
        self.reselect(item)

    def restore_default(self):
        item = self.selected_item()
        if item:
            self.value_var.set(item["default"])
            self.set_value(item, item["default"])

    def reselect(self, item):
        index = self.visible.index(item) if item in self.visible else 0
        yview = self.listbox.yview()[0]
        self.refresh()
        if self.visible:
            index = self.visible.index(item) if item in self.visible else min(index, len(self.visible) - 1)
            self.listbox.selection_set(index)
            self.listbox.yview_moveto(yview)

    def refresh_preset_list(self):
        names = sorted(self.presets.data)
        active = self.store.data.get("active_preset", "")
        self.preset_list_label.configure(text="Saved: %s%s" % (", ".join(names) or "none", "   Active: %s" % active if active else ""))

    def save_preset(self):
        name = self.preset_var.get().strip()
        if not name:
            self.helper_label.configure(text="Enter a preset name first")
            return
        self.presets.data[name] = dict(self.store.data["values"])
        self.presets.save()
        self.store.data["active_preset"] = name
        self.store.save()
        self.refresh_preset_list()

    def select_preset(self):
        name = self.preset_var.get().strip()
        if name not in self.presets.data:
            self.helper_label.configure(text="No preset named '%s'" % name)
            return
        self.store.data["values"] = dict(self.presets.data[name])
        self.store.data["active_preset"] = name
        self.store.save()
        self.refresh()
        self.refresh_preset_list()

    def delete_preset(self):
        name = self.preset_var.get().strip()
        if self.presets.data.pop(name, None) is not None:
            self.presets.save()
            if self.store.data.get("active_preset") == name:
                self.store.data["active_preset"] = ""
                self.store.save()
            self.refresh_preset_list()

    def reset_all(self):
        self.store.data["values"] = {}
        self.store.data["active_preset"] = ""
        self.store.save()
        self.refresh()
        self.refresh_preset_list()

    def install_helper(self, name):
        target = os.path.join(INSTALL_DIR, name)
        if not IS_WINDOWS:
            self.helper_label.configure(text="Helper installers download Windows builds and run on Windows only")
            return
        progress = self.app.thread_safe(self, self.loading.set_fraction)
        say = self.app.thread_safe(self, self.helper_label.configure)

        def work(cancel):
            say(text="Looking up latest %s release..." % name)
            url = latest_tor_url() if name == "tor" else latest_i2p_url()
            say(text="Downloading %s" % url)
            return download_and_extract(url, target, progress, cancel)

        self.app.run_task(
            self, work,
            done=lambda completed: self.helper_label.configure(text="%s installed in %s" % (name, target) if completed else "Install cancelled"),
            failed=lambda error: self.helper_label.configure(text="Install failed: %s" % error),
        )

    def start_helper(self, name):
        executable = "tor.exe" if name == "tor" else "i2pd.exe"
        found = glob.glob(os.path.join(INSTALL_DIR, name, "**", executable), recursive=True)
        if not found:
            self.helper_label.configure(text="%s is not installed yet" % name)
            return
        if name in self.helper_processes and self.helper_processes[name].poll() is None:
            self.helper_label.configure(text="%s is already running" % name)
            return
        arguments = [found[0]] + (["--SocksPort", "9050"] if name == "tor" else [])
        try:
            self.helper_processes[name] = subprocess.Popen(
                arguments, cwd=os.path.dirname(found[0]), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL, creationflags=hidden_process_flags(),
            )
            self.helper_label.configure(text="%s started" % name)
        except OSError as error:
            self.helper_label.configure(text="Cannot start %s: %s" % (name, error))

    def stop_helpers(self):
        for process in self.helper_processes.values():
            if process.poll() is None:
                process.terminate()
        self.helper_processes = {}
        self.helper_label.configure(text="Helpers stopped")

    def on_close(self):
        self.stop_helpers()


class CustomizeWindow(ThemedWindow):
    def __init__(self, app):
        super().__init__(app, "Customize", 760, 640, min_size=(600, 460))
        self.place_client()
        data = app.settings.data
        status = app.statusbar_store.data
        left = tk.Frame(self.client)
        left.pack(side="left", fill="y", padx=6, pady=4)
        tk.Label(left, text="Font family").pack(anchor="w")
        family_frame = tk.Frame(left)
        family_frame.pack(fill="y", expand=True)
        self.family_list = tk.Listbox(family_frame, width=28, exportselection=False)
        family_scroll = tk.Scrollbar(family_frame, command=self.family_list.yview, width=12)
        self.family_list.configure(yscrollcommand=family_scroll.set)
        family_scroll.pack(side="right", fill="y")
        self.family_list.pack(side="left", fill="y", expand=True)
        families = sorted({name for name in tkinter.font.families() if not name.startswith("@")} | {"Terminal"}, key=str.lower)
        for family in families:
            self.family_list.insert("end", family)
        if data["font"] in families:
            index = families.index(data["font"])
            self.family_list.selection_set(index)
            self.family_list.see(index)
        self.families = families
        self.family_list.bind("<<ListboxSelect>>", self.on_family)
        right = tk.Frame(self.client)
        right.pack(side="left", fill="both", expand=True, padx=6, pady=4)
        self.size_scale = self.add_scale(right, "Text size", 6, 40, 1, data["size"])
        self.size_scale.bind("<ButtonRelease-1>", lambda event: self.update_setting("size", int(self.size_scale.get())))
        colors = tk.Frame(right)
        colors.pack(fill="x", pady=6)
        tk.Button(colors, text="Text color...", command=lambda: self.pick_color("fg")).pack(side="left", padx=3)
        tk.Button(colors, text="Background color...", command=lambda: self.pick_color("bg")).pack(side="left", padx=3)
        self.color_label = tk.Label(colors, text="")
        self.color_label.pack(side="left", padx=8)
        icons = tk.Frame(right)
        icons.pack(fill="x", pady=6)
        tk.Button(icons, text="Choose icon...", command=self.pick_icon).pack(side="left", padx=3)
        tk.Button(icons, text="Default icon", command=lambda: self.set_icon("")).pack(side="left", padx=3)
        self.icon_label = tk.Label(icons, text="", anchor="w")
        self.icon_label.pack(side="left", padx=8)
        background = tk.Frame(right)
        background.pack(fill="x", pady=6)
        tk.Button(background, text="Background image...", command=self.pick_background).pack(side="left", padx=3)
        tk.Button(background, text="No image", command=lambda: self.update_setting("background_image", "")).pack(side="left", padx=3)
        self.background_label = tk.Label(background, text="", anchor="w")
        self.background_label.pack(side="left", padx=8)
        self.dim_scale = self.add_scale(right, "Image dim (%)", 0, 95, 1, int(float(data["dim"]) * 100))
        self.dim_scale.bind("<ButtonRelease-1>", lambda event: self.update_setting("dim", int(self.dim_scale.get()) / 100.0))
        self.margin_scale = self.add_scale(right, "Image margin (px)", 0, 80, 1, int(data["margin"]))
        self.margin_scale.bind("<ButtonRelease-1>", lambda event: self.update_setting("margin", int(self.margin_scale.get())))
        tk.Label(right, text="Status bar", anchor="w").pack(fill="x", pady=(10, 0))
        self.monitor_var = tk.IntVar(value=1 if status.get("enabled", True) else 0)
        tk.Checkbutton(right, text="Live network speed enabled", variable=self.monitor_var, command=self.update_status).pack(anchor="w")
        server_row = tk.Frame(right)
        server_row.pack(fill="x")
        tk.Label(server_row, text="Test server (auto or URL):").pack(side="left")
        self.server_var = tk.StringVar(value=str(status.get("server", "auto")))
        server_entry = tk.Entry(server_row, textvariable=self.server_var)
        server_entry.pack(side="left", fill="x", expand=True, padx=4)
        server_entry.bind("<Return>", lambda event: self.update_status())
        tk.Button(server_row, text="Apply", command=self.update_status).pack(side="left")
        self.scroll_scale = self.add_scale(right, "Scroll speed", 0, 8, 1, int(status.get("scroll_speed", 2)))
        self.scroll_scale.bind("<ButtonRelease-1>", lambda event: self.update_status())
        tk.Button(right, text="Reset to defaults", command=self.reset_defaults).pack(anchor="w", pady=10)
        self.style_new()
        self.refresh_labels()

    def add_scale(self, parent, label, start, end, resolution, value):
        row = tk.Frame(parent)
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label, width=18, anchor="w").pack(side="left")
        scale = tk.Scale(row, from_=start, to=end, resolution=resolution, orient="horizontal", length=240)
        scale.set(value)
        scale.pack(side="left")
        return scale

    def refresh_labels(self):
        data = self.app.settings.data
        self.color_label.configure(text="text %s  background %s" % (data["fg"], data["bg"]))
        self.icon_label.configure(text=os.path.basename(data["icon"]) if data["icon"] else "default icon")
        self.background_label.configure(text=os.path.basename(data["background_image"]) if data["background_image"] else "none")

    def update_setting(self, key, value):
        self.app.settings.data[key] = value
        self.app.settings.save()
        self.app.refresh_all_themes()
        self.refresh_labels()

    def on_family(self, event=None):
        selection = self.family_list.curselection()
        if selection:
            self.update_setting("font", self.families[selection[0]])

    def pick_color(self, key):
        chosen = tkinter.colorchooser.askcolor(color=self.app.settings.data[key], parent=self, title="Choose color")
        if chosen and chosen[1]:
            self.update_setting(key, chosen[1])

    def pick_icon(self):
        path = tkinter.filedialog.askopenfilename(parent=self, title="Choose icon", filetypes=[("Images", "*.png *.gif *.jpg *.jpeg *.bmp *.ico"), ("All files", "*.*")])
        if path:
            self.set_icon(path)

    def set_icon(self, path):
        self.app.settings.data["icon"] = path
        self.app.settings.save()
        self.app.load_icon()
        self.refresh_labels()

    def pick_background(self):
        path = tkinter.filedialog.askopenfilename(parent=self, title="Choose background image", filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"), ("All files", "*.*")])
        if path:
            self.update_setting("background_image", path)

    def update_status(self):
        status = self.app.statusbar_store.data
        status["enabled"] = bool(self.monitor_var.get())
        status["server"] = self.server_var.get().strip() or "auto"
        status["scroll_speed"] = int(self.scroll_scale.get())
        self.app.statusbar_store.save()
        self.app.monitor.server = None

    def reset_defaults(self):
        self.app.settings.data.update(DEFAULT_SETTINGS)
        self.app.settings.save()
        self.app.load_icon()
        self.app.refresh_all_themes()
        self.size_scale.set(DEFAULT_SETTINGS["size"])
        self.dim_scale.set(int(DEFAULT_SETTINGS["dim"] * 100))
        self.margin_scale.set(DEFAULT_SETTINGS["margin"])
        self.refresh_labels()


def main():
    if IS_WINDOWS:
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Program.NetworkToolkit")
        except (OSError, AttributeError):
            pass
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (OSError, AttributeError):
            pass
    App().run()


if __name__ == "__main__":
    main()
