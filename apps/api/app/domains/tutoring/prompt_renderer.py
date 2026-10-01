"""Loading and rendering the versioned prompt template.

Issue #59 fixes this module's location: it lives under the tutoring domain, not
under `ai/` and not in an adapter. `ai/` is a data directory, so Python placed
there escapes both mypy (`apps/api/pyproject.toml` has `files = ["app"]`) and
coverage (`ai/prompts/README.md:196-201`); adapters only transmit a prompt and
never render one (`docs/adr/0002-model-adapter.md`).

What rendering does, and nothing else (`ai/prompts/README.md:117-128`):

1. read the whole template file, **stripping nothing**;
2. pick **exactly one** stage block and put it at `{{stage_instruction}}`;
3. fill the other two slots;
4. render an empty value as `（无）`, never as an empty string.
"""

import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from app.domains.tutoring.adapters import RetrievedChunk
from app.domains.tutoring.stages import STAGE_ORDER, Stage

__all__ = [
    "EMPTY_SLOT_VALUE",
    "PromptTemplateError",
    "PromptTemplate",
    "citation_label",
    "citation_labels",
    "format_retrieved_passages",
    "load_prompt_template",
]

#: What an empty slot renders as (`ai/prompts/README.md:126-128`). The empty
#: string is wrong: `本轮允许引用的标签只有：``` reads as "cite whatever you like"
#: to a model, where `（无）` reads as "not a single one".
EMPTY_SLOT_VALUE: Final[str] = "（无）"

_PROMPTS_DIR_ENV: Final[str] = "TUTORING_PROMPTS_DIR"

#: Sentinel used to find the repository root by walking up from this file.
_REPO_SENTINEL: Final[tuple[str, ...]] = ("ai", "prompts")
_MAX_WALK_UP: Final[int] = 8

#: The **stem** is the prompt's identity; the **version** is read from the
#: filename and must never be written into code that produces a real response
#: (`ai/prompts/README.md:11-16`). Naming the stem here is unavoidable and is not
#: the version literal that rule is about.
_TEMPLATE_NAME: Final[re.Pattern[str]] = re.compile(r"^guided-tutoring\.v(?P<version>\d+)\.md$")

#: Line-anchored on purpose: a delimiter indented by a formatter must fail loudly
#: rather than be tolerated (`ai/prompts/README.md:136-140`). Tolerating it turns
#: "the template was quietly reformatted" into "rendering succeeded but the
#: content is misplaced", which is far harder to trace.
_STAGE_BLOCK: Final[re.Pattern[str]] = re.compile(
    r"^<<<STAGE:(?P<stage>[a-z]+)>>>\n(?P<body>.*?)^<<<END_STAGE>>>$",
    re.MULTILINE | re.DOTALL,
)

_SLOT: Final[re.Pattern[str]] = re.compile(r"\{\{(?P<slot>[a-z_]+)\}\}")


class PromptTemplateError(RuntimeError):
    """The template is missing, malformed, or does not match this renderer.

    Raised while the service is being assembled, so a broken prompt fails before
    the first byte of a stream rather than halfway through one.
    """


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """One loaded template, ready to render many turns.

    `version` is the filename stem and is echoed verbatim as `promptVersion`
    (`packages/contracts/tutoring/tutoring-response.md:78`): a version-bumped
    prompt keeps old evaluation results attributable.
    """

    version: str
    text: str
    stage_blocks: Mapping[Stage, str]

    def render(self, *, stage: Stage, chunks: Sequence[RetrievedChunk]) -> str:
        """The `systemPrompt` for one turn.

        `stage` reaches the model only through the rendered stage instruction;
        it is never a `ModelRequest` field, which ADR-0002 requires to stay
        absent. That is what the ADR means by "the rendered systemPrompt".
        """

        return _substitute(
            self.text,
            {
                "retrieved_passages": format_retrieved_passages(chunks),
                "citation_allowlist": ", ".join(citation_labels(chunks)),
                "stage_instruction": self.stage_blocks[stage],
            },
        )


def citation_label(index: int) -> str:
    """The label the server assigns to the `index`-th chunk (0-based).

    Labels are positional and server-allocated (`tutoring-response.md:104`); the
    model is only ever told which ones it may use. Passages and the allow-list
    both call this, so the two cannot disagree about what `c2` refers to.
    """

    return f"c{index + 1}"


def citation_labels(chunks: Sequence[RetrievedChunk]) -> tuple[str, ...]:
    """The allow-list for one turn, in retrieval order."""

    return tuple(citation_label(index) for index in range(len(chunks)))


