"""Orchestration for one tutoring turn: retrieve, render, stream, settle.

The interesting part of this file is not the happy path. It is that a turn can end
five ways -- completed, stopped, disconnected, a model failure, a rejected
envelope -- and exactly one of them may reach the client as a terminal frame. The
writer enforces the "exactly one"; this file enforces the "agrees with what the
turn's state became".

The stop signal is read once, at the top of the post-read section, and every exit
below it changes state with **no `await` in between**. That single-threaded run is
the whole synchronisation strategy: a stop that arrived earlier has already moved
the turn out of `active`, so it wins here; a stop that arrives later finds the
turn settled and changes nothing. Introduce an `await` between the read and the
`settle_*`/`complete_turn` call and the guarantee is gone, silently -- both orders
still "work" in any test that never races them.
"""

import logging
import time
from collections.abc import AsyncIterator, Callable, Sequence
from datetime import UTC, datetime
from typing import Final

from app.domains.tutoring.adapters import ModelClient, ModelRequest, RetrievedChunk, Turn
from app.domains.tutoring.envelope import ResponseEnvelope
from app.domains.tutoring.prompt_renderer import PromptTemplate, citation_labels
from app.domains.tutoring.repository import InMemoryTutoringRepository, TurnRecord, TurnStatus
from app.domains.tutoring.retrieval import DEFAULT_LIMIT, RetrievalError, Retriever
from app.domains.tutoring.schemas import (
    Citation,
    ErrorBody,
    ErrorCode,
    StopReason,
    TutoringResponse,
)
from app.domains.tutoring.stages import Stage
from app.domains.tutoring.stream import (
    EventStreamWriter,
    ModelOutcome,
    ModelStreamReader,
    OutcomeKind,
)

__all__ = ["TutoringService"]

#: Only `client_stop` can ever be delivered. `client_disconnect` is in the enum
#: because the contract needs it to tell user intent from a dropped connection,
#: but a dropped connection has nobody left to deliver to: that turn is recorded
#: as `disconnected` and logged, and no frame is written.
_DELIVERABLE_STOP: Final[StopReason] = "client_stop"

#: `details.reason` for an output that could not be split into body plus envelope.
#: Matches `samples/04-error-model-output-invalid.json`.
_ENVELOPE_FAILURE_REASON: Final[str] = "response_envelope_parse_failed"

#: Client-facing text per code. Free-form per the contract, so these are written
#: to be actionable rather than to be matched by a client.
_ERROR_MESSAGES: Final[dict[ErrorCode, str]] = {
    "MODEL_OUTPUT_INVALID": "模型输出无法通过结构校验，请重试",
    "MODEL_REFUSED": "模型拒绝作答，请换一种问法",
    "MODEL_TIMEOUT": "模型调用超时，请重试",
    "RETRIEVAL_UNAVAILABLE": "检索服务暂不可用，请稍后重试",
    "TURN_ABORTED": "服务端内部中断，请重试",
}

#: How a model outcome that is not a completion becomes an error code. Total over
#: the non-completing kinds, so the service does a lookup rather than an `if`
#: ladder that a new `OutcomeKind` could slip past unnoticed.
_OUTCOME_ERRORS: Final[dict[OutcomeKind, ErrorCode]] = {
    "timed_out": "MODEL_TIMEOUT",
    "refused": "MODEL_REFUSED",
    "failed": "TURN_ABORTED",
}

MODEL_NAME: Final[str] = "mock"
MAX_OUTPUT_TOKENS: Final[int] = 1024
TEMPERATURE: Final[float] = 0.0
MODEL_TIMEOUT_SECONDS: Final[float] = 30.0


def _utc_now() -> datetime:
    return datetime.now(UTC)


