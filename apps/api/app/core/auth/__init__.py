"""Authentication primitives for S1 (Issue #45).

Login, credential issuance, session tokens and logout live here. Authorization
dependencies (`require_user` / `require_teacher` / course ACL) belong to
Issue #16 and consume `SessionAuthority.parse`.
"""
