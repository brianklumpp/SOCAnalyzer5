"""Extractor package public API.

Expose only the current control extractor (v2) to discourage accidental use
of deprecated implementations. Legacy modules are intentionally not re-exported;
they will be archived and removed in a future cleanup.
"""

from .control_extractor_v2 import extract_controls_v2  # current implementation

__all__ = [
	'extract_controls_v2',
]

