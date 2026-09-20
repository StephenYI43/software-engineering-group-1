"""Deterministic offline model client for development, tests and CI.

Zero configuration, no network, no real clock, no unseeded randomness: the same
request always produces byte-identical chunks (`docs/adr/0002-model-adapter.md`,
"离线 Mock 的确定性"). The scenario is chosen from an explicit key or from the
request's *shape* -- never from the student's text, which would be both a privacy
smell and unstable whenever a prompt changes.

Scenario coverage in this first slice is `normal` and `no_evidence`. The ADR also
requires `refused`, `timeout`, `invalid_output`, `thinking_only` and
`slow_cancellable`; those need the adapter's error types and follow in a later
slice, so they are absent rather than faked here.
"""

import asyncio
from collections.abc import AsyncIterator, Sequence

from app.domains.tutoring.adapters.base import ModelRequest
from app.domains.tutoring.adapters.chunks import Finished, ModelChunk, TextDelta, Usage

__all__ = ["SCENARIOS", "MockModelClient"]

# Fixed chunk boundaries. Each script concatenates to the `content` of a frozen
# sample under `packages/contracts/tutoring/samples/`, which is what lets the
# tests prove the adapter reproduces the frozen contract without changing it.
_SCRIPTS: dict[str, tuple[str, ...]] = {
    "normal": (
        "我们先不急着写出定义。",
        "你想一想，说「当 x 靠近 a 时",
        " f(x) 趋近 L」",
        "，这里的「靠近」是一种动态描述——",
        "那我怎么用一个确定的、可以检验的说法，来代替这个「靠近」呢？",
        "\n\n提示你一个方向：既然要「可以检验」，就得分清楚谁先给定、谁随之确定。",
        "你先说说看，在这个定义里，应该先给定哪一个量？",
    ),
    "no_evidence": (
        "这个问题我在当前课程的课件里没有找到相关依据，",
        "所以我不给你一个可能不准确的结论。",
        "\n\n我检索的范围是这门高等数学课程的已授权课件，其中没有覆盖到这个主题。你可以：\n\n",
        "1. 换一种问法，或者确认一下这个知识点是否属于本课程范围；",
        "\n2. 如果你是想要延伸学习，",
        "我可以基于课程内已讲过的相关概念（比如导数的定义）帮你梳理思路，",
        "但那属于课程外的延伸，我会明确标注。",
        "\n\n你希望我怎么做？",
    ),
}

SCENARIOS: frozenset[str] = frozenset(_SCRIPTS)


def _placeholder_token_count(texts: Sequence[str]) -> int:
    """A deterministic stand-in, not a tokenizer: two characters per token.

    The exact number is meaningless; what matters is that it is a pure function
    of the request and the script, so CI output never moves.
    """

    return sum(len(text) for text in texts) // 2


class MockModelClient:
    """An in-process `ModelClient` that never touches the network.

    With `scenario=None` the script follows the request's shape: an empty
    `retrieved_chunks` means there is nothing to cite, so the no-evidence script
    runs. `latency_seconds` is injectable so cancellation stays testable; CI
    keeps it at `0`.
    """

    def __init__(self, *, scenario: str | None = None, latency_seconds: float = 0.0) -> None:
        if scenario is not None and scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario: {scenario!r}; expected one of {sorted(SCENARIOS)}")
        if latency_seconds < 0:
            raise ValueError("latency_seconds must not be negative")
        self._scenario = scenario
        self._latency_seconds = latency_seconds
        self._closed = False

    async def generate(self, request: ModelRequest) -> AsyncIterator[ModelChunk]:
        if self._closed:
            raise RuntimeError("model client is closed")
        script = _SCRIPTS[self._select_scenario(request)]
        for piece in script:
            if self._latency_seconds:
                await asyncio.sleep(self._latency_seconds)
            yield TextDelta(text=piece)
        yield Usage(
            input_tokens=_placeholder_token_count(
                [request.system_prompt, *(turn.content for turn in request.turns)]
            ),
            output_tokens=_placeholder_token_count(script),
        )
        yield Finished(stop_reason="stop")

    async def aclose(self) -> None:
        """The Mock owns no resources; the flag keeps the protocol's
        "safe to call repeatedly" rule enforceable and testable."""
        self._closed = True

    def _select_scenario(self, request: ModelRequest) -> str:
        if self._scenario is not None:
            return self._scenario
        return "normal" if request.retrieved_chunks else "no_evidence"
