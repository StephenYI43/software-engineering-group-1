"""The wire models for the tutoring endpoints.

camelCase on the wire, snake_case in Python, with the alias doing the conversion
(`docs/code-standards.md:48,55`). Field order here matches the order the frozen
samples use, so a dumped event reads the same way the contract documents it.

Every invariant `packages/contracts/tutoring/tutoring-response.md:115-130` lists
is enforced by a validator rather than left to callers: that file says explicitly
they "should be caught by a Pydantic validator or a test".
"""

from datetime import UTC, datetime
from typing import Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from app.domains.tutoring.envelope import Action, Emotion
from app.domains.tutoring.stages import Stage

__all__ = [
    "Citation",
    "CompletedEvent",
    "DeltaEvent",
    "ErrorBody",
    "ErrorCode",
    "ErrorEvent",
    "MessageRequest",
    "StartedEvent",
    "StopReason",
    "StoppedEvent",
    "StreamEvent",
    "TutoringResponse",
]

#: The in-stream error codes (`packages/contracts/tutoring/sse-events.md:129-137`).
ErrorCode = Literal[
    "MODEL_OUTPUT_INVALID",
    "MODEL_REFUSED",
    "MODEL_TIMEOUT",
    "RETRIEVAL_UNAVAILABLE",
    "TURN_ABORTED",
]

#: Why a turn stopped (`sse-events.md:98`). Note that `client_disconnect` can
#: never be delivered: the student is gone, so it is recorded server-side only.
StopReason = Literal["client_stop", "client_disconnect"]

#: Length bounds on the student's question (`tutoring-response.md:24`).
MAX_CONTENT_CHARS: Final[int] = 2000


class _WireModel(BaseModel):
    """Shared config for models crossing the wire.

    `populate_by_name` lets internal code and tests build these with Python
    names while the wire keeps camelCase.
    """

    model_config = ConfigDict(populate_by_name=True)


class Citation(_WireModel):
    """One citation, assembled by the server (`tutoring-response.md:100-113`).

    `document_title` is displayed but never put in a prompt: the uploader chooses
    it, so it is untrusted input.
    """

    citation_id: str = Field(alias="citationId")
    document_id: str = Field(alias="documentId")
    document_title: str = Field(alias="documentTitle")
    #: 1-based; the contract forbids 0 and negatives.
    page_number: int = Field(alias="pageNumber", ge=1)
    snippet: str


class MessageRequest(_WireModel):
    """`POST /api/v1/tutoring/sessions/{sessionId}/messages`.

    `extra="forbid"` is load-bearing: it is what turns a client-supplied `stage`
    into a 422 instead of letting a student skip straight to `summary`
    (`tutoring-response.md:28-34`).
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    content: str = Field(min_length=1, max_length=MAX_CONTENT_CHARS)
    requested_stage: Stage | None = Field(default=None, alias="requestedStage")
    #: May only narrow what the server already authorised, never widen it.
    course_id: str | None = Field(default=None, alias="courseId")


class TutoringResponse(_WireModel):
    """The payload of `completed` (`tutoring-response.md:36-79`)."""

    turn_id: str = Field(alias="turnId")
    session_id: str = Field(alias="sessionId")
    stage: Stage
    content: str
    citations: list[Citation] = Field(default_factory=list)
    has_evidence: bool = Field(alias="hasEvidence")
    follow_ups: list[str] = Field(alias="followUps", default_factory=list, max_length=3)
    emotion: Emotion
    action: Action
    is_mock: bool = Field(alias="isMock")
    prompt_version: str = Field(alias="promptVersion")
    created_at: datetime = Field(alias="createdAt")

    @field_serializer("created_at")
    def _serialize_created_at(self, value: datetime) -> str:
        """The contract's samples all end in `Z`, so emit that rather than
        pydantic's default `+00:00` (`docs/code-standards.md:55`)."""

        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    @model_validator(mode="after")
    def _require_evidence_to_agree_with_citations(self) -> Self:
        """Invariant 1: `hasEvidence = false` exactly when `citations` is empty.

        Both directions matter. `hasEvidence=true` with no citations would tell
        M2 an answer is sourced when it is not; `false` with citations would hide
        sources it actually used. An empty list is how "no evidence" is spelled --
        `citations` must never be `null` (invariant 3).
        """

        if self.has_evidence != bool(self.citations):
            raise ValueError("hasEvidence must be false exactly when citations is empty")
        return self


class _StreamEvent(_WireModel):
    """Fields every SSE event carries (`sse-events.md:29-35`)."""

    seq: int = Field(ge=1)
    turn_id: str = Field(alias="turnId")


class StartedEvent(_StreamEvent):
    """Always the first event, always `seq=1` (`sse-events.md:31`).

    `stage` is sent up front so M2 can render the stage indicator immediately
    instead of waiting for the answer to finish.
    """

    stage: Stage
    is_mock: bool = Field(alias="isMock")


class DeltaEvent(_StreamEvent):
    """Incremental prose, and nothing else (`sse-events.md:69-70`).

    Structured fields stay out of `delta` on purpose: M2 should never have to
    handle a half-built structure mid-stream.
    """

    text_delta: str = Field(alias="textDelta")


class CompletedEvent(_StreamEvent):
    """The only event carrying the full response (`sse-events.md:72-85`)."""

    is_complete: Literal[True] = Field(alias="isComplete", default=True)
    response: TutoringResponse


class StoppedEvent(_StreamEvent):
    """The user stopped, or the connection dropped -- not a system failure."""

    is_complete: Literal[False] = Field(alias="isComplete", default=False)
    reason: StopReason


class ErrorBody(_WireModel):
    """The error structure from `sse-events.md:111-137`."""

    code: ErrorCode
    message: str
    request_id: str = Field(alias="requestId")
    #: Free-form. Deliberately **not** filled with a fabricated `attempts` count:
    #: the frozen sample has one because it illustrates a retry, and S1 has no
    #: retry, so copying it would state something untrue.
    details: dict[str, object] = Field(default_factory=dict)


class ErrorEvent(_StreamEvent):
    """A system failure, as opposed to `stopped`, which is user intent."""

    is_complete: Literal[False] = Field(alias="isComplete", default=False)
    error: ErrorBody


#: Any of the five events, for callers that hand them around as one type.
StreamEvent = StartedEvent | DeltaEvent | CompletedEvent | StoppedEvent | ErrorEvent
