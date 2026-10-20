"""Unit tests for the teaching-stage ladder (Issue #59).

Stage values come from `docs/code-standards.md:95`; the movement rule comes from
Issue #59 -- only a turn that **completes successfully** moves one rung, capped
at `summary`.
"""

from typing import get_args

import pytest

from app.domains.tutoring.stages import (
    INITIAL_STAGE,
    STAGE_ORDER,
    Stage,
    advance_stage,
    resolve_stage,
)

#: Requests for a *later* stage, used to prove a client cannot advance the ladder.
_ADVANCING_REQUESTS: list[tuple[Stage, Stage]] = [
    (current, requested)
    for index, current in enumerate(STAGE_ORDER)
    for requested in STAGE_ORDER[index + 1 :]
]

#: Requests for an *earlier* stage, used to prove a client can pull it back.
_PULLING_BACK_REQUESTS: list[tuple[Stage, Stage]] = [
    (current, requested)
    for index, current in enumerate(STAGE_ORDER)
    for requested in STAGE_ORDER[:index]
]


def test_stage_set_is_closed() -> None:
    """`Stage` must be a closed set that agrees with the ladder order.

    Ladder order is semantics (the index is the progress), so a mismatch would
    let `advance_stage` walk onto a stage that should not exist. This assertion
    is the only place that catches it.
    """

    assert set(get_args(Stage)) == {"thought", "hint", "step", "summary"}
    assert set(STAGE_ORDER) == set(get_args(Stage))
    assert len(STAGE_ORDER) == len(set(STAGE_ORDER)), "the ladder has a duplicate stage"


def test_initial_stage_is_the_first_step() -> None:
    assert INITIAL_STAGE == STAGE_ORDER[0]


@pytest.mark.parametrize("current", STAGE_ORDER)
def test_absent_request_keeps_the_current_stage(current: Stage) -> None:
    assert resolve_stage(current, None) == current


@pytest.mark.parametrize(("current", "requested"), _ADVANCING_REQUESTS)
def test_request_cannot_advance_the_stage(current: Stage, requested: Stage) -> None:
    """A request for a later stage is clamped back to the current one.

    This is the executable form of `docs/code-standards.md:95`: "clients must not
    advance the teaching state and bypass server validation".
    """

    assert resolve_stage(current, requested) == current


@pytest.mark.parametrize(("current", "requested"), _PULLING_BACK_REQUESTS)
def test_request_can_pull_the_stage_back(current: Stage, requested: Stage) -> None:
    assert resolve_stage(current, requested) == requested


@pytest.mark.parametrize("current", STAGE_ORDER)
def test_requesting_the_current_stage_is_a_no_op(current: Stage) -> None:
    assert resolve_stage(current, current) == current


def test_advance_walks_the_ladder_one_step_at_a_time() -> None:
    assert advance_stage("thought") == "hint"
    assert advance_stage("hint") == "step"
    assert advance_stage("step") == "summary"


def test_advance_caps_at_the_last_stage() -> None:
    assert advance_stage("summary") == "summary"


@pytest.mark.parametrize("current", STAGE_ORDER)
def test_advance_stays_on_the_ladder(current: Stage) -> None:
    assert advance_stage(current) in STAGE_ORDER
