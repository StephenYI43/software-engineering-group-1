"""Reading the model, and writing the SSE frames.

Two objects, one job each.

`EventStreamWriter` is the **only** thing in the process that turns an event into
bytes, and it owns `seq`. That is the whole mechanism behind "exactly one terminal
event, and its `seq` is the maximum": one writer, one counter, and a closed flag
that raises rather than dropping a second terminal frame on the floor. Dropping it
silently is the tempting alternative and it is the wrong one -- it would make
"two terminal events" a class of bug that no test can ever see.

`ModelStreamReader` races one model call against the stop signal and the deadline,
and hides how the call ended behind a closed set of outcomes, so the service never
has to know what a provider raises.

**Cancellation is the client-disconnect signal, and it is handled by not handling
it.** The reader lets `CancelledError` through untouched: there is nothing useful
to await while being cancelled (any `await` is itself cancelled a moment later),
so the reader does no cleanup at all on that path. The upstream iterator is closed
on every path the reader *does* own -- normal end, stop, deadline, model failure --
because on those the reader is not itself being cancelled.
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal

from app.domains.tutoring.adapters import (
    Finished,
    ModelChunk,
    ModelClient,
    ModelRequest,
    Usage,
)
from app.domains.tutoring.envelope import (
    BodyEnvelopeSplitter,
    EnvelopeFailure,
    ResponseEnvelope,
)
from app.domains.tutoring.schemas import (
    CompletedEvent,
    DeltaEvent,
    ErrorBody,
    ErrorEvent,
    StartedEvent,
    StoppedEvent,
    StopReason,
    StreamEvent,
    TutoringResponse,
)
from app.domains.tutoring.stages import Stage

__all__ = [
    "EventStreamWriter",
    "ModelOutcome",
    "ModelRefusedError",
    "ModelStreamReader",
    "ModelTimeoutError",
    "OutcomeKind",
    "StreamInvariantError",
]

#: How one model call ended. Closed on purpose: every member has exactly one
#: place in the service that turns it into a terminal event, and adding a member
#: is a deliberate act rather than a new `except` clause someone forgot to test.
OutcomeKind = Literal["completed", "stopped", "timed_out", "refused", "failed"]


class StreamInvariantError(RuntimeError):
    """The writer was asked to do something the contract forbids.

    Raised rather than absorbed. Every one of these is a bug in the caller, and a
    bug that the client would otherwise experience as a protocol violation it has
    to detect itself (`sse-events.md:15-19` puts that duty on M2).
    """


class ModelRefusedError(RuntimeError):
    """The model declined to answer.

    Declared on the domain side of the adapter seam, so a provider-specific error
    can be translated into it where the provider lives and the service can stay
    ignorant of which provider it is talking to.
    """


class ModelTimeoutError(RuntimeError):
    """The model call exceeded its deadline, as reported by the client itself.

    Distinct from the reader's own deadline only in who noticed it. Both become
    `MODEL_TIMEOUT`: the client's is the one that sees a stalled connection, the
    reader's is the backstop.
    """


@dataclass(frozen=True, slots=True)
class ModelOutcome:
    """What one model call produced, and how it ended.

    `body` is the concatenation of every piece handed to a `delta` and nothing
    else, which is what lets `completed.response.content` be assembled from it
    without a second pass. `envelope` and `envelope_failure` are both ignored
    unless `kind` is `completed`.
    """

    kind: OutcomeKind
    body: str
    envelope: ResponseEnvelope | None
    envelope_failure: EnvelopeFailure | None
    usage: Usage | None
    stop_reason: StopReason | None
    cause: BaseException | None = None


class _Stopped(Exception):
    """Internal: the stop signal won the race."""


class _Deadline(Exception):
    """Internal: the deadline won the race."""


async def _aclose(upstream: AsyncIterator[ModelChunk]) -> None:
    """Close the upstream iterator if it can be closed.

    The seam promises an `AsyncIterator`, which has no `aclose`; every
    implementation in this repository is an async generator, which does. Guarded
    rather than asserted, so a future adapter written as a hand-rolled iterator is
    not a crash on the last frame.
    """

    close = getattr(upstream, "aclose", None)
    if close is not None:
        await close()


class ModelStreamReader:
    """One model call, read to the end or until something stops it."""

    def __init__(self, *, stop: asyncio.Event, deadline_seconds: float) -> None:
        self._stop = stop
        self._deadline_seconds = deadline_seconds
        self._kind: OutcomeKind = "completed"
        self._stop_reason: StopReason | None = None
        self._cause: BaseException | None = None
        self._usage: Usage | None = None
        self._splitter = BodyEnvelopeSplitter()

    async def read(self, client: ModelClient, request: ModelRequest) -> AsyncIterator[str]:
        """Yield body text as it arrives, then stop. See `outcome` for how it ended.

        Every piece yielded here is prose destined for a `delta`. The response
        envelope is withheld by the splitter and never appears in one, which is
        the contract's rule that structured fields ride only a terminal event
        (`sse-events.md:69-70`) -- not a convention, but an invariant that this
        function is the only place able to break.
        """

        stop_waiter = asyncio.ensure_future(self._stop.wait())
        upstream = client.generate(request)
        deadline = asyncio.get_running_loop().time() + self._deadline_seconds

        try:
            while True:
                chunk = await self._next(upstream, stop_waiter, deadline)
                if chunk is None or isinstance(chunk, Finished):
                    break
                if isinstance(chunk, Usage):
                    self._usage = chunk
                    continue
                for piece in self._splitter.feed(chunk.text):
                    yield piece
        except _Stopped:
            self._kind = "stopped"
            self._stop_reason = "client_stop"
        except _Deadline:
            self._kind = "timed_out"
        except ModelRefusedError as exc:
            self._kind = "refused"
            self._cause = exc
        except ModelTimeoutError as exc:
            self._kind = "timed_out"
            self._cause = exc
        except asyncio.CancelledError:
            # The client is gone. Await nothing here: any await would be cancelled
            # too, and a half-run cleanup is worse than none. The abandoned read is
            # left to the loop; the service records the turn as `disconnected`.
            raise
        except Exception as exc:
            self._kind = "failed"
            self._cause = exc

        await _aclose(upstream)
        stop_waiter.cancel()
        await asyncio.gather(stop_waiter, return_exceptions=True)

    @property
    def outcome(self) -> ModelOutcome:
        """How the call ended. Only meaningful once `read` is exhausted."""

        finished = self._splitter.finish()
        return ModelOutcome(
            kind=self._kind,
            body=finished.body,
            envelope=finished.envelope,
            envelope_failure=finished.failure,
            usage=self._usage,
            stop_reason=self._stop_reason,
            cause=self._cause,
        )

    async def _next(
        self,
        upstream: AsyncIterator[ModelChunk],
        stop_waiter: asyncio.Task[bool],
        deadline: float,
    ) -> ModelChunk | None:
        """The next chunk, or `None` when the upstream stream ended.

        Raises `_Stopped` or `_Deadline` rather than returning a sentinel for
        them, because both are control flow the caller must not be able to ignore.
        """

        read = asyncio.ensure_future(anext(upstream, None))
        remaining = deadline - asyncio.get_running_loop().time()
        try:
            done, _ = await asyncio.wait(
                {read, stop_waiter},
                timeout=max(remaining, 0),
                return_when=asyncio.FIRST_COMPLETED,
            )
        except asyncio.CancelledError:
            # Our own read is abandoned. Cancel it without awaiting, because we
            # are the one being cancelled.
            read.cancel()
            raise
        if not done:
            await self._abandon(read)
            raise _Deadline
        if stop_waiter in done:
            # User intent outranks a chunk that landed in the same tick: the
            # student asked to stop, and a half answer is not a completion
            # (`sse-events.md:100-107`).
            await self._abandon(read)
            raise _Stopped
        return read.result()

    async def _abandon(self, read: asyncio.Task[ModelChunk | None]) -> None:
        """Cancel a read that lost the race, and wait for it to unwind.

        Awaiting is safe here and only here: on the stop and deadline paths the
        reader is not itself being cancelled, so the unwind really runs. Waiting
        for it is what leaves the upstream generator quiescent -- cancelling the
        `anext` throws into the generator at its suspension point, which finalises
        it. Not waiting would leave a stray task writing into a stream nobody is
        reading.
        """

        read.cancel()
        await asyncio.gather(read, return_exceptions=True)


class EventStreamWriter:
    """Turns events into SSE frames for exactly one turn.

    Frames are `event:` + one-line-JSON `data:` + a blank line
    (`sse-events.md:6-8`). The blank line is not decoration: it is the frame
    boundary, and M2 splits on it.
    """

    def __init__(self, *, turn_id: str) -> None:
        self._turn_id = turn_id
        self._seq = 0
        self._closed = False
        self._opened = False

    @property
    def seq(self) -> int:
        """The sequence number of the last frame written; `0` before `started`."""

        return self._seq

    @property
    def closed(self) -> bool:
        """Whether a terminal frame has been written. After that, nothing may be."""

        return self._closed

    def started(self, *, stage: Stage, is_mock: bool) -> str:
        """Always first, always `seq = 1` (`sse-events.md:29-31`)."""

        if self._opened:
            raise StreamInvariantError("started was already written")
        self._opened = True
        return self._write(
            "started",
            StartedEvent(seq=self._take(), turnId=self._turn_id, stage=stage, isMock=is_mock),
        )

    def delta(self, text: str) -> str:
        """One increment of prose. Carries no structured field, by construction."""

        if not self._opened:
            raise StreamInvariantError("delta was written before started")
        return self._write(
            "delta", DeltaEvent(seq=self._take(), turnId=self._turn_id, textDelta=text)
        )

    def completed(self, response: TutoringResponse) -> str:
        """The only frame carrying the assembled response (`sse-events.md:72-85`)."""

        if response.turn_id != self._turn_id:
            raise StreamInvariantError(
                f"response is for {response.turn_id}, this stream is {self._turn_id}"
            )
        return self._terminate(
            "completed",
            CompletedEvent(seq=self._take(), turnId=self._turn_id, response=response),
        )

    def stopped(self, reason: StopReason) -> str:
        """User intent, or a dropped connection -- not a system failure."""

        return self._terminate(
            "stopped", StoppedEvent(seq=self._take(), turnId=self._turn_id, reason=reason)
        )

    def error(self, body: ErrorBody) -> str:
        """A system failure (`sse-events.md:109-141`)."""

        return self._terminate(
            "error", ErrorEvent(seq=self._take(), turnId=self._turn_id, error=body)
        )

    def _take(self) -> int:
        """Claim the next `seq`.

        The closed check lives here rather than in the five callers, so "no event
        after the terminal event" is one branch that one test covers instead of
        five that four of them would forget.
        """

        if self._closed:
            raise StreamInvariantError("the stream already has a terminal event")
        self._seq += 1
        return self._seq

    def _terminate(self, name: str, event: StreamEvent) -> str:
        frame = self._write(name, event)
        self._closed = True
        return frame

    def _write(self, name: str, event: StreamEvent) -> str:
        return f"event: {name}\ndata: {event.model_dump_json(by_alias=True)}\n\n"
