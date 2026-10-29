"""Generate auditable v2 contracts and types without altering v1 or runtime routes."""

from __future__ import annotations

import argparse
import json
import re
from copy import deepcopy
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlencode

from contract_model import IDS, NOW, SCHEMAS, TRACE, model, number, ref, text
from operations import GROUPS, INTERNAL_PORTS, OPERATIONS

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "packages/contracts/api-v2"
HEAD = "7c174a4b7241125af812ebe669e9a6c1af89ec76"
ERRORS = {
    400: (10000, "请求格式错误", "MALFORMED_REQUEST"),
    401: (20010, "请先登录", "UNAUTHENTICATED"),
    403: (20011, "当前角色不能执行该操作", "ROLE_FORBIDDEN"),
    404: (20001, "未找到", "RESOURCE_NOT_FOUND"),
    409: (20002, "资源状态冲突，请核对后重试", "STATE_CONFLICT"),
    412: (20003, "资源已更新，请刷新后再提交", "ETAG_MISMATCH"),
    413: (10002, "请求内容超过大小限制", "PAYLOAD_TOO_LARGE"),
    415: (10003, "不支持的内容类型", "UNSUPPORTED_MEDIA_TYPE"),
    422: (10001, "请求参数未通过校验", "VALIDATION_FAILED"),
    429: (20020, "请求过于频繁，请稍后重试", "RATE_LIMITED"),
    500: (50000, "服务暂时异常", "INTERNAL_ERROR"),
    503: (50001, "依赖服务暂时不可用", "DEPENDENCY_UNAVAILABLE"),
}
FIELD_EXAMPLES = {
    "created_at": NOW,
    "updated_at": NOW,
    "occurred_at": NOW,
    "generated_at": NOW,
    "started_at": NOW,
    "period_start": NOW,
    "period_end": "2026-11-03T01:00:00Z",
    "expires_at": "2026-10-27T02:00:00Z",
    "due_at": "2026-11-03T01:00:00Z",
    "trace_id": TRACE,
    "from": "2026-10-20T00:00:00Z",
    "to": "2026-10-27T00:00:00Z",
    "timezone": "Asia/Shanghai",
    "token": "SYNTHETIC_TOKEN_DO_NOT_USE",
    "request_id": TRACE,
    "citation_id": "c1",
    "schema_version": "1.0",
    "title": "高等数学第一章复习",
    "display_name": "合成学生甲",
    "password": "synthetic-example-not-a-real-password",
    "initial_password": "synthetic-example-not-a-real-password",
    "username": "student_a",
    "mime_type": "application/pdf",
    "voice_code": "demo_voice",
    "knowledge_point": "极限定义",
    "content": "先回顾极限定义，再尝试一道基础题。",
    "description": "合成教学示例，不含真实学生资料或课件原文。",
    "question_type": "single_choice",
    "max_score": 100,
    "score": 0,
    "prompt_version": "guided-tutoring.v1",
    "page": 1,
    "page_size": 20,
    "status": "queued",
    "student_count": 0,
    "is_mock": True,
    "algorithm": "session_inference_v1",
    "key": "A",
    "text": "合成选项A",
    "avatar_asset_id": IDS["asset"],
    "config_version_id": IDS["config"],
}
ID_FIELDS = {
    "user_id": "user",
    "student_id": "user",
    "student_user_id": "user",
    "teacher_id": "user",
    "teacher_user_id": "user",
    "actor_user_id": "user",
    "graded_by": "user",
    "course_id": "course",
    "class_id": "class",
    "chapter_id": "chapter",
    "assignment_id": "assignment",
    "submission_id": "submission",
    "mistake_id": "mistake",
    "plan_id": "plan",
    "item_id": "item",
    "reminder_id": "reminder",
    "session_id": "session",
    "turn_id": "turn",
    "source_turn_id": "turn",
    "document_id": "document",
    "asset_id": "asset",
    "input_asset_id": "asset",
    "job_id": "job",
    "report_id": "report",
    "config_id": "config",
    "event_id": "event",
    "paper_id": "exam",
    "attempt_id": "attempt",
    "focus_id": "focus",
    "playback_id": "playback",
    "utterance_id": "playback",
}


