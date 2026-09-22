"""Wire-model tests for the tutoring endpoints (Issue #59).

Two families of assertion live here. One is the camelCase mapping, since the
contract's field names are what M2 codes against. The other is the contract's
invariants (`tutoring-response.md:115-130`), which that file asks to be caught by
"a Pydantic validator or a test" -- so both.

The sharpest one is `test_delta_carries_prose_only`: it is a *structural* check
that `delta` has no structured fields, which is what stops the response envelope
from ever being rendered into a student's answer.
"""

import json
from datetime import UTC, datetime
from typing import get_args

import pytest
from pydantic import ValidationError

from app.domains.tutoring.envelope import Action, Emotion
from app.domains.tutoring.schemas import (
    MAX_CONTENT_CHARS,
    Citation,
    CompletedEvent,
    DeltaEvent,
    ErrorBody,
    ErrorCode,
    ErrorEvent,
    MessageRequest,
    StartedEvent,
    StoppedEvent,
    StopReason,
    StreamEvent,
    TutoringResponse,
)
from app.domains.tutoring.stages import STAGE_ORDER

_CREATED_AT = datetime(2026, 9, 14, 8, 0, tzinfo=UTC)


def _citation(page: int = 12) -> Citation:
    return Citation(
        citation_id="c1",
        document_id="doc_9a2f4c",
        document_title="高等数学-上册-第1章.pdf",
        page_number=page,
        snippet="设函数 f(x) 在点 a 的某个去心邻域内有定义。",
    )


def _response(**overrides: object) -> TutoringResponse:
    fields: dict[str, object] = {
        "turn_id": "turn_7f3a9c21",
        "session_id": "sess_4b8d1e02",
        "stage": "thought",
        "content": "content",
        "citations": [_citation()],
        "has_evidence": True,
        "follow_ups": ["a"],
        "emotion": "encouraging",
        "action": "nod",
        "is_mock": True,
        "prompt_version": "guided-tutoring.v1",
        "created_at": _CREATED_AT,
    }
    fields.update(overrides)
    return TutoringResponse(**fields)  # type: ignore[arg-type]


def _wire(model: object) -> dict[str, object]:
    return json.loads(model.model_dump_json(by_alias=True))  # type: ignore[attr-defined]


# --- the request body -------------------------------------------------------


def test_the_request_accepts_the_contract_fields() -> None:
    request = MessageRequest.model_validate(
        {"content": "极限的定义是什么？", "requestedStage": "hint", "courseId": "course_b3f1c2d4"}
    )

    assert request.content == "极限的定义是什么？"
    assert request.requested_stage == "hint"
    assert request.course_id == "course_b3f1c2d4"


def test_the_optional_request_fields_default_to_none() -> None:
    request = MessageRequest.model_validate({"content": "问题"})

    assert request.requested_stage is None
    assert request.course_id is None


@pytest.mark.parametrize("forbidden", ["stage", "emotion", "action"])
def test_the_request_forbids_client_supplied_teaching_state(forbidden: str) -> None:
    """`tutoring-response.md:28-34`: a client must not be able to name a stage.

    If it could, a student would simply ask for `summary` and be handed the full
    solution, which is the whole thing the ladder exists to prevent.
    """

    with pytest.raises(ValidationError):
        MessageRequest.model_validate({"content": "问题", forbidden: "summary"})


@pytest.mark.parametrize("stage", STAGE_ORDER)
def test_a_valid_requested_stage_is_accepted(stage: str) -> None:
    request = MessageRequest.model_validate({"content": "问题", "requestedStage": stage})

    assert request.requested_stage == stage


def test_an_invented_requested_stage_is_rejected() -> None:
    with pytest.raises(ValidationError):
        MessageRequest.model_validate({"content": "问题", "requestedStage": "answer"})


@pytest.mark.parametrize("content", ["", "x" * (MAX_CONTENT_CHARS + 1)])
def test_the_content_bounds_are_enforced(content: str) -> None:
    with pytest.raises(ValidationError):
        MessageRequest.model_validate({"content": content})


def test_content_at_the_upper_bound_is_accepted() -> None:
    assert len(MessageRequest.model_validate({"content": "x" * MAX_CONTENT_CHARS}).content) == 2000


# --- the response -----------------------------------------------------------


def test_the_response_dumps_camel_case() -> None:
    """Field order and names both match the frozen samples, so a dumped event
    reads the way the contract documents it."""

    assert list(_wire(_response())) == [
        "turnId",
        "sessionId",
        "stage",
        "content",
        "citations",
        "hasEvidence",
        "followUps",
        "emotion",
        "action",
        "isMock",
        "promptVersion",
        "createdAt",
    ]


def test_created_at_serializes_as_utc_z() -> None:
    """The samples all end in `Z`; pydantic would otherwise emit `+00:00`."""

    assert _wire(_response())["createdAt"] == "2026-09-14T08:00:00Z"


def test_a_non_utc_created_at_is_converted_rather_than_relabelled() -> None:
    """Converting, not replacing the offset, is the difference between a correct
    timestamp and one shifted by the offset."""

    from datetime import timedelta, timezone

    eight_hours_ahead = datetime(2026, 9, 14, 16, 0, tzinfo=timezone(timedelta(hours=8)))

    assert _wire(_response(created_at=eight_hours_ahead))["createdAt"] == "2026-09-14T08:00:00Z"


def test_citations_are_never_null() -> None:
    assert _wire(_response(citations=[], has_evidence=False))["citations"] == []


def test_has_evidence_without_citations_is_rejected() -> None:
    """Invariant 1, one direction: claiming a sourced answer with nothing behind
    it tells M2 the answer is grounded when it is not."""

    with pytest.raises(ValidationError):
        _response(citations=[], has_evidence=True)


