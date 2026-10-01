"""The in-memory session registry (Issue #59).

Most of what is asserted here is a *rule about the ladder*, because the ladder is
the thing a student can feel: a stopped turn must not hand out the next rung, and
a second turn must not be able to run beside the first and skip one. The rest is
the bookkeeping those rules need.

The stop signal is tested by actually awaiting it. Asserting `is_set()` alone
would pass even if nothing ever woke up, which is the failure that matters.
"""

import asyncio

import pytest

from app.domains.tutoring.repository import (
    MAX_HISTORY_MESSAGES,
    MAX_SESSIONS,
    MAX_TURNS_PER_SESSION,
    FailedTurnStatus,
    InMemoryTutoringRepository,
    TurnInProgressError,
    UnknownTurnError,
)
from app.domains.tutoring.stages import STAGE_ORDER

_SESSION = "sess_4b8d1e02"


def _repository(
    *,
    max_sessions: int = MAX_SESSIONS,
    max_turns: int = MAX_TURNS_PER_SESSION,
) -> InMemoryTutoringRepository:
    return InMemoryTutoringRepository(max_sessions=max_sessions, max_turns=max_turns)


def _settle(repository: InMemoryTutoringRepository, session_id: str = _SESSION) -> str:
    """Claim and successfully complete one turn, returning its id."""

    record = repository.claim_turn(session_id, None)
    repository.complete_turn(
        session_id,
        record.turn_id,
        student_content="问题",
        assistant_content="答案",
    )
    return record.turn_id


def _settle_count(repository: InMemoryTutoringRepository, count: int) -> None:
    """Complete `count` turns in a row. Written out rather than looped-until,
    because a ladder that stopped moving should fail the test, not hang CI."""

    for _ in range(count):
        _settle(repository)


# --- sessions ---------------------------------------------------------------


def test_a_session_opens_on_first_use() -> None:
    """M2 posts a question without a separate "create session" round trip."""

    repository = _repository()

    assert repository.stage(_SESSION) == "thought"
    assert repository.history(_SESSION) == ()


def test_the_same_session_id_returns_the_same_state() -> None:
    repository = _repository()
    _settle(repository)

    assert repository.stage(_SESSION) == "hint"


def test_two_sessions_do_not_share_a_stage() -> None:
    repository = _repository()
    _settle(repository, "sess_a")

    assert repository.stage("sess_b") == "thought"


def test_sessions_are_evicted_least_recently_used_first() -> None:
    """The eviction is silent, so the only evidence is that the stage is gone.

    Order matters in the assertions. Reading `sess_a` back re-creates it -- a read
    is a session opening -- and that creation is itself the newest, so it evicts
    whichever session was oldest at that point. Asking after the survivor first
    keeps the two effects from being confused for one another.
    """

    repository = _repository(max_sessions=2)
    _settle(repository, "sess_a")
    _settle(repository, "sess_b")

    repository.stage("sess_c")

    assert repository.stage("sess_b") == "hint"
    assert repository.stage("sess_a") == "thought"


def test_a_session_with_a_turn_in_flight_is_not_evicted() -> None:
    """Dropping it would break a stream already being delivered."""

    repository = _repository(max_sessions=1)
    record = repository.claim_turn("sess_a", None)

    repository.stage("sess_b")

    assert repository.turn("sess_a", record.turn_id).status == "active"


# --- claiming a turn --------------------------------------------------------


def test_a_claimed_turn_gets_a_turn_prefixed_id() -> None:
    """`turn_` is the prefix the platform contract fixes for this domain."""

    repository = _repository()
    record = repository.claim_turn(_SESSION, None)

    assert record.turn_id.startswith("turn_")


def test_two_turns_never_get_the_same_id() -> None:
    repository = _repository()
    first = repository.claim_turn("sess_a", None).turn_id
    second = repository.claim_turn("sess_b", None).turn_id

    assert first != second


def test_a_requested_stage_can_only_pull_the_stage_back() -> None:
    """A request for `summary` from `thought` is clamped, not honoured.

    This is the whole reason the endpoint can accept `requestedStage` from a
    student without letting them skip the ladder.
    """

    repository = _repository()

    assert repository.claim_turn(_SESSION, "summary").stage == "thought"


def test_a_requested_stage_pulls_the_stage_back_to_what_it_asks_for() -> None:
    repository = _repository()
    _settle_count(repository, 2)

    assert repository.stage(_SESSION) == "step"
    assert repository.claim_turn(_SESSION, "hint").stage == "hint"


