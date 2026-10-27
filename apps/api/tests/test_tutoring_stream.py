"""The SSE writer and the model reader (Issue #59).

The writer's tests are mostly about what it *refuses* to do. "Exactly one terminal
event" and "nothing after it" are enforced by raising, and raising is only worth
anything if something asserts it -- so each refusal has a test, and the frames
themselves are checked against the shape `samples/05-sse-stream.txt` uses.

The reader's tests are about the four ways a model call can be cut short, and one
of them is checked by its effect rather than its report: after a stop, the upstream
generator's `finally` must have run. Reporting `stopped` while leaving the upstream
writing into nothing is the bug that would cost money against a real model.
"""

import asyncio
import json
from collections.abc import AsyncIterator

import pytest

from app.domains.tutoring.adapters import (
    Finished,
    ModelChunk,
    ModelRequest,
    RetrievedChunk,
    TextDelta,
    Usage,
)
from app.domains.tutoring.envelope import RESPONSE_CLOSE, RESPONSE_OPEN
from app.domains.tutoring.schemas import Citation, ErrorBody, TutoringResponse
from app.domains.tutoring.stream import (
    EventStreamWriter,
    ModelRefusedError,
    ModelStreamReader,
    ModelTimeoutError,
    StreamInvariantError,
)

_TURN = "turn_7f3a9c21"
_CHUNK = RetrievedChunk(
    document_id="doc_9a2f4c",
    document_title="高等数学-上册-第1章.pdf",
    page_number=12,
    text="设函数 f(x) 在点 a 的某个去心邻域内有定义。",
)


def _request() -> ModelRequest:
    return ModelRequest(
        request_id="req_8d1f0c33",
        prompt_version="guided-tutoring.v1",
        model_name="mock",
        system_prompt="prompt",
        turns=(),
        retrieved_chunks=(_CHUNK,),
        max_output_tokens=1024,
        temperature=0.0,
        timeout_seconds=30.0,
    )


def _response(turn_id: str = _TURN) -> TutoringResponse:
    return TutoringResponse(
        turn_id=turn_id,
        session_id="sess_4b8d1e02",
        stage="thought",
        content="正文",
        citations=[
            Citation(
                citation_id="c1",
                document_id="doc_9a2f4c",
                document_title="高等数学-上册-第1章.pdf",
                page_number=12,
                snippet="设函数 f(x) 在点 a 的某个去心邻域内有定义。",
            )
        ],
        has_evidence=True,
        follow_ups=["下一个问题？"],
        emotion="encouraging",
        action="nod",
        is_mock=True,
        prompt_version="guided-tutoring.v1",
        created_at="2026-09-14T08:00:00Z",  # type: ignore[arg-type]
    )


def _parse(frame: str) -> tuple[str, dict[str, object]]:
    """Split one frame into its event name and its decoded `data:` object."""

    lines = frame.split("\n")
    assert frame.endswith("\n\n"), "a frame must end with the blank line M2 splits on"
    assert lines[0].startswith("event: ")
    assert lines[1].startswith("data: ")
    return lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: "))


# --- the writer's frames ----------------------------------------------------


def test_started_is_the_first_frame_and_carries_seq_one() -> None:
    writer = EventStreamWriter(turn_id=_TURN)

    name, payload = _parse(writer.started(stage="thought", is_mock=True))

    assert name == "started"
    assert payload == {"seq": 1, "turnId": _TURN, "stage": "thought", "isMock": True}


def test_deltas_take_consecutive_sequence_numbers() -> None:
    writer = EventStreamWriter(turn_id=_TURN)
    writer.started(stage="thought", is_mock=True)

    numbers = [_parse(writer.delta(text))[1]["seq"] for text in ("一", "二", "三")]

    assert numbers == [2, 3, 4]


def test_a_delta_frame_carries_prose_and_nothing_structured() -> None:
    """`sse-events.md:69-70`: structured fields ride only a terminal event.

    Checked on the frame rather than on the schema, because this is the layer where
    a stray field would actually reach M2.
    """

    writer = EventStreamWriter(turn_id=_TURN)
    writer.started(stage="thought", is_mock=True)

    _, payload = _parse(writer.delta("我们先不急着写出定义。"))

    assert payload == {"seq": 2, "turnId": _TURN, "textDelta": "我们先不急着写出定义。"}


def test_the_terminal_frame_has_the_highest_sequence_number() -> None:
    writer = EventStreamWriter(turn_id=_TURN)
    frames = [
        writer.started(stage="thought", is_mock=True),
        writer.delta("一"),
        writer.delta("二"),
        writer.completed(_response()),
    ]

    names = [_parse(frame)[0] for frame in frames]
    numbers = [_parse(frame)[1]["seq"] for frame in frames]

    assert names == ["started", "delta", "delta", "completed"]
    assert numbers == [1, 2, 3, 4]
    assert numbers[-1] == max(numbers)


