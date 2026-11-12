"""Learning domain (M5): courses, homework, mistakes, study plans.

S1 skeleton per Issue #42 -- schemas layer and an in-memory repository only.
There is no router, service or authentication here yet: those land with #16
(auth/session) and the M3 planSuggestion delivery interface. Migration files
are intentionally absent until the #48 database plan is frozen.

Field contracts: packages/contracts/learning/ (S0 v2, merged in PR #26).
Layering: docs/code-standards.md:33 (router / schemas / service / repository).
"""