class TutoringService:
    """Everything one turn needs, assembled once and shared by both endpoints."""

    def __init__(
        self,
        *,
        client: ModelClient,
        retriever: Retriever,
        repository: InMemoryTutoringRepository,
        template: PromptTemplate,
        is_mock: bool,
        model_name: str = MODEL_NAME,
        timeout_seconds: float = MODEL_TIMEOUT_SECONDS,
        now: Callable[[], datetime] = _utc_now,
        logger: logging.Logger | None = None,
    ) -> None:
        self._client = client
        self._retriever = retriever
        self._repository = repository
        self._template = template
        self._is_mock = is_mock
        self._model_name = model_name
        self._timeout_seconds = timeout_seconds
        self._now = now
        self._logger = logger if logger is not None else logging.getLogger(__name__)

    # --- the stop endpoint --------------------------------------------------

    def check_available(self, session_id: str) -> None:
        """Refuse a second turn in a session, before any streaming begins.

        Called by the router so the refusal can be an ordinary 409. See
        `InMemoryTutoringRepository.assert_can_claim` for why the claim itself
        must not happen here.
        """

        self._repository.assert_can_claim(session_id)

    def stop(self, session_id: str, turn_id: str, request_id: str) -> TurnStatus:
        """Ask a live turn to stop. Returns its status *after* the call.

        Reports what actually happened rather than what was asked for: a stop that
        arrives after the turn completed returns `completed`, because the client
        was already told so and no second terminal frame may follow.
        """

        status = self._repository.request_stop(session_id, turn_id)
        self._logger.info(
            "tutoring stop requested: requestId=%s sessionId=%s turnId=%s status=%s",
            request_id,
            session_id,
            turn_id,
            status,
        )
        return status

    # --- the streaming endpoint ---------------------------------------------

    async def stream_turn(
        self,
        *,
        session_id: str,
        content: str,
        requested_stage: Stage | None,
        course_id: str | None,
        request_id: str,
    ) -> AsyncIterator[str]:
        """Yield the SSE frames for one turn, from `started` to a terminal event.

        `content` is the student's question. It reaches the prompt as a conversation
        turn and is never logged and never rendered into the template, which is
        reserved for the server's own instructions and the retrieved passages.
        """

        record = self._repository.claim_turn(session_id, requested_stage)
        writer = EventStreamWriter(turn_id=record.turn_id)
        started_at = time.perf_counter()
        self._logger.info(
            "tutoring turn started: requestId=%s sessionId=%s turnId=%s stage=%s "
            "promptVersion=%s model=%s isMock=%s",
            request_id,
            session_id,
            record.turn_id,
            record.stage,
            self._template.version,
            self._model_name,
            self._is_mock,
        )

        try:
            yield writer.started(stage=record.stage, is_mock=self._is_mock)

            try:
                chunks = await self._retriever.retrieve(
                    query=content, course_id=course_id, limit=DEFAULT_LIMIT
                )
            except RetrievalError:
                yield self._terminal_failure(
                    writer, record, session_id, request_id, "RETRIEVAL_UNAVAILABLE"
                )
                return

            reader = ModelStreamReader(stop=record.stop, deadline_seconds=self._timeout_seconds)
            async for piece in reader.read(
                self._client, self._model_request(record, content, chunks)
            ):
                yield writer.delta(piece)

            outcome = reader.outcome
            if record.stop.is_set():
                # No `await` has run since the stop signal was read, so this is not
                # a re-check of a stale flag: either the stop was set before the
                # read above finished, in which case the endpoint has already told
                # the client `stopped`, or it was set after and this is the first
                # moment anyone could have noticed.
                yield writer.stopped(_DELIVERABLE_STOP)
                return

            if outcome.kind != "completed":
                yield self._terminal_failure(
                    writer, record, session_id, request_id, _OUTCOME_ERRORS[outcome.kind]
                )
                return

            envelope = outcome.envelope
            if envelope is None:
                yield self._terminal_failure(
                    writer,
                    record,
                    session_id,
                    request_id,
                    "MODEL_OUTPUT_INVALID",
                    _ENVELOPE_FAILURE_REASON,
                )
                return

            response = self._assemble(session_id, record, envelope, chunks, outcome.body)
            self._repository.complete_turn(
                session_id,
                record.turn_id,
                student_content=content,
                assistant_content=response.content,
            )
            self._log_completion(request_id, record, outcome, started_at)
            yield writer.completed(response)
        finally:
            self._record_disconnect(request_id, session_id, record)

    def _record_disconnect(self, request_id: str, session_id: str, record: TurnRecord) -> None:
        """Settle a turn nobody settled: the client went away mid-stream.

        This runs in a `finally` on every path, and it does exactly one thing
        because of that. The disconnect path is a **task cancellation**: this body
        runs while a `CancelledError` unwinds, and any `await` here would be
        cancelled a second time before it finished, leaving the work half done. So
        this is a plain synchronous state transition and nothing else.

        Without it a disconnect leaves the turn `active` -- and an `active` turn is
        what makes its session busy -- so the session would answer 409 to every
        later question for the life of the process, with nobody left to call stop.

        The `active` check is the whole "was anybody else faster" test, and reading
        it off `record` is exact rather than approximate: every settler mutates
        this same object, and none of them can interleave with this line because
        none of them runs inside an `await`. Completed, stopped and errored turns
        are all skipped here, so this never overwrites a real outcome. It also
        cannot raise: an `active` turn pins its session against eviction and its
        own record against eviction, both of which only ever collect settled ones.
        """

        if record.status != "active":
            return

        self._repository.settle_failed_turn(session_id, record.turn_id, "disconnected")
        self._logger.warning(
            "tutoring turn disconnected: requestId=%s sessionId=%s turnId=%s stage=%s",
            request_id,
            session_id,
            record.turn_id,
            record.stage,
        )

    # --- terminal decisions -------------------------------------------------

    def _terminal_failure(
        self,
        writer: EventStreamWriter,
        record: TurnRecord,
        session_id: str,
        request_id: str,
        code: ErrorCode,
        reason: str | None = None,
    ) -> str:
        """The terminal frame for a turn that produced nothing usable.

        Stop first: the student asked to stop, and the stop endpoint has already
        answered `stopped`, so an `error` frame here would contradict it. Nothing
        is settled in that case -- `request_stop` did it.
        """

        if record.stop.is_set():
            return writer.stopped(_DELIVERABLE_STOP)

        self._repository.settle_failed_turn(session_id, record.turn_id, "errored")
        self._logger.warning(
            "tutoring turn failed: requestId=%s turnId=%s code=%s reason=%s",
            request_id,
            record.turn_id,
            code,
            reason,
        )
        details: dict[str, object] = {}
        if reason is not None:
            details["reason"] = reason
        return writer.error(
            ErrorBody(
                code=code,
                message=_ERROR_MESSAGES[code],
                requestId=request_id,
                details=details,
            )
        )

    # --- assembly -----------------------------------------------------------

    def _model_request(
        self, record: TurnRecord, content: str, chunks: Sequence[RetrievedChunk]
    ) -> ModelRequest:
        """Everything the model is allowed to see for this turn.

        Two things are load-bearing. The stage reaches the prompt through
        `render`, never as a field -- the adapter's field list has no place for
        it, and a model that could see the ladder could skip rungs the server
        meant to withhold. And the student's new question is appended to the
        history rather than substituted into the prompt, so it arrives as data to
        answer rather than as text spliced into the instructions.
        """

        return ModelRequest(
            request_id="-",
            prompt_version=self._template.version,
            model_name=self._model_name,
            system_prompt=self._template.render(stage=record.stage, chunks=chunks),
            turns=(
                *self._repository.history(record.session_id),
                Turn(role="student", content=content),
            ),
            retrieved_chunks=chunks,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            temperature=TEMPERATURE,
            timeout_seconds=self._timeout_seconds,
        )

    def _assemble(
        self,
        session_id: str,
        record: TurnRecord,
        envelope: ResponseEnvelope,
        chunks: Sequence[RetrievedChunk],
        content: str,
    ) -> TutoringResponse:
        """The `completed` payload from the model's envelope plus server state.

        `content` is the concatenated deltas, so M2 can swap its streaming text for
        this object without the two disagreeing by a character
        (`samples/05-sse-stream.txt:26-27`).
        """

        citations = _allowed_citations(envelope, chunks)
        return TutoringResponse(
            turnId=record.turn_id,
            sessionId=session_id,
            stage=record.stage,
            content=content,
            citations=citations,
            hasEvidence=bool(citations),
            followUps=list(envelope.follow_ups),
            emotion=envelope.emotion,
            action=envelope.action,
            isMock=self._is_mock,
            promptVersion=self._template.version,
            createdAt=self._now(),
        )

    def _log_completion(
        self, request_id: str, record: TurnRecord, outcome: ModelOutcome, started_at: float
    ) -> None:
        """Log identifiers and counters, never content.

        No student question, no answer text, no prompt (`docs/code-standards.md:105`).
        The token counts are the only thing here whose value is not an identifier,
        and they are the point of logging a model call at all.
        """

        usage = outcome.usage
        self._logger.info(
            "tutoring turn completed: requestId=%s sessionId=%s turnId=%s stage=%s "
            "promptVersion=%s model=%s inputTokens=%s outputTokens=%s durationMs=%d",
            request_id,
            record.session_id,
            record.turn_id,
            record.stage,
            self._template.version,
            self._model_name,
            usage.input_tokens if usage is not None else None,
            usage.output_tokens if usage is not None else None,
            int((time.perf_counter() - started_at) * 1000),
        )


def _allowed_citations(
    envelope: ResponseEnvelope, chunks: Sequence[RetrievedChunk]
) -> list[Citation]:
    """The model's claimed labels, filtered to what retrieval actually found.

    Iterating the allow-list rather than the model's list does two things: a label
    the server never issued is dropped, and the order is the server's, so a model
    that repeats or reshuffles its claims cannot change the output. Dropping an
    unissued label is the contract's existing semantics, unlike dropping a
    too-long `followUps` entry, which the envelope rejects outright.
    """

    claimed = set(envelope.citations)
    return [
        Citation(
            citationId=label,
            documentId=chunk.document_id,
            documentTitle=chunk.document_title,
            pageNumber=chunk.page_number,
            snippet=chunk.text,
        )
        for label, chunk in zip(citation_labels(chunks), chunks, strict=True)
        if label in claimed
    ]
