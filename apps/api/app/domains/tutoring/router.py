"""The two tutoring endpoints. Protocol only -- no teaching rules live here.

`POST .../messages` answers `text/event-stream`; everything it yields comes from
`service.stream_turn`. `POST .../turns/{turnId}/stop` writes no events at all: it
flips a signal and reports what happened, because a second writer is exactly how a
stream ends up with two terminal events.

Two things are worth knowing before reading the handlers.

**Failures are split by whether the first byte has been sent.** Everything that can
be refused up front -- a busy session, a course the caller cannot reach -- is
refused as an ordinary JSON response with a real status code. Only what goes wrong
after the stream is open can be an in-band `error` event, because by then the status
line is long gone and an HTTP code would be a lie the client never sees.

**Nothing is claimed inside the stream generator.** A generator body does not run
until the first chunk is pulled, and it does not run at all if the client
disconnected first; a turn claimed there would never be released and the session
would be wedged for good. So the availability check happens here, and the claim
happens at the top of the generator, one immediately after the other.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.domains.tutoring.adapters import MockModelClient
from app.domains.tutoring.principal import Principal, can_reach_course, get_principal
from app.domains.tutoring.prompt_renderer import load_prompt_template
from app.domains.tutoring.repository import (
    InMemoryTutoringRepository,
    TurnInProgressError,
    TurnStatus,
    UnknownTurnError,
)
from app.domains.tutoring.retrieval import StaticRetriever
from app.domains.tutoring.schemas import MessageRequest
from app.domains.tutoring.service import TutoringService

__all__ = ["get_service", "router"]

router = APIRouter(prefix="/api/v1/tutoring", tags=["tutoring"])

_SSE_HEADERS: dict[str, str] = {
    # A buffering proxy would hold the whole answer and release it at once, which
    # defeats the point of the transport; `no-store` keeps one student's answer out
    # of any cache.
    "Cache-Control": "no-store",
    "X-Accel-Buffering": "no",
}


class StopTurnResponse(BaseModel):
    """The body of a successful stop.

    Not part of `packages/contracts/`: the contract fixes the endpoint's behaviour
    but not its response body, so this lives beside the endpoint rather than in the
    schema module that mirrors the contract. It reports the turn's status *after*
    the call, which is what makes a repeated stop truthful -- see the PR notes.
    """

    turn_id: str = Field(serialization_alias="turnId")
    status: TurnStatus


def get_service(request: Request) -> TutoringService:
    """The application's service, built on first use and shared thereafter.

    Lazy because `app/main.py` is outside this change's scope beyond registering
    the router, so there is no lifespan hook to build it in. It hangs off
    `app.state` rather than a module global: every `with TestClient(...)` gets its
    own app and its own event loop, and an `asyncio.Event` created on one loop
    cannot be waited on from another.

    The two-step assignment is safe without a lock because nothing between the read
    and the write awaits, so no second request can interleave. That matters: two
    services would mean two registries, and a turn claimed in one would be
    invisible to the other.
    """

    service: TutoringService | None = getattr(request.app.state, "tutoring_service", None)
    if service is None:
        service = _build_service()
        request.app.state.tutoring_service = service
    return service


def _build_service() -> TutoringService:
    """Wire the S1 stack: a Mock model, a static retriever and an in-memory registry.

    Building the service is also what loads and parses the prompt template, so a
    template that will not parse fails here -- on the first request, before any
    bytes of any stream, which is the last point at which a client can still be
    told something true about it.
    """

    return TutoringService(
        client=MockModelClient(envelope=True),
        retriever=StaticRetriever(),
        repository=InMemoryTutoringRepository(),
        template=load_prompt_template(),
        is_mock=True,
    )


def _error_response(request: Request, *, status_code: int, code: str, message: str) -> JSONResponse:
    """A refusal in the platform's error shape (`docs/code-standards.md:74-80`)."""

    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": message,
            "requestId": request.state.request_id,
            "details": {},
        },
    )


@router.post(
    "/sessions/{session_id}/messages",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"text/event-stream": {}}, "description": "The turn's event stream"},
        404: {"description": "No such course, or none this caller can reach"},
        409: {"description": "The session already has a turn in flight"},
        422: {"description": "The request body named teaching state a client may not set"},
    },
)
async def create_message(
    request: Request,
    body: MessageRequest,
    session_id: Annotated[str, Path(description="Session the question belongs to")],
    principal: Annotated[Principal, Depends(get_principal)],
    service: Annotated[TutoringService, Depends(get_service)],
) -> Response:
    """Ask a question and stream the guided answer.

    The body's `courseId` may only narrow what the principal can already reach. It
    is checked here, before the stream opens and therefore before any retrieval
    runs, so a course this caller cannot reach never reaches the index
    (`packages/contracts/platform/README.md:32-33`).
    """

    if body.course_id is not None and not can_reach_course(principal, body.course_id):
        return _error_response(
            request, status_code=404, code="COURSE_NOT_FOUND", message="未找到课程"
        )

    try:
        service.check_available(session_id)
    except TurnInProgressError:
        return _error_response(
            request,
            status_code=409,
            code="TUTORING_TURN_IN_PROGRESS",
            message="该会话已有正在进行的答疑轮次",
        )

    return StreamingResponse(
        service.stream_turn(
            session_id=session_id,
            content=body.content,
            requested_stage=body.requested_stage,
            course_id=body.course_id,
            request_id=request.state.request_id,
        ),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.post(
    "/sessions/{session_id}/turns/{turn_id}/stop",
    responses={
        200: {"description": "The turn's status after the call"},
        404: {"description": "No such turn in this session"},
    },
)
async def stop_turn(
    request: Request,
    session_id: Annotated[str, Path(description="Session the turn belongs to")],
    turn_id: Annotated[str, Path(description="Turn to stop")],
    service: Annotated[TutoringService, Depends(get_service)],
) -> Response:
    """Stop a live turn. Idempotent, and it holds no state of its own.

    `async def` is not decoration. A synchronous handler would be run in a worker
    thread, and the stop signal would then be set from a thread other than the one
    the stream is running on. It writes no events: the streaming task is the only
    writer, which is what keeps the terminal event unique.
    """

    try:
        status = service.stop(session_id, turn_id, request.state.request_id)
    except UnknownTurnError:
        return _error_response(
            request,
            status_code=404,
            code="TUTORING_TURN_NOT_FOUND",
            message="未找到该答疑轮次",
        )

    return JSONResponse(
        status_code=200,
        content=StopTurnResponse(turn_id=turn_id, status=status).model_dump(by_alias=True),
    )