def test_every_frame_keeps_the_same_turn_id() -> None:
    writer = EventStreamWriter(turn_id=_TURN)
    frames = [
        writer.started(stage="thought", is_mock=True),
        writer.delta("一"),
        writer.stopped("client_stop"),
    ]

    assert {_parse(frame)[1]["turnId"] for frame in frames} == {_TURN}


@pytest.mark.parametrize(
    "frame_factory",
    [
        lambda writer: writer.completed(_response()),
        lambda writer: writer.stopped("client_stop"),
        lambda writer: writer.error(ErrorBody(code="TURN_ABORTED", message="m", requestId="req_1")),
    ],
    ids=["completed", "stopped", "error"],
)
def test_writing_a_second_terminal_frame_is_refused(frame_factory: object) -> None:
    """The invariant the whole design rests on. Silently dropping the second frame
    would make "two terminal events" a bug no test could ever observe."""

    writer = EventStreamWriter(turn_id=_TURN)
    writer.started(stage="thought", is_mock=True)
    writer.stopped("client_stop")

    with pytest.raises(StreamInvariantError):
        frame_factory(writer)  # type: ignore[operator]


def test_a_delta_after_the_terminal_frame_is_refused() -> None:
    """`sse-events.md:38`: nothing follows the terminal event."""

    writer = EventStreamWriter(turn_id=_TURN)
    writer.started(stage="thought", is_mock=True)
    writer.completed(_response())

    with pytest.raises(StreamInvariantError):
        writer.delta("迟到的正文")


def test_a_delta_before_started_is_refused() -> None:
    writer = EventStreamWriter(turn_id=_TURN)

    with pytest.raises(StreamInvariantError):
        writer.delta("过早的正文")


def test_starting_twice_is_refused() -> None:
    writer = EventStreamWriter(turn_id=_TURN)
    writer.started(stage="thought", is_mock=True)

    with pytest.raises(StreamInvariantError):
        writer.started(stage="thought", is_mock=True)


def test_a_response_for_another_turn_is_refused() -> None:
    """Otherwise `completed.response.turnId` could disagree with every other frame
    in the stream, and M2 correlates on exactly that field."""

    writer = EventStreamWriter(turn_id=_TURN)
    writer.started(stage="thought", is_mock=True)

    with pytest.raises(StreamInvariantError):
        writer.completed(_response(turn_id="turn_somewhere_else"))


def test_the_writer_reports_its_progress() -> None:
    writer = EventStreamWriter(turn_id=_TURN)
    assert (writer.seq, writer.closed) == (0, False)

    writer.started(stage="thought", is_mock=True)
    assert (writer.seq, writer.closed) == (1, False)

    writer.completed(_response())
    assert (writer.seq, writer.closed) == (2, True)


# --- the reader's outcomes --------------------------------------------------


class _ScriptedClient:
    """Yields a fixed script. Optionally raises instead of finishing."""

    def __init__(self, *chunks: ModelChunk, error: BaseException | None = None) -> None:
        self._chunks = chunks
        self._error = error
        self.closed = False

    async def generate(self, request: ModelRequest) -> AsyncIterator[ModelChunk]:
        try:
            for chunk in self._chunks:
                yield chunk
            if self._error is not None:
                raise self._error
        finally:
            self.closed = True

    async def aclose(self) -> None:
        return None


class _GatedClient:
    """Yields one chunk, announces it, then blocks until released.

    The announcement is what makes a mid-stream stop deterministic: the test waits
    for `reached` rather than sleeping and hoping the first chunk got through.
    """

    #: Longer than the splitter's look-back window on purpose, so that part of it
    #: really is emitted before the gate closes. With a shorter first chunk the
    #: reader would legitimately emit nothing and the test would prove nothing
    #: about a partial stream.
    FIRST = "第一段：设函数 f(x) 在点 a 的某个去心邻域内有定义。"
    SECOND = "第二段：导数的定义要从这个极限说起。"

    def __init__(self) -> None:
        self.reached = asyncio.Event()
        self.gate = asyncio.Event()
        self.closed = False

    async def generate(self, request: ModelRequest) -> AsyncIterator[ModelChunk]:
        try:
            yield TextDelta(text=self.FIRST)
            self.reached.set()
            await self.gate.wait()
            yield TextDelta(text=self.SECOND)
        finally:
            self.closed = True

    async def aclose(self) -> None:
        return None


