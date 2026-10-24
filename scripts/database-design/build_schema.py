"""Generate reference SQL and dictionaries. Run with the locked apps/api Python.

This is not an application migration; never point the output at a populated DB.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps/api"))
from app.core.db.metadata import Base
from domain_model import TABLES
from json_properties import JSON
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

OUT = ROOT / "docs/database-design"
DICT = ROOT / "docs/data-model"
OUT.mkdir(exist_ok=True)


def q(value):
    return '"' + value.replace('"', '""') + '"'


def lit(value):
    return "'" + value.replace("'", "''") + "'"


def parse_platform():
    result = {}
    current = None
    for line in (DICT / "platform.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            name = line[3:].strip()
            current = (
                result.setdefault(name, []) if name in Base.metadata.tables else None
            )
        if current is not None and line.startswith("|"):
            cells = [
                re.sub(r"`|\*\*", "", s.strip())
                for s in re.split(r"(?<!\\)\|", line.strip().strip("|"))
            ]
            if len(cells) == 7 and re.fullmatch(r"[a-z_]+", cells[0]):
                current.append(cells)
    assert sum(map(len, result.values())) == 49
    return result


def main():
    dialect = postgresql.dialect()
    source = parse_platform()
    tables = []
    platform_titles = {
        "users": "平台用户",
        "user_profiles": "用户资料",
        "roles": "角色目录",
        "user_roles": "角色分配",
        "auth_sessions": "持久认证会话",
        "admin_audit_logs": "管理审计",
        "system_config_versions": "平台配置版本",
    }
    sql = [
        "-- 第一组 数据库设计 2026-10-24",
        "-- Reference DESIGN only. Not an Alembic migration.",
        "-- Empty disposable *_test database only. No DROP, no production seed, no credentials.",
        "BEGIN;",
        "SET LOCAL TIME ZONE 'UTC';",
        "SET LOCAL lock_timeout = '5s';",
        "SET LOCAL statement_timeout = '30s';",
    ]
    for table in Base.metadata.sorted_tables:
        sql.append(str(CreateTable(table).compile(dialect=dialect)).strip() + ";")
        for index in sorted(table.indexes, key=lambda i: i.name or ""):
            sql.append(str(CreateIndex(index).compile(dialect=dialect)) + ";")
        rows = []
        for cells in source[table.name]:
            col = table.c[cells[0]]
            refs = list(col.foreign_keys)
            rows.append(
                {
                    "name": col.name,
                    "type": cells[2],
                    "meaning": cells[1],
                    "nullable": col.nullable,
                    "default": str(col.server_default.arg)
                    if col.server_default
                    else None,
                    "primary": col.primary_key,
                    "reference": refs[0].target_fullname if refs else None,
                    "delete": refs[0].ondelete if refs else "RESTRICT",
                    "rule": cells[5],
                    "check": None,
                    "key_description": cells[6],
                }
            )
        tables.append(
            {
                "name": table.name,
                "meaning": platform_titles[table.name],
                "owner": "M1",
                "category": "管理"
                if table.name
                in ("roles", "user_roles", "admin_audit_logs", "system_config_versions")
                else "业务",
                "columns": rows,
                "constraints": sorted(
                    [str(x.sqltext) for x in table.constraints if hasattr(x, "sqltext")]
                    + (
                        ["(value->>'schemaVersion') IS NOT DISTINCT FROM '1.0'"]
                        if table.name == "system_config_versions"
                        else []
                    )
                ),
                "indexes": sorted(i.name for i in table.indexes),
                "rules": "沿用#75平台实现；用户名白名单及配置发布状态已在本批字典明确。权限/审计/密码与会话边界见平台说明。"
                + (
                    "本批参考DDL另补schemaVersion不得为JSON null的CHECK，尚需新增应用迁移；不声称#75已具备。"
                    if table.name == "system_config_versions"
                    else ""
                ),
                "json": {},
                "status": "#75候选实现及真实PG测试已通过；未合并部署",
            }
        )
    # Strengthening proposal for JSON null: existing #75 CHECK alone can yield SQL UNKNOWN.
    sql.append(
        "ALTER TABLE system_config_versions ADD CONSTRAINT ck_syscfg_version_nonnull CHECK ((value->>'schemaVersion') IS NOT DISTINCT FROM '1.0');"
    )
    deferred = []
    for table in TABLES:
        columns = []
        for col in table.columns:
            definition = f"{q(col.name)} {col.type}"
            if not col.nullable:
                definition += " NOT NULL"
            if col.default is not None:
                definition += " DEFAULT " + col.default
            if col.check:
                definition += " CHECK (" + col.check + ")"
            columns.append(definition)
            if col.reference:
                target, key = col.reference.split(".")
                deferred.append(
                    f"ALTER TABLE {q(table.name)} ADD FOREIGN KEY ({q(col.name)}) REFERENCES {q(target)}({q(key)}) ON DELETE {col.delete} ON UPDATE NO ACTION;"
                )
        primary = [q(x.name) for x in table.columns if x.primary]
        columns.append("PRIMARY KEY (" + ",".join(primary) + ")")
        for constraint in table.constraints:
            if constraint.startswith("FOREIGN KEY"):
                deferred.append(f"ALTER TABLE {q(table.name)} ADD {constraint};")
            else:
                columns.append(constraint)
        sql.append(
            f"CREATE TABLE {q(table.name)} (\n  " + ",\n  ".join(columns) + "\n);"
        )
        sql.extend(index + ";" for index in table.indexes)
        for col in table.columns:
            if col.reference:
                name = "ix_" + table.name + "_" + col.name
                if len(name) > 63:
                    name = (
                        name[:50] + "_" + hashlib.sha256(name.encode()).hexdigest()[:8]
                    )
                sql.append(f"CREATE INDEX {q(name)} ON {q(table.name)}({q(col.name)});")
        tables.append(table.export())
    sql.extend(deferred)
    # Public source projection: no keys, identities cannot be overridden by a browser.
    sql.append(
        "CREATE VIEW v_learning_event_feed AS SELECT id AS event_id,event_type,user_id,course_id,class_id,occurred_at,recorded_at,trace_id,schema_version,payload FROM learning_events;"
    )
    for table in tables:
        sql.append(
            f"COMMENT ON TABLE {q(table['name'])} IS {lit(table['meaning'] + '；owner ' + table['owner'] + '；设计基线2026-10-24')};"
        )
        for col in table["columns"]:
            sql.append(
                f"COMMENT ON COLUMN {q(table['name'])}.{q(col['name'])} IS {lit(col['meaning'])};"
            )
    sql.append("COMMIT;")
    (OUT / "schema.sql").write_text("\n\n".join(sql) + "\n", encoding="utf-8")
    json_columns = {
        t["name"] + "." + c["name"]
        for t in tables
        for c in t["columns"]
        if c["type"] == "jsonb"
    }
    assert json_columns == set(JSON), (
        json_columns - set(JSON),
        set(JSON) - json_columns,
    )
    inventory = {
        "date": "2026-10-24",
        "platformCommit": "e1fb5ff",
        "studentCommit": "423d0d6",
        "tutoringCommit": "b2eab6b",
        "tables": tables,
        "jsonProperties": JSON,
    }
    (OUT / "schema.json").write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    json_lines = [
        "# JSONB属性七要素与版本位置",
        "",
        "所有下列属性都是设计约束，除平台已验证子集外尚待service校验实现；数据库CHECK不替代所有嵌套结构校验。@前缀表示外置列元数据而不是JSON键，不修改既有wire。",
        "",
    ]
    for qualified, spec in JSON.items():
        json_lines += [
            "## " + qualified,
            "",
            "版本位置：" + spec["version"],
            "",
            "| 属性路径 | 中文名称/含义 | 类型及长度 | 必填或可空 | 默认值 | 范围与约束 | 关联与版本位置 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        json_lines += [
            "| " + " | ".join(x.replace("|", "\\|") for x in row) + " |"
            for row in spec["fields"]
        ]
        json_lines.append("")
    (OUT / "jsonb-schemas.md").write_text("\n".join(json_lines), encoding="utf-8")
    files = {
        "M5": "learning.md",
        "M3": "tutoring-knowledge.md",
        "M4": "avatar-media.md",
        "M6": "analytics-admin.md",
    }
    for owner, filename in files.items():
        selected = [x for x in tables if x["owner"] == owner]
        lines = [
            f"# {owner} 业务与管理数据字典",
            "",
            f"owner：{owner}；本批由M1补全设计，原owner负责后续实现；日期2026-10-24。",
            "关联#69、#42、#71、#72、#65；状态：设计草案，待非作者评审，未接应用迁移/repository。",
            "",
            "物理结构唯一源为scripts/database-design/domain_model.py；生成DDL在docs/database-design/schema.sql。现有API字段不因新增列自动改变；公共增量须另经schema和消费者确认。",
            "",
        ]
        for table in selected:
            lines += [
                "## " + table["name"],
                "",
                f"- 用途：{table['meaning']}；{table['category']}。",
                f"- owner：{owner}；M1补全，相关提供方/消费者交叉评审。",
                "- 索引：主键与FK查询索引；"
                + ("；".join(table["indexes"]) or "组合唯一键见约束"),
                "- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。",
                "- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。",
                "- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。",
                "",
                table["rules"],
                "",
                "| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
            for col in table["columns"]:
                key = "PK" if col["primary"] else "无"
                if col.get("reference"):
                    key = (
                        ("PK+" if col["primary"] else "")
                        + "FK→"
                        + col["reference"]
                        + "；ON DELETE "
                        + col["delete"]
                    )
                values = (
                    "; ".join(x for x in (col.get("check"), col.get("rule")) if x)
                    or "按类型边界；跨行/权限由service验证"
                )
                cells = [
                    col["name"],
                    col["meaning"],
                    col["type"],
                    "是" if col["nullable"] else "否",
                    col["default"] or ("NULL" if col["nullable"] else "无；调用方提供"),
                    values,
                    key,
                ]
                lines.append(
                    "| " + " | ".join(str(x).replace("|", "\\|") for x in cells) + " |"
                )
            if table["constraints"]:
                lines += ["", "表级约束："] + [
                    "- `" + x + "`" for x in table["constraints"]
                ]
            if table["json"]:
                lines += ["", "JSONB版本及属性："] + [
                    f"- `{k}`：{v}" for k, v in table["json"].items()
                ]
            lines.append("")
        lines += [
            "## JSONB内部字典",
            "",
            "内部属性使用对象内版本或相邻schema_version列；两种方式都不修改既有wire。具体必填键/类型/取值/空值见各表JSONB规则；见docs/database-design/jsonb-schemas.md的七列属性明细。",
            "",
        ]
        (DICT / filename).write_text("\n".join(lines), encoding="utf-8")
    print(
        json.dumps(
            {
                "tables": len(tables),
                "columns": sum(len(x["columns"]) for x in tables),
                "domainTables": len(TABLES),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