def test_citations_without_has_evidence_is_rejected() -> None:
    """Invariant 1, the other direction: hiding citations the answer really used."""

    with pytest.raises(ValidationError):
        _response(citations=[_citation()], has_evidence=False)


@pytest.mark.parametrize("page", [0, -1])
def test_a_non_positive_page_number_is_rejected(page: int) -> None:
    """Invariant 4 -- parsing layer page numbers are 1-based."""

    with pytest.raises(ValidationError):
        _citation(page=page)


def test_follow_ups_are_capped_at_three() -> None:
    with pytest.raises(ValidationError):
        _response(follow_ups=["a", "b", "c", "d"])


# --- the events -------------------------------------------------------------


def test_every_event_dumps_camel_case_on_one_line() -> None:
    """A `data:` line with a newline in it would split the SSE frame in half."""

    events = [
        StartedEvent(seq=1, turn_id="turn_1", stage="thought", is_mock=True),
        DeltaEvent(seq=2, turn_id="turn_1", text_delta="我们"),
        CompletedEvent(seq=3, turn_id="turn_1", response=_response()),
        StoppedEvent(seq=4, turn_id="turn_1", reason="client_stop"),
        ErrorEvent(
            seq=5,
            turn_id="turn_1",
            error=ErrorBody(code="MODEL_TIMEOUT", message="m", request_id="req_1"),
        ),
    ]

    for event in events:
        raw = event.model_dump_json(by_alias=True)
        assert "\n" not in raw
        assert list(json.loads(raw))[0] == "seq"
        assert json.loads(raw)["turnId"] == "turn_1"


def test_delta_carries_prose_only() -> None:
    """Structural: `delta` has no structured field to leak the envelope through.

    This is the assertion that keeps citations / followUps / emotion / action out
    of the streaming path, which is what stops the raw envelope JSON from being
    rendered into a student's answer (`sse-events.md:69-70`).
    """

    assert set(DeltaEvent.model_fields) == {"seq", "turn_id", "text_delta"}
    assert set(get_args(StreamEvent)) == {
        StartedEvent,
        DeltaEvent,
        CompletedEvent,
        StoppedEvent,
        ErrorEvent,
    }


def test_started_carries_the_stage_and_the_mock_flag() -> None:
    assert _wire(StartedEvent(seq=1, turn_id="turn_1", stage="hint", is_mock=True)) == {
        "seq": 1,
        "turnId": "turn_1",
        "stage": "hint",
        "isMock": True,
    }


@pytest.mark.parametrize(
    ("reason", "is_complete"),
    [("client_stop", False), ("client_disconnect", False)],
)
def test_stopped_reports_the_reason_and_incompleteness(reason: str, is_complete: bool) -> None:
    wire = _wire(StoppedEvent(seq=4, turn_id="turn_1", reason=reason))  # type: ignore[arg-type]

    assert wire == {"seq": 4, "turnId": "turn_1", "isComplete": is_complete, "reason": reason}


def test_a_reason_outside_the_contract_is_rejected() -> None:
    with pytest.raises(ValidationError):
        StoppedEvent(seq=4, turn_id="turn_1", reason="client_gave_up")  # type: ignore[arg-type]


def test_completed_is_always_complete() -> None:
    event = CompletedEvent(seq=9, turn_id="turn_1", response=_response())

    assert _wire(event)["isComplete"] is True


def test_the_error_event_never_claims_completeness() -> None:
    wire = _wire(
        ErrorEvent(
            seq=3,
            turn_id="turn_1",
            error=ErrorBody(
                code="MODEL_OUTPUT_INVALID",
                message="模型输出无法通过结构校验，请重试",
                request_id="req_8d1f0c33",
                details={"reason": "response_envelope_parse_failed"},
            ),
        )
    )

    assert wire["isComplete"] is False
    assert wire["error"] == {
        "code": "MODEL_OUTPUT_INVALID",
        "message": "模型输出无法通过结构校验，请重试",
        "requestId": "req_8d1f0c33",
        "details": {"reason": "response_envelope_parse_failed"},
    }


def test_the_error_codes_are_the_contract_set() -> None:
    assert set(get_args(ErrorCode)) == {
        "MODEL_OUTPUT_INVALID",
        "MODEL_REFUSED",
        "MODEL_TIMEOUT",
        "RETRIEVAL_UNAVAILABLE",
        "TURN_ABORTED",
    }


def test_an_error_code_outside_the_contract_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ErrorBody(code="MODEL_EXPLODED", message="m", request_id="req_1")  # type: ignore[arg-type]


def test_details_defaults_to_an_empty_object() -> None:
    """`details` is present but empty when there is nothing to add; the frozen
    sample's `attempts` is absent because S1 does not retry."""

    assert _wire(ErrorBody(code="TURN_ABORTED", message="m", request_id="req_1"))["details"] == {}


def test_a_sequence_number_below_one_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DeltaEvent(seq=0, turn_id="turn_1", text_delta="x")


def test_the_stop_reasons_are_the_contract_set() -> None:
    assert set(get_args(StopReason)) == {"client_stop", "client_disconnect"}


def test_the_emotion_and_action_enums_are_shared_with_the_envelope() -> None:
    """One definition, two users. Were they separate, the envelope validator could
    accept an `emotion` the response schema then refuses, and the failure would
    surface only at the very end of a stream."""

    assert set(get_args(Emotion)) | set(get_args(Action)) == {
        "neutral",
        "encouraging",
        "thinking",
        "celebrating",
        "idle",
        "nod",
        "point",
        "write",
    }
