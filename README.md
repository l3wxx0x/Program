# Program

Program is a Windows desktop app that puts network tools, a file inspector and a media player in one place. You can use a clickable menu or type commands such as ping, status, ofile, netconf, custom, help, clear and exit. Tab autocompletes, Up/Down recalls earlier commands, and a mistyped command gets a "did you mean…?" suggestion you can click.

Network

Ping over TCP or UDP, with IPv4 or IPv6, a port and a packet count.
A live network speed bar at the bottom of the window, with a configurable test server.
A system and network status report.
A network configuration window with about 1,300 settings, savable presets, and Tor and I2P setup helpers.
Files

Open images, text, audio and video.
A hex view for any file type.
A hash and metadata report, plus an integrity check.
Audio and video

Audio:
A waveform seek bar you can click or drag, and a cover-art preview.
Loop, mute and volume.
Video:
Resizable window, fullscreen, frame-step and loop.
Both:
A speed slider from 0.25x to 2x, with a choice to keep or shift the pitch.
Keyboard shortcuts.
Interface

Fast Ctrl+F search.
Customizable font, colors, text size and background image.
Ctrl+A to select all, Shift+wheel to zoom, and Ctrl+X to close a window or cancel a command.
Resizable windows that show in the taskbar.
Requirements: Python 3.13 with Pillow, pygame and numpy. ffmpeg and ffprobe must be on PATH for the media features. A single-file program.exe can be built with PyInstaller.

Privacy: it doesn't need administrator rights. It saves only a few local settings files next to the program and sends nothing except the network tests you start.