def test_a_second_turn_in_the_same_session_is_refused() -> None:
    """Two concurrently completing turns would each advance the stage."""

    repository = _repository()
    record = repository.claim_turn(_SESSION, None)

    with pytest.raises(TurnInProgressError) as caught:
        repository.claim_turn(_SESSION, None)

    assert caught.value.turn_id == record.turn_id


def test_the_stage_freezes_when_the_turn_is_claimed() -> None:
    """`started.stage` and `completed.response.stage` must agree, so the stage
    cannot be read off the session afterwards."""

    repository = _repository()
    record = repository.claim_turn(_SESSION, None)
    repository.complete_turn(_SESSION, record.turn_id, student_content="问", assistant_content="答")

    assert record.stage == "thought"
    assert repository.stage(_SESSION) == "hint"


def test_a_busy_session_can_be_told_apart_without_claiming_anything() -> None:
    """The router asks first so it can answer 409 before it commits to a stream.

    Reading must not claim: a request that is refused this way has to leave the
    session exactly as it found it, or the client's retry would find a turn in
    flight that nobody is serving.
    """

    repository = _repository()
    record = repository.claim_turn(_SESSION, None)

    with pytest.raises(TurnInProgressError) as caught:
        repository.assert_can_claim(_SESSION)

    assert caught.value.turn_id == record.turn_id
    assert repository.session(_SESSION).active_turn_id == record.turn_id


def test_an_idle_session_passes_the_availability_check() -> None:
    repository = _repository()

    repository.assert_can_claim(_SESSION)

    assert repository.session(_SESSION).active_turn_id is None


def test_the_availability_check_passes_once_a_stopped_turn_is_settled() -> None:
    repository = _repository()
    record = repository.claim_turn(_SESSION, None)
    repository.request_stop(_SESSION, record.turn_id)

    repository.assert_can_claim(_SESSION)


def test_an_unknown_turn_is_not_silently_created() -> None:
    repository = _repository()

    with pytest.raises(UnknownTurnError):
        repository.turn(_SESSION, "turn_missing")


def test_a_turn_is_unknown_in_a_session_that_was_never_opened() -> None:
    repository = _repository()

    with pytest.raises(UnknownTurnError):
        repository.turn("sess_never", "turn_missing")


# --- the ladder -------------------------------------------------------------


def test_a_completed_turn_advances_the_stage() -> None:
    repository = _repository()
    _settle(repository)

    assert repository.stage(_SESSION) == "hint"


def test_the_ladder_stops_at_the_last_stage() -> None:
    repository = _repository()
    for _ in range(len(STAGE_ORDER) + 2):
        _settle(repository)

    assert repository.stage(_SESSION) == STAGE_ORDER[-1]


@pytest.mark.parametrize("status", ["stopped", "errored", "disconnected"])
def test_a_failed_turn_does_not_advance_the_stage(status: FailedTurnStatus) -> None:
    """A half answer must not buy the student the next rung
    (`packages/contracts/tutoring/sse-events.md:104-152`)."""

    repository = _repository()
    record = repository.claim_turn(_SESSION, None)

    repository.settle_failed_turn(_SESSION, record.turn_id, status)

    assert repository.stage(_SESSION) == "thought"
    assert repository.history(_SESSION) == ()


@pytest.mark.parametrize("status", ["stopped", "errored", "disconnected"])
def test_a_failed_turn_frees_the_session_for_the_next_one(status: FailedTurnStatus) -> None:
    repository = _repository()
    record = repository.claim_turn(_SESSION, None)
    repository.settle_failed_turn(_SESSION, record.turn_id, status)

    assert repository.claim_turn(_SESSION, None).stage == "thought"


def test_settling_a_failed_turn_twice_is_a_no_op() -> None:
    """Reachable: a stop can land while the writer is awaiting the model."""

    repository = _repository()
    record = repository.claim_turn(_SESSION, None)
    repository.settle_failed_turn(_SESSION, record.turn_id, "stopped")

    repository.settle_failed_turn(_SESSION, record.turn_id, "errored")

    assert repository.turn(_SESSION, record.turn_id).status == "stopped"


# --- history ----------------------------------------------------------------


def test_a_completed_turn_is_remembered_as_one_exchange() -> None:
    """The hint and step instructions assume the student already tried, so the
    next turn has to be able to see what was said."""

    repository = _repository()
    _settle(repository)

    assert [(turn.role, turn.content) for turn in repository.history(_SESSION)] == [
        ("student", "问题"),
        ("assistant", "答案"),
    ]


