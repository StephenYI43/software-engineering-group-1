"""The Mock's optional response envelope (Issue #59).

`envelope=True` is what lets the SSE service run end to end against a frozen
sample. These tests tie the appended bytes back to those samples, so the Mock
cannot drift away from the contract it stands in for.

The flag defaults to **off** precisely so `test_tutoring_adapters_mock.py` keeps
passing untouched; that file is the regression guard for everything above.
"""

import asyncio
import json
from pathlib import Path

import pytest

from app.domains.tutoring.adapters import (
    MockModelClient,
    ModelRequest,
    RetrievedChunk,
    TextDelta,
)
from app.domains.tutoring.envelope import (
    RESPONSE_CLOSE,
    RESPONSE_OPEN,
    BodyEnvelopeSplitter,
    EnvelopeOutcome,
)

_SAMPLES = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "tutoring" / "samples"

_CHUNK = RetrievedChunk(
    document_id="doc_9a2f4c",
    document_title="高等数学-上册-第1章.pdf",
    page_number=12,
    text="设函数 f(x) 在点 a 的某个去心邻域内有定义。",
)


def _request(chunks: tuple[RetrievedChunk, ...] = (_CHUNK,)) -> ModelRequest:
    return ModelRequest(
        request_id="req_8d1f0c33",
        prompt_version="guided-tutoring.v1",
        model_name="mock",
        system_prompt="prompt",
        turns=(),
        retrieved_chunks=chunks,
        max_output_tokens=1024,
        temperature=0.0,
        timeout_seconds=30.0,
    )


async def _texts(*, envelope: bool, chunks: tuple[RetrievedChunk, ...] = (_CHUNK,)) -> list[str]:
    client = MockModelClient(envelope=envelope)
    return [
        chunk.text
        async for chunk in client.generate(_request(chunks))
        if isinstance(chunk, TextDelta)
    ]


def _body_and_envelope(
    *, envelope: bool, chunks: tuple[RetrievedChunk, ...] = (_CHUNK,)
) -> tuple[list[str], EnvelopeOutcome]:
    """Run the Mock through the real splitter, so the two are checked together."""

    splitter = BodyEnvelopeSplitter()
    pieces: list[str] = []
    for text in asyncio.run(_texts(envelope=envelope, chunks=chunks)):
        pieces.extend(splitter.feed(text))
    return pieces, splitter.finish()


def _sample(name: str) -> dict[str, object]:
    return json.loads((_SAMPLES / name).read_text(encoding="utf-8"))


# --- the flag's shape -------------------------------------------------------


def test_the_envelope_is_one_extra_chunk() -> None:
    """The script is untouched; the envelope rides along as one more text chunk."""

    without = asyncio.run(_texts(envelope=False))
    with_envelope = asyncio.run(_texts(envelope=True))

    assert with_envelope[:-1] == without
    assert len(with_envelope) == len(without) + 1
    assert RESPONSE_OPEN in with_envelope[-1]
    assert RESPONSE_CLOSE in with_envelope[-1]


def test_the_envelope_chunk_holds_one_newline() -> None:
    """The template puts the envelope on its own line, and the JSON itself must
    stay single-line -- a `data:` field with a newline in it would split the SSE
    frame."""

    piece = asyncio.run(_texts(envelope=True))[-1]

    assert piece.startswith("\n")
    assert piece.count("\n") == 1


def test_the_envelope_is_not_leaked_into_the_prose() -> None:
    """Nothing between the markers reaches a `delta`; only the separator newline
    does, which is what keeps `delta` prose-only."""

    pieces, outcome = _body_and_envelope(envelope=True)

    assert "".join(pieces) == outcome.body
    assert outcome.body.endswith("\n")
    assert outcome.failure is None
    assert outcome.envelope is not None
    for piece in pieces:
        assert RESPONSE_OPEN not in piece
        assert RESPONSE_CLOSE not in piece
        assert '"citations"' not in piece


def test_the_mock_stays_deterministic_with_the_envelope_on() -> None:
    assert asyncio.run(_texts(envelope=True)) == asyncio.run(_texts(envelope=True))


# --- agreement with the frozen samples --------------------------------------


def test_the_normal_envelope_matches_the_frozen_sample() -> None:
    """`normal` must reproduce `01-thought-with-citation.json`.

    The body differs from that sample by exactly the separator newline: the
    sample predates the envelope convention, which the template introduced
    afterwards. That is written down here rather than smoothed over, because
    `content` must equal the concatenated deltas character for character and the
    newline is dispatched before the marker is recognised
    (`samples/05-sse-stream.txt:26-27`).
    """

    sample = _sample("01-thought-with-citation.json")
    _, outcome = _body_and_envelope(envelope=True)

    assert outcome.envelope is not None
    assert outcome.envelope.follow_ups == sample["followUps"]
    assert outcome.envelope.emotion == sample["emotion"]
    assert outcome.envelope.action == sample["action"]
    assert outcome.envelope.citations == ["c1"]
    assert outcome.body == f"{sample['content']}\n"


def test_the_no_evidence_envelope_matches_the_frozen_sample() -> None:
    """`no_evidence` must reproduce `03-no-evidence.json`."""

    sample = _sample("03-no-evidence.json")
    _, outcome = _body_and_envelope(envelope=True, chunks=())

    assert outcome.envelope is not None
    assert outcome.envelope.follow_ups == sample["followUps"]
    assert outcome.envelope.emotion == sample["emotion"]
    assert outcome.envelope.action == sample["action"]
    assert outcome.envelope.citations == []
    assert outcome.body == f"{sample['content']}\n"


@pytest.mark.parametrize("chunks", [(), (_CHUNK,)])
def test_a_claim_with_no_label_behind_it_is_not_made(
    chunks: tuple[RetrievedChunk, ...],
) -> None:
    """Labels come from the server's allow-list step, so with no retrieved chunks
    there is no `c1` to cite.

    A mock that claimed one regardless would be inventing a citation, and the
    allow-list rule would then never be exercised by the tests.
    """

    _, outcome = _body_and_envelope(envelope=True, chunks=chunks)

    assert outcome.envelope is not None
    assert outcome.envelope.citations == (["c1"] if chunks else [])
