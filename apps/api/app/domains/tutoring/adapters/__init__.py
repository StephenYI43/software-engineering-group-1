"""Model adapter layer for the tutoring domain (ADR-0002, option B).

`adapters/` is a fifth layer beyond the router / schemas / service / repository
split in `docs/code-standards.md:33`; that document is unchanged by this slice.
"""

from app.domains.tutoring.adapters.base import (
    ModelClient,
    ModelRequest,
    RetrievedChunk,
    Turn,
)
from app.domains.tutoring.adapters.chunks import Finished, ModelChunk, TextDelta, Usage
from app.domains.tutoring.adapters.mock import SCENARIOS, MockModelClient

__all__ = [
    "SCENARIOS",
    "Finished",
    "MockModelClient",
    "ModelChunk",
    "ModelClient",
    "ModelRequest",
    "RetrievedChunk",
    "TextDelta",
    "Turn",
    "Usage",
]