def test_the_history_keeps_only_the_most_recent_exchanges() -> None:
    repository = _repository()
    exchanges = MAX_HISTORY_MESSAGES // 2
    for index in range(MAX_HISTORY_MESSAGES):
        record = repository.claim_turn(_SESSION, None)
        repository.complete_turn(
            _SESSION,
            record.turn_id,
            student_content=f"问{index}",
            assistant_content=f"答{index}",
        )

    history = repository.history(_SESSION)

    assert [turn.content for turn in history] == [
        f"{prefix}{index}"
        for index in range(MAX_HISTORY_MESSAGES - exchanges, MAX_HISTORY_MESSAGES)
        for prefix in ("问", "答")
    ]


# --- turns are kept, and bounded --------------------------------------------


def test_a_settled_turn_is_still_readable_afterwards() -> None:
    """M2 may send a stop the instant it sees `completed`."""

    repository = _repository()
    turn_id = _settle(repository)

    assert repository.turn(_SESSION, turn_id).status == "completed"


def test_the_oldest_settled_turn_is_dropped_once_the_cap_is_reached() -> None:
    repository = _repository(max_turns=2)
    first = _settle(repository)
    second = _settle(repository)
    third = _settle(repository)

    with pytest.raises(UnknownTurnError):
        repository.turn(_SESSION, first)
    assert repository.turn(_SESSION, second).status == "completed"
    assert repository.turn(_SESSION, third).status == "completed"


def test_a_turn_in_flight_is_never_evicted() -> None:
    """Even under a cap that cannot be met the live turn survives: the cap is
    exceeded rather than the stream broken."""

    repository = _repository(max_turns=0)
    record = repository.claim_turn(_SESSION, None)

    assert repository.turn(_SESSION, record.turn_id).status == "active"


# --- stop -------------------------------------------------------------------


def test_a_stop_is_recorded_as_stopped() -> None:
    repository = _repository()
    record = repository.claim_turn(_SESSION, None)

    status = repository.request_stop(_SESSION, record.turn_id)

    assert status == "stopped"
    assert repository.turn(_SESSION, record.turn_id).status == "stopped"


def test_a_stop_wakes_the_stream() -> None:
    """The signal itself, not just the flag it leaves behind."""

    async def scenario() -> bool:
        repository = _repository()
        record = repository.claim_turn(_SESSION, None)
        waiter = asyncio.ensure_future(record.stop.wait())
        await asyncio.sleep(0)

        repository.request_stop(_SESSION, record.turn_id)

        return await waiter

    assert asyncio.run(scenario()) is True


def test_a_stop_frees_the_session_for_the_next_turn() -> None:
    repository = _repository()
    record = repository.claim_turn(_SESSION, None)
    repository.request_stop(_SESSION, record.turn_id)

    assert repository.claim_turn(_SESSION, None).stage == "thought"


def test_stopping_twice_reports_the_same_status() -> None:
    """The endpoint stays idempotent without inventing a second terminal event."""

    repository = _repository()
    record = repository.claim_turn(_SESSION, None)

    first = repository.request_stop(_SESSION, record.turn_id)
    second = repository.request_stop(_SESSION, record.turn_id)

    assert (first, second) == ("stopped", "stopped")
    assert repository.turn(_SESSION, record.turn_id).status == "stopped"


def test_a_stop_after_completion_reports_completed_and_changes_nothing() -> None:
    """The writer got there first, so the client was already told `completed`.

    Reporting `stopped` here would have M2 render a stop that never happened, and
    emitting a `stopped` frame would be the second terminal event the contract
    forbids.
    """

    repository = _repository()
    turn_id = _settle(repository)

    status = repository.request_stop(_SESSION, turn_id)

    assert status == "completed"
    assert repository.turn(_SESSION, turn_id).stop.is_set() is False


def test_a_stop_after_completion_does_not_move_the_ladder() -> None:
    repository = _repository()
    turn_id = _settle(repository)

    repository.request_stop(_SESSION, turn_id)

    assert repository.stage(_SESSION) == "hint"


def test_a_stop_after_a_failure_does_not_overwrite_the_failure() -> None:
    """A disconnect stays recorded as a disconnect: the two reasons need telling
    apart in the logs, so a late stop must not relabel one as the other."""

    repository = _repository()
    record = repository.claim_turn(_SESSION, None)
    repository.settle_failed_turn(_SESSION, record.turn_id, "disconnected")

    assert repository.request_stop(_SESSION, record.turn_id) == "disconnected"


def test_a_stop_for_an_unknown_turn_is_refused() -> None:
    repository = _repository()

    with pytest.raises(UnknownTurnError):
        repository.request_stop(_SESSION, "turn_missing")
