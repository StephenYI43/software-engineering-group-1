"""Splitting model output into a prose body and a trailing response envelope.

One model output is a prose body followed by a single-line JSON envelope fenced
by `<<<RESPONSE_ENVELOPE>>>` / `<<<END_RESPONSE_ENVELOPE>>>`, as the template in
`ai/prompts/` specifies.

The SSE contract (`packages/contracts/tutoring/sse-events.md:69-70`) lets only
prose ride on a `delta`, so the envelope has to be withheld **before anything is
sent**: it is where `citations` / `followUps` / `emotion` / `action` come from,
not text a student should ever read. Forwarding it as a `delta` would make M2
render the raw JSON into the answer.

The envelope carries **labels** only (`c1`), never document details. Mapping a
label to a `Citation` (page, excerpt) belongs to the service layer
(`docs/adr/0004-rag-retrieval-boundary.md:257`): the model neither should nor can
decide which page a citation points at.
"""

import json
from dataclasses import dataclass
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

__all__ = [
    "MAX_FOLLOW_UPS",
    "MAX_FOLLOW_UP_CHARS",
    "RESPONSE_CLOSE",
    "RESPONSE_OPEN",
    "Action",
    "BodyEnvelopeSplitter",
    "Emotion",
    "EnvelopeFailure",
    "EnvelopeOutcome",
    "ResponseEnvelope",
]

RESPONSE_OPEN: Final[str] = "<<<RESPONSE_ENVELOPE>>>"
RESPONSE_CLOSE: Final[str] = "<<<END_RESPONSE_ENVELOPE>>>"

Emotion = Literal["neutral", "encouraging", "thinking", "celebrating"]
Action = Literal["idle", "nod", "point", "write"]

#: Limits come from the template's field table in `ai/prompts/`.
#: Exceeding them is reported as invalid output rather than truncated: quietly
#: repairing the model would also hide that it stopped honouring the contract.
MAX_FOLLOW_UPS: Final[int] = 3
MAX_FOLLOW_UP_CHARS: Final[int] = 200

#: Internal reason a split failed. **Not** the `details.reason` sent to clients:
#: that is always `response_envelope_parse_failed`, matching the frozen sample
#: `samples/04-error-model-output-invalid.json`. The finer reason is for logs and
#: test assertions only.
EnvelopeFailure = Literal["missing", "unterminated", "parse_failed", "invalid"]


class ResponseEnvelope(BaseModel):
    """The single-line JSON between the envelope markers.

    `citations` holds labels (`c1`) only. Unknown fields are ignored, because
    adding one is the normal shape of a prompt-version bump and should not fail
    a whole turn.
    """

    model_config = ConfigDict(extra="ignore")

    citations: list[str] = Field(default_factory=list)
    follow_ups: list[str] = Field(default_factory=list, alias="followUps")
    emotion: Emotion
    action: Action

    @field_validator("follow_ups")
    @classmethod
    def _enforce_follow_up_limits(cls, value: list[str]) -> list[str]:
        if len(value) > MAX_FOLLOW_UPS:
            raise ValueError(f"at most {MAX_FOLLOW_UPS} followUps")
        if any(len(item) > MAX_FOLLOW_UP_CHARS for item in value):
            raise ValueError(f"each followUps entry at most {MAX_FOLLOW_UP_CHARS} characters")
        return value


@dataclass(frozen=True, slots=True)
class EnvelopeOutcome:
    """How one stream's split turned out.

    `envelope` and `failure` are mutually exclusive: a successful split leaves
    `failure` as `None`, a failed one leaves `envelope` as `None`.
    """

    body: str
    envelope: ResponseEnvelope | None
    failure: EnvelopeFailure | None


class BodyEnvelopeSplitter:
    """Splits "body + trailing envelope" into safe-to-send prose pieces.

    One instance per stream. The invariants, each with a test of its own:

    * the concatenation of everything emitted equals the model's prose, envelope
      excluded;
    * no emitted piece ever cuts `RESPONSE_OPEN` in half -- implemented by always
      holding back the trailing `len(RESPONSE_OPEN) - 1` characters, so any
      suffix that could become the start of a marker stays in the buffer;
    * once inside the envelope nothing more is emitted;
    * failure paths do **not** flush the look-back window, so a half-typed marker
      is never sent out as prose.

    Markers are matched as **substrings**, not with the "must start a line" rule
    the template uses. The rules differ on purpose: line-anchored matching is for
    **our own** template, which should fail loudly if a formatter breaks it, while
    model output is the untrusted and unreliable side and one stray newline must
    not fail a whole turn.
    """

    def __init__(self) -> None:
        self._state: Literal["outside", "inside", "done"] = "outside"
        self._buffer = ""
        self._body = ""
        self._raw_envelope = ""
        self._trailing = ""

    @property
    def body(self) -> str:
        """Everything emitted so far; equal to the concatenation of `feed` results."""

        return self._body

    @property
    def trailing(self) -> str:
        """Output found after the closing marker (the template says there is none).

        Kept for logging only, and never emitted as prose.
        """

        return self._trailing

    def feed(self, text: str) -> tuple[str, ...]:
        """Consume one model chunk and return the prose pieces safe to send now."""

        if self._state == "done":
            # Anything after the envelope cannot be prose. Keep it for logs, never
            # let it out as a delta.
            self._trailing += text
            return ()

        self._buffer += text
        emitted: list[str] = []

        if self._state == "outside":
            index = self._buffer.find(RESPONSE_OPEN)
            if index < 0:
                # Look-back window: hold back what could still become a marker.
                emit = len(self._buffer) - (len(RESPONSE_OPEN) - 1)
                if emit > 0:
                    emitted.append(self._accept_body(self._buffer[:emit]))
                    self._buffer = self._buffer[emit:]
                return tuple(emitted)
            if index > 0:
                emitted.append(self._accept_body(self._buffer[:index]))
            self._buffer = self._buffer[index + len(RESPONSE_OPEN) :]
            self._state = "inside"

        # The opening and closing markers can arrive in the same piece (a whole
        # output fed at once, for instance), so this cannot wait for the next feed.
        end = self._buffer.find(RESPONSE_CLOSE)
        if end >= 0:
            self._raw_envelope = self._buffer[:end]
            self._trailing += self._buffer[end + len(RESPONSE_CLOSE) :]
            self._buffer = ""
            self._state = "done"

        return tuple(emitted)

    def finish(self) -> EnvelopeOutcome:
        """Settle the stream. Pure read, so calling it twice is safe."""

        if self._state == "outside":
            return EnvelopeOutcome(body=self._body, envelope=None, failure="missing")
        if self._state == "inside":
            return EnvelopeOutcome(body=self._body, envelope=None, failure="unterminated")
        return self._parse()

    def _accept_body(self, text: str) -> str:
        self._body += text
        return text

    def _parse(self) -> EnvelopeOutcome:
        try:
            payload = json.loads(self._raw_envelope)
        except json.JSONDecodeError:
            return EnvelopeOutcome(body=self._body, envelope=None, failure="parse_failed")
        if not isinstance(payload, dict):
            return EnvelopeOutcome(body=self._body, envelope=None, failure="invalid")
        try:
            envelope = ResponseEnvelope.model_validate(payload)
        except ValidationError:
            return EnvelopeOutcome(body=self._body, envelope=None, failure="invalid")
        return EnvelopeOutcome(body=self._body, envelope=envelope, failure=None)