class _PlainIterator:
    """An async iterator that is *not* an async generator, so it has no `aclose`.

    Handed out by `_PlainClient` to prove the reader tolerates the seam's declared
    type rather than assuming every implementation is a generator.
    """

    def __init__(self, chunks: list[ModelChunk]) -> None:
        self._chunks = chunks

    def __aiter__(self) -> "_PlainIterator":
        return self

    async def __anext__(self) -> ModelChunk:
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


class _PlainClient:
    def __init__(self, *chunks: ModelChunk) -> None:
        self._chunks = list(chunks)

    def generate(self, request: ModelRequest) -> AsyncIterator[ModelChunk]:
        return _PlainIterator(self._chunks)

    async def aclose(self) -> None:
        return None


def _drain(client: object, *, reader: ModelStreamReader) -> list[str]:
    async def scenario() -> list[str]:
        return [piece async for piece in reader.read(client, _request())]  # type: ignore[arg-type]

    return asyncio.run(scenario())


def _reader(*, stop: asyncio.Event | None = None, deadline: float = 30.0) -> ModelStreamReader:
    return ModelStreamReader(
        stop=stop if stop is not None else asyncio.Event(), deadline_seconds=deadline
    )


#: A complete model output: one line of prose, then the envelope. Split across
#: three chunks here so the reader has to reassemble a marker rather than being
#: handed one whole.
_BODY = "正文。\n"
_ENVELOPE_JSON = '{"citations":[],"followUps":[],"emotion":"neutral","action":"idle"}'


def test_a_normal_read_reports_completion_and_keeps_usage() -> None:
    reader = _reader()
    client = _ScriptedClient(
        TextDelta(text="正文。"),
        TextDelta(text=f"\n{RESPONSE_OPEN}{_ENVELOPE_JSON}"),
        TextDelta(text=RESPONSE_CLOSE),
        Usage(input_tokens=10, output_tokens=4),
        Finished(stop_reason="stop"),
    )

    pieces = _drain(client, reader=reader)
    outcome = reader.outcome

    assert "".join(pieces) == _BODY
    assert outcome.kind == "completed"
    assert outcome.body == _BODY
    assert outcome.envelope_failure is None
    assert outcome.envelope is not None
    assert outcome.envelope.emotion == "neutral"
    assert outcome.usage == Usage(input_tokens=10, output_tokens=4)


def test_the_envelope_never_reaches_the_caller_as_a_piece() -> None:
    """What the caller yields goes straight into a `delta`."""

    reader = _reader()
    client = _ScriptedClient(
        TextDelta(
            text='正文。\n<<<RESPONSE_ENVELOPE>>>{"citations":[],"followUps":[],'
            '"emotion":"neutral","action":"idle"}<<<END_RESPONSE_ENVELOPE>>>'
        ),
    )

    pieces = _drain(client, reader=reader)

    assert "".join(pieces) == "正文。\n"
    assert all(RESPONSE_OPEN not in piece for piece in pieces)


def test_a_stop_before_the_first_chunk_ends_the_read_immediately() -> None:
    stop = asyncio.Event()
    stop.set()
    reader = _reader(stop=stop)
    client = _ScriptedClient(TextDelta(text="不该出现"))

    pieces = _drain(client, reader=reader)

    assert pieces == []
    assert reader.outcome.kind == "stopped"
    assert reader.outcome.body == ""


def test_a_stop_mid_stream_closes_the_upstream() -> None:
    """The `finally` check is the point: reporting `stopped` while leaving the
    upstream writing into nothing costs money against a real model."""

    async def scenario() -> tuple[list[str], str, bool]:
        client = _GatedClient()
        stop = asyncio.Event()
        reader = _reader(stop=stop)

        async def consume() -> list[str]:
            return [piece async for piece in reader.read(client, _request())]

        task = asyncio.ensure_future(consume())
        await client.reached.wait()

        stop.set()
        pieces = await task

        return pieces, reader.outcome.kind, client.closed

    pieces, kind, closed = asyncio.run(scenario())

    assert pieces, "the look-back window must not hold back a whole first chunk"
    assert _GatedClient.SECOND not in "".join(pieces)
    assert kind == "stopped"
    assert closed is True


def test_a_stop_mid_stream_reports_the_prose_it_already_emitted() -> None:
    """`stopped` carries no content, so the partial text is only ever what the
    client already has -- the server must not pretend to complete it.

    The coupling worth pinning is `outcome.body == "".join(deltas)`, not any
    particular split: it is what lets the same reader serve both the `completed`
    content and the `stopped` partial, and a look-back window that held back
    *different* text than it reported would break `completed.response.content`
    without breaking any single assertion on a delta.
    """

    async def consume(reader: ModelStreamReader, client: _GatedClient) -> list[str]:
        return [piece async for piece in reader.read(client, _request())]

    async def run() -> tuple[list[str], str]:
        client = _GatedClient()
        stop = asyncio.Event()
        reader = _reader(stop=stop)
        task = asyncio.ensure_future(consume(reader, client))
        await client.reached.wait()
        stop.set()
        pieces = await task
        return pieces, reader.outcome.body

    pieces, body = asyncio.run(run())

    assert "".join(pieces) == body
    assert body and _GatedClient.FIRST.startswith(body)


