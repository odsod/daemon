"""Copy finished documents to configured targets.

SUBSYSTEM: publishing
Reads: finished, publishing config.
Writes: published/<target>, target copies, run/health/pipeline.json.
ADR: docs/adr/0017-publishing.md
"""

SUBSYSTEM = "publishing"
