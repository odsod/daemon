"""Own whisper-server and llama-server: pins, setup, and the unit facts.

SUBSYSTEM: inference
Reads: inference config, the machine data dir (models to adopt).
Writes: state/servers/, state/models/ (whisper and llama models).
ADR: docs/adr/0023-inference-servers.md
"""

from odsod_daemon.components.servers.contract import Inference as CONFIG_MODEL

SUBSYSTEM = "inference"

__all__ = ["CONFIG_MODEL"]
