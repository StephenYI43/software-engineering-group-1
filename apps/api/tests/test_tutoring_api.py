"""The two endpoints over HTTP (Issue #59).

Everything here goes through the real application: the middleware that mints the
request id, the router, and a streaming response. The point is the seams that only
exist on the wire -- that the body really is `text/event-stream`, that a refusal
before the first byte is an ordinary JSON error with a status code, that a failure
after it is an in-band event carrying the same request id as the header, and that
the stop endpoint can end a stream that is running right now.

The stop test needs two threads, and not by preference. This version of
`TestClient` buffers the whole response body, so a test cannot hold a live stream
open and post to a second endpoint from the same thread; the stream and the stop
have to be in flight at once. The threads are joined with a timeout so a failure
is a failed assertion rather than a hung CI job.

The disconnect is tested at the ASGI level and **by cancelling the app task**,
because that is what a dropped connection actually is here: a real client's
`http.disconnect` message is never read (the app's middleware replaces the
downstream `receive`), so a test that fed one would be asserting on a code path
that does not run. The `receive` below still returns one, and the comment says
what that is worth.
"""

import asyncio
import json
import threading
from collections.abc import AsyncIterator, Sequence
from contextlib import suppress
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.domains.tutoring.adapters import MockModelClient, ModelChunk, ModelRequest, TextDelta
from app.domains.tutoring.envelope import RESPONSE_CLOSE, RESPONSE_OPEN
from app.domains.tutoring.prompt_renderer import load_prompt_template
from app.domains.tutoring.repository import InMemoryTutoringRepository
from app.domains.tutoring.retrieval import StaticRetriever
from app.domains.tutoring.service import TutoringService
from app.main import create_app

_SESSION = "sess_5c1e7a93"
_MESSAGES = f"/api/v1/tutoring/sessions/{_SESSION}/messages"
_STOP = f"/api/v1/tutoring/sessions/{_SESSION}/turns/{{turn_id}}/stop"
_QUESTION = "什么是函数的极限？"
_ENVELOPE = (
    '{"citations":["c1"],"followUps":["那 ε 和 δ 哪个先给定？"],'
    '"emotion":"encouraging","action":"nod"}'
)
_OUTPUT = (
    "我们先不急着写出定义。你想一想，说「当 x 靠近 a 时 f(x) 趋近 L」"
    "，这里的「靠近」怎么换成可以检验的说法？"
    f"\n{RESPONSE_OPEN}{_ENVELOPE}{RESPONSE_CLOSE}"
)


class _GatedClient:
    """Streams one chunk, hands control over, then waits to be stopped.

    `reached` is a `threading.Event` because the thread waiting on it is not the
    one running the event loop: the request is in flight on the TestClient's portal
    thread, and the stop is posted from the test's own thread.
    """

    def __init__(self, reached: threading.Event | None = None) -> None:
        self.reached = reached if reached is not None else threading.Event()

    async def generate(self, request: ModelRequest) -> AsyncIterator[ModelChunk]:
        yield TextDelta(text=_OUTPUT)
        self.reached.set()
        # Nothing releases this: the only things that can end the turn now are a
        # stop and a cancelled client.
        await asyncio.Event().wait()

    async def aclose(self) -> None:
        return None


def _service(
    *,
    client: object | None = None,
    repository: InMemoryTutoringRepository | None = None,
    retriever: object | None = None,
) -> TutoringService:
    return TutoringService(
        client=client if client is not None else MockModelClient(envelope=True),  # type: ignore[arg-type]
        retriever=retriever if retriever is not None else StaticRetriever(),  # type: ignore[arg-type]
        repository=repository if repository is not None else InMemoryTutoringRepository(),
        template=load_prompt_template(),
        is_mock=True,
        now=lambda: datetime(2026, 9, 14, 8, 0, 0, tzinfo=UTC),
    )


def _app(**kwargs: object) -> object:
    """An app whose tutoring service is the one the test built.

    The router reads `app.state.tutoring_service` before it builds one, so
    assigning here is the supported way to drive the endpoints with a fake model
    -- the same seam a later slice will use for the real one.
    """

    application = create_app()
    application.state.tutoring_service = _service(**kwargs)  # type: ignore[arg-type]
    return application


def _frames(body: str) -> list[tuple[str, dict[str, object]]]:
    """Every SSE frame in a response body, in order.

    Sliced on the blank line, which is the frame boundary `sse-events.md:6-8`
    defines -- a client that got this wrong would render half a frame.
    """

    parsed: list[tuple[str, dict[str, object]]] = []
    for block in body.split("\n\n"):
        if not block:
            continue
        lines = block.split("\n")
        assert len(lines) == 2, f"a frame is an event line and a data line: {block!r}"
        assert lines[0].startswith("event: ")
        assert lines[1].startswith("data: ")
        # One line of JSON, never pretty-printed: a newline inside `data:` would
        # split one event into two frame boundaries.
        payload = json.loads(lines[1].removeprefix("data: "))
        parsed.append((lines[0].removeprefix("event: "), payload))
    return parsed


def _names(frames: Sequence[tuple[str, dict[str, object]]]) -> list[str]:
    return [name for name, _ in frames]


