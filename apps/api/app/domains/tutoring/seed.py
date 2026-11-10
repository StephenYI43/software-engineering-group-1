"""Idempotent tutoring version seeds. Prompt body stays in Git, not in the database."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

from app.domains.tutoring.models import ModelConfigVersion, PromptVersion

PROMPT_SEED_ID = "promptver_11111111111111111111111111111111"
MODEL_SEED_ID = "modelcfg_11111111111111111111111111111111"
PROMPT_PATH = Path("ai/prompts/guided-tutoring.v1.md")


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / PROMPT_PATH).is_file():
            return candidate
    raise FileNotFoundError(f"Cannot locate {PROMPT_PATH} from {here}")


def prompt_content_sha256() -> str:
    return hashlib.sha256((_repo_root() / PROMPT_PATH).read_bytes()).hexdigest()


def seed_tutoring_versions(session) -> None:
    """Register the published prompt and the S1 mock model config if missing."""
    if session.get(PromptVersion, PROMPT_SEED_ID) is None and session.scalar(
        select(PromptVersion.id).where(
            PromptVersion.series == "guided-tutoring",
            PromptVersion.version_label == "guided-tutoring.v1",
        )
    ) is None:
        now = session.scalar(select(func.now())) or datetime.now(UTC)
        session.add(
            PromptVersion(
                id=PROMPT_SEED_ID,
                series="guided-tutoring",
                version_label="guided-tutoring.v1",
                template_path=PROMPT_PATH.as_posix(),
                content_sha256=prompt_content_sha256(),
                status="active",
                activated_at=now,
            )
        )
    if session.get(ModelConfigVersion, MODEL_SEED_ID) is None and session.scalar(
        select(ModelConfigVersion.id).where(
            ModelConfigVersion.config_key == "tutoring_default",
            ModelConfigVersion.version == 1,
        )
    ) is None:
        now = session.scalar(select(func.now())) or datetime.now(UTC)
        session.add(
            ModelConfigVersion(
                id=MODEL_SEED_ID,
                config_key="tutoring_default",
                version=1,
                provider="mock",
                model_name="mock-tutoring",
                is_mock=True,
                temperature=0,
                max_output_tokens=2048,
                timeout_seconds=30,
                status="active",
                activated_at=now,
            )
        )