def deref(schema: dict) -> dict:
    if "$ref" not in schema:
        return schema
    return SCHEMAS[schema["$ref"].rsplit("/", 1)[-1]]


def sample(schema: dict, field: str = "", depth: int = 0):
    if depth > 12:
        raise ValueError("Unexpected reference cycle")
    schema = deref(schema)
    if "example" in schema:
        return deepcopy(schema["example"])
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    if "anyOf" in schema:
        if any(x.get("type") == "null" for x in schema["anyOf"]):
            return None
        return sample(schema["anyOf"][0], field, depth + 1)
    if "oneOf" in schema:
        return sample(schema["oneOf"][0], field, depth + 1)
    if "default" in schema:
        return schema["default"]
    kind = schema.get("type")
    if kind == "object":
        return {
            k: sample(v, k, depth + 1)
            for k, v in schema.get("properties", {}).items()
            if k in schema.get("required", [])
        }
    if kind == "array":
        return [sample(schema["items"], field, depth + 1) for _ in range(schema.get("minItems", 0))]
    if kind == "null":
        return None
    if field in ID_FIELDS:
        return IDS[ID_FIELDS[field]]
    if field in FIELD_EXAMPLES:
        return deepcopy(FIELD_EXAMPLES[field])
    if kind == "boolean":
        return False
    if kind in {"integer", "number"}:
        return schema.get("minimum", 0)
    if kind == "string":
        if schema.get("format") == "date-time":
            return NOW
        if schema.get("format") == "date":
            return "2026-10-27"
        if schema.get("format") == "uri":
            return "https://example.invalid/synthetic-resource"
        if schema.get("format") == "binary":
            return "synthetic-file-bytes-selected-locally"
        if field == "id" or field.endswith("_id"):
            return "resource_" + "1" * 32
        value = "合成示例"
        return value[: schema.get("maxLength", 100)]
    raise ValueError(f"No example rule for {field}: {schema}")


