"""The teaching-stage ladder and how it moves (`docs/code-standards.md:95`).

Stages are decided by a **server-side** state machine; a client may only ask to
pull the stage back. The asymmetry is deliberate: letting a client advance the
stage would also let it bypass the server's judgement of whether the student has
already attempted the problem.
"""

from typing import Final, Literal

__all__ = ["INITIAL_STAGE", "STAGE_ORDER", "Stage", "advance_stage", "resolve_stage"]

#: The four stages come from `docs/code-standards.md:95`. `thought` is the
#: student-facing line of attack; `summary` is the only stage allowed to give a
#: complete solution.
Stage = Literal["thought", "hint", "step", "summary"]

#: Ladder order. The index *is* the progress, so the order is semantics, not layout.
STAGE_ORDER: Final[tuple[Stage, ...]] = ("thought", "hint", "step", "summary")

INITIAL_STAGE: Final[Stage] = "thought"


def resolve_stage(current: Stage, requested: Stage | None) -> Stage:
    """The stage this turn's `started` event should carry.

    `requested` can only pull the stage **backwards**: a request for a later
    stage is clamped to `current`, because only the server's state machine knows
    whether the student has attempted anything (`docs/code-standards.md:95`,
    "clients must not advance the teaching state and bypass server validation").

    `None` means the client expressed no preference, so the current stage stands.
    """

    if requested is None:
        return current
    return min(current, requested, key=STAGE_ORDER.index)


def advance_stage(current: Stage) -> Stage:
    """Move one rung after a turn **completes successfully**, capped at `summary`.

    Callers may only reach this on the `completed` path. `stopped`, `error` and
    disconnects never advance (Issue #59), so this counts successes rather than
    turns.
    """

    index = STAGE_ORDER.index(current)
    return STAGE_ORDER[min(index + 1, len(STAGE_ORDER) - 1)]
