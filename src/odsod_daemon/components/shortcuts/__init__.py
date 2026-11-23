"""Install the KWin script, bind chords and launch apps.

SUBSYSTEM: shortcuts
Reads: shortcuts.json, KWin, KGlobalAccel.
Writes: KWin package, kwinrc, KGlobalAccel, D-Bus interface, systemd scopes, log.
ADR: docs/adr/0008-shortcuts-and-kwin-script.md
"""

SUBSYSTEM = "shortcuts"