def format_retrieved_passages(chunks: Sequence[RetrievedChunk]) -> str:
    """Render the data slot as delimited blocks (`ai/prompts/README.md:75-81`).

    `document_title` is deliberately absent: uploaders name their own files, so
    it is untrusted input and `tutoring-response.md:112-113` forbids putting it
    in a prompt. `id` and `page` are server-assigned instead, so neither is an
    injection surface.

    Passage text is stripped so the delimiters always sit alone on their own
    lines -- that boundary is the only thing telling the model where material
    ends, so stray whitespace from a parser would blur it.
    """

    blocks = [
        f"<<<RETRIEVED_PASSAGE id={citation_label(index)} page={chunk.page_number}>>>\n"
        f"{chunk.text.strip()}\n"
        f"<<<END_RETRIEVED_PASSAGE>>>"
        for index, chunk in enumerate(chunks)
    ]
    return "\n\n".join(blocks)


def load_prompt_template(directory: Path | None = None) -> PromptTemplate:
    """Load the current template, or raise `PromptTemplateError`.

    The current version is the highest one present: `ai/prompts/README.md:58-61`
    makes a new version the current one as soon as it lands, and only v1 exists
    today.
    """

    prompts_dir = directory or _prompts_dir_from_env() or _walk_up_to_prompts_dir(Path(__file__))
    path = _select_template(prompts_dir)
    text = path.read_text(encoding="utf-8")
    return PromptTemplate(
        version=path.stem,
        text=text,
        stage_blocks=_extract_stage_blocks(text),
    )


def _prompts_dir_from_env() -> Path | None:
    raw = os.environ.get(_PROMPTS_DIR_ENV)
    if not raw:
        return None
    path = Path(raw)
    if not path.is_dir():
        raise PromptTemplateError(f"{_PROMPTS_DIR_ENV} is not a directory: {raw}")
    return path


def _walk_up_to_prompts_dir(start: Path) -> Path:
    """The nearest `ai/prompts` above `start`, or raise `PromptTemplateError`."""

    for parent in list(start.resolve().parents)[:_MAX_WALK_UP]:
        candidate = parent.joinpath(*_REPO_SENTINEL)
        if candidate.is_dir():
            return candidate
    raise PromptTemplateError(
        f"no {'/'.join(_REPO_SENTINEL)} directory within {_MAX_WALK_UP} levels of "
        f"{start.resolve()}; set {_PROMPTS_DIR_ENV} instead"
    )


def _select_template(prompts_dir: Path) -> Path:
    if not prompts_dir.is_dir():
        raise PromptTemplateError(f"prompt directory does not exist: {prompts_dir}")

    candidates: list[tuple[int, Path]] = []
    for entry in sorted(prompts_dir.iterdir()):
        match = _TEMPLATE_NAME.match(entry.name)
        if match is not None and entry.is_file():
            candidates.append((int(match.group("version")), entry))

    if not candidates:
        raise PromptTemplateError(f"no versioned prompt template in {prompts_dir}")
    return max(candidates, key=lambda candidate: candidate[0])[1]


def _extract_stage_blocks(text: str) -> Mapping[Stage, str]:
    """Pull the stage library out of the template.

    Every stage on the ladder needs exactly one block, and no block may name a
    stage that is not on it. A partial match is the failure mode that matters:
    silently falling back to "no stage instruction" would send the model into a
    turn with no idea which step it is on.
    """

    found: dict[str, list[str]] = {}
    for match in _STAGE_BLOCK.finditer(text):
        found.setdefault(match.group("stage"), []).append(match.group(0))

    if set(found) != set(STAGE_ORDER):
        raise PromptTemplateError(
            f"stage blocks must be exactly {sorted(STAGE_ORDER)}, got {sorted(found)}"
        )

    duplicated = sorted(stage for stage, blocks in found.items() if len(blocks) > 1)
    if duplicated:
        raise PromptTemplateError(f"more than one block for stage(s): {duplicated}")

    return {stage: found[stage][0] for stage in STAGE_ORDER}


def _substitute(template: str, values: Mapping[str, str]) -> str:
    """Fill every `{{slot}}` in **one pass**.

    `re.sub` scans the original string and builds a new one, so text introduced
    by a replacement is never rescanned. That is the entire defence against a
    retrieved passage containing `{{citation_allowlist}}`: with successive
    `str.replace` calls an uploaded document would be substituted again and would
    get to decide which citations are allowed.
    """

    def replace(match: re.Match[str]) -> str:
        slot = match.group("slot")
        if slot not in values:
            raise PromptTemplateError(f"template has an unknown slot: {slot}")
        return values[slot].strip() or EMPTY_SLOT_VALUE

    return _SLOT.sub(replace, template)
