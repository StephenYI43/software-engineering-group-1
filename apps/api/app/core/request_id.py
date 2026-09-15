"""Generate server-owned request identifiers without trusting incoming headers."""

from uuid import uuid4


def create_request_id() -> str:
    return f"req_{uuid4().hex}"
