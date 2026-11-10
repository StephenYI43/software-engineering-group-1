"""Explicit operator command for persistent identity binding and revocation."""

import argparse
import hashlib
from datetime import UTC, datetime

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.core.db.models import AuthSession, ExternalIdentity, User
from app.core.db.repository import PlatformRepository, new_id
from app.core.db.session import Database, load_database_url
from app.core.request_id import create_request_id


def configure_identity(
    session: Session,
    *,
    provider: str,
    issuer: str,
    subject: str,
    user_id: str,
    revoke: bool = False,
) -> None:
    """Operator already owns DB credentials. Never grants a role or reassigns an identity."""
    if provider not in {"github", "wechat", "school", "sms"} or any(
        not value.strip() or len(value) > 255 for value in (issuer, subject)
    ):
        raise ValueError("Invalid identity provider, issuer or subject")
    if provider == "github" and (
        issuer != "https://github.com" or not subject.isascii() or not subject.isdigit()
    ):
        raise ValueError("GitHub requires its fixed issuer and numeric user ID")
    if provider == "sms" and issuer != "phone:e164":
        raise ValueError("SMS requires the phone:e164 issuer")
    digest = hashlib.sha256(f"{provider}\0{issuer}\0{subject}".encode()).digest()
    lock_id = int.from_bytes(digest[:8], "big", signed=True)
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
    binding = session.scalar(
        select(ExternalIdentity)
        .where(
            ExternalIdentity.provider == provider,
            ExternalIdentity.issuer == issuer,
            ExternalIdentity.subject == subject,
        )
        .with_for_update()
    )
    if binding is not None and binding.user_id != user_id:
        raise ValueError("Identity is already assigned to another user")
    if revoke:
        if binding is None or binding.revoked_at is not None:
            return
        binding.revoked_at = datetime.now(UTC)
        session.execute(
            update(AuthSession)
            .where(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC), revoke_reason="admin_revoke")
        )
        action = "external_identity_revoked"
    else:
        user = session.get(User, user_id)
        if user is None or user.status != "active":
            raise ValueError("Binding requires an active local account")
        if binding is not None and binding.revoked_at is None:
            return
        if binding is None:
            binding = ExternalIdentity(
                id=new_id("identity"),
                provider=provider,
                issuer=issuer,
                subject=subject,
                user_id=user_id,
            )
            session.add(binding)
        binding.revoked_at = None
        action = "external_identity_bound"
    session.flush()
    PlatformRepository(session).audit(
        actor_user_id=None,
        action=action,
        target_type="external_identities",
        target_id=binding.id,
        request_id=create_request_id(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True, choices=["github", "wechat", "school", "sms"])
    parser.add_argument("--issuer", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--revoke", action="store_true")
    args = parser.parse_args()
    url = load_database_url()
    if url is None:
        raise SystemExit("DATABASE_URL is required")
    database = Database(url)
    try:
        with database.sessions.begin() as session:
            configure_identity(
                session,
                provider=args.provider,
                issuer=args.issuer,
                subject=args.subject,
                user_id=args.user_id,
                revoke=args.revoke,
            )
    finally:
        database.close()
    print("Identity operation completed; no credentials or provider subject logged.")


if __name__ == "__main__":
    main()
