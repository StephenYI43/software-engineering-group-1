"""Static contract validation, not proof of runtime ACL, PG or model integration."""

import json
import re
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate

ROOT = Path(__file__).resolve().parents[4]
DESIGN = ROOT / "scripts/api-design"
sys.path.insert(0, str(DESIGN))
from build_contracts import outputs, sample  # noqa: E402
from contract_model import SCHEMAS  # noqa: E402

SPEC = json.loads((ROOT / "packages/contracts/api-v2/openapi.json").read_text(encoding="utf-8"))
CATALOG = json.loads((ROOT / "packages/contracts/api-v2/catalog.json").read_text(encoding="utf-8"))


def validator(schema: dict) -> Draft202012Validator:
    return Draft202012Validator(
        {**schema, "components": SPEC["components"]}, format_checker=FormatChecker()
    )


def validates(name: str, value) -> bool:
    return validator({"$ref": f"#/components/schemas/{name}"}).is_valid(value)


def test_official_openapi_validator():
    validate(SPEC)


def test_all_generated_files_match_design_source():
    for path, content in outputs().items():
        assert path.read_text(encoding="utf-8") == content, str(path)


def test_postman_contains_non_executed_request_and_response_examples():
    collection = json.loads(
        (ROOT / "packages/contracts/api-v2/postman.collection.json").read_text(encoding="utf-8")
    )
    assert len(collection["item"]) == len(CATALOG)
    for item, op in zip(collection["item"], CATALOG, strict=True):
        request = item["request"]
        assert all(
            p["name"] + "=" in request["url"] for p in op["parameters"] if p["in"] == "query"
        )
        response = item["response"][0]
        assert response["code"] == op["status"]
        assert response["originalRequest"] == request
        assert response["name"] == "合成设计样例，未执行HTTP"
        if op["status"] == 204 or op["media"] == "binary":
            assert response["body"] == ""
        elif op["media"] != "sse":
            assert json.loads(response["body"]) == op["response_example"]


@pytest.mark.parametrize("name", list(SPEC["components"]["schemas"]))
def test_schema_examples_are_valid(name):
    schema = SPEC["components"]["schemas"][name]
    Draft202012Validator.check_schema(schema)
    value = sample(SCHEMAS[name])
    errors = list(validator({"$ref": f"#/components/schemas/{name}"}).iter_errors(value))
    assert not errors, f"{name}: {errors[0] if errors else ''}"


@pytest.mark.parametrize("op", CATALOG, ids=lambda op: op["id"])
def test_operation_examples_and_security_declarations(op):
    definition = SPEC["paths"][op["path"]][op["method"].lower()]
    assert definition["x-implementation-status"] == "design-only"
    assert definition["security"] == ([{"BearerAuth": []}] if op["roles"] else [])
    assert definition["x-object-authorization"]
    names = re.findall(r"\{([^}]+)\}", op["path"])
    declared = [p["name"] for p in definition["parameters"] if p["in"] == "path"]
    assert names == declared
    assert all(p["required"] for p in definition["parameters"] if p["in"] == "path")
    assert "token" not in [p["name"] for p in definition["parameters"] if p["in"] == "query"]
    if op["request"]:
        assert validates(op["request"], op["request_example"]), op["id"]
    response = definition["responses"][str(op["status"])]
    if op["status"] == 204:
        assert "content" not in response
        assert op["response_example"] is None
    elif op["media"] not in {"sse", "binary"}:
        assert validator(response["content"]["application/json"]["schema"]).is_valid(
            op["response_example"]
        )
        assert set(op["response_example"]) == {"code", "message", "data", "trace_id"}
        assert op["response_example"]["code"] == 0
    if op["idempotency"] == "required":
        assert any(
            p["name"] == "Idempotency-Key" and p["required"] for p in definition["parameters"]
        )
    if op["paged"]:
        query = {p["name"]: p["schema"] for p in definition["parameters"] if p["in"] == "query"}
        assert query["page_size"]["maximum"] == 100
        assert "enum" in query["sort"]


def test_no_ambiguous_paths_or_ids():
    normalized = [(x["method"], re.sub(r"\{[^}]+\}", "{}", x["path"])) for x in CATALOG]
    assert len(set(normalized)) == len(CATALOG)
    assert len({x["operation_id"] for x in CATALOG}) == len(CATALOG)
    assert len({x["id"] for x in CATALOG}) == len(CATALOG)
    assert {x["group"] for x in CATALOG} == set("PCAWLTKVRMGE")


def test_snake_case_wire_names_and_local_refs_only():
    def walk(node):
        if isinstance(node, dict):
            if "properties" in node:
                assert all(re.fullmatch(r"[a-z][a-z0-9_]*", key) for key in node["properties"])
            if "$ref" in node:
                assert node["$ref"].startswith("#/components/")
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(SPEC["components"]["schemas"])


