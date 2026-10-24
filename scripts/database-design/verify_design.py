"""Execute reference DESIGN in an empty disposable local PostgreSQL database.

Not an application test. Does not infer API, authorization, migrations or UI work.
"""

import hashlib
import json
import os
import re
import sys
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = json.loads(
    (ROOT / "docs/database-design/schema.json").read_text(encoding="utf-8")
)


def main():
    raw = os.environ["DESIGN_TEST_DATABASE_URL"]
    url = make_url(raw)
    if url.host not in ("localhost", "127.0.0.1") or not (url.database or "").endswith(
        "_test"
    ):
        raise ValueError("Refusing: require local disposable *_test database")
    dbname = url.database
    with psycopg.connect(
        host=url.host,
        port=url.port,
        user=url.username,
        password=url.password,
        dbname=dbname,
        connect_timeout=5,
        autocommit=True,
    ) as conn:

        def snapshot():
            result = {}
            for tab in INVENTORY["tables"]:
                keys = [c["name"] for c in tab["columns"] if c["primary"]]
                rows = conn.execute(
                    sql.SQL("SELECT * FROM {} ORDER BY {}").format(
                        sql.Identifier(tab["name"]),
                        sql.SQL(",").join(map(sql.Identifier, keys)),
                    )
                ).fetchall()
                result[tab["name"]] = {
                    "count": len(rows),
                    "digest": hashlib.sha256(
                        json.dumps(rows, default=str, ensure_ascii=False).encode()
                    ).hexdigest(),
                }
            return result

        if sys.argv[1:] == ["--read-existing"]:
            proof = json.loads(
                Path(os.environ["DESIGN_SNAPSHOT_PATH"]).read_text(encoding="utf-8")
            )
            assert proof["database"] == dbname and snapshot() == proof["tables"]
            print(
                "RESTART PASS: all 40 tables retain identical row counts, primary keys and field digests after PostgreSQL restart"
            )
            return
        if conn.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
        ).fetchone()[0]:
            raise ValueError("Refusing: database public schema is not empty")
        conn.execute(
            (ROOT / "docs/database-design/schema.sql").read_text(encoding="utf-8")
        )
        names = {
            x[0]
            for x in conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public'"
            )
        }
        assert names == {t["name"] for t in INVENTORY["tables"]}
        actual_columns = conn.execute(
            "SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name<>'v_learning_event_feed'"
        ).fetchone()[0]
        expected_columns = sum(len(t["columns"]) for t in INVENTORY["tables"])
        assert actual_columns == expected_columns
        print(
            f"DDL: {len(names)} tables / {actual_columns} columns; all FK definitions installed"
        )
        for t in INVENTORY["tables"]:
            actual = {
                x[0]
                for x in conn.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",
                    (t["name"],),
                )
            }
            assert actual == {c["name"] for c in t["columns"]}

        sys.path.insert(0, str(ROOT / "apps/api"))
        from app.core.auth.tokens import SessionAuthority
        from app.core.db.repository import DatabaseSessionStore, PlatformRepository
        from app.core.db.seed import seed
        from app.core.db.session import Database, load_database_url

        database = Database(load_database_url(raw))
        try:
            seed(database)
            seed(database)
            with database.sessions.begin() as session:
                user = PlatformRepository(session).authenticate(
                    "student1", "demo-student-1"
                )
                store = DatabaseSessionStore(session, "req_" + "d" * 32)
                authority = SessionAuthority(
                    "synthetic-design-check-secret-not-for-deployment", 86400, store
                )
                issued = authority.issue(user)
                authority.revoke(issued.token)
        finally:
            database.close()
        assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 4
        existing = {}
        for t in INVENTORY["tables"][:7]:
            # Fetch by named columns using dict_row for the known seeded platform rows.
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                cur.execute(
                    sql.SQL("SELECT * FROM {} LIMIT 1").format(
                        sql.Identifier(t["name"])
                    )
                )
                existing[t["name"]] = cur.fetchone()
        now = datetime.now(UTC)

        def value(col):
            name, typ = col["name"], col["type"]
            if col.get("reference"):
                table, key = col["reference"].split(".")
                return existing[table][key]
            if name == "id":
                return "design_" + uuid.uuid4().hex
            if name in ("request_id", "trace_id"):
                return "req_" + uuid.uuid4().hex
            if name == "provider":
                return "mock"
            if name == "citation_id":
                return "c1"
            if "sha256" in name or name.endswith("hash"):
                return "0" * 64
            if "schema_version" in name:
                return "1.0"
            if typ == "boolean":
                return name == "is_mock"
            if typ in ("integer", "bigint") or typ.startswith("numeric"):
                return 0 if name in ("char_start", "chunk_index") else 1
            if typ.startswith("timestamptz"):
                return now
            if typ == "date":
                return date(2026, 10, 24)
            if typ == "jsonb":
                return Jsonb({"schemaVersion": "1.0"})
            pattern = re.search(r"IN\s*\(\s*'([^']+)'", col.get("check") or "")
            if pattern:
                return pattern[1]
            return "synthetic"

        pending = [t for t in INVENTORY["tables"] if t["owner"] != "M1"]
        while pending:
            progressed = False
            for t in list(pending):
                needed = [
                    c
                    for c in t["columns"]
                    if not c["nullable"] and c["default"] is None
                ]
                if any(
                    c.get("reference") and c["reference"].split(".")[0] not in existing
                    for c in needed
                ):
                    continue
                vals = {c["name"]: value(c) for c in needed}
                if t["name"] == "study_plans":
                    vals["source"] = "manual"
                if t["name"] == "mistakes":
                    vals["submission_id"] = existing["submissions"]["id"]
                    vals["question"] = Jsonb(
                        {
                            "stem": "合成题目",
                            "questionType": "single_choice",
                            "options": [],
                            "attachmentUrl": None,
                        }
                    )
                if t["name"] == "reminders":
                    vals["plan_id"] = existing["study_plans"]["id"]
                if t["name"] == "learning_events":
                    vals["payload"] = Jsonb(
                        {
                            "submissionId": existing["submissions"]["id"],
                            "assignmentId": existing["assignments"]["id"],
                            "questionType": "single_choice",
                            "isCorrect": None,
                            "score": None,
                        }
                    )
                if t["name"] in (
                    "document_grants",
                    "analytics_report_snapshots",
                    "report_jobs",
                ):
                    vals[
                        "user_id"
                        if t["name"] == "document_grants"
                        else "student_user_id"
                    ] = existing["users"]["id"]
                if t["name"] in ("analytics_report_snapshots", "report_jobs"):
                    vals["period_start"] = datetime(2026, 10, 1, tzinfo=UTC)
                    vals["period_end"] = datetime(2026, 11, 1, tzinfo=UTC)
                if t["name"] == "analytics_report_snapshots":
                    vals["metrics"] = Jsonb(
                        {
                            "schemaVersion": "1.0",
                            "dataState": "unknown",
                            "studySeconds": None,
                            "knowledgePoints": [],
                            "weakSubjects": [],
                            "suggestions": [],
                        }
                    )
                cols = list(vals)
                statement = sql.SQL(
                    "INSERT INTO {} ({}) VALUES ({}) RETURNING *"
                ).format(
                    sql.Identifier(t["name"]),
                    sql.SQL(",").join(map(sql.Identifier, cols)),
                    sql.SQL(",").join(sql.Placeholder() for _ in cols),
                )
                with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                    cur.execute(statement, [vals[k] for k in cols])
                    existing[t["name"]] = cur.fetchone()
                pending.remove(t)
                progressed = True
            if not progressed:
                raise RuntimeError(
                    "Unresolved required FK cycle: " + str([t["name"] for t in pending])
                )
        print(
            "INSERT: synthetic rows accepted across all 40 tables; platform seed retained"
        )

        rejected = 0

        def reject(statement, params, label):
            nonlocal rejected
            try:
                with conn.transaction():
                    conn.execute(statement, params)
            except psycopg.IntegrityError:
                rejected += 1
                print("REJECT:", label)
            else:
                raise AssertionError("Expected constraint rejection: " + label)

        reject(
            "UPDATE users SET username='中文' WHERE id=%s",
            (existing["users"]["id"],),
            "ASCII username whitelist",
        )
        reject(
            "UPDATE system_config_versions SET value=%s",
            (Jsonb({"schemaVersion": None}),),
            "JSON null schemaVersion",
        )
        reject(
            "UPDATE system_config_versions SET status='retired',activated_at=NULL",
            (),
            "unpublished draft retirement",
        )
        reject(
            "UPDATE enrollments SET class_id='missing' WHERE id=%s",
            (existing["enrollments"]["id"],),
            "missing FK",
        )
        reject(
            "UPDATE avatar_profiles SET volume=1.5 WHERE id=%s",
            (existing["avatar_profiles"]["id"],),
            "out-of-range preference",
        )
        reject(
            "UPDATE tutoring_turns SET status='stopped' WHERE id=%s",
            (existing["tutoring_turns"]["id"],),
            "uncontracted persistent status",
        )
        reject(
            "UPDATE tutoring_turns SET follow_ups=%s WHERE id=%s",
            (Jsonb({"schemaVersion": None}), existing["tutoring_turns"]["id"]),
            "JSON object version is not null",
        )
        before = conn.execute("SELECT count(*) FROM learning_events").fetchone()[0]
        try:
            with conn.transaction():
                conn.execute(
                    "INSERT INTO learning_events(id,event_type,user_id,occurred_at,trace_id,payload) VALUES(%s,'mistake_resolved',%s,now(),%s,'{}')",
                    (
                        "rollback_" + uuid.uuid4().hex,
                        existing["users"]["id"],
                        "req_" + "a" * 32,
                    ),
                )
                conn.execute("UPDATE avatar_profiles SET volume=2")
        except psycopg.IntegrityError:
            pass
        assert (
            conn.execute("SELECT count(*) FROM learning_events").fetchone()[0] == before
        )
        print("ROLLBACK: failed transaction left no event")
        # Two independent connections: an older, invisible event commits AFTER a newer one was processed.
        consumer = existing["analytics_consumers"]["id"]
        uid = existing["users"]["id"]
        old, new = "event_" + uuid.uuid4().hex, "event_" + uuid.uuid4().hex
        insert_event = "INSERT INTO learning_events(id,event_type,user_id,occurred_at,trace_id,payload) VALUES(%s,'mistake_resolved',%s,%s,%s,'{}')"
        params = {
            "host": url.host,
            "port": url.port,
            "user": url.username,
            "password": url.password,
            "dbname": dbname,
            "connect_timeout": 5,
        }
        with psycopg.connect(**params) as a, psycopg.connect(**params) as b:
            a.execute(
                insert_event,
                (old, uid, datetime(2026, 1, 1, tzinfo=UTC), "req_" + "b" * 32),
            )
            b.execute(
                insert_event,
                (new, uid, datetime(2026, 10, 24, tzinfo=UTC), "req_" + "c" * 32),
            )
            b.commit()
            conn.execute(
                "INSERT INTO analytics_processed_events(consumer_id,event_id,source_hash) VALUES(%s,%s,%s)",
                (consumer, new, "0" * 64),
            )
            assert (
                conn.execute(
                    "SELECT count(*) FROM learning_events WHERE id=%s", (old,)
                ).fetchone()[0]
                == 0
            )
            a.commit()
        pending_ids = {
            r[0]
            for r in conn.execute(
                "SELECT e.event_id FROM v_learning_event_feed e WHERE NOT EXISTS(SELECT 1 FROM analytics_processed_events p WHERE p.consumer_id=%s AND p.event_id=e.event_id)",
                (consumer,),
            )
        }
        assert old in pending_ids and new not in pending_ids
        print(
            "LATE COMMIT: older invisible event became pending after later commit; processed event excluded"
        )
        count = conn.execute(
            "SELECT count(*) FROM pg_constraint WHERE connamespace='public'::regnamespace"
        ).fetchone()[0]
        print(
            f"PASS: {len(names)} tables/{actual_columns} columns/{count} constraints; {rejected} negative constraints; rollback and two-connection ledger query"
        )
        if os.getenv("DESIGN_SNAPSHOT_PATH"):
            result = snapshot()
            assert all(x["count"] > 0 for x in result.values())
            Path(os.environ["DESIGN_SNAPSHOT_PATH"]).write_text(
                json.dumps({"database": dbname, "tables": result}, indent=2),
                encoding="utf-8",
            )
            print(
                "SNAPSHOT: all 40 tables populated; only counts and aggregate digests recorded, no raw token"
            )
        print(
            "NOT VERIFIED: application ORM/migration integration, service ACL, full consumer, real models, UI, domain API process restart"
        )


if __name__ == "__main__":
    main()
