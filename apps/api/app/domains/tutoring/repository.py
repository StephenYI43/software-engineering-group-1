"""In-process session state: the teaching stage, the history, and the live turn.

This is the only shared mutable state the domain has. It hangs off `app.state`
rather than a module-level singleton, because each `with TestClient(...)` starts a
fresh event loop and an `asyncio.Event` created on one loop cannot be awaited from
another.

**Every mutating method is synchronous on purpose.** Under a single event loop a
synchronous method runs to completion without interleaving, so no lock is needed
and no request can observe a half-applied change. Making any of these `async`
would introduce an `await` in the middle and silently destroy that property --
which is why the stop endpoint is `async def` and never hands this object to a
worker thread either.

S1 keeps all of this in memory: one process, one worker, and it is gone on
restart. The PR description records what that does and does not cover.
"""

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Final, Literal
from uuid import uuid4

from app.domains.tutoring.adapters import Turn
from app.domains.tutoring.stages import INITIAL_STAGE, Stage, advance_stage, resolve_stage

__all__ = [
    "MAX_HISTORY_MESSAGES",
    "MAX_SESSIONS",
    "MAX_TURNS_PER_SESSION",
    "FailedTurnStatus",
    "InMemoryTutoringRepository",
    "SessionState",
    "TurnInProgressError",
    "TurnRecord",
    "TurnStatus",
    "UnknownTurnError",
]


#: How a turn ended. `active` is the only non-terminal value, and it is what the
#: stop endpoint reports when a stop arrives before the turn settles.
TurnStatus = Literal["active", "completed", "stopped", "errored", "disconnected"]

#: The ways a turn can end without a usable answer. Kept separate from
#: `TurnStatus` so `settle_failed_turn` cannot be called to claim success: success
#: is the one path that moves the teaching stage, and it deserves its own call.
FailedTurnStatus = Literal["stopped", "errored", "disconnected"]

#: Sessions kept before the oldest idle one is dropped. S1 has no persistence, so
#: this is the only bound on memory.
MAX_SESSIONS: Final[int] = 256

#: Turns kept per session. The point of keeping more than one is that M2 may send
#: a stop the instant it sees `completed`; evicting immediately would turn that
#: legitimate call into a 404.
MAX_TURNS_PER_SESSION: Final[int] = 16

#: Six exchanges, which is what the prompt tolerates. A turn that fails is never
#: appended, so this counts *completed* exchanges.
MAX_HISTORY_MESSAGES: Final[int] = 12


class TurnInProgressError(RuntimeError):
    """The session already has a turn in flight.

    Refusing the second one matters: two concurrently completing turns would each
    advance the stage, and the student would skip a rung of the ladder.
    """

    def __init__(self, turn_id: str) -> None:
        super().__init__(f"session already has a turn in flight: {turn_id}")
        self.turn_id = turn_id


class UnknownTurnError(LookupError):
    """No such turn in this session. The stop endpoint turns this into a 404."""

    def __init__(self, session_id: str, turn_id: str) -> None:
        super().__init__(f"no turn {turn_id} in session {session_id}")
        self.session_id = session_id
        self.turn_id = turn_id


@dataclass(slots=True)
class TurnRecord:
    """One turn's server-side state.

    `stage` is fixed when the turn is claimed, so the `started` event and the
    `completed` response cannot disagree about which stage the answer was written
    for.

    `stop` is the signal the streaming task waits on; the stop endpoint only ever
    sets it and never writes an event itself.

    There is deliberately no `stop_reason` here. The only way this event is ever
    set is the stop endpoint, so a stored reason could only ever read
    `client_stop`; `client_disconnect` is not a stop, it is a task cancellation
    recorded straight to `disconnected`. A field that cannot vary is a field that
    invites a caller to trust it.
    """

    turn_id: str
    session_id: str
    stage: Stage
    status: TurnStatus = "active"
    stop: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass(slots=True)
class SessionState:
    """One session: where the student is on the ladder, and what was said."""

    session_id: str
    stage: Stage = INITIAL_STAGE
    history: list[Turn] = field(default_factory=list)
    active_turn_id: str | None = None
    turns: dict[str, TurnRecord] = field(default_factory=dict)


def _new_id(prefix: str) -> str:
    """`prefix_<hex>`, matching `app.core.request_id.create_request_id`.

    The suffixes in the frozen samples are illustrative and the platform contract
    says the format is not settled, so this does not try to reproduce them.
    """

    return f"{prefix}_{uuid4().hex}"


