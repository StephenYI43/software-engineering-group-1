"""Unit tests for the body/envelope splitter (Issue #59).

There is really one risk here: **a marker cut in half at a `feed` boundary**.
Streaming text is chopped at whatever pace the model emits, and we do not choose
the cut points, so a split-sensitive bug reproduces only at some chunk sizes --
which is exactly the kind that survives into production.

The counter is to treat the cut points as a parameter: run the same output
through every chunk size from 1 to its length and require identical results.
"""

import pytest

from app.domains.tutoring.envelope import (
    MAX_FOLLOW_UP_CHARS,
    RESPONSE_CLOSE,
    RESPONSE_OPEN,
    BodyEnvelopeSplitter,
    EnvelopeOutcome,
)

#: A realistic model output: prose, a newline, then the single-line JSON envelope.
_BODY = (
    "Start with the step you wrote: substituting the value was the right direction.\n"
    "Now think about the units on the left-hand side."
)
_ENVELOPE = (
    '{"citations": ["c1", "c2"], "followUps": ["Try a different order"],'
    ' "emotion": "encouraging", "action": "nod"}'
)
_OUTPUT = f"{_BODY}\n{RESPONSE_OPEN}{_ENVELOPE}{RESPONSE_CLOSE}"


def _run(text: str, size: int) -> tuple[list[str], EnvelopeOutcome]:
    """Feed all of `text` in fixed-size chunks; return (emitted pieces, outcome)."""

    splitter = BodyEnvelopeSplitter()
    emitted: list[str] = []
    for start in range(0, len(text), size):
        emitted.extend(splitter.feed(text[start : start + size]))
    return emitted, splitter.finish()


def _envelope(payload: str) -> str:
    return f"{_BODY}\n{RESPONSE_OPEN}{payload}{RESPONSE_CLOSE}"


# --- happy path -------------------------------------------------------------


def test_body_and_envelope_are_separated() -> None:
    emitted, outcome = _run(_OUTPUT, len(_OUTPUT))

    assert "".join(emitted) == f"{_BODY}\n"
    assert outcome.body == f"{_BODY}\n"
    assert outcome.failure is None
    assert outcome.envelope is not None
    assert outcome.envelope.citations == ["c1", "c2"]
    assert outcome.envelope.follow_ups == ["Try a different order"]
    assert outcome.envelope.emotion == "encouraging"
    assert outcome.envelope.action == "nod"


def test_body_property_is_the_concatenated_pieces() -> None:
    """`body` is the single source of truth for sent prose; the service uses it
    instead of accumulating deltas itself."""

    splitter = BodyEnvelopeSplitter()
    emitted: list[str] = []
    for start in range(0, len(_OUTPUT), 5):
        emitted.extend(splitter.feed(_OUTPUT[start : start + 5]))

    assert splitter.body == "".join(emitted)
    assert splitter.body == f"{_BODY}\n"


def test_every_chunking_yields_the_same_body() -> None:
    """Cut-point equivalence -- the only strong evidence a marker was not split.

    If the splitter ever cut a marker in half, some chunk size would leak marker
    characters into the concatenation and this goes red. Feeding the whole output
    in one piece cannot catch that.
    """

    for size in range(1, len(_OUTPUT) + 1):
        emitted, outcome = _run(_OUTPUT, size)

        assert "".join(emitted) == f"{_BODY}\n", f"prose rewritten at chunk size {size}"
        assert outcome.failure is None, f"envelope lost at chunk size {size}"
        assert outcome.envelope is not None
        assert outcome.envelope.citations == ["c1", "c2"]


def test_no_prefix_of_the_marker_is_ever_emitted() -> None:
    """Feed one character at a time; what has been sent is always a prefix of the
    prose. Stronger than end-state equality: it asserts *during* the run, so a
    leak points straight at the step that produced it."""

    splitter = BodyEnvelopeSplitter()
    emitted = ""

    for char in _OUTPUT:
        for piece in splitter.feed(char):
            emitted += piece
        assert f"{_BODY}\n".startswith(emitted), f"sent text left the prose: {emitted!r}"


def test_empty_body_is_allowed() -> None:
    """An envelope-only output is not an error; it just has no prose to show."""

    emitted, outcome = _run(_OUTPUT.replace(f"{_BODY}\n", "", 1), 3)

    assert emitted == []
    assert outcome.body == ""
    assert outcome.failure is None


def test_finish_is_repeatable() -> None:
    """`finish` only reads, so a second call agrees -- which is why the service
    needs no re-entry guard."""

    splitter = BodyEnvelopeSplitter()
    splitter.feed(_OUTPUT)

    assert splitter.finish() == splitter.finish()


def test_text_after_the_closing_marker_is_kept_but_never_emitted() -> None:
    """Output past the closing marker lands in `trailing` for log triage and is
    never sent as prose."""

    splitter = BodyEnvelopeSplitter()
    emitted = splitter.feed(f"{_OUTPUT}\nThat is all.")
    outcome = splitter.finish()

    assert "That is all." not in "".join(emitted)
    assert splitter.trailing == "\nThat is all."
    assert outcome.failure is None


def test_feeding_after_the_envelope_is_closed_does_not_emit() -> None:
    splitter = BodyEnvelopeSplitter()
    splitter.feed(_OUTPUT)

    assert splitter.feed("more text") == ()
    assert splitter.trailing == "more text"


# --- failure paths ----------------------------------------------------------


def test_missing_envelope_is_reported() -> None:
    """No opening marker anywhere means no structured fields, so the turn is void."""

    emitted, outcome = _run("Prose with no envelope at all.", 4)

    assert outcome.failure == "missing"
    assert outcome.envelope is None
    assert "".join(emitted) == outcome.body


