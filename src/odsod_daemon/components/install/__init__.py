"""Write and enable the units; build and install keys.

SUBSYSTEM: install
Reads: Package metadata, unit templates, state/install/current.
Writes: User units, D-Bus activation file, state/install, system keys files.
ADR: docs/adr/0006-installation.md
"""

SUBSYSTEM = "install"
