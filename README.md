# Program

A terminal-styled Windows desktop toolkit for network diagnostics, file inspection and media playback.
Written in Python 3.13 with Tkinter, delivered as a single `main.py` that packages into one `program.exe`.

## Features

- Borderless themed windows with a custom title bar (drag, resize grips, minimize/maximize/close), shown in the taskbar, using `icon.png`.
- Black background, red text, "Terminal" font by default. Font, size, colors, icon and background image (with dim and margin) are customizable and saved in `settings.json` next to the exe.
- Main window with a clickable menu and a command line: `help`, `status`, `ping TCP|UDP PORT HOST [COUNT] [-4|-6]`, `ping`, `ofile [PATH]`, `netconf`, `custom`, `clear`, `exit`. Tab autocompletes, Up/Down walks history, typos get a clickable "did you mean X?" button.
- Ping tool: TCP or UDP, IPv4 or IPv6, port, packet count, per-packet results and a summary.
- Status report: OS, CPU, memory, disks, adapters, DNS, routes, ARP, open ports, connections, Wi-Fi, proxy, firewall, connectivity and more, with a progress bar.
- Network configuration: searchable catalog of 1,300 settings by category, savable and selectable presets (`presets.json`, `netconfig.json`), helper installers for Tor and I2P (`installed/`).
- Open file: image viewer, audio player, video player, text viewer, hex viewer and integrity check (MD5, SHA-1, SHA-256, SHA-512, CRC32).
  - Audio: waveform seek bar (click, drag, hover time), embedded and folder cover art (click to cycle), loop, mute, volume (mouse wheel), shortcuts (Space, Left/Right, Up/Down, M, L, Home), metadata and hash report.
  - Video: ffmpeg rawvideo pipe synced to the audio clock, resizable, fullscreen (F, Esc, double-click), frame step (`,` and `.`), loop.
  - Both: speed 0.25x to 2.0x with "keep pitch" or "shift pitch".
- Ctrl+F search bar in text views, Ctrl+A select all, Shift+mouse wheel zoom, Ctrl+X closes the current window or cancels the running command, cursor coordinates in the title bar.
- Bottom status bar with a horizontally scrolling live network speed (configurable test server, default the lowest-latency one) and a loading bar during slow work.

## Screenshots

- Main window: _placeholder_
- Audio player: _placeholder_
- Video player: _placeholder_
- Network configuration: _placeholder_

## Requirements

- Windows, Python 3.13
- `pip install -r requirements.txt` (Pillow, pygame, numpy)
- `ffmpeg` and `ffprobe` on `PATH`

## Run

```
python main.py
```

## Build

```
pip install pyinstaller
pyinstaller --onefile --windowed --name program --icon icon.png --add-data "icon.png;." --hidden-import ctypes.wintypes --hidden-import tkinter.filedialog --hidden-import tkinter.font --hidden-import tkinter.colorchooser main.py
```

The GitHub Actions workflow in `.github/workflows/build.yml` does this and uploads `program.exe` as an artifact.

## Privacy

The app stores only local config files next to the exe (`settings.json`, `statusbar.json`, `presets.json`, `netconfig.json`, `installed/`) and sends nothing anywhere except the network tests you start. The status bar speed monitor contacts the configured test server to measure speed; turn it off in Customize. Tor and I2P are downloaded only when you press their install buttons.