def install_examples() -> None:
    def snake_keys(value):
        if isinstance(value, dict):
            return {
                re.sub(r"(?<!^)(?=[A-Z])", "_", k).lower(): snake_keys(v) for k, v in value.items()
            }
        if isinstance(value, list):
            return [snake_keys(v) for v in value]
        return value

    legacy_statistics = json.loads(
        (ROOT / "packages/contracts/analytics/samples/01-class-overview-ok.json").read_text(
            encoding="utf-8"
        )
    )
    SCHEMAS["ClassOverview"]["example"] = snake_keys(legacy_statistics)
    SCHEMAS["StatisticsPeriod"]["example"] = {
        "from": "2026-10-20T00:00:00Z",
        "to": "2026-10-27T00:00:00Z",
        "timezone": "Asia/Shanghai",
        "days": 7,
    }
    SCHEMAS["AssignmentCreate"]["example"] = {
        "class_id": IDS["class"],
        "title": "极限概念练习",
        "description": "以下哪项符合题意？",
        "question_type": "single_choice",
        "options": [
            {"key": "A", "text": "合成选项甲"},
            {"key": "B", "text": "合成选项乙"},
        ],
        "answer_key": {"options": ["A"]},
        "max_score": 100,
        "publish": True,
    }
    SCHEMAS["AnswerKey"]["example"] = {"options": ["A"]}
    public_assignment = sample(SCHEMAS["Assignment"])
    public_assignment.update(
        {
            k: deepcopy(v)
            for k, v in SCHEMAS["AssignmentCreate"]["example"].items()
            if k in public_assignment
        }
    )
    public_assignment["published_at"] = NOW
    SCHEMAS["Assignment"]["example"] = public_assignment
    SCHEMAS["ExamQuestion"]["example"] = {
        "id": "question_" + "1" * 32,
        "paper_id": IDS["exam"],
        "order": 1,
        **deepcopy(SCHEMAS["ExamQuestionInput"]["example"]),
    }
    SCHEMAS["ExamQuestion"]["example"].pop("answer_key")
    SCHEMAS["SubmissionCreate"]["example"] = {"answer": {"options": ["B"]}}
    SCHEMAS["StudentAnswer"]["example"] = {"options": ["B"]}
    SCHEMAS["MistakeCreate"]["example"] = {"source_turn_id": IDS["turn"]}
    SCHEMAS["DocumentGrantCreate"]["example"] = {"class_id": IDS["class"]}
    SCHEMAS["MediaJobCreate"]["example"] = {
        "type": "tts",
        "source_turn_id": IDS["turn"],
        "language": "zh-CN",
    }
    SCHEMAS["ReportCreate"]["example"] = {
        "student_user_id": IDS["user"],
        "period_start": "2026-10-20T00:00:00Z",
        "period_end": "2026-10-27T00:00:00Z",
        "timezone": "Asia/Shanghai",
    }
    SCHEMAS["ConfigCreate"]["example"] = {
        "config_key": "session_policy",
        "value": {"schema_version": "1.0", "session_ttl_seconds": 3600},
    }
    SCHEMAS["ConfigVersion"]["example"] = {
        "id": IDS["config"],
        "config_key": "session_policy",
        "version": 1,
        "status": "draft",
        "created_at": NOW,
        "activated_at": None,
        "retired_at": None,
    }
    SCHEMAS["ProfilePatch"]["example"] = {"display_name": "合成学生甲"}
    SCHEMAS["AssignmentPatch"]["example"] = {"due_at": "2026-11-03T01:00:00Z"}
    SCHEMAS["PlanPatch"]["example"] = {"title": "第一章复习计划"}
    SCHEMAS["PlanItemPatch"]["example"] = {"status": "done"}
    SCHEMAS["AvatarProfilePatch"]["example"] = {"auto_play": False, "volume": 0.8}
    SCHEMAS["AdminUserPatch"]["example"] = {"status": "disabled"}
    SCHEMAS["PlaybackPatch"]["example"] = {"status": "completed"}
    SCHEMAS["TutoringTurn"]["example"] = {
        "turn_id": IDS["turn"],
        "session_id": IDS["session"],
        "seq": 1,
        "status": "active",
        "is_complete": False,
        "partial_content": None,
        "abort_reason": None,
        "response": None,
        "created_at": NOW,
        "settled_at": None,
    }
    SCHEMAS["LearningEventReceipt"]["example"] = {
        "event_id": IDS["event"],
        "occurred_at": NOW,
        "schema_version": "2.0",
    }
    SCHEMAS["TutoringResponse"]["example"] = {
        "turn_id": IDS["turn"],
        "session_id": IDS["session"],
        "stage": "thought",
        "content": "先回顾极限定义，再尝试一道基础题。\n",
        "citations": [],
        "has_evidence": False,
        "follow_ups": ["能用一个具体例子说明吗？"],
        "emotion": "encouraging",
        "action": "nod",
        "is_mock": True,
        "prompt_version": "guided-tutoring.v1",
        "created_at": NOW,
        "plan_suggestion": None,
    }
    SCHEMAS["Job"]["example"] = {
        "job_id": IDS["job"],
        "status": "queued",
        "is_mock": True,
        "result_id": None,
        "error_code": None,
        "created_at": NOW,
        "started_at": None,
        "finished_at": None,
    }
    report = sample(SCHEMAS["LearningReport"])
    report["student_user_id"] = IDS["user"]
    SCHEMAS["LearningReport"]["example"] = report
    # Show a useful single item in page examples, not a hundred copies.
    for name, schema in list(SCHEMAS.items()):
        if name.endswith("Page"):
            item = schema["properties"]["items"]["items"]
            schema["example"] = {
                "items": [sample(item)],
                "total": 1,
                "page": 1,
                "page_size": 20,
            }


def envelope(name: str, data: dict, *, error=False) -> str:
    if name not in SCHEMAS:
        model(
            name,
            "v2统一响应封套",
            {
                "code": number("业务码", 10000 if error else 0, 59999 if error else 0),
                "message": text("可展示提示", 300),
                "data": data,
                "trace_id": text("服务端请求号，同X-Request-ID", 36, pattern=r"^req_[0-9a-f]{32}$"),
            },
        )
    return name