def test_holdback_tail_is_not_flushed_on_failure() -> None:
    """A failed split does not flush the look-back window.

    What the window holds are characters that *might* have started a marker.
    Sending them out on a void stream would add text of unknown provenance for no
    benefit and one more leak surface.
    """

    text = "prose " * 8
    emitted, outcome = _run(text, len(text))

    assert outcome.failure == "missing"
    assert "".join(emitted) == outcome.body
    assert len(text) - len(outcome.body) == len(RESPONSE_OPEN) - 1


def test_unterminated_envelope_is_reported() -> None:
    """An opening marker with no closing one means the envelope is incomplete."""

    emitted, outcome = _run(f"{_BODY}\n{RESPONSE_OPEN}{_ENVELOPE}", 5)

    assert outcome.failure == "unterminated"
    assert outcome.envelope is None
    assert "".join(emitted) == f"{_BODY}\n"


def test_malformed_json_is_reported() -> None:
    emitted, outcome = _run(_envelope('{"citations": ["c1"'), 7)

    assert outcome.failure == "parse_failed"
    assert outcome.envelope is None
    assert "".join(emitted) == f"{_BODY}\n"


def test_json_that_is_not_an_object_is_reported() -> None:
    """An envelope must be a JSON object; an array or string will not do, however
    well it parses."""

    _, outcome = _run(_envelope('["c1"]'), 7)

    assert outcome.failure == "invalid"
    assert outcome.envelope is None


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param('{"emotion": "angry", "action": "nod"}', id="emotion-not-in-enum"),
        pytest.param('{"emotion": "neutral", "action": "shrug"}', id="action-not-in-enum"),
        pytest.param('{"action": "nod"}', id="emotion-absent"),
        pytest.param('{"emotion": "neutral"}', id="action-absent"),
        pytest.param(
            '{"emotion": "neutral", "action": "nod", "followUps": ["a", "b", "c", "d"]}',
            id="followUps-over-three",
        ),
        pytest.param(
            '{"emotion": "neutral", "action": "nod", "followUps": ["'
            + "x" * (MAX_FOLLOW_UP_CHARS + 1)
            + '"]}',
            id="followUps-entry-too-long",
        ),
    ],
)
def test_structurally_invalid_envelope_is_reported(payload: str) -> None:
    """A field that breaks the contract voids the output; it is **not** repaired.

    Truncating or defaulting would make "the model stopped honouring the
    contract" permanently invisible -- and during S1 that is precisely what we
    need to see. The accepted bounds (exactly 3 entries, exactly 200 characters)
    are covered by the next test.
    """

    _, outcome = _run(_envelope(payload), 9)

    assert outcome.failure == "invalid"
    assert outcome.envelope is None


def test_upper_bound_values_are_accepted() -> None:
    """The bounds themselves are legal: 3 entries of 200 characters must pass, or
    the limits are really 2 and 199."""

    payload = (
        '{"emotion": "neutral", "action": "idle", "followUps": ["'
        + "x" * MAX_FOLLOW_UP_CHARS
        + '", "b", "c"]}'
    )
    _, outcome = _run(_envelope(payload), 11)

    assert outcome.failure is None
    assert outcome.envelope is not None
    assert len(outcome.envelope.follow_ups) == 3


@pytest.mark.parametrize(
    "extra",
    [
        pytest.param('"confidence": 0.8', id="new-field"),
        # A snake_case spelling is an unknown field too, so it is ignored and
        # `followUps` degrades to an empty list. That is a direct consequence of
        # extra="ignore" and it is written down because it is a **silent
        # downgrade**: the template mandates camelCase, and a model that ignores
        # that loses suggested follow-ups rather than the answer itself, so this
        # tolerates it instead of failing the turn.
        pytest.param('"follow_ups": ["try again"]', id="snake-case-spelling"),
    ],
)
def test_unknown_fields_are_ignored_without_defaulting_follow_ups(extra: str) -> None:
    """Unknown fields are ignored: adding one is a normal prompt-version bump and
    should not fail a whole turn."""

    _, outcome = _run(_envelope(f'{{"emotion": "neutral", "action": "idle", {extra}}}'), 6)

    assert outcome.failure is None
    assert outcome.envelope is not None
    assert outcome.envelope.follow_ups == []


def test_absent_optional_fields_default_to_empty() -> None:
    _, outcome = _run(_envelope('{"emotion": "neutral", "action": "idle"}'), 6)

    assert outcome.envelope is not None
    assert outcome.envelope.citations == []
    assert outcome.envelope.follow_ups == []


# --- text that looks like a marker ------------------------------------------


def test_marker_like_text_inside_the_body_ends_the_body() -> None:
    """Prose that happens to contain the marker string is treated as the envelope start.

    This is a deliberate trade-off: allowing arbitrary prose would need escaping
    on the model's side and the model does not escape. The cost is that such an
    output is void -- it is **neither fabricated nor a crash**. The prompt already
    tells the model not to emit the literal; fixing it properly means adding
    escaping to the protocol, which is a contract change outside this issue.
    """

    text = f"{_BODY}\nOne more thing {RESPONSE_OPEN} then the rest"
    emitted, outcome = _run(text, 4)

    # Text before the literal is still sent as prose; from it on, the splitter is
    # inside the envelope and never finds a closing marker.
    assert "".join(emitted) == f"{_BODY}\nOne more thing "
    assert outcome.failure == "unterminated"
    assert outcome.envelope is None