# --- the streaming endpoint -------------------------------------------------


def test_a_question_is_answered_as_an_event_stream() -> None:
    with TestClient(_app()) as client:
        response = client.post(_MESSAGES, json={"content": _QUESTION})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-store"
    # A buffering proxy would release the whole answer at once, which is the one
    # thing the transport exists to avoid.
    assert response.headers["x-accel-buffering"] == "no"


def test_the_body_is_frames_a_client_can_read_one_at_a_time() -> None:
    with TestClient(_app()) as client:
        body = client.post(_MESSAGES, json={"content": _QUESTION}).text

    assert body.endswith("\n\n"), "the last frame needs its terminating blank line"

    frames = _frames(body)
    names = _names(frames)
    assert names[0] == "started"
    assert names[-1] == "completed"
    assert set(names) == {"started", "delta", "completed"}
    # The mock's script is seven pieces, so this reproduces
    # `samples/05-sse-stream.txt` exactly: deltas at seq 2..8, `completed` at 9.
    assert [payload["seq"] for _, payload in frames] == list(range(1, len(frames) + 1))
    assert len(frames) == 9


def test_the_response_agrees_with_the_frames_that_preceded_it() -> None:
    with TestClient(_app()) as client:
        body = client.post(_MESSAGES, json={"content": _QUESTION}).text

    frames = _frames(body)
    terminal = frames[-1][1]["response"]
    assert isinstance(terminal, dict)
    assert terminal["sessionId"] == _SESSION
    assert terminal["turnId"] == frames[0][1]["turnId"]
    assert terminal["content"] == "".join(
        str(payload["textDelta"]) for name, payload in frames if name == "delta"
    )


def test_every_event_of_one_turn_names_the_same_turn() -> None:
    with TestClient(_app()) as client:
        body = client.post(_MESSAGES, json={"content": _QUESTION}).text

    assert len({payload["turnId"] for _, payload in _frames(body)}) == 1


def test_a_course_the_caller_cannot_reach_is_not_found() -> None:
    """`courseId` may only narrow what the caller already has. Checked before the
    stream opens, so a course they cannot reach never reaches the index."""

    with TestClient(_app()) as client:
        response = client.post(
            _MESSAGES, json={"content": _QUESTION, "courseId": "course_someone_else"}
        )

    assert response.status_code == 404
    assert response.json()["code"] == "COURSE_NOT_FOUND"
    assert response.json()["details"] == {}


def test_a_course_the_caller_can_reach_is_answered() -> None:
    with TestClient(_app()) as client:
        response = client.post(
            _MESSAGES, json={"content": _QUESTION, "courseId": "course_b3f1c2d4"}
        )

    assert response.status_code == 200
    assert "event: completed" in response.text


def test_a_second_question_for_a_busy_session_is_a_conflict() -> None:
    repository = InMemoryTutoringRepository()
    repository.claim_turn(_SESSION, None)

    with TestClient(_app(repository=repository)) as client:
        response = client.post(_MESSAGES, json={"content": _QUESTION})

    assert response.status_code == 409
    assert response.json()["code"] == "TUTORING_TURN_IN_PROGRESS"


def test_a_refusal_before_the_stream_carries_the_request_id() -> None:
    """The status line is still available, so a refusal is an ordinary error body
    -- and it must be correlated the same way an event is."""

    repository = InMemoryTutoringRepository()
    repository.claim_turn(_SESSION, None)

    with TestClient(_app(repository=repository)) as client:
        response = client.post(_MESSAGES, json={"content": _QUESTION})

    assert response.json()["requestId"] == response.headers["x-request-id"]


def test_a_failure_after_the_stream_opens_is_an_event_not_a_status_code() -> None:
    """By then the status line is long gone; an HTTP code here would be a lie the
    client never sees."""

    with TestClient(_app(retriever=StaticRetriever(unavailable=True))) as client:
        response = client.post(_MESSAGES, json={"content": _QUESTION})

    assert response.status_code == 200
    frames = _frames(response.text)
    assert _names(frames) == ["started", "error"]
    assert frames[-1][1]["error"]["code"] == "RETRIEVAL_UNAVAILABLE"  # type: ignore[index]
    assert frames[-1][1]["error"]["requestId"] == response.headers["x-request-id"]  # type: ignore[index]


def test_the_stream_carries_the_envelope_but_never_the_markers() -> None:
    """The envelope's fields arrive in the terminal event; a client must never see
    the raw markers, which would render as text in the answer."""

    with TestClient(_app()) as client:
        body = client.post(_MESSAGES, json={"content": _QUESTION}).text

    assert RESPONSE_OPEN not in body
    assert RESPONSE_CLOSE not in body
    terminal = _frames(body)[-1][1]["response"]
    assert isinstance(terminal, dict)
    # The two the mock's envelope asks for, and the moods it names.
    assert terminal["followUps"] == [
        "那 ε 和 δ 哪个是先给定的？",
        "如果只从右侧趋近，结论还成立吗？",
    ]
    assert terminal["emotion"] == "encouraging"
    assert terminal["action"] == "nod"