def wrap(data, message="ok", code=0) -> dict:
    return {"code": code, "message": message, "data": deepcopy(data), "trace_id": TRACE}


def parameter(name, location, schema, description="", required=False) -> dict:
    return {
        "name": name,
        "in": location,
        "required": required,
        "description": description or schema.get("description", "参数"),
        "schema": deepcopy(schema),
        "example": sample(schema, name),
    }


def parameters(operation: dict) -> list[dict]:
    result = [
        parameter(name, "path", ID_SCHEMA, "资源ID，必须鉴权并核验父子关系", True)
        for name in re.findall(r"\{([^}]+)\}", operation["path"])
    ]
    if operation["idempotency"] == "required" and not operation["path"].endswith("/auth/login"):
        result.append(
            parameter(
                "Idempotency-Key",
                "header",
                {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 128,
                    "pattern": r"^[A-Za-z0-9._:-]{1,128}$",
                },
                "当前actor/操作/资源范围内的稳定重试键；同键换参409",
                True,
            )
        )
        result[-1]["example"] = "synthetic-key-20261027-001"
    if operation["optimistic_lock"]:
        result.append(
            parameter(
                "If-Match",
                "header",
                text("上次响应ETag，避免覆盖并发修改", 128),
                required=True,
            )
        )
        result[-1]["example"] = '"synthetic-etag-v1"'
    query_names = ["page", "page_size", "sort"] if operation["paged"] else []
    query_names += [x for x in operation["filters"] if x not in query_names]
    query_types = {
        "page": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 1},
        "page_size": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
        "sort": {
            "type": "string",
            "enum": ["created_at", "-created_at"],
            "default": "-created_at",
        },
        "subject": SCHEMAS["Course"]["properties"]["subject"],
        "status": text("本资源状态白名单，不能拼SQL", 32),
        "role": {"type": "string", "enum": ["student", "teacher", "admin"]},
        "course_id": ID_SCHEMA,
        "graded": {"type": "boolean"},
        "is_read": {"type": "boolean"},
        "period": {
            "type": "string",
            "enum": ["last7d", "last30d", "custom"],
            "default": "last7d",
        },
        "from": {"type": "string", "format": "date-time", "pattern": "Z$"},
        "to": {"type": "string", "format": "date-time", "pattern": "Z$"},
        "timezone": {
            "type": "string",
            "minLength": 1,
            "maxLength": 64,
            "default": "Asia/Shanghai",
        },
    }
    if "status" in query_names:
        values = {
            "A": ["draft", "published"],
            "W": ["unresolved", "resolved"],
            "L": ["active", "completed", "archived"],
            "R": ["open", "retry_ready", "resolved"],
            "M": ["draft", "active", "retired"],
        }[operation["group"]]
        query_types["status"] = {"type": "string", "enum": values}
    result += [
        parameter(name, "query", query_types[name], f"{name}按文档白名单校验；未知筛选参数422")
        for name in query_names
    ]
    return result


ID_SCHEMA = {"type": "string", "minLength": 1, "maxLength": 64}