async def _collect(reader: ModelStreamReader, client: object) -> None:
    async for _ in reader.read(client, _request()):  # type: ignore[arg-type]
        pass


def test_a_deadline_is_reported_as_a_timeout() -> None:
    async def scenario() -> str:
        client = _GatedClient()
        reader = _reader(deadline=0.02)
        task = asyncio.ensure_future(_collect(reader, client))
        await task
        return reader.outcome.kind

    assert asyncio.run(scenario()) == "timed_out"


def test_a_model_that_refuses_is_reported_as_refused() -> None:
    reader = _reader()
    client = _ScriptedClient(TextDelta(text="一"), error=ModelRefusedError("no"))

    _drain(client, reader=reader)

    assert reader.outcome.kind == "refused"
    assert isinstance(reader.outcome.cause, ModelRefusedError)


def test_a_model_that_times_out_itself_is_reported_as_a_timeout() -> None:
    """Distinct from the reader's own deadline only in who noticed it."""

    reader = _reader()
    client = _ScriptedClient(error=ModelTimeoutError("slow"))

    _drain(client, reader=reader)

    assert reader.outcome.kind == "timed_out"


def test_an_unexpected_failure_is_reported_as_failed() -> None:
    reader = _reader()
    client = _ScriptedClient(error=RuntimeError("provider exploded"))

    _drain(client, reader=reader)

    assert reader.outcome.kind == "failed"
    assert isinstance(reader.outcome.cause, RuntimeError)


def test_an_upstream_without_aclose_is_still_read() -> None:
    """The seam promises an `AsyncIterator`, and not every implementation is a
    generator; the reader must not assume `aclose` exists."""

    reader = _reader()
    client = _PlainClient(
        TextDelta(text=f"{_BODY}{RESPONSE_OPEN}{_ENVELOPE_JSON}{RESPONSE_CLOSE}"),
        Finished(stop_reason="stop"),
    )

    pieces = _drain(client, reader=reader)

    assert "".join(pieces) == _BODY
    assert reader.outcome.kind == "completed"
    assert reader.outcome.envelope is not None


def test_an_ended_upstream_with_no_finished_chunk_completes() -> None:
    """Exhaustion is an ending too: a client that just stops yielding without a
    `Finished` chunk is not an error, and the body it produced is still valid."""

    reader = _reader()
    client = _PlainClient(TextDelta(text=f"{_BODY}{RESPONSE_OPEN}{_ENVELOPE_JSON}{RESPONSE_CLOSE}"))

    pieces = _drain(client, reader=reader)

    assert "".join(pieces) == _BODY
    assert reader.outcome.kind == "completed"
    assert reader.outcome.envelope is not None


def test_prose_held_by_the_look_back_window_is_lost_when_no_envelope_arrives() -> None:
    """A consequence worth pinning rather than discovering later.

    The splitter always holds back `len(RESPONSE_OPEN) - 1` characters and never
    flushes them (`envelope.py:106-107`), so an output with no envelope at all can
    emit *nothing*: the whole body is inside the window. That is only safe because
    the service turns a `missing` envelope into `MODEL_OUTPUT_INVALID` and never
    uses `body`. Start trusting `body` on this path -- to keep a student's partial
    answer, say -- and the tail of every envelope-less answer disappears, here is
    where that shows up, and `completed.response.content` would stop matching the
    deltas that were already sent.
    """

    reader = _reader()
    client = _ScriptedClient(TextDelta(text="短正文。"), Finished(stop_reason="stop"))

    pieces = _drain(client, reader=reader)

    assert pieces == []
    assert reader.outcome.kind == "completed"
    assert reader.outcome.envelope is None
    assert reader.outcome.envelope_failure == "missing"


def test_a_cancelled_read_lets_the_cancellation_through() -> None:
    """Client disconnect arrives as task cancellation, and the reader must not
    swallow it -- the service distinguishes it from a stop by exactly this."""

    async def scenario() -> bool:
        client = _GatedClient()
        reader = _reader()
        task = asyncio.ensure_future(_collect(reader, client))
        await client.reached.wait()

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return True
        return False

    assert asyncio.run(scenario()) is True
