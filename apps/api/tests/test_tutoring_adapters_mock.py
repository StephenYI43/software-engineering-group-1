"""Tests for the tutoring model adapter's offline Mock (Issue #28, slice 1).

This slice implements the happy path only, so the tests cover determinism,
scenario selection and lifecycle. Error mapping (`MODEL_TIMEOUT`,
`MODEL_REFUSED`, dropped reasoning deltas, cancellation) belongs to the slice
that adds the real client and is not exercised here.
"""

import asyncio
import json
import re
from dataclasses import fields, is_dataclass, replace
from pathlib import Path
from typing import get_args, get_type_hints

import pytest

from app.domains.tutoring.adapters import (
    Finished,
    MockModelClient,
    ModelChunk,
    ModelRequest,
    RetrievedChunk,
    TextDelta,
    Turn,
    Usage,
)
from app.domains.tutoring.adapters import chunks as chunks_module

_SAMPLES = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "tutoring" / "samples"

_EVIDENCE = RetrievedChunk(
    document_id="doc_9a2f4c",
    document_title="高等数学-上册-第1章.pdf",
    page_number=12,
    text="设函数 f(x) 在点 a 的某个去心邻域内有定义……",
)


def _request(*, with_evidence: bool = True) -> ModelRequest:
    return ModelRequest(
        request_id="req_8d1f0c33",
        prompt_version="guided-tutoring.v1",
        model_name="mock",
        system_prompt="（测试不校验提示词内容）",
        turns=(Turn(role="student", content="什么是极限？"),),
        retrieved_chunks=(_EVIDENCE,) if with_evidence else (),
        max_output_tokens=512,
        temperature=0.2,
        timeout_seconds=30.0,
    )


def _collect(client: MockModelClient, request: ModelRequest) -> list[ModelChunk]:
    async def drain() -> list[ModelChunk]:
        return [chunk async for chunk in client.generate(request)]

    return asyncio.run(drain())


def _deltas(chunks: list[ModelChunk]) -> list[TextDelta]:
    return [chunk for chunk in chunks if isinstance(chunk, TextDelta)]


def _content(chunks: list[ModelChunk]) -> str:
    return "".join(delta.text for delta in _deltas(chunks))


def _sample_content(name: str) -> str:
    raw = (_SAMPLES / name).read_text(encoding="utf-8")
    return str(json.loads(raw)["content"])


def test_happy_path_is_deltas_then_usage_then_finished() -> None:
    chunks = _collect(MockModelClient(), _request())
    assert [type(chunk) for chunk in chunks][-2:] == [Usage, Finished]
    assert {type(chunk) for chunk in chunks[:-2]} == {TextDelta}


def test_normal_output_reproduces_the_frozen_sample_content() -> None:
    chunks = _collect(MockModelClient(scenario="normal"), _request())
    assert _content(chunks) == _sample_content("01-thought-with-citation.json")


def test_no_evidence_output_reproduces_the_frozen_sample_content() -> None:
    chunks = _collect(MockModelClient(scenario="no_evidence"), _request(with_evidence=False))
    assert _content(chunks) == _sample_content("03-no-evidence.json")


def test_chunk_boundaries_match_the_frozen_sse_sample() -> None:
    """Seven deltas is why `05-sse-stream.txt` variant one runs `seq` 1..9."""
    deltas = _deltas(_collect(MockModelClient(scenario="normal"), _request()))
    variant_one = (_SAMPLES / "05-sse-stream.txt").read_text(encoding="utf-8").split("## 变体二")[0]
    visible = re.findall(r'"textDelta":"([^"]*)"', variant_one)
    assert len(visible) == 3, "样例只印出首两个与最后一个 delta，其余用省略号"
    assert len(deltas) == 7
    assert [deltas[0].text, deltas[-1].text] == [visible[0], visible[-1]]


def test_adapter_chunks_reproduce_the_frozen_seq_range() -> None:
    """Executable form of the ADR walkthrough: chunks -> the events of variant one.

    The server emits `started`, turns each `TextDelta` into one `delta`, logs the
    single `Usage` without sending it, and closes with `completed` once it sees
    `Finished`. That is exactly the `seq` 1..9 the frozen sample pins.
    """
    chunks = _collect(MockModelClient(scenario="normal"), _request())
    seq = 1  # `started`
    seq += len(_deltas(chunks))
    seq += 1  # `completed`
    assert seq == 9
    assert isinstance(chunks[-1], Finished)
    assert len([chunk for chunk in chunks if isinstance(chunk, Usage)]) == 1


def test_chunk_variants_are_closed() -> None:
    assert set(get_args(ModelChunk.__value__)) == {TextDelta, Usage, Finished}
    exposed = {
        name
        for name, value in vars(chunks_module).items()
        if isinstance(value, type) and is_dataclass(value)
    }
    assert exposed == {"TextDelta", "Usage", "Finished"}


def test_turn_role_is_a_closed_set() -> None:
    """`role` must stay a closed set, not degrade back to free text.

    The annotation is the only enforcement point: this dataclass deliberately
    does no runtime parsing, so a regression to `str` would let a typo reach a
    prompt while every other test still passed.
    """
    assert set(get_args(get_type_hints(Turn)["role"])) == {"student", "assistant"}


def test_chunks_carry_no_teaching_semantics() -> None:
    """`stage` / `citations` belong to the server, so no chunk may carry them."""
    assert {field.name for field in fields(TextDelta)} == {"text"}
    assert {field.name for field in fields(Usage)} == {"input_tokens", "output_tokens"}
    assert {field.name for field in fields(Finished)} == {"stop_reason"}
    assert "stage" not in {field.name for field in fields(ModelRequest)}


def test_same_request_yields_identical_chunks() -> None:
    request = _request()
    assert _collect(MockModelClient(), request) == _collect(MockModelClient(), request)


def test_scenario_follows_request_shape_when_not_given() -> None:
    assert _content(_collect(MockModelClient(), _request())) == _sample_content(
        "01-thought-with-citation.json"
    )
    assert _content(_collect(MockModelClient(), _request(with_evidence=False))) == _sample_content(
        "03-no-evidence.json"
    )


def test_explicit_scenario_overrides_request_shape() -> None:
    chunks = _collect(MockModelClient(scenario="no_evidence"), _request())
    assert _content(chunks) == _sample_content("03-no-evidence.json")


def test_scenario_is_not_derived_from_student_text() -> None:
    baseline = _collect(MockModelClient(), _request())
    reworded = replace(_request(), turns=(Turn(role="student", content="完全不同的提问"),))
    assert _collect(MockModelClient(), reworded) == baseline


def test_unknown_scenario_is_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="unknown scenario"):
        MockModelClient(scenario="refused")


def test_negative_latency_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        MockModelClient(latency_seconds=-0.1)


def test_injected_latency_preserves_the_chunk_sequence() -> None:
    assert _collect(MockModelClient(latency_seconds=0.001), _request()) == _collect(
        MockModelClient(), _request()
    )


def test_aclose_is_idempotent_and_stops_further_calls() -> None:
    async def drain() -> None:
        client = MockModelClient()
        await client.aclose()
        await client.aclose()
        with pytest.raises(RuntimeError, match="closed"):
            [chunk async for chunk in client.generate(_request())]

    asyncio.run(drain())