def test_a_client_that_names_the_teaching_state_is_rejected() -> None:
    """`extra="forbid"`: a student cannot ask for `summary` and skip the ladder."""

    with TestClient(_app()) as client:
        response = client.post(_MESSAGES, json={"content": _QUESTION, "stage": "summary"})

    assert response.status_code == 422


def test_an_empty_question_is_rejected() -> None:
    with TestClient(_app()) as client:
        response = client.post(_MESSAGES, json={"content": ""})

    assert response.status_code == 422


# --- the stop endpoint ------------------------------------------------------


def test_a_stop_ends_a_stream_that_is_running_right_now() -> None:
    """The two endpoints, in flight at the same time, on two threads.

    The handshake is the model itself: it says when the turn is live and then
    blocks, so the stop is posted while the stream is genuinely open rather than
    at a moment guessed with a sleep.
    """

    reached = threading.Event()
    repository = InMemoryTutoringRepository()
    app = _app(client=_GatedClient(reached), repository=repository)

    with TestClient(app) as client:
        streamed: dict[str, object] = {}

        def ask() -> None:
            streamed["response"] = client.post(_MESSAGES, json={"content": _QUESTION})

        worker = threading.Thread(target=ask, daemon=True)
        worker.start()
        assert reached.wait(timeout=10), "the turn never started"
        turn_id = repository.session(_SESSION).active_turn_id

        stopped = client.post(_STOP.format(turn_id=turn_id))

        worker.join(timeout=10)
        assert not worker.is_alive(), "the stop did not end the stream"

    response = streamed["response"]
    assert response.status_code == 200
    assert stopped.status_code == 200
    frames = _frames(response.text)
    assert _names(frames)[-1] == "stopped"
    assert frames[-1][1]["reason"] == "client_stop"
    assert frames[-1][1]["turnId"] == turn_id


def test_a_stop_that_arrives_after_the_turn_completed_says_so() -> None:
    with TestClient(_app()) as client:
        frames = _frames(client.post(_MESSAGES, json={"content": _QUESTION}).text)
        turn_id = frames[0][1]["turnId"]
        response = client.post(_STOP.format(turn_id=turn_id))

    assert response.status_code == 200
    assert response.json() == {"turnId": turn_id, "status": "completed"}


def test_stopping_an_unknown_turn_is_not_found() -> None:
    with TestClient(_app()) as client:
        response = client.post(_STOP.format(turn_id="turn_01a2b3c4"))

    assert response.status_code == 404
    assert response.json()["code"] == "TUTORING_TURN_NOT_FOUND"
    assert response.json()["requestId"] == response.headers["x-request-id"]


def test_both_endpoints_see_the_same_turn() -> None:
    """One service, one registry: the claim made while streaming is the turn the
    stop endpoint finds. Two registries would make this a 404."""

    with TestClient(_app()) as client:
        frames = _frames(client.post(_MESSAGES, json={"content": _QUESTION}).text)
        turn_id = frames[0][1]["turnId"]
        response = client.post(_STOP.format(turn_id=turn_id))

    assert response.json()["turnId"] == turn_id


# --- the connection dropping ------------------------------------------------


def test_a_client_that_disappears_mid_stream_is_recorded() -> None:
    """Through the whole application, at the seam a real client leaves by.

    Cancelling the app's task is the disconnect: it is what the server does when
    the socket goes, and it is the *only* thing that happens, because nothing in
    this stack reads the `http.disconnect` message. `receive` returns one anyway
    and it is never requested a second time, which is the fact this test exists to
    keep visible -- a future change that starts polling `receive` would show up
    here as the turn coming back `disconnected` for a different reason.
    """

    async def scenario() -> tuple[InMemoryTutoringRepository, list[dict[str, object]]]:
        repository = InMemoryTutoringRepository()
        app = _app(client=_GatedClient(), repository=repository)

        body = json.dumps({"content": _QUESTION}).encode()
        pending: list[dict[str, object]] = [
            {"type": "http.request", "body": body, "more_body": False}
        ]
        sent: list[dict[str, object]] = []
        first_frame = asyncio.Event()

        async def receive() -> dict[str, object]:
            if not pending:
                return {"type": "http.disconnect"}
            return pending.pop(0)

        async def send(message: dict[str, object]) -> None:
            sent.append(message)
            if message["type"] == "http.response.body" and message.get("body"):
                first_frame.set()

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": _MESSAGES,
            "raw_path": _MESSAGES.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
            "client": ("127.0.0.1", 41234),
            "server": ("testserver", 80),
        }

        task = asyncio.ensure_future(app(scope, receive, send))
        await asyncio.wait_for(first_frame.wait(), timeout=5)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        return repository, sent

    repository, sent = asyncio.run(scenario())

    assert sent[0]["type"] == "http.response.start"  # type: ignore[comparison-overlap]
    assert [record.status for record in repository.session(_SESSION).turns.values()] == [
        "disconnected"
    ]
    # And the session is usable again: with nobody left to call stop, a leaked
    # in-flight turn would be a 409 for the rest of the process's life.
    repository.assert_can_claim(_SESSION)