class InMemoryTutoringRepository:
    """The S1 registry. Everything below is synchronous; see the module docstring."""

    def __init__(
        self,
        *,
        max_sessions: int = MAX_SESSIONS,
        max_turns: int = MAX_TURNS_PER_SESSION,
    ) -> None:
        self._max_sessions = max_sessions
        self._max_turns = max_turns
        #: An `OrderedDict` rather than a `dict` only because the eviction order
        #: is part of the design: `move_to_end` on every touch is what makes the
        #: oldest entry the least recently *used* rather than the first created.
        self._sessions: OrderedDict[str, SessionState] = OrderedDict()

    # --- reading ------------------------------------------------------------

    def session(self, session_id: str) -> SessionState:
        """The session, created if this is the first time it is seen.

        Opening a session on first use is what lets M2 post a question without a
        separate "create session" round trip.
        """

        existing = self._sessions.get(session_id)
        if existing is not None:
            self._sessions.move_to_end(session_id)
            return existing

        session = SessionState(session_id=session_id)
        self._sessions[session_id] = session
        self._evict_sessions()
        return session

    def turn(self, session_id: str, turn_id: str) -> TurnRecord:
        """The turn, or `UnknownTurnError`. Never creates one."""

        session = self._sessions.get(session_id)
        if session is None or turn_id not in session.turns:
            raise UnknownTurnError(session_id, turn_id)
        return session.turns[turn_id]

    def stage(self, session_id: str) -> Stage:
        return self.session(session_id).stage

    def history(self, session_id: str) -> tuple[Turn, ...]:
        return tuple(self.session(session_id).history)

    # --- the live turn ------------------------------------------------------

    def assert_can_claim(self, session_id: str) -> None:
        """Raise if a turn is already in flight. Claims nothing.

        Separate from `claim_turn` so the router can answer 409 as an ordinary
        JSON response *before* it commits to a streaming one. Claiming inside the
        stream generator would be worse than awkward: if the client disconnected
        first, the generator never runs, the claim is never released, and the
        session stays wedged for every later request.
        """

        self._require_idle(self.session(session_id))

    def claim_turn(self, session_id: str, requested_stage: Stage | None) -> TurnRecord:
        """Start a turn and freeze its stage.

        `requested_stage` only ever pulls the stage back, never forward; the
        clamping lives in `resolve_stage`, where it is tested on its own.
        """

        session = self.session(session_id)
        self._require_idle(session)

        record = TurnRecord(
            turn_id=_new_id("turn"),
            session_id=session_id,
            stage=resolve_stage(session.stage, requested_stage),
        )
        session.active_turn_id = record.turn_id
        session.turns[record.turn_id] = record
        self._evict_turns(session)
        return record

    def complete_turn(
        self,
        session_id: str,
        turn_id: str,
        *,
        student_content: str,
        assistant_content: str,
    ) -> None:
        """Settle a successful turn: advance the ladder and remember the exchange.

        Advancing here rather than when the frame reaches the client is
        deliberate. The stage counts *successful* turns, and delivery cannot be
        confirmed on a stream the client may have walked away from.

        **Calling convention for the writer.** The stop check and this call must
        be separated by no `await`, and the terminal frame is yielded only after
        both. That single-threaded run is what makes stop and completion
        mutually exclusive without a lock: a stop that arrived earlier has
        already flipped the status and the writer emits `stopped` instead of
        getting here, while a stop that arrives later finds the status settled
        and changes nothing. So this method has no `active` guard -- adding one
        would be code no ordering can reach.
        """

        record = self.turn(session_id, turn_id)
        session = self.session(session_id)

        record.status = "completed"
        session.active_turn_id = None
        session.stage = advance_stage(record.stage)
        session.history.extend(
            [
                Turn(role="student", content=student_content),
                Turn(role="assistant", content=assistant_content),
            ]
        )
        del session.history[:-MAX_HISTORY_MESSAGES]

    def settle_failed_turn(self, session_id: str, turn_id: str, status: FailedTurnStatus) -> None:
        """Settle a turn that produced nothing usable.

        The ladder does not move and nothing is appended to the history. Both are
        the contract's rule that a half answer must not let a student skip a stage
        (`packages/contracts/tutoring/sse-events.md:104-152`), and a half answer
        must not become context for the next one either.

        The already-settled guard is reachable, unlike `complete_turn`'s absent
        one: a stop can land while the writer is mid-`await` on the model, and
        the writer then reports the failure it hit. The student has already been
        told the turn stopped, so the stop stands and this becomes a no-op.
        """

        record = self.turn(session_id, turn_id)
        if record.status != "active":
            return
        record.status = status
        self.session(session_id).active_turn_id = None

    def request_stop(self, session_id: str, turn_id: str) -> TurnStatus:
        """Ask the live turn to stop, and report where it got to. Idempotent.

        Returns the status *after* the call, so a repeat, or a stop that arrived
        after the turn already settled, reports what actually happened instead of
        pretending to have stopped something. Only an `active` turn is affected:
        once a turn has settled there is nothing left to stop, and emitting a
        second terminal event is exactly what the contract forbids.
        """

        record = self.turn(session_id, turn_id)
        if record.status == "active":
            record.status = "stopped"
            record.stop.set()
            self.session(session_id).active_turn_id = None
        return record.status

    # --- internals ----------------------------------------------------------

    def _require_idle(self, session: SessionState) -> None:
        """The one definition of "this session is busy", shared by the two callers."""

        if session.active_turn_id is not None:
            raise TurnInProgressError(session.active_turn_id)

    # --- bounds -------------------------------------------------------------

    def _evict_sessions(self) -> None:
        """Drop the least recently used idle session, losing its stage and history.

        A turn in flight is never a candidate: evicting one would break a stream
        already being delivered, and that is worse than using more memory than
        planned. So when every session is busy the cap is simply exceeded.
        """

        idle = [
            session_id
            for session_id, session in self._sessions.items()
            if session.active_turn_id is None
        ]
        excess = len(self._sessions) - self._max_sessions
        for session_id in idle[: max(excess, 0)]:
            del self._sessions[session_id]

    def _evict_turns(self, session: SessionState) -> None:
        """Keep the most recent settled turns, for the same reasons as above.

        The point of keeping any of them is that M2 may send a stop the instant it
        sees `completed`; evicting the turn immediately would turn that legitimate
        call into a 404.
        """

        settled = [
            turn_id for turn_id, record in session.turns.items() if record.status != "active"
        ]
        excess = len(session.turns) - self._max_turns
        for turn_id in settled[: max(excess, 0)]:
            del session.turns[turn_id]