def build_spec() -> tuple[dict, list[dict]]:
    install_examples()
    trace_header = {
        "description": "服务端生成，与响应trace_id相同",
        "schema": {"type": "string", "pattern": r"^req_[0-9a-f]{32}$"},
    }
    common_responses = {}
    for status, (code, message, reason) in ERRORS.items():
        headers = {
            "X-Request-ID": deepcopy(trace_header),
            "Cache-Control": {"schema": {"type": "string", "const": "no-store"}},
        }
        if status == 401:
            headers["WWW-Authenticate"] = {"schema": {"type": "string", "const": "Bearer"}}
        if status == 429:
            headers["Retry-After"] = {
                "schema": {"type": "integer", "minimum": 1},
                "description": "等待秒数",
            }
        common_responses[f"Error{status}"] = {
            "description": message,
            "headers": headers,
            "content": {
                "application/json": {
                    "schema": ref("ErrorEnvelope"),
                    "example": wrap({"reason_code": reason}, message, code),
                }
            },
        }
    sse_examples = {}
    for kind, data_name in {
        "started": "SseStartedData",
        "delta": "SseDeltaData",
        "completed": "SseCompletedData",
        "stopped": "SseStoppedData",
        "error": "SseErrorData",
    }.items():
        env_name = envelope(
            "Sse" + kind.title() + "Envelope", ref(data_name), error=kind == "error"
        )
        data = sample(ref(data_name))
        if kind == "delta":
            data["text_delta"] = SCHEMAS["TutoringResponse"]["example"]["content"]
        if kind in {"completed", "stopped", "error"}:
            data["seq"] = 3
        sse_examples[kind] = {
            "schema": ref(env_name),
            "value": wrap(data, kind, 50012 if kind == "error" else 0),
        }
    paths, catalog = {}, []
    for item in OPERATIONS:
        op = deepcopy(item)
        params = parameters(op)
        responses = {}
        success = {
            "description": "已受理，尚未完成" if op["status"] == 202 else "操作成功",
            "headers": {
                "X-Request-ID": deepcopy(trace_header),
                "Cache-Control": {"schema": {"type": "string", "const": "no-store"}},
            },
        }
        if op["status"] in {201, 202}:
            success["headers"]["Location"] = {
                "description": "新资源或任务状态URI；202指向/jobs/{job_id}",
                "schema": {"type": "string", "format": "uri-reference"},
            }
        if op["optimistic_lock"] or op["method"] == "GET":
            success["headers"]["ETag"] = {
                "description": "资源版本标识；含私有数据不共享缓存",
                "schema": {"type": "string"},
            }
        if op["media"] == "sse":
            stream = "".join(
                f"event: {kind}\ndata: "
                + json.dumps(sse_examples[kind]["value"], ensure_ascii=False, separators=(",", ":"))
                + "\n\n"
                for kind in ("started", "delta", "completed")
            )
            success["content"] = {
                "text/event-stream": {"schema": {"type": "string"}, "example": stream}
            }
            op["response_example"] = stream
        elif op["media"] == "binary":
            success["content"] = {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            }
            success["headers"]["Content-Disposition"] = {
                "schema": {"type": "string"},
                "description": "attachment；文件名去除控制字符与路径",
            }
            op["response_example"] = "受鉴权的二进制流，不套JSON封套"
        elif op["status"] != 204:
            name = envelope(op["response"] + "Envelope", ref(op["response"]))
            value = wrap(sample(ref(op["response"])), "accepted" if op["status"] == 202 else "ok")
            if op["request"] and isinstance(value["data"], dict):
                request_example = sample(ref(op["request"]))
                if isinstance(request_example, dict):
                    for key, field in request_example.items():
                        if key in value["data"] and not isinstance(field, (dict, list)):
                            value["data"][key] = deepcopy(field)
                    if "published_at" in value["data"] and "publish" in request_example:
                        value["data"]["published_at"] = NOW if request_example["publish"] else None
                if op["response"] == "ConfigVersion" and value["data"]["status"] != "draft":
                    value["data"]["activated_at"] = NOW
                    if value["data"]["status"] == "retired":
                        value["data"]["retired_at"] = NOW
            success["content"] = {"application/json": {"schema": ref(name), "example": value}}
            op["response_example"] = value
        else:
            op["response_example"] = None
        responses[str(op["status"])] = success
        error_statuses = [400, 422, 429, 500, 503]
        if op["roles"]:
            error_statuses += [401, 403, 404]
        elif op["path"].endswith("/auth/login"):
            error_statuses += [401]
        if op["method"] in {"POST", "PATCH"}:
            error_statuses += [409]
        if op["method"] == "GET" and op["path"].endswith(
            ("/result", "/summary", "/report", "/transcript")
        ):
            error_statuses += [409]
        if op["optimistic_lock"]:
            error_statuses += [412]
        if op["media"] == "multipart":
            error_statuses += [413, 415]
        for status in sorted(set(error_statuses)):
            responses[str(status)] = {"$ref": f"#/components/responses/Error{status}"}
        definition = {
            "operationId": op["operation_id"],
            "summary": op["summary"],
            "description": op["access"] + " " + op["policy"],
            "tags": [op["tag"]],
            "security": [{"BearerAuth": []}] if op["roles"] else [],
            "parameters": params,
            "responses": responses,
            "x-interface-id": op["id"],
            "x-owner": op["owner"],
            "x-consumers": op["consumers"],
            "x-roles": op["roles"],
            "x-implementation-status": "design-only",
            "x-v1-evidence": op["legacy_stage"],
            "x-phase": op["phase"],
            "x-idempotency": op["idempotency"],
            "x-object-authorization": op["access"],
        }
        if op["request"]:
            mime = "multipart/form-data" if op["media"] == "multipart" else "application/json"
            value = sample(ref(op["request"]))
            definition["requestBody"] = {
                "required": True,
                "content": {mime: {"schema": ref(op["request"]), "example": value}},
            }
            op["request_example"] = value
        else:
            op["request_example"] = None
        if op["media"] == "sse":
            definition["x-sse-events"] = {k: v["schema"] for k, v in sse_examples.items()}
        paths.setdefault(op["path"], {})[op["method"].lower()] = definition
        op["parameters"] = params
        op["error_statuses"] = sorted(set(error_statuses))
        catalog.append(op)
    spec = {
        "openapi": "3.1.1",
        "jsonSchemaDialect": "https://json-schema.org/draft/2020-12/schema",
        "info": {
            "title": "大学生辅助学习 AI 数字人系统 v2 候选接口",
            "version": "2.0.0-design.1",
            "description": (
                "Issue #80。按老师规范补齐的设计候选，所有v2操作尚未接运行路由，"
                "不是从当前FastAPI导出的运行快照。保留v1兼容。"
            ),
        },
        "servers": [
            {
                "url": "https://api.example.invalid",
                "description": "仅设计占位域名，不是真实部署地址",
            },
            {
                "url": "http://127.0.0.1:8000",
                "description": "本机显式开发环境，v2尚待实现",
            },
        ],
        "security": [{"BearerAuth": []}],
        "tags": [{"name": value[0], "description": value[1]} for value in GROUPS.values()],
        "paths": paths,
        "components": {
            "schemas": deepcopy(SCHEMAS),
            "responses": common_responses,
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": (
                        "验签、到期、持久撤销和当前权限检查，不接受URL Token或固定Mock身份"
                    ),
                }
            },
        },
        "x-baseline": {
            "main": HEAD,
            "databaseDesign": "8061f4b",
            "platformCandidate": "e1fb5ff",
            "date": "2026-10-27",
            "issue": 80,
        },
        "x-sse-examples": sse_examples,
    }
    return spec, catalog


