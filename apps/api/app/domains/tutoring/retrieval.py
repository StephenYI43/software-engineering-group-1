"""Retrieval, behind the seam the tutoring service depends on.

S1 has no vector store, no parsed PDFs and no database, so the concrete retriever
here hands back a fixed passage. It exists for two reasons: the service can be
driven end to end without them, and the real retrieval from #53 can be dropped in
without the service changing.

The default passage is the citation in `samples/01-thought-with-citation.json`,
which is what lets the end-to-end test compare a whole response against a frozen
sample rather than against itself.
"""

from collections.abc import Sequence
from typing import Protocol

from app.domains.tutoring.adapters import RetrievedChunk

__all__ = ["DEFAULT_CHUNK", "RetrievalError", "Retriever", "StaticRetriever"]

#: The one passage S1 retrieves, matching the frozen sample's citation exactly.
DEFAULT_CHUNK = RetrievedChunk(
    document_id="doc_9a2f4c",
    document_title="高等数学-上册-第1章.pdf",
    page_number=12,
    text=(
        "设函数 f(x) 在点 a 的某个去心邻域内有定义。如果存在常数 L，使得对于任意给定的正数 ε，"
        "总存在正数 δ，当 0 < |x - a| < δ 时，有 |f(x) - L| < ε，则称 L 为函数 f(x) 当 x→a "
        "时的极限。"
    ),
)

#: How many passages one turn may carry. Also the citation-label range.
DEFAULT_LIMIT = 5


class RetrievalError(RuntimeError):
    """Retrieval could not answer. The service maps this to `RETRIEVAL_UNAVAILABLE`."""


class Retriever(Protocol):
    """What the service depends on; it never sees a concrete retriever."""

    async def retrieve(
        self, *, query: str, course_id: str | None, limit: int
    ) -> Sequence[RetrievedChunk]:
        """Passages to ground one turn. Raises `RetrievalError` on failure."""
        ...


class StaticRetriever:
    """A deterministic retriever for S1.

    `chunks` is what it returns and `unavailable` makes it raise instead, which
    is how the service's `RETRIEVAL_UNAVAILABLE` path is reached. Both are
    ordinary constructor arguments rather than test-only back doors, so a caller
    can also configure an empty result without patching anything.

    `query` and `course_id` are accepted and ignored: a real retriever narrows by
    both, but pretending to here would only imply S1 filters when it does not.
    """

    def __init__(
        self,
        chunks: Sequence[RetrievedChunk] | None = None,
        *,
        unavailable: bool = False,
    ) -> None:
        self._chunks = tuple(chunks) if chunks is not None else (DEFAULT_CHUNK,)
        self._unavailable = unavailable

    async def retrieve(
        self, *, query: str, course_id: str | None, limit: int
    ) -> Sequence[RetrievedChunk]:
        if self._unavailable:
            raise RetrievalError("retrieval is unavailable")
        return self._chunks[:limit]
