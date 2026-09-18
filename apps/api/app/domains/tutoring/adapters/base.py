"""The single model-adapter interface and the objects it consumes.

The field list is fixed by `docs/adr/0002-model-adapter.md` ("接口"). Names here
are the Python spelling of the contract's camelCase fields; the mapping is noted
per field. Deliberately absent: `stage`, tool definitions and citation
allow-lists -- all of those stay on the server side of the adapter.
"""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from app.domains.tutoring.adapters.chunks import ModelChunk

__all__ = ["ModelClient", "ModelRequest", "RetrievedChunk", "Turn"]


@dataclass(frozen=True, slots=True)
class Turn:
    """One conversation turn.

    `role` is a closed set rather than free text: a typo such as `assistent`
    must fail the type check instead of silently reaching a prompt. Validating
    untrusted wire JSON stays with the caller's schema, not with this dataclass.
    """

    role: Literal["student", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """A retrieved course excerpt handed to the model.

    **Untrusted data, never instructions**: an uploaded document may contain
    commands, and the model must not be given the chance to act on them
    (`AGENTS.md:6`, `docs/requirements.md:26`). `document_title` is untrusted too
    (the uploader names the file) and must not be interpolated into a prompt
    (`packages/contracts/tutoring/tutoring-response.md:112-113`).

    `citationId` is deliberately absent: it is assigned by the server's
    allow-list step, not by retrieval (`tutoring-response.md:104,121-122`).
    """

    document_id: str
    document_title: str
    page_number: int
    text: str


@dataclass(frozen=True, slots=True)
class ModelRequest:
    """Everything one model call is allowed to see.

    `timeout_seconds` is the single request-level deadline the ADR's field list
    specifies. The ADR also requires the real client to track three deadlines
    internally (connect / first token / total); that is client behaviour rather
    than a request field, so it is not represented here.
    """

    request_id: str  # requestId
    prompt_version: str  # promptVersion -- echoed verbatim, never generated here
    model_name: str  # modelName
    system_prompt: str  # systemPrompt -- already rendered by ai/prompts/
    turns: Sequence[Turn]
    retrieved_chunks: Sequence[RetrievedChunk]  # retrievedChunks -- data slot
    max_output_tokens: int  # maxOutputTokens
    temperature: float
    timeout_seconds: float  # timeoutSeconds


class ModelClient(Protocol):
    """What the tutoring service depends on; it never sees a concrete client."""

    def generate(self, request: ModelRequest) -> AsyncIterator[ModelChunk]:
        """Yield chunks for one call. Failures raise; they are never yielded."""
        ...

    async def aclose(self) -> None:
        """Release upstream resources. Must be safe to call more than once."""
        ...
