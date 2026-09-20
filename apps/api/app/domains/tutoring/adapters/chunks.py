"""In-process chunk variants produced by a model adapter.

These are Python types, not wire JSON: see `docs/adr/0002-model-adapter.md`
("chunk 变体"). The union is closed, and a `ThinkingDelta` will never be added:
`packages/contracts/tutoring/tutoring-response.md:92-95` forbids an adapter from
forwarding internal reasoning deltas, so any reasoning channel is dropped
inside the adapter and never reaches this type set.
"""

from dataclasses import dataclass

__all__ = ["Finished", "ModelChunk", "TextDelta", "Usage"]


@dataclass(frozen=True, slots=True)
class TextDelta:
    """Incremental answer text. The server concatenates these in order."""

    text: str


@dataclass(frozen=True, slots=True)
class Usage:
    """Token usage for one call. Only logged; never sent to the client."""

    input_tokens: int
    output_tokens: int


@dataclass(frozen=True, slots=True)
class Finished:
    """The upstream stream ended normally."""

    stop_reason: str


type ModelChunk = TextDelta | Usage | Finished