def ts_type(schema: dict) -> str:
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if "const" in schema:
        return json.dumps(schema["const"], ensure_ascii=False)
    if "enum" in schema:
        return " | ".join(json.dumps(x, ensure_ascii=False) for x in schema["enum"])
    if ("oneOf" in schema or "anyOf" in schema) and schema.get("type") != "object":
        return (
            "(" + " | ".join(ts_type(x) for x in schema.get("oneOf", schema.get("anyOf", []))) + ")"
        )
    kind = schema.get("type")
    if kind == "object":
        fields = [
            f"{json.dumps(k)}{'' if k in schema.get('required', []) else '?'}: {ts_type(v)};"
            for k, v in schema.get("properties", {}).items()
        ]
        return "{ " + " ".join(fields) + " }" if fields else "Record<string, never>"
    if kind == "array":
        return "Array<" + ts_type(schema["items"]) + ">"
    return {
        "string": "string",
        "integer": "number",
        "number": "number",
        "boolean": "boolean",
        "null": "null",
    }[kind]


def outputs() -> dict[Path, str]:
    spec, catalog = build_spec()

    def dump(value):
        return json.dumps(value, ensure_ascii=False, indent=2) + "\n"

    ts = [
        "// Generated by scripts/api-design/build_contracts.py. Do not edit.",
        "// V2 candidate wire types only; runtime validation and ACL remain mandatory.",
    ]
    ts += [f"export type {name} = {ts_type(schema)}" for name, schema in SCHEMAS.items()]
    lines = [
        "# v2 候选接口目录",
        "",
        "所有v2接口均为设计待实现。v1证据列仅标旧版本进展，不是v2验收。",
        "",
        "| 编号 | 方法与路径 | 接口 | owner | v1证据 | 阶段 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    lines += [
        f"| {x['id']} | {x['method']} `{x['path']}` | {x['summary']} | {x['owner']} | "
        f"{x['legacy_stage']} | {x['phase']} |"
        for x in catalog
    ]
    collection = {
        "info": {
            "name": "第一组 接口设计 v2 候选",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            "description": (
                "设计示例集合；不自动执行，不代表接口已部署。上传需在本机选择获许可合成文件。"
            ),
        },
        "variable": [
            {"key": "base_url", "value": "https://api.example.invalid"},
            {"key": "token", "value": "SYNTHETIC_TOKEN_DO_NOT_USE"},
        ],
        "item": [],
    }
    for x in catalog:
        url = re.sub(r"\{([^}]+)\}", lambda m: str(sample(ID_SCHEMA, m[1])), x["path"])
        queries = [(p["name"], p["example"]) for p in x["parameters"] if p["in"] == "query"]
        if queries:
            url += "?" + urlencode(queries)
        req = {
            "method": x["method"],
            "url": "{{base_url}}" + url,
            "auth": {
                "type": "bearer",
                "bearer": [{"key": "token", "value": "{{token}}", "type": "string"}],
            }
            if x["roles"]
            else {"type": "noauth"},
            "header": [
                {"key": p["name"], "value": str(p["example"])}
                for p in x["parameters"]
                if p["in"] == "header"
            ],
            "description": x["summary"] + "；v2尚待实现。" + x["access"],
        }
        if x["request"] and x["media"] != "multipart":
            req["header"].append({"key": "Content-Type", "value": "application/json"})
            req["body"] = {
                "mode": "raw",
                "raw": dump(x["request_example"]),
                "options": {"raw": {"language": "json"}},
            }
        elif x["media"] == "multipart":
            req["body"] = {
                "mode": "formdata",
                "formdata": [
                    {"key": k, "type": "file", "src": []}
                    if k == "file"
                    else {
                        "key": k,
                        "type": "text",
                        "value": json.dumps(v) if isinstance(v, bool) else str(v),
                    }
                    for k, v in x["request_example"].items()
                ],
            }
        content_type = (
            "text/event-stream"
            if x["media"] == "sse"
            else "application/octet-stream"
            if x["media"] == "binary"
            else "application/json"
        )
        body = (
            ""
            if x["status"] == 204 or x["media"] == "binary"
            else x["response_example"]
            if x["media"] == "sse"
            else dump(x["response_example"])
        )
        saved_response = {
            "name": "合成设计样例，未执行HTTP",
            "originalRequest": deepcopy(req),
            "status": HTTPStatus(x["status"]).phrase,
            "code": x["status"],
            "header": [
                {"key": "X-Request-ID", "value": TRACE},
                {"key": "Cache-Control", "value": "no-store"},
            ]
            + ([] if x["status"] == 204 else [{"key": "Content-Type", "value": content_type}]),
            "body": body,
        }
        collection["item"].append(
            {
                "name": x["id"] + " " + x["summary"],
                "request": req,
                "response": [saved_response],
            }
        )
    return {
        OUT / "openapi.json": dump(spec),
        OUT / "catalog.json": dump(catalog),
        OUT / "postman.collection.json": dump(collection),
        OUT / "internal-contracts.json": dump(INTERNAL_PORTS),
        ROOT / "apps/web/src/generated/api-v2.ts": "\n".join(ts) + "\n",
        ROOT / "docs/api-design/interface-catalog.md": "\n".join(lines) + "\n",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    products = outputs()
    for path, content in products.items():
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                raise SystemExit(f"Generated artifact drift: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
    print(
        f"{'CHECK' if args.check else 'BUILD'}: {len(OPERATIONS)} operations / "
        f"{len(SCHEMAS)} schemas / {len(products)} generated files"
    )


if __name__ == "__main__":
    main()