@pytest.mark.parametrize(
    ("name", "extra"),
    [
        ("MessageCreate", {"stage": "summary"}),
        ("MessageCreate", {"user_id": "other"}),
        ("SubmissionCreate", {"is_correct": True}),
        ("GradingPatch", {"graded_by": "someone"}),
        ("ProfilePatch", {"role": "admin"}),
        ("FocusPatch", {"duration_seconds": 99999}),
    ],
)
def test_mass_assignment_examples_rejected(name, extra):
    value = sample(SCHEMAS[name])
    value.update(extra)
    assert not validates(name, value)


@pytest.mark.parametrize(
    "field", ["answer_key", "password", "token", "storage_key", "session_secret"]
)
def test_student_assignment_never_contains_secret_fields(field):
    value = sample(SCHEMAS["Assignment"])
    value[field] = "must-not-leak"
    assert not validates("Assignment", value)


def test_exam_draft_requires_teacher_checked_questions_and_hides_answer_key():
    draft = sample(SCHEMAS["ExamPaperCreate"])
    assert validates("ExamPaperCreate", draft)
    draft.pop("questions")
    assert not validates("ExamPaperCreate", draft)
    question = sample(SCHEMAS["ExamQuestion"])
    question["answer_key"] = {"options": ["A"]}
    assert not validates("ExamQuestion", question)


def test_unknown_metric_is_not_a_zero_value():
    assert validates("MetricNumber", {"state": "unknown", "reason": "no_events_in_period"})
    assert validates("MetricNumber", {"state": "known", "value": 0})
    assert not validates("MetricNumber", {"state": "unknown", "value": 0})


def test_plan_source_does_not_accept_frontend_transferred_suggestion():
    assert validates("PlanCreate", {"source": "tutoring", "source_turn_id": "turn_synthetic"})
    assert not validates(
        "PlanCreate", {"source": "tutoring", "source_turn_id": "turn_synthetic", "items": []}
    )
    assert not validates("PlanCreate", {"source": "manual", "title": "test", "items": []})


def test_config_has_typed_value_and_non_null_version():
    value = sample(SCHEMAS["ConfigCreate"])
    assert validates("ConfigCreate", value)
    value["value"]["schema_version"] = None
    assert not validates("ConfigCreate", value)
    assert not validates("ConfigCreate", {"config_key": "session_policy", "value": "{}"})
    assert not validates(
        "ConfigCreate",
        {
            "config_key": "session_policy",
            "value": {
                "schema_version": "1.0",
                "max_upload_bytes": 100,
                "allowed_mime_types": ["application/pdf"],
            },
        },
    )


def test_terminal_turn_cannot_claim_complete_without_response():
    value = sample(SCHEMAS["TutoringTurn"])
    value.update(status="completed", is_complete=True)
    assert not validates("TutoringTurn", value)
    value.update(status="aborted", is_complete=False, settled_at="2026-10-27T01:01:00Z")
    assert not validates("TutoringTurn", value)
    value["abort_reason"] = "client_stop"
    assert validates("TutoringTurn", value)


def assert_stream(frames):
    assert frames and frames[0][0] == "started"
    terminal = {"completed", "stopped", "error"}
    turn_id = frames[0][1]["data"]["turn_id"]
    content = ""
    for index, (kind, value) in enumerate(frames, 1):
        assert kind in SPEC["x-sse-examples"]
        assert validator(SPEC["x-sse-examples"][kind]["schema"]).is_valid(value)
        assert value["data"]["seq"] == index
        assert value["data"]["turn_id"] == turn_id
        assert (kind in terminal) == (index == len(frames))
        if kind == "delta":
            content += value["data"]["text_delta"]
        if kind == "completed":
            assert value["data"]["response"]["content"] == content
        if kind != "error":
            assert value["code"] == 0


def frames_from_example():
    operation = next(x for x in CATALOG if x["media"] == "sse")
    frames = []
    for block in operation["response_example"].strip().split("\n\n"):
        lines = block.splitlines()
        frames.append(
            (lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: ")))
        )
    return frames


def test_sse_example_and_counterexamples():
    frames = frames_from_example()
    assert_stream(frames)
    for kind in ("seq", "turn", "tail", "content"):
        bad = deepcopy(frames)
        if kind == "seq":
            bad[1][1]["data"]["seq"] = 1
        elif kind == "turn":
            bad[1][1]["data"]["turn_id"] = "other"
        elif kind == "tail":
            bad.append(deepcopy(bad[1]))
        else:
            bad[-1][1]["data"]["response"]["content"] = "not-the-delta"
        with pytest.raises(AssertionError):
            assert_stream(bad)


def test_v1_runtime_is_not_silently_replaced_by_candidate():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.main import create_app\n"
            "import json\n"
            "print(json.dumps(sorted(create_app().openapi()['paths'])))",
        ],
        cwd=ROOT / "apps/api",
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == [
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/health",
    ]
