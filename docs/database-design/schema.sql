-- 第一组 数据库设计 2026-10-24

-- Reference DESIGN only. Not an Alembic migration.

-- Empty disposable *_test database only. No DROP, no production seed, no credentials.

BEGIN;

SET LOCAL TIME ZONE 'UTC';

SET LOCAL lock_timeout = '5s';

SET LOCAL statement_timeout = '30s';

CREATE TABLE roles (
	code VARCHAR(16) NOT NULL, 
	name VARCHAR(50) NOT NULL, 
	description VARCHAR(255), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_roles PRIMARY KEY (code), 
	CONSTRAINT ck_roles_code CHECK (code IN ('student','teacher','admin'))
);

CREATE TABLE users (
	id VARCHAR(64) NOT NULL, 
	username VARCHAR(64) NOT NULL, 
	username_key VARCHAR(64) NOT NULL, 
	password_hash TEXT NOT NULL, 
	status VARCHAR(16) DEFAULT 'active' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_users PRIMARY KEY (id), 
	CONSTRAINT ck_users_id_format CHECK (id ~ '^user_[0-9a-f]{32}$'), 
	CONSTRAINT ck_users_username_format CHECK (username ~ '^[A-Za-z0-9_.-]{1,64}$'), 
	CONSTRAINT ck_users_username_key CHECK (username_key = lower(username)), 
	CONSTRAINT ck_users_status CHECK (status IN ('active','disabled')), 
	CONSTRAINT ck_users_timestamps CHECK (updated_at >= created_at), 
	CONSTRAINT uq_users_username_key UNIQUE (username_key)
);

CREATE INDEX ix_users_status ON users (status);

CREATE TABLE admin_audit_logs (
	id VARCHAR(64) NOT NULL, 
	actor_user_id VARCHAR(64), 
	actor_type VARCHAR(16) DEFAULT 'user' NOT NULL, 
	action VARCHAR(64) NOT NULL, 
	target_type VARCHAR(64) NOT NULL, 
	target_id VARCHAR(64), 
	result VARCHAR(16) NOT NULL, 
	request_id VARCHAR(36) NOT NULL, 
	details JSONB DEFAULT '{}'::jsonb NOT NULL, 
	occurred_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_admin_audit_logs PRIMARY KEY (id), 
	CONSTRAINT ck_admin_audit_logs_actor_type CHECK (actor_type IN ('user','system')), 
	CONSTRAINT ck_admin_audit_logs_result CHECK (result IN ('succeeded','failed','denied')), 
	CONSTRAINT ck_admin_audit_logs_request_format CHECK (request_id ~ '^req_[0-9a-f]{32}$'), 
	CONSTRAINT ck_admin_audit_logs_details_object CHECK (jsonb_typeof(details) = 'object'), 
	CONSTRAINT fk_admin_audit_logs_actor_user_id_users FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_admin_audit_actor_time ON admin_audit_logs (actor_user_id, occurred_at);

CREATE INDEX ix_admin_audit_request ON admin_audit_logs (request_id);

CREATE INDEX ix_admin_audit_target_time ON admin_audit_logs (target_type, target_id, occurred_at);

CREATE TABLE auth_sessions (
	id VARCHAR(64) NOT NULL, 
	jti_digest VARCHAR(64) NOT NULL, 
	user_id VARCHAR(64) NOT NULL, 
	role_code VARCHAR(16) NOT NULL, 
	issued_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	revoked_at TIMESTAMP WITH TIME ZONE, 
	revoke_reason VARCHAR(32), 
	request_id VARCHAR(36) NOT NULL, 
	CONSTRAINT pk_auth_sessions PRIMARY KEY (id), 
	CONSTRAINT ck_auth_sessions_digest_format CHECK (jti_digest ~ '^[0-9a-f]{64}$'), 
	CONSTRAINT ck_auth_sessions_expiry CHECK (expires_at > issued_at), 
	CONSTRAINT ck_auth_sessions_request_format CHECK (request_id ~ '^req_[0-9a-f]{32}$'), 
	CONSTRAINT ck_auth_sessions_revocation CHECK ((revoked_at IS NULL AND revoke_reason IS NULL) OR (revoked_at IS NOT NULL AND revoke_reason IS NOT NULL AND revoke_reason IN ('logout','admin_revoke','role_changed','password_changed'))), 
	CONSTRAINT uq_auth_sessions_jti_digest UNIQUE (jti_digest), 
	CONSTRAINT fk_auth_sessions_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_auth_sessions_role_code_roles FOREIGN KEY(role_code) REFERENCES roles (code) ON DELETE RESTRICT
);

CREATE INDEX ix_auth_sessions_expiry ON auth_sessions (expires_at);

CREATE INDEX ix_auth_sessions_user_expiry ON auth_sessions (user_id, expires_at);

CREATE TABLE system_config_versions (
	id VARCHAR(64) NOT NULL, 
	config_key VARCHAR(100) NOT NULL, 
	version INTEGER NOT NULL, 
	status VARCHAR(16) DEFAULT 'draft' NOT NULL, 
	value JSONB NOT NULL, 
	created_by_user_id VARCHAR(64), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	activated_at TIMESTAMP WITH TIME ZONE, 
	CONSTRAINT pk_system_config_versions PRIMARY KEY (id), 
	CONSTRAINT uq_system_config_versions_config_key UNIQUE (config_key, version), 
	CONSTRAINT ck_system_config_versions_positive_version CHECK (version > 0), 
	CONSTRAINT ck_system_config_versions_status CHECK (status IN ('draft','active','retired')), 
	CONSTRAINT ck_system_config_versions_value_object CHECK (jsonb_typeof(value) = 'object'), 
	CONSTRAINT ck_system_config_versions_schema_version CHECK (value ? 'schemaVersion' AND value ->> 'schemaVersion' = '1.0'), 
	CONSTRAINT ck_system_config_versions_activation CHECK ((status = 'draft' AND activated_at IS NULL) OR (status <> 'draft' AND activated_at IS NOT NULL)), 
	CONSTRAINT fk_system_config_versions_created_by_user_id_users FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX uq_system_config_active ON system_config_versions (config_key) WHERE status = 'active';

CREATE TABLE user_profiles (
	user_id VARCHAR(64) NOT NULL, 
	display_name VARCHAR(100) NOT NULL, 
	student_number VARCHAR(32), 
	major VARCHAR(100), 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_user_profiles PRIMARY KEY (user_id), 
	CONSTRAINT ck_user_profiles_name CHECK (length(btrim(display_name)) BETWEEN 1 AND 100), 
	CONSTRAINT ck_user_profiles_student_number CHECK (student_number IS NULL OR length(student_number) > 0), 
	CONSTRAINT fk_user_profiles_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	CONSTRAINT uq_user_profiles_student_number UNIQUE (student_number)
);

CREATE TABLE user_roles (
	user_id VARCHAR(64) NOT NULL, 
	role_code VARCHAR(16) NOT NULL, 
	is_primary BOOLEAN DEFAULT false NOT NULL, 
	granted_by_user_id VARCHAR(64), 
	granted_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	revoked_at TIMESTAMP WITH TIME ZONE, 
	CONSTRAINT pk_user_roles PRIMARY KEY (user_id, role_code), 
	CONSTRAINT ck_user_roles_timestamps CHECK (revoked_at IS NULL OR revoked_at >= granted_at), 
	CONSTRAINT ck_user_roles_primary_active CHECK (NOT is_primary OR revoked_at IS NULL), 
	CONSTRAINT fk_user_roles_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_user_roles_role_code_roles FOREIGN KEY(role_code) REFERENCES roles (code) ON DELETE RESTRICT, 
	CONSTRAINT fk_user_roles_granted_by_user_id_users FOREIGN KEY(granted_by_user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_user_roles_role_user ON user_roles (role_code, user_id);

CREATE UNIQUE INDEX uq_user_roles_primary ON user_roles (user_id) WHERE is_primary;

ALTER TABLE system_config_versions ADD CONSTRAINT ck_syscfg_version_nonnull CHECK ((value->>'schemaVersion') IS NOT DISTINCT FROM '1.0');

CREATE TABLE "courses" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "title" varchar(100) NOT NULL CHECK (length(btrim(title)) BETWEEN 1 AND 100),
  "description" varchar(2000),
  "subject" varchar(32) NOT NULL CHECK (subject IN ('math','physics','chemistry','english','cs','other')),
  "cover_image_url" varchar(2048),
  "teacher_user_id" varchar(64) NOT NULL,
  "created_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK (updated_at >= created_at),
  PRIMARY KEY ("id")
);

CREATE INDEX "ix_courses_teacher_user_id" ON "courses"("teacher_user_id");

CREATE TABLE "classes" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "course_id" varchar(64) NOT NULL,
  "teacher_user_id" varchar(64) NOT NULL,
  "title" varchar(100) NOT NULL CHECK (length(btrim(title)) > 0),
  "semester" varchar(32),
  "created_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK (updated_at >= created_at),
  PRIMARY KEY ("id"),
  UNIQUE(id, course_id)
);

CREATE INDEX "ix_classes_course_id" ON "classes"("course_id");

CREATE INDEX "ix_classes_teacher_user_id" ON "classes"("teacher_user_id");

CREATE TABLE "enrollments" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "student_user_id" varchar(64) NOT NULL,
  "class_id" varchar(64) NOT NULL,
  "joined_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "left_at" timestamptz(6) CHECK (left_at IS NULL OR left_at >= joined_at),
  "granted_by_user_id" varchar(64),
  PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX uq_enrollments_active ON enrollments(student_user_id,class_id) WHERE left_at IS NULL;

CREATE INDEX "ix_enrollments_student_user_id" ON "enrollments"("student_user_id");

CREATE INDEX "ix_enrollments_class_id" ON "enrollments"("class_id");

CREATE INDEX "ix_enrollments_granted_by_user_id" ON "enrollments"("granted_by_user_id");

CREATE TABLE "teaching_assignments" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "teacher_user_id" varchar(64) NOT NULL,
  "class_id" varchar(64) NOT NULL,
  "granted_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "revoked_at" timestamptz(6) CHECK (revoked_at IS NULL OR revoked_at >= granted_at),
  "granted_by_user_id" varchar(64),
  PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX uq_teaching_primary ON teaching_assignments(class_id) WHERE revoked_at IS NULL;

CREATE INDEX "ix_teaching_assignments_teacher_user_id" ON "teaching_assignments"("teacher_user_id");

CREATE INDEX "ix_teaching_assignments_class_id" ON "teaching_assignments"("class_id");

CREATE INDEX "ix_teaching_assignments_granted_by_user_id" ON "teaching_assignments"("granted_by_user_id");

CREATE TABLE "chapters" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "course_id" varchar(64) NOT NULL,
  "title" varchar(100) NOT NULL CHECK (length(btrim(title)) > 0),
  "order" integer NOT NULL CHECK ("order" >= 1),
  "description" text,
  "document_id" varchar(64),
  "created_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK (updated_at >= created_at),
  PRIMARY KEY ("id"),
  UNIQUE(course_id, "order"),
  UNIQUE(id,course_id)
);

CREATE INDEX "ix_chapters_course_id" ON "chapters"("course_id");

CREATE INDEX "ix_chapters_document_id" ON "chapters"("document_id");

CREATE TABLE "assignments" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "course_id" varchar(64) NOT NULL,
  "class_id" varchar(64),
  "chapter_id" varchar(64),
  "teacher_user_id" varchar(64) NOT NULL,
  "title" varchar(100) NOT NULL CHECK (length(btrim(title)) > 0),
  "description" varchar(8000),
  "question_type" varchar(32) NOT NULL CHECK (question_type IN ('single_choice','multiple_choice','fill_blank','short_answer','proof')),
  "public_question" jsonb NOT NULL DEFAULT '{"schemaVersion":"1.0","options":[]}'::jsonb CHECK (jsonb_typeof(public_question) = 'object' AND (public_question->>'schemaVersion') IS NOT DISTINCT FROM '1.0'),
  "answer_key" jsonb CHECK (jsonb_typeof(answer_key) = 'object'),
  "answer_key_schema_version" varchar(16) NOT NULL DEFAULT '1.0' CHECK (answer_key_schema_version = '1.0'),
  "max_score" integer NOT NULL CHECK (max_score >= 1),
  "due_at" timestamptz(6),
  "published_at" timestamptz(6),
  "created_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK (updated_at >= created_at),
  PRIMARY KEY ("id"),
  UNIQUE(id,course_id),
  UNIQUE(id,class_id)
);

CREATE INDEX "ix_assignments_course_id" ON "assignments"("course_id");

CREATE INDEX "ix_assignments_class_id" ON "assignments"("class_id");

CREATE INDEX "ix_assignments_chapter_id" ON "assignments"("chapter_id");

CREATE INDEX "ix_assignments_teacher_user_id" ON "assignments"("teacher_user_id");

CREATE TABLE "submissions" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "assignment_id" varchar(64) NOT NULL,
  "student_user_id" varchar(64) NOT NULL,
  "course_id" varchar(64) NOT NULL,
  "class_id" varchar(64),
  "answer" jsonb NOT NULL CHECK (jsonb_typeof(answer) IN ('object','string')),
  "answer_schema_version" varchar(16) NOT NULL DEFAULT '1.0' CHECK (answer_schema_version = '1.0'),
  "is_correct" boolean,
  "score" integer CHECK (score IS NULL OR score >= 0),
  "graded_by" varchar(32) NOT NULL CHECK (graded_by IN ('auto','teacher','ai_assisted')),
  "graded_at" timestamptz(6),
  "idempotency_key" varchar(128) NOT NULL CHECK (length(idempotency_key) > 0),
  "request_hash" varchar(64) NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
  "revision" integer NOT NULL DEFAULT 1 CHECK (revision >= 1),
  "submitted_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "created_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK (updated_at >= created_at),
  PRIMARY KEY ("id"),
  UNIQUE(assignment_id,student_user_id),
  UNIQUE(student_user_id,idempotency_key),
  CHECK ((graded_at IS NULL AND is_correct IS NULL AND score IS NULL) OR graded_at IS NOT NULL)
);

CREATE INDEX "ix_submissions_assignment_id" ON "submissions"("assignment_id");

CREATE INDEX "ix_submissions_student_user_id" ON "submissions"("student_user_id");

CREATE INDEX "ix_submissions_course_id" ON "submissions"("course_id");

CREATE INDEX "ix_submissions_class_id" ON "submissions"("class_id");

CREATE TABLE "mistakes" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "student_user_id" varchar(64) NOT NULL,
  "course_id" varchar(64) NOT NULL,
  "chapter_id" varchar(64),
  "assignment_id" varchar(64),
  "submission_id" varchar(64),
  "source_turn_id" varchar(64),
  "source" varchar(32) NOT NULL CHECK (source IN ('wrong_submission','manual')),
  "question" jsonb NOT NULL CHECK (jsonb_typeof(question) = 'object'),
  "student_answer" jsonb CHECK (student_answer IS NULL OR jsonb_typeof(student_answer) IN ('object','string')),
  "snapshot_schema_version" varchar(16) NOT NULL DEFAULT '1.0' CHECK (snapshot_schema_version = '1.0'),
  "note" varchar(500),
  "status" varchar(32) NOT NULL DEFAULT 'active' CHECK (status IN ('active','resolved','archived')),
  "created_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK (updated_at >= created_at),
  PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX uq_mistakes_submission ON mistakes(student_user_id,submission_id) WHERE submission_id IS NOT NULL;

CREATE UNIQUE INDEX uq_mistakes_turn ON mistakes(student_user_id,source_turn_id) WHERE source_turn_id IS NOT NULL;

CREATE INDEX "ix_mistakes_student_user_id" ON "mistakes"("student_user_id");

CREATE INDEX "ix_mistakes_course_id" ON "mistakes"("course_id");

CREATE INDEX "ix_mistakes_chapter_id" ON "mistakes"("chapter_id");

CREATE INDEX "ix_mistakes_assignment_id" ON "mistakes"("assignment_id");

CREATE INDEX "ix_mistakes_submission_id" ON "mistakes"("submission_id");

CREATE INDEX "ix_mistakes_source_turn_id" ON "mistakes"("source_turn_id");

CREATE TABLE "study_plans" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "student_user_id" varchar(64) NOT NULL,
  "title" varchar(100) NOT NULL,
  "course_id" varchar(64),
  "chapter_id" varchar(64),
  "source_turn_id" varchar(64),
  "source" varchar(32) NOT NULL CHECK (source IN ('tutoring','manual','imported')),
  "status" varchar(32) NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed','archived')),
  "due_at" timestamptz(6),
  "created_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK (updated_at >= created_at),
  PRIMARY KEY ("id")
);

CREATE INDEX "ix_study_plans_student_user_id" ON "study_plans"("student_user_id");

CREATE INDEX "ix_study_plans_course_id" ON "study_plans"("course_id");

CREATE INDEX "ix_study_plans_chapter_id" ON "study_plans"("chapter_id");

CREATE INDEX "ix_study_plans_source_turn_id" ON "study_plans"("source_turn_id");

CREATE TABLE "plan_items" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "plan_id" varchar(64) NOT NULL,
  "content" varchar(500) NOT NULL CHECK (length(btrim(content)) > 0),
  "order" integer NOT NULL CHECK ("order" >= 1),
  "status" varchar(32) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','done')),
  "due_at" timestamptz(6),
  "chapter_id" varchar(64),
  "knowledge_point" varchar(200),
  "related_mistake_id" varchar(64),
  "related_assignment_id" varchar(64),
  "created_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK (updated_at >= created_at),
  PRIMARY KEY ("id"),
  UNIQUE(plan_id,"order")
);

CREATE INDEX "ix_plan_items_plan_id" ON "plan_items"("plan_id");

CREATE INDEX "ix_plan_items_chapter_id" ON "plan_items"("chapter_id");

CREATE INDEX "ix_plan_items_related_mistake_id" ON "plan_items"("related_mistake_id");

CREATE INDEX "ix_plan_items_related_assignment_id" ON "plan_items"("related_assignment_id");

CREATE TABLE "reminders" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "student_user_id" varchar(64) NOT NULL,
  "plan_id" varchar(64),
  "assignment_id" varchar(64),
  "type" varchar(32) NOT NULL CHECK (type IN ('plan_due','assignment_due','mistake_review_due')),
  "title" varchar(100) NOT NULL,
  "body" varchar(500),
  "due_at" timestamptz(6) NOT NULL,
  "is_read" boolean NOT NULL DEFAULT false,
  "read_at" timestamptz(6),
  "dedup_key" varchar(128) NOT NULL,
  "created_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY ("id"),
  UNIQUE(student_user_id,dedup_key),
  CHECK (is_read = (read_at IS NOT NULL))
);

CREATE INDEX "ix_reminders_student_user_id" ON "reminders"("student_user_id");

CREATE INDEX "ix_reminders_plan_id" ON "reminders"("plan_id");

CREATE INDEX "ix_reminders_assignment_id" ON "reminders"("assignment_id");

CREATE TABLE "learning_events" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "event_type" varchar(32) NOT NULL CHECK (event_type IN ('assignment_submitted','assignment_graded','mistake_recorded','mistake_resolved','study_plan_saved','plan_item_completed','reminder_triggered','chapter_viewed')),
  "user_id" varchar(64) NOT NULL,
  "course_id" varchar(64),
  "class_id" varchar(64),
  "occurred_at" timestamptz(6) NOT NULL,
  "recorded_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "trace_id" varchar(36) NOT NULL CHECK (trace_id ~ '^req_[0-9a-f]{32}$'),
  "schema_version" varchar(16) NOT NULL DEFAULT '1.0' CHECK (schema_version = '1.0'),
  "payload" jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
  "idempotency_key" varchar(128) CHECK (idempotency_key IS NULL OR length(idempotency_key)>0),
  "request_hash" varchar(64) CHECK (request_hash IS NULL OR request_hash ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY ("id"),
  CHECK(class_id IS NULL OR course_id IS NOT NULL),
  CHECK(event_type <> 'chapter_viewed' OR (course_id IS NOT NULL AND idempotency_key IS NOT NULL AND request_hash IS NOT NULL))
);

CREATE UNIQUE INDEX uq_learning_intent ON learning_events(user_id,idempotency_key) WHERE idempotency_key IS NOT NULL;

CREATE INDEX ix_events_order ON learning_events(occurred_at,id);

CREATE INDEX ix_events_class_time ON learning_events(class_id,occurred_at);

CREATE INDEX "ix_learning_events_user_id" ON "learning_events"("user_id");

CREATE INDEX "ix_learning_events_course_id" ON "learning_events"("course_id");

CREATE INDEX "ix_learning_events_class_id" ON "learning_events"("class_id");

CREATE TABLE "tutoring_sessions" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "student_user_id" varchar(64) NOT NULL,
  "course_id" varchar(64),
  "current_stage" varchar(32) NOT NULL DEFAULT 'thought' CHECK (current_stage IN ('thought','hint','step','summary')),
  "created_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK (updated_at >= created_at),
  PRIMARY KEY ("id")
);

CREATE INDEX "ix_tutoring_sessions_student_user_id" ON "tutoring_sessions"("student_user_id");

CREATE INDEX "ix_tutoring_sessions_course_id" ON "tutoring_sessions"("course_id");

CREATE TABLE "tutoring_turns" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "session_id" varchar(64) NOT NULL,
  "seq" integer NOT NULL CHECK (seq >= 1),
  "request_id" varchar(36) NOT NULL CHECK (request_id ~ '^req_[0-9a-f]{32}$'),
  "student_content" varchar(2000) NOT NULL CHECK (length(btrim(student_content))>0),
  "assistant_content" text CHECK (assistant_content IS NULL OR length(assistant_content)<=16000),
  "stage" varchar(32) NOT NULL CHECK (stage IN ('thought','hint','step','summary')),
  "status" varchar(32) NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed','aborted')),
  "abort_reason" varchar(32) CHECK (abort_reason IN ('client_stop','client_disconnect','model_error','retrieval_error','server_restart')),
  "is_complete" boolean NOT NULL DEFAULT false,
  "is_mock" boolean NOT NULL,
  "emotion" varchar(32) CHECK (emotion IN ('neutral','encouraging','thinking','celebrating')),
  "action" varchar(32) CHECK (action IN ('idle','nod','point','write')),
  "follow_ups" jsonb NOT NULL DEFAULT '{"schemaVersion":"1.0","items":[]}'::jsonb CHECK (jsonb_typeof(follow_ups) = 'object' AND (follow_ups->>'schemaVersion') IS NOT DISTINCT FROM '1.0'),
  "prompt_version_id" varchar(64) NOT NULL,
  "model_config_version_id" varchar(64) NOT NULL,
  "input_tokens" integer CHECK (input_tokens IS NULL OR input_tokens>=0),
  "output_tokens" integer CHECK (output_tokens IS NULL OR output_tokens>=0),
  "duration_ms" integer CHECK (duration_ms IS NULL OR duration_ms>=0),
  "error_code" varchar(32) CHECK (error_code IN ('MODEL_OUTPUT_INVALID','MODEL_REFUSED','MODEL_TIMEOUT','RETRIEVAL_UNAVAILABLE','TURN_ABORTED')),
  "error_reason" varchar(64),
  "created_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "settled_at" timestamptz(6),
  PRIMARY KEY ("id"),
  UNIQUE(session_id,seq),
  CHECK(is_complete = (status='completed')),
  CHECK((status='active') = (settled_at IS NULL)),
  CHECK(settled_at IS NULL OR settled_at >= created_at),
  CHECK((status='aborted') = (abort_reason IS NOT NULL)),
  CHECK(status<>'completed' OR (assistant_content IS NOT NULL AND emotion IS NOT NULL AND action IS NOT NULL)),
  CHECK(error_code IS NULL OR status='aborted')
);

CREATE UNIQUE INDEX uq_turns_active ON tutoring_turns(session_id) WHERE status='active';

CREATE INDEX "ix_tutoring_turns_session_id" ON "tutoring_turns"("session_id");

CREATE INDEX "ix_tutoring_turns_prompt_version_id" ON "tutoring_turns"("prompt_version_id");

CREATE INDEX "ix_tutoring_turns_model_config_version_id" ON "tutoring_turns"("model_config_version_id");

CREATE TABLE "turn_citations" (
  "turn_id" varchar(64) NOT NULL,
  "citation_id" varchar(8) NOT NULL CHECK (citation_id ~ '^c[1-9][0-9]?$'),
  "document_id" varchar(64) NOT NULL,
  "chunk_id" varchar(64) NOT NULL,
  "document_title_snapshot" varchar(200) NOT NULL,
  "document_version" integer NOT NULL CHECK (document_version>=1),
  "page_number" integer NOT NULL CHECK (page_number>=1),
  "snippet" varchar(1000) NOT NULL,
  "created_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY ("turn_id","citation_id"),
  UNIQUE(turn_id,chunk_id)
);

CREATE INDEX "ix_turn_citations_turn_id" ON "turn_citations"("turn_id");

CREATE INDEX "ix_turn_citations_document_id" ON "turn_citations"("document_id");

CREATE INDEX "ix_turn_citations_chunk_id" ON "turn_citations"("chunk_id");

CREATE TABLE "documents" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "course_id" varchar(64) NOT NULL,
  "uploader_user_id" varchar(64) NOT NULL,
  "title" varchar(200) NOT NULL,
  "storage_key" varchar(512) NOT NULL,
  "file_sha256" varchar(64) NOT NULL CHECK (file_sha256 ~ '^[0-9a-f]{64}$'),
  "mime_type" varchar(100) NOT NULL,
  "byte_size" bigint NOT NULL CHECK (byte_size>0),
  "version" integer NOT NULL DEFAULT 1 CHECK (version>=1),
  "previous_document_id" varchar(64),
  "status" varchar(32) NOT NULL DEFAULT 'uploaded' CHECK (status IN ('uploaded','available','withdrawn')),
  "created_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK (updated_at >= created_at),
  PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX uq_document_successor ON documents(previous_document_id) WHERE previous_document_id IS NOT NULL;

CREATE INDEX "ix_documents_course_id" ON "documents"("course_id");

CREATE INDEX "ix_documents_uploader_user_id" ON "documents"("uploader_user_id");

CREATE INDEX "ix_documents_previous_document_id" ON "documents"("previous_document_id");

CREATE TABLE "document_chunks" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "document_id" varchar(64) NOT NULL,
  "chunk_index" integer NOT NULL CHECK (chunk_index>=0),
  "page_number" integer NOT NULL CHECK (page_number>=1),
  "char_start" integer NOT NULL CHECK (char_start>=0),
  "char_end" integer NOT NULL CHECK (char_end>char_start),
  "text" text NOT NULL CHECK (length(text)>0),
  "text_sha256" varchar(64) NOT NULL CHECK (text_sha256 ~ '^[0-9a-f]{64}$'),
  "created_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY ("id"),
  UNIQUE(document_id,chunk_index),
  UNIQUE(id,document_id)
);

CREATE INDEX "ix_document_chunks_document_id" ON "document_chunks"("document_id");

CREATE TABLE "document_grants" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "document_id" varchar(64) NOT NULL,
  "user_id" varchar(64),
  "class_id" varchar(64),
  "granted_by_user_id" varchar(64),
  "granted_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "revoked_at" timestamptz(6) CHECK (revoked_at IS NULL OR revoked_at>=granted_at),
  PRIMARY KEY ("id"),
  CHECK((user_id IS NOT NULL)::integer + (class_id IS NOT NULL)::integer = 1)
);

CREATE UNIQUE INDEX uq_doc_grant_user ON document_grants(document_id,user_id) WHERE revoked_at IS NULL AND user_id IS NOT NULL;

CREATE UNIQUE INDEX uq_doc_grant_class ON document_grants(document_id,class_id) WHERE revoked_at IS NULL AND class_id IS NOT NULL;

CREATE INDEX "ix_document_grants_document_id" ON "document_grants"("document_id");

CREATE INDEX "ix_document_grants_user_id" ON "document_grants"("user_id");

CREATE INDEX "ix_document_grants_class_id" ON "document_grants"("class_id");

CREATE INDEX "ix_document_grants_granted_by_user_id" ON "document_grants"("granted_by_user_id");

CREATE TABLE "document_import_jobs" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "document_id" varchar(64) NOT NULL,
  "parser_version" varchar(64) NOT NULL,
  "idempotency_key" varchar(128) NOT NULL,
  "status" varchar(32) NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','succeeded','failed')),
  "request_id" varchar(36) NOT NULL CHECK (request_id ~ '^req_[0-9a-f]{32}$'),
  "attempts" integer NOT NULL DEFAULT 0 CHECK (attempts>=0),
  "error_code" varchar(64),
  "pages_without_text" jsonb NOT NULL DEFAULT '{"schemaVersion":"1.0","pages":[]}'::jsonb CHECK (jsonb_typeof(pages_without_text) = 'object' AND (pages_without_text->>'schemaVersion') IS NOT DISTINCT FROM '1.0'),
  "created_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "started_at" timestamptz(6),
  "finished_at" timestamptz(6),
  PRIMARY KEY ("id"),
  UNIQUE(document_id,idempotency_key),
  CHECK((status IN ('succeeded','failed')) = (finished_at IS NOT NULL)),
  CHECK(started_at IS NULL OR started_at>=created_at),
  CHECK(finished_at IS NULL OR (started_at IS NOT NULL AND finished_at>=started_at))
);

CREATE INDEX "ix_document_import_jobs_document_id" ON "document_import_jobs"("document_id");

CREATE TABLE "prompt_versions" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "series" varchar(64) NOT NULL,
  "version_label" varchar(64) NOT NULL,
  "template_path" varchar(255) NOT NULL,
  "content_sha256" varchar(64) NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
  "status" varchar(32) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','active','retired')),
  "created_by_user_id" varchar(64),
  "created_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "activated_at" timestamptz(6),
  "retired_at" timestamptz(6),
  PRIMARY KEY ("id"),
  UNIQUE(series,version_label),
  CHECK((status='draft' AND activated_at IS NULL AND retired_at IS NULL) OR (status='active' AND activated_at IS NOT NULL AND retired_at IS NULL) OR (status='retired' AND activated_at IS NOT NULL AND retired_at>=activated_at))
);

CREATE UNIQUE INDEX uq_prompt_active ON prompt_versions(series) WHERE status='active';

CREATE INDEX "ix_prompt_versions_created_by_user_id" ON "prompt_versions"("created_by_user_id");

CREATE TABLE "model_config_versions" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "config_key" varchar(64) NOT NULL,
  "version" integer NOT NULL CHECK (version>=1),
  "provider" varchar(32) NOT NULL,
  "model_name" varchar(100) NOT NULL,
  "is_mock" boolean NOT NULL,
  "temperature" numeric(3,2) NOT NULL CHECK (temperature BETWEEN 0 AND 2),
  "max_output_tokens" integer NOT NULL CHECK (max_output_tokens>0),
  "timeout_seconds" numeric(6,2) NOT NULL CHECK (timeout_seconds>0),
  "status" varchar(32) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','active','retired')),
  "created_by_user_id" varchar(64),
  "created_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "activated_at" timestamptz(6),
  "retired_at" timestamptz(6),
  PRIMARY KEY ("id"),
  UNIQUE(config_key,version),
  CHECK(is_mock = (provider='mock')),
  CHECK((status='draft' AND activated_at IS NULL AND retired_at IS NULL) OR (status='active' AND activated_at IS NOT NULL AND retired_at IS NULL) OR (status='retired' AND activated_at IS NOT NULL AND retired_at>=activated_at))
);

CREATE UNIQUE INDEX uq_model_config_active ON model_config_versions(config_key) WHERE status='active';

CREATE INDEX "ix_model_config_versions_created_by_user_id" ON "model_config_versions"("created_by_user_id");

CREATE TABLE "avatar_config_versions" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "config_key" varchar(64) NOT NULL,
  "version" integer NOT NULL CHECK (version>=1),
  "name" varchar(100) NOT NULL,
  "config" jsonb NOT NULL CHECK (jsonb_typeof(config) = 'object' AND (config->>'schemaVersion') IS NOT DISTINCT FROM '1.0'),
  "status" varchar(32) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','active','retired')),
  "created_by_user_id" varchar(64),
  "created_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY ("id"),
  UNIQUE(config_key,version)
);

CREATE UNIQUE INDEX uq_avatar_config_active ON avatar_config_versions(config_key) WHERE status='active';

CREATE INDEX "ix_avatar_config_versions_created_by_user_id" ON "avatar_config_versions"("created_by_user_id");

CREATE TABLE "avatar_profiles" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "user_id" varchar(64) NOT NULL,
  "config_version_id" varchar(64) NOT NULL,
  "auto_play" boolean NOT NULL DEFAULT false,
  "volume" numeric(3,2) NOT NULL DEFAULT 1.00 CHECK (volume BETWEEN 0 AND 1),
  "speech_rate" numeric(3,2) NOT NULL DEFAULT 1.00 CHECK (speech_rate BETWEEN 0.5 AND 2),
  "subtitles_enabled" boolean NOT NULL DEFAULT true,
  "created_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK (updated_at >= created_at),
  PRIMARY KEY ("id"),
  UNIQUE(user_id)
);

CREATE INDEX "ix_avatar_profiles_user_id" ON "avatar_profiles"("user_id");

CREATE INDEX "ix_avatar_profiles_config_version_id" ON "avatar_profiles"("config_version_id");

CREATE TABLE "media_assets" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "owner_user_id" varchar(64) NOT NULL,
  "course_id" varchar(64),
  "storage_key" varchar(512) NOT NULL,
  "sha256" varchar(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  "mime_type" varchar(100) NOT NULL,
  "byte_size" bigint NOT NULL CHECK (byte_size>0),
  "kind" varchar(32) NOT NULL CHECK (kind IN ('image','audio','video','document','avatar')),
  "status" varchar(32) NOT NULL DEFAULT 'ready' CHECK (status IN ('ready','withdrawn','deleting','deleted')),
  "consent_version" varchar(32),
  "consented_at" timestamptz(6),
  "expires_at" timestamptz(6),
  "deleted_at" timestamptz(6),
  "created_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK (updated_at >= created_at),
  PRIMARY KEY ("id"),
  UNIQUE(storage_key),
  CHECK(kind<>'audio' OR (consent_version IS NOT NULL AND consented_at IS NOT NULL)),
  CHECK((status='deleted') = (deleted_at IS NOT NULL))
);

CREATE INDEX "ix_media_assets_owner_user_id" ON "media_assets"("owner_user_id");

CREATE INDEX "ix_media_assets_course_id" ON "media_assets"("course_id");

CREATE TABLE "media_jobs" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "owner_user_id" varchar(64) NOT NULL,
  "input_asset_id" varchar(64),
  "output_asset_id" varchar(64),
  "job_type" varchar(32) NOT NULL CHECK (job_type IN ('tts','asr','ocr','transcode')),
  "processor_version" varchar(64) NOT NULL,
  "is_mock" boolean NOT NULL,
  "idempotency_key" varchar(128) NOT NULL,
  "request_hash" varchar(64) NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
  "params" jsonb NOT NULL DEFAULT '{"schemaVersion":"1.0"}'::jsonb CHECK (jsonb_typeof(params) = 'object' AND (params->>'schemaVersion') IS NOT DISTINCT FROM '1.0'),
  "status" varchar(32) NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','succeeded','failed','cancelled')),
  "attempts" integer NOT NULL DEFAULT 0 CHECK (attempts>=0),
  "error_code" varchar(64),
  "request_id" varchar(36) NOT NULL CHECK (request_id ~ '^req_[0-9a-f]{32}$'),
  "created_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "started_at" timestamptz(6),
  "finished_at" timestamptz(6),
  PRIMARY KEY ("id"),
  UNIQUE(owner_user_id,job_type,idempotency_key),
  CHECK((status IN ('succeeded','failed','cancelled')) = (finished_at IS NOT NULL))
);

CREATE INDEX "ix_media_jobs_owner_user_id" ON "media_jobs"("owner_user_id");

CREATE INDEX "ix_media_jobs_input_asset_id" ON "media_jobs"("input_asset_id");

CREATE INDEX "ix_media_jobs_output_asset_id" ON "media_jobs"("output_asset_id");

CREATE TABLE "playback_records" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "utterance_id" varchar(64) NOT NULL,
  "user_id" varchar(64) NOT NULL,
  "turn_id" varchar(64),
  "media_job_id" varchar(64),
  "config_version_id" varchar(64) NOT NULL,
  "is_mock" boolean NOT NULL,
  "status" varchar(32) NOT NULL DEFAULT 'started' CHECK (status IN ('started','completed','stopped','error')),
  "stop_reason" varchar(32) CHECK (stop_reason IN ('user_stop','replaced','component_unmounted')),
  "error_code" varchar(64),
  "started_at" timestamptz(6) NOT NULL,
  "ended_at" timestamptz(6),
  "duration_ms" integer CHECK (duration_ms IS NULL OR duration_ms>=0),
  PRIMARY KEY ("id"),
  UNIQUE(user_id,utterance_id),
  CHECK((status='started')=(ended_at IS NULL)),
  CHECK(ended_at IS NULL OR ended_at>=started_at),
  CHECK((status='stopped')=(stop_reason IS NOT NULL)),
  CHECK((status='error')=(error_code IS NOT NULL))
);

CREATE INDEX "ix_playback_records_user_id" ON "playback_records"("user_id");

CREATE INDEX "ix_playback_records_turn_id" ON "playback_records"("turn_id");

CREATE INDEX "ix_playback_records_media_job_id" ON "playback_records"("media_job_id");

CREATE INDEX "ix_playback_records_config_version_id" ON "playback_records"("config_version_id");

CREATE TABLE "focus_sessions" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "user_id" varchar(64) NOT NULL,
  "course_id" varchar(64),
  "started_at" timestamptz(6) NOT NULL,
  "ended_at" timestamptz(6),
  "duration_seconds" integer CHECK (duration_seconds IS NULL OR duration_seconds BETWEEN 0 AND 86400),
  "status" varchar(32) NOT NULL DEFAULT 'running' CHECK (status IN ('running','completed','cancelled')),
  "idempotency_key" varchar(128) NOT NULL,
  PRIMARY KEY ("id"),
  UNIQUE(user_id,idempotency_key),
  CHECK((status='running')=(ended_at IS NULL)),
  CHECK(ended_at IS NULL OR ended_at>=started_at)
);

CREATE UNIQUE INDEX uq_focus_running ON focus_sessions(user_id) WHERE status='running';

CREATE INDEX "ix_focus_sessions_user_id" ON "focus_sessions"("user_id");

CREATE INDEX "ix_focus_sessions_course_id" ON "focus_sessions"("course_id");

CREATE TABLE "analytics_consumers" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "consumer_key" varchar(64) NOT NULL,
  "algorithm_version" varchar(32) NOT NULL,
  "status" varchar(32) NOT NULL DEFAULT 'paused' CHECK (status IN ('active','paused','retired')),
  "last_poll_at" timestamptz(6),
  "last_observed_at" timestamptz(6),
  "processed_count" bigint NOT NULL DEFAULT 0 CHECK (processed_count>=0),
  "created_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK (updated_at >= created_at),
  PRIMARY KEY ("id"),
  UNIQUE(consumer_key,algorithm_version)
);

CREATE TABLE "analytics_processed_events" (
  "consumer_id" varchar(64) NOT NULL,
  "event_id" varchar(64) NOT NULL,
  "processed_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "source_hash" varchar(64) NOT NULL CHECK (source_hash ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY ("consumer_id","event_id")
);

CREATE INDEX "ix_analytics_processed_events_consumer_id" ON "analytics_processed_events"("consumer_id");

CREATE INDEX "ix_analytics_processed_events_event_id" ON "analytics_processed_events"("event_id");

CREATE TABLE "analytics_daily_metrics" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "consumer_id" varchar(64) NOT NULL,
  "student_user_id" varchar(64) NOT NULL,
  "course_id" varchar(64),
  "class_id" varchar(64),
  "metric_date" date NOT NULL,
  "timezone" varchar(64) NOT NULL DEFAULT 'Asia/Shanghai',
  "study_seconds" integer CHECK (study_seconds IS NULL OR study_seconds>=0),
  "submission_count" integer NOT NULL DEFAULT 0 CHECK (submission_count>=0),
  "wrong_count" integer NOT NULL DEFAULT 0 CHECK (wrong_count>=0),
  "sample_count" integer NOT NULL DEFAULT 0 CHECK (sample_count>=0),
  "data_state" varchar(32) NOT NULL DEFAULT 'unknown' CHECK (data_state IN ('unknown','partial','known')),
  "data_through" timestamptz(6),
  "created_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK (updated_at >= created_at),
  PRIMARY KEY ("id"),
  UNIQUE NULLS NOT DISTINCT(consumer_id,student_user_id,course_id,class_id,metric_date,timezone),
  CHECK(class_id IS NULL OR course_id IS NOT NULL),
  CHECK(data_state <> 'unknown' OR study_seconds IS NULL)
);

CREATE INDEX "ix_analytics_daily_metrics_consumer_id" ON "analytics_daily_metrics"("consumer_id");

CREATE INDEX "ix_analytics_daily_metrics_student_user_id" ON "analytics_daily_metrics"("student_user_id");

CREATE INDEX "ix_analytics_daily_metrics_course_id" ON "analytics_daily_metrics"("course_id");

CREATE INDEX "ix_analytics_daily_metrics_class_id" ON "analytics_daily_metrics"("class_id");

CREATE TABLE "analytics_report_snapshots" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "consumer_id" varchar(64) NOT NULL,
  "student_user_id" varchar(64),
  "class_id" varchar(64),
  "period_start" timestamptz(6) NOT NULL,
  "period_end" timestamptz(6) NOT NULL CHECK (period_end>period_start),
  "metrics" jsonb NOT NULL CHECK (jsonb_typeof(metrics) = 'object' AND (metrics->>'schemaVersion') IS NOT DISTINCT FROM '1.0'),
  "sample_count" integer NOT NULL CHECK (sample_count>=0),
  "data_through" timestamptz(6),
  "generated_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY ("id"),
  CHECK((student_user_id IS NOT NULL)::integer+(class_id IS NOT NULL)::integer=1),
  UNIQUE NULLS NOT DISTINCT(consumer_id,student_user_id,class_id,period_start,period_end)
);

CREATE INDEX "ix_analytics_report_snapshots_consumer_id" ON "analytics_report_snapshots"("consumer_id");

CREATE INDEX "ix_analytics_report_snapshots_student_user_id" ON "analytics_report_snapshots"("student_user_id");

CREATE INDEX "ix_analytics_report_snapshots_class_id" ON "analytics_report_snapshots"("class_id");

CREATE TABLE "report_jobs" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "requested_by_user_id" varchar(64) NOT NULL,
  "student_user_id" varchar(64),
  "class_id" varchar(64),
  "consumer_id" varchar(64) NOT NULL,
  "period_start" timestamptz(6) NOT NULL,
  "period_end" timestamptz(6) NOT NULL CHECK (period_end>period_start),
  "status" varchar(32) NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','succeeded','failed','cancelled')),
  "idempotency_key" varchar(128) NOT NULL,
  "error_code" varchar(64),
  "report_id" varchar(64),
  "created_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "finished_at" timestamptz(6),
  PRIMARY KEY ("id"),
  UNIQUE(requested_by_user_id,idempotency_key),
  CHECK((student_user_id IS NOT NULL)::integer+(class_id IS NOT NULL)::integer=1),
  CHECK((status IN ('succeeded','failed','cancelled'))=(finished_at IS NOT NULL)),
  CHECK(status<>'succeeded' OR report_id IS NOT NULL)
);

CREATE INDEX "ix_report_jobs_requested_by_user_id" ON "report_jobs"("requested_by_user_id");

CREATE INDEX "ix_report_jobs_student_user_id" ON "report_jobs"("student_user_id");

CREATE INDEX "ix_report_jobs_class_id" ON "report_jobs"("class_id");

CREATE INDEX "ix_report_jobs_consumer_id" ON "report_jobs"("consumer_id");

CREATE INDEX "ix_report_jobs_report_id" ON "report_jobs"("report_id");

CREATE TABLE "analytics_quarantined_events" (
  "id" varchar(64) NOT NULL CHECK (length(id) > 0),
  "consumer_id" varchar(64) NOT NULL,
  "event_id" varchar(64) NOT NULL,
  "error_code" varchar(64) NOT NULL,
  "status" varchar(32) NOT NULL DEFAULT 'open' CHECK (status IN ('open','retry_ready','resolved')),
  "attempts" integer NOT NULL DEFAULT 1 CHECK (attempts>=1),
  "resolved_by_user_id" varchar(64),
  "first_failed_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "last_failed_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "resolved_at" timestamptz(6),
  PRIMARY KEY ("id"),
  UNIQUE(consumer_id,event_id),
  CHECK(last_failed_at>=first_failed_at),
  CHECK((status='resolved')=(resolved_at IS NOT NULL))
);

CREATE INDEX "ix_analytics_quarantined_events_consumer_id" ON "analytics_quarantined_events"("consumer_id");

CREATE INDEX "ix_analytics_quarantined_events_event_id" ON "analytics_quarantined_events"("event_id");

CREATE INDEX "ix_analytics_quarantined_events_resolved_by_user_id" ON "analytics_quarantined_events"("resolved_by_user_id");

ALTER TABLE "courses" ADD FOREIGN KEY ("teacher_user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "classes" ADD FOREIGN KEY ("course_id") REFERENCES "courses"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "classes" ADD FOREIGN KEY ("teacher_user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "enrollments" ADD FOREIGN KEY ("student_user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "enrollments" ADD FOREIGN KEY ("class_id") REFERENCES "classes"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "enrollments" ADD FOREIGN KEY ("granted_by_user_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE NO ACTION;

ALTER TABLE "teaching_assignments" ADD FOREIGN KEY ("teacher_user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "teaching_assignments" ADD FOREIGN KEY ("class_id") REFERENCES "classes"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "teaching_assignments" ADD FOREIGN KEY ("granted_by_user_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE NO ACTION;

ALTER TABLE "chapters" ADD FOREIGN KEY ("course_id") REFERENCES "courses"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "chapters" ADD FOREIGN KEY ("document_id") REFERENCES "documents"("id") ON DELETE SET NULL ON UPDATE NO ACTION;

ALTER TABLE "assignments" ADD FOREIGN KEY ("course_id") REFERENCES "courses"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "assignments" ADD FOREIGN KEY ("class_id") REFERENCES "classes"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "assignments" ADD FOREIGN KEY ("chapter_id") REFERENCES "chapters"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "assignments" ADD FOREIGN KEY ("teacher_user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "assignments" ADD FOREIGN KEY(class_id,course_id) REFERENCES classes(id,course_id) ON DELETE RESTRICT;

ALTER TABLE "assignments" ADD FOREIGN KEY(chapter_id,course_id) REFERENCES chapters(id,course_id) ON DELETE RESTRICT;

ALTER TABLE "submissions" ADD FOREIGN KEY ("assignment_id") REFERENCES "assignments"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "submissions" ADD FOREIGN KEY ("student_user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "submissions" ADD FOREIGN KEY ("course_id") REFERENCES "courses"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "submissions" ADD FOREIGN KEY ("class_id") REFERENCES "classes"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "submissions" ADD FOREIGN KEY(assignment_id,course_id) REFERENCES assignments(id,course_id) ON DELETE RESTRICT;

ALTER TABLE "submissions" ADD FOREIGN KEY(assignment_id,class_id) REFERENCES assignments(id,class_id) ON DELETE RESTRICT;

ALTER TABLE "mistakes" ADD FOREIGN KEY ("student_user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "mistakes" ADD FOREIGN KEY ("course_id") REFERENCES "courses"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "mistakes" ADD FOREIGN KEY ("chapter_id") REFERENCES "chapters"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "mistakes" ADD FOREIGN KEY ("assignment_id") REFERENCES "assignments"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "mistakes" ADD FOREIGN KEY ("submission_id") REFERENCES "submissions"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "mistakes" ADD FOREIGN KEY ("source_turn_id") REFERENCES "tutoring_turns"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "study_plans" ADD FOREIGN KEY ("student_user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "study_plans" ADD FOREIGN KEY ("course_id") REFERENCES "courses"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "study_plans" ADD FOREIGN KEY ("chapter_id") REFERENCES "chapters"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "study_plans" ADD FOREIGN KEY ("source_turn_id") REFERENCES "tutoring_turns"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "plan_items" ADD FOREIGN KEY ("plan_id") REFERENCES "study_plans"("id") ON DELETE CASCADE ON UPDATE NO ACTION;

ALTER TABLE "plan_items" ADD FOREIGN KEY ("chapter_id") REFERENCES "chapters"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "plan_items" ADD FOREIGN KEY ("related_mistake_id") REFERENCES "mistakes"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "plan_items" ADD FOREIGN KEY ("related_assignment_id") REFERENCES "assignments"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "reminders" ADD FOREIGN KEY ("student_user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "reminders" ADD FOREIGN KEY ("plan_id") REFERENCES "study_plans"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "reminders" ADD FOREIGN KEY ("assignment_id") REFERENCES "assignments"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "learning_events" ADD FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "learning_events" ADD FOREIGN KEY ("course_id") REFERENCES "courses"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "learning_events" ADD FOREIGN KEY ("class_id") REFERENCES "classes"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "learning_events" ADD FOREIGN KEY(class_id,course_id) REFERENCES classes(id,course_id) ON DELETE RESTRICT;

ALTER TABLE "tutoring_sessions" ADD FOREIGN KEY ("student_user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "tutoring_sessions" ADD FOREIGN KEY ("course_id") REFERENCES "courses"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "tutoring_turns" ADD FOREIGN KEY ("session_id") REFERENCES "tutoring_sessions"("id") ON DELETE CASCADE ON UPDATE NO ACTION;

ALTER TABLE "tutoring_turns" ADD FOREIGN KEY ("prompt_version_id") REFERENCES "prompt_versions"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "tutoring_turns" ADD FOREIGN KEY ("model_config_version_id") REFERENCES "model_config_versions"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "turn_citations" ADD FOREIGN KEY ("turn_id") REFERENCES "tutoring_turns"("id") ON DELETE CASCADE ON UPDATE NO ACTION;

ALTER TABLE "turn_citations" ADD FOREIGN KEY ("document_id") REFERENCES "documents"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "turn_citations" ADD FOREIGN KEY ("chunk_id") REFERENCES "document_chunks"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "turn_citations" ADD FOREIGN KEY(chunk_id,document_id) REFERENCES document_chunks(id,document_id) ON DELETE RESTRICT;

ALTER TABLE "documents" ADD FOREIGN KEY ("course_id") REFERENCES "courses"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "documents" ADD FOREIGN KEY ("uploader_user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "documents" ADD FOREIGN KEY ("previous_document_id") REFERENCES "documents"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "document_chunks" ADD FOREIGN KEY ("document_id") REFERENCES "documents"("id") ON DELETE CASCADE ON UPDATE NO ACTION;

ALTER TABLE "document_grants" ADD FOREIGN KEY ("document_id") REFERENCES "documents"("id") ON DELETE CASCADE ON UPDATE NO ACTION;

ALTER TABLE "document_grants" ADD FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "document_grants" ADD FOREIGN KEY ("class_id") REFERENCES "classes"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "document_grants" ADD FOREIGN KEY ("granted_by_user_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE NO ACTION;

ALTER TABLE "document_import_jobs" ADD FOREIGN KEY ("document_id") REFERENCES "documents"("id") ON DELETE CASCADE ON UPDATE NO ACTION;

ALTER TABLE "prompt_versions" ADD FOREIGN KEY ("created_by_user_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE NO ACTION;

ALTER TABLE "model_config_versions" ADD FOREIGN KEY ("created_by_user_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE NO ACTION;

ALTER TABLE "avatar_config_versions" ADD FOREIGN KEY ("created_by_user_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE NO ACTION;

ALTER TABLE "avatar_profiles" ADD FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "avatar_profiles" ADD FOREIGN KEY ("config_version_id") REFERENCES "avatar_config_versions"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "media_assets" ADD FOREIGN KEY ("owner_user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "media_assets" ADD FOREIGN KEY ("course_id") REFERENCES "courses"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "media_jobs" ADD FOREIGN KEY ("owner_user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "media_jobs" ADD FOREIGN KEY ("input_asset_id") REFERENCES "media_assets"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "media_jobs" ADD FOREIGN KEY ("output_asset_id") REFERENCES "media_assets"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "playback_records" ADD FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "playback_records" ADD FOREIGN KEY ("turn_id") REFERENCES "tutoring_turns"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "playback_records" ADD FOREIGN KEY ("media_job_id") REFERENCES "media_jobs"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "playback_records" ADD FOREIGN KEY ("config_version_id") REFERENCES "avatar_config_versions"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "focus_sessions" ADD FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "focus_sessions" ADD FOREIGN KEY ("course_id") REFERENCES "courses"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "analytics_processed_events" ADD FOREIGN KEY ("consumer_id") REFERENCES "analytics_consumers"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "analytics_processed_events" ADD FOREIGN KEY ("event_id") REFERENCES "learning_events"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "analytics_daily_metrics" ADD FOREIGN KEY ("consumer_id") REFERENCES "analytics_consumers"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "analytics_daily_metrics" ADD FOREIGN KEY ("student_user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "analytics_daily_metrics" ADD FOREIGN KEY ("course_id") REFERENCES "courses"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "analytics_daily_metrics" ADD FOREIGN KEY ("class_id") REFERENCES "classes"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "analytics_daily_metrics" ADD FOREIGN KEY(class_id,course_id) REFERENCES classes(id,course_id) ON DELETE RESTRICT;

ALTER TABLE "analytics_report_snapshots" ADD FOREIGN KEY ("consumer_id") REFERENCES "analytics_consumers"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "analytics_report_snapshots" ADD FOREIGN KEY ("student_user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "analytics_report_snapshots" ADD FOREIGN KEY ("class_id") REFERENCES "classes"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "report_jobs" ADD FOREIGN KEY ("requested_by_user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "report_jobs" ADD FOREIGN KEY ("student_user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "report_jobs" ADD FOREIGN KEY ("class_id") REFERENCES "classes"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "report_jobs" ADD FOREIGN KEY ("consumer_id") REFERENCES "analytics_consumers"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "report_jobs" ADD FOREIGN KEY ("report_id") REFERENCES "analytics_report_snapshots"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "analytics_quarantined_events" ADD FOREIGN KEY ("consumer_id") REFERENCES "analytics_consumers"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "analytics_quarantined_events" ADD FOREIGN KEY ("event_id") REFERENCES "learning_events"("id") ON DELETE RESTRICT ON UPDATE NO ACTION;

ALTER TABLE "analytics_quarantined_events" ADD FOREIGN KEY ("resolved_by_user_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE NO ACTION;

CREATE VIEW v_learning_event_feed AS SELECT id AS event_id,event_type,user_id,course_id,class_id,occurred_at,recorded_at,trace_id,schema_version,payload FROM learning_events;

COMMENT ON TABLE "roles" IS '角色目录；owner M1；设计基线2026-10-24';

COMMENT ON COLUMN "roles"."code" IS '角色码；兼容JWT role';

COMMENT ON COLUMN "roles"."name" IS '角色中文名称';

COMMENT ON COLUMN "roles"."description" IS '角色职责说明';

COMMENT ON COLUMN "roles"."created_at" IS '定义时间';

COMMENT ON TABLE "users" IS '平台用户；owner M1；设计基线2026-10-24';

COMMENT ON COLUMN "users"."id" IS '用户标识；API userId/studentId/teacherId均引用此值';

COMMENT ON COLUMN "users"."username" IS '登录名原始展示值';

COMMENT ON COLUMN "users"."username_key" IS '登录名规范化值';

COMMENT ON COLUMN "users"."password_hash" IS '密码哈希及算法参数编码';

COMMENT ON COLUMN "users"."status" IS '账号状态';

COMMENT ON COLUMN "users"."created_at" IS '创建时间';

COMMENT ON COLUMN "users"."updated_at" IS '最后修改时间';

COMMENT ON TABLE "admin_audit_logs" IS '管理审计；owner M1；设计基线2026-10-24';

COMMENT ON COLUMN "admin_audit_logs"."id" IS '审计记录ID';

COMMENT ON COLUMN "admin_audit_logs"."actor_user_id" IS '操作者；系统动作/身份失效时可为空';

COMMENT ON COLUMN "admin_audit_logs"."actor_type" IS '操作者类别';

COMMENT ON COLUMN "admin_audit_logs"."action" IS '管理动作码';

COMMENT ON COLUMN "admin_audit_logs"."target_type" IS '目标实体类型';

COMMENT ON COLUMN "admin_audit_logs"."target_id" IS '目标实体ID快照';

COMMENT ON COLUMN "admin_audit_logs"."result" IS '操作结果';

COMMENT ON COLUMN "admin_audit_logs"."request_id" IS '请求追踪ID';

COMMENT ON COLUMN "admin_audit_logs"."details" IS '脱敏变更摘要';

COMMENT ON COLUMN "admin_audit_logs"."occurred_at" IS '审计发生时间';

COMMENT ON TABLE "auth_sessions" IS '持久认证会话；owner M1；设计基线2026-10-24';

COMMENT ON COLUMN "auth_sessions"."id" IS '持久会话记录ID';

COMMENT ON COLUMN "auth_sessions"."jti_digest" IS '现有JWT jti的SHA-256摘要';

COMMENT ON COLUMN "auth_sessions"."user_id" IS '会话用户；JWT sub';

COMMENT ON COLUMN "auth_sessions"."role_code" IS '签发角色快照';

COMMENT ON COLUMN "auth_sessions"."issued_at" IS '签发时间';

COMMENT ON COLUMN "auth_sessions"."expires_at" IS '过期时间';

COMMENT ON COLUMN "auth_sessions"."revoked_at" IS '退出/撤销时间';

COMMENT ON COLUMN "auth_sessions"."revoke_reason" IS '撤销原因';

COMMENT ON COLUMN "auth_sessions"."request_id" IS '签发请求追踪ID';

COMMENT ON TABLE "system_config_versions" IS '平台配置版本；owner M1；设计基线2026-10-24';

COMMENT ON COLUMN "system_config_versions"."id" IS '配置版本ID';

COMMENT ON COLUMN "system_config_versions"."config_key" IS '配置项标识';

COMMENT ON COLUMN "system_config_versions"."version" IS '递增版本号';

COMMENT ON COLUMN "system_config_versions"."status" IS '配置版本状态';

COMMENT ON COLUMN "system_config_versions"."value" IS '有版本的配置值';

COMMENT ON COLUMN "system_config_versions"."created_by_user_id" IS '创建者；系统seed可空';

COMMENT ON COLUMN "system_config_versions"."created_at" IS '版本创建时间';

COMMENT ON COLUMN "system_config_versions"."activated_at" IS '发布时间';

COMMENT ON TABLE "user_profiles" IS '用户资料；owner M1；设计基线2026-10-24';

COMMENT ON COLUMN "user_profiles"."user_id" IS '资料所属用户';

COMMENT ON COLUMN "user_profiles"."display_name" IS '显示名；API name';

COMMENT ON COLUMN "user_profiles"."student_number" IS '学号；教师/管理员可以为空';

COMMENT ON COLUMN "user_profiles"."major" IS '专业名称';

COMMENT ON COLUMN "user_profiles"."updated_at" IS '资料修改时间';

COMMENT ON TABLE "user_roles" IS '角色分配；owner M1；设计基线2026-10-24';

COMMENT ON COLUMN "user_roles"."user_id" IS '被授权用户';

COMMENT ON COLUMN "user_roles"."role_code" IS '角色码';

COMMENT ON COLUMN "user_roles"."is_primary" IS '当前API签发的单角色';

COMMENT ON COLUMN "user_roles"."granted_by_user_id" IS '授予人；系统seed时为空';

COMMENT ON COLUMN "user_roles"."granted_at" IS '授予时间';

COMMENT ON COLUMN "user_roles"."revoked_at" IS '撤销时间';

COMMENT ON TABLE "courses" IS '课程内容；owner M5；设计基线2026-10-24';

COMMENT ON COLUMN "courses"."id" IS '记录标识';

COMMENT ON COLUMN "courses"."title" IS '课程名';

COMMENT ON COLUMN "courses"."description" IS '课程简介';

COMMENT ON COLUMN "courses"."subject" IS '学科';

COMMENT ON COLUMN "courses"."cover_image_url" IS '封面地址';

COMMENT ON COLUMN "courses"."teacher_user_id" IS '课程主讲教师';

COMMENT ON COLUMN "courses"."created_at" IS '创建时刻';

COMMENT ON COLUMN "courses"."updated_at" IS '修改时刻';

COMMENT ON TABLE "classes" IS '教学班；owner M5；设计基线2026-10-24';

COMMENT ON COLUMN "classes"."id" IS '记录标识';

COMMENT ON COLUMN "classes"."course_id" IS '所属课程';

COMMENT ON COLUMN "classes"."teacher_user_id" IS '主讲教师';

COMMENT ON COLUMN "classes"."title" IS '班级名';

COMMENT ON COLUMN "classes"."semester" IS '学期';

COMMENT ON COLUMN "classes"."created_at" IS '创建时刻';

COMMENT ON COLUMN "classes"."updated_at" IS '修改时刻';

COMMENT ON TABLE "enrollments" IS '学生选课及班级归属历史；owner M5；设计基线2026-10-24';

COMMENT ON COLUMN "enrollments"."id" IS '记录标识';

COMMENT ON COLUMN "enrollments"."student_user_id" IS '学生';

COMMENT ON COLUMN "enrollments"."class_id" IS '教学班';

COMMENT ON COLUMN "enrollments"."joined_at" IS '加入时间';

COMMENT ON COLUMN "enrollments"."left_at" IS '退出时间';

COMMENT ON COLUMN "enrollments"."granted_by_user_id" IS '操作人';

COMMENT ON TABLE "teaching_assignments" IS '教师授课授权；owner M5；设计基线2026-10-24';

COMMENT ON COLUMN "teaching_assignments"."id" IS '记录标识';

COMMENT ON COLUMN "teaching_assignments"."teacher_user_id" IS '教师';

COMMENT ON COLUMN "teaching_assignments"."class_id" IS '教学班';

COMMENT ON COLUMN "teaching_assignments"."granted_at" IS '授予时间';

COMMENT ON COLUMN "teaching_assignments"."revoked_at" IS '撤销时间';

COMMENT ON COLUMN "teaching_assignments"."granted_by_user_id" IS '授予人';

COMMENT ON TABLE "chapters" IS '课程章节；owner M5；设计基线2026-10-24';

COMMENT ON COLUMN "chapters"."id" IS '记录标识';

COMMENT ON COLUMN "chapters"."course_id" IS '所属课程';

COMMENT ON COLUMN "chapters"."title" IS '章节名';

COMMENT ON COLUMN "chapters"."order" IS '课程内顺序';

COMMENT ON COLUMN "chapters"."description" IS '章节简介';

COMMENT ON COLUMN "chapters"."document_id" IS '关联课件版本';

COMMENT ON COLUMN "chapters"."created_at" IS '创建时刻';

COMMENT ON COLUMN "chapters"."updated_at" IS '修改时刻';

COMMENT ON TABLE "assignments" IS '作业发布与答案管理；owner M5；设计基线2026-10-24';

COMMENT ON COLUMN "assignments"."id" IS '记录标识';

COMMENT ON COLUMN "assignments"."course_id" IS '课程';

COMMENT ON COLUMN "assignments"."class_id" IS '教学班';

COMMENT ON COLUMN "assignments"."chapter_id" IS '章节';

COMMENT ON COLUMN "assignments"."teacher_user_id" IS '发布教师';

COMMENT ON COLUMN "assignments"."title" IS '作业名';

COMMENT ON COLUMN "assignments"."description" IS '题面说明';

COMMENT ON COLUMN "assignments"."question_type" IS '题型';

COMMENT ON COLUMN "assignments"."public_question" IS '学生可见题目与选项';

COMMENT ON COLUMN "assignments"."answer_key" IS '教师私有标准答案';

COMMENT ON COLUMN "assignments"."answer_key_schema_version" IS '答案键外置版本';

COMMENT ON COLUMN "assignments"."max_score" IS '满分';

COMMENT ON COLUMN "assignments"."due_at" IS '截止时刻';

COMMENT ON COLUMN "assignments"."published_at" IS '发布时间';

COMMENT ON COLUMN "assignments"."created_at" IS '创建时刻';

COMMENT ON COLUMN "assignments"."updated_at" IS '修改时刻';

COMMENT ON TABLE "submissions" IS '作业提交与批阅结果；owner M5；设计基线2026-10-24';

COMMENT ON COLUMN "submissions"."id" IS '记录标识';

COMMENT ON COLUMN "submissions"."assignment_id" IS '作业';

COMMENT ON COLUMN "submissions"."student_user_id" IS '提交学生';

COMMENT ON COLUMN "submissions"."course_id" IS '提交时课程快照';

COMMENT ON COLUMN "submissions"."class_id" IS '提交时班级快照';

COMMENT ON COLUMN "submissions"."answer" IS '学生答案';

COMMENT ON COLUMN "submissions"."answer_schema_version" IS '答案存储版本';

COMMENT ON COLUMN "submissions"."is_correct" IS '判分对错';

COMMENT ON COLUMN "submissions"."score" IS '得分';

COMMENT ON COLUMN "submissions"."graded_by" IS '判分来源';

COMMENT ON COLUMN "submissions"."graded_at" IS '批阅时间';

COMMENT ON COLUMN "submissions"."idempotency_key" IS '首次提交重试键';

COMMENT ON COLUMN "submissions"."request_hash" IS '规范化请求摘要';

COMMENT ON COLUMN "submissions"."revision" IS '乐观锁版本';

COMMENT ON COLUMN "submissions"."submitted_at" IS '首次提交时刻';

COMMENT ON COLUMN "submissions"."created_at" IS '创建时刻';

COMMENT ON COLUMN "submissions"."updated_at" IS '修改时刻';

COMMENT ON TABLE "mistakes" IS '个人错题快照；owner M5；设计基线2026-10-24';

COMMENT ON COLUMN "mistakes"."id" IS '记录标识';

COMMENT ON COLUMN "mistakes"."student_user_id" IS '所属学生';

COMMENT ON COLUMN "mistakes"."course_id" IS '课程';

COMMENT ON COLUMN "mistakes"."chapter_id" IS '章节';

COMMENT ON COLUMN "mistakes"."assignment_id" IS '作业';

COMMENT ON COLUMN "mistakes"."submission_id" IS '错误提交';

COMMENT ON COLUMN "mistakes"."source_turn_id" IS '主动标记答疑轮次';

COMMENT ON COLUMN "mistakes"."source" IS '收录来源';

COMMENT ON COLUMN "mistakes"."question" IS '题目快照';

COMMENT ON COLUMN "mistakes"."student_answer" IS '答案快照';

COMMENT ON COLUMN "mistakes"."snapshot_schema_version" IS '快照解码版本';

COMMENT ON COLUMN "mistakes"."note" IS '学生备注';

COMMENT ON COLUMN "mistakes"."status" IS '复习状态';

COMMENT ON COLUMN "mistakes"."created_at" IS '创建时刻';

COMMENT ON COLUMN "mistakes"."updated_at" IS '修改时刻';

COMMENT ON TABLE "study_plans" IS '预习复习计划；owner M5；设计基线2026-10-24';

COMMENT ON COLUMN "study_plans"."id" IS '记录标识';

COMMENT ON COLUMN "study_plans"."student_user_id" IS '所属学生';

COMMENT ON COLUMN "study_plans"."title" IS '计划名';

COMMENT ON COLUMN "study_plans"."course_id" IS '课程';

COMMENT ON COLUMN "study_plans"."chapter_id" IS '章节';

COMMENT ON COLUMN "study_plans"."source_turn_id" IS '授权导学建议来源';

COMMENT ON COLUMN "study_plans"."source" IS '来源';

COMMENT ON COLUMN "study_plans"."status" IS '计划状态';

COMMENT ON COLUMN "study_plans"."due_at" IS '整体截止';

COMMENT ON COLUMN "study_plans"."created_at" IS '创建时刻';

COMMENT ON COLUMN "study_plans"."updated_at" IS '修改时刻';

COMMENT ON TABLE "plan_items" IS '计划条目；owner M5；设计基线2026-10-24';

COMMENT ON COLUMN "plan_items"."id" IS '记录标识';

COMMENT ON COLUMN "plan_items"."plan_id" IS '所属计划';

COMMENT ON COLUMN "plan_items"."content" IS '任务内容';

COMMENT ON COLUMN "plan_items"."order" IS '条目顺序';

COMMENT ON COLUMN "plan_items"."status" IS '完成状态';

COMMENT ON COLUMN "plan_items"."due_at" IS '条目截止';

COMMENT ON COLUMN "plan_items"."chapter_id" IS '关联章节';

COMMENT ON COLUMN "plan_items"."knowledge_point" IS '知识点标签';

COMMENT ON COLUMN "plan_items"."related_mistake_id" IS '关联错题';

COMMENT ON COLUMN "plan_items"."related_assignment_id" IS '关联作业';

COMMENT ON COLUMN "plan_items"."created_at" IS '创建时刻';

COMMENT ON COLUMN "plan_items"."updated_at" IS '修改时刻';

COMMENT ON TABLE "reminders" IS '站内截止与复习提醒；owner M5；设计基线2026-10-24';

COMMENT ON COLUMN "reminders"."id" IS '记录标识';

COMMENT ON COLUMN "reminders"."student_user_id" IS '接收学生';

COMMENT ON COLUMN "reminders"."plan_id" IS '计划';

COMMENT ON COLUMN "reminders"."assignment_id" IS '作业';

COMMENT ON COLUMN "reminders"."type" IS '提醒类型';

COMMENT ON COLUMN "reminders"."title" IS '提醒标题';

COMMENT ON COLUMN "reminders"."body" IS '提醒正文';

COMMENT ON COLUMN "reminders"."due_at" IS '关联截止';

COMMENT ON COLUMN "reminders"."is_read" IS '是否已读';

COMMENT ON COLUMN "reminders"."read_at" IS '阅读时刻';

COMMENT ON COLUMN "reminders"."dedup_key" IS '扫描生成去重键';

COMMENT ON COLUMN "reminders"."created_at" IS '创建时刻';

COMMENT ON TABLE "learning_events" IS '不可变学习事件与幂等事实；owner M5；设计基线2026-10-24';

COMMENT ON COLUMN "learning_events"."id" IS '记录标识';

COMMENT ON COLUMN "learning_events"."event_type" IS '事件类型';

COMMENT ON COLUMN "learning_events"."user_id" IS '学生主体';

COMMENT ON COLUMN "learning_events"."course_id" IS '课程';

COMMENT ON COLUMN "learning_events"."class_id" IS '发生时教学班快照';

COMMENT ON COLUMN "learning_events"."occurred_at" IS '实际发生时刻';

COMMENT ON COLUMN "learning_events"."recorded_at" IS '数据库接受时刻';

COMMENT ON COLUMN "learning_events"."trace_id" IS '平台请求号';

COMMENT ON COLUMN "learning_events"."schema_version" IS '事件envelope版本';

COMMENT ON COLUMN "learning_events"."payload" IS '事件特有数据';

COMMENT ON COLUMN "learning_events"."idempotency_key" IS '章节浏览动作幂等键';

COMMENT ON COLUMN "learning_events"."request_hash" IS '浏览请求摘要';

COMMENT ON TABLE "tutoring_sessions" IS '学生私有多轮答疑会话；owner M3；设计基线2026-10-24';

COMMENT ON COLUMN "tutoring_sessions"."id" IS '记录标识';

COMMENT ON COLUMN "tutoring_sessions"."student_user_id" IS '所属学生';

COMMENT ON COLUMN "tutoring_sessions"."course_id" IS '课程上下文';

COMMENT ON COLUMN "tutoring_sessions"."current_stage" IS '当前教学阶段';

COMMENT ON COLUMN "tutoring_sessions"."created_at" IS '创建时刻';

COMMENT ON COLUMN "tutoring_sessions"."updated_at" IS '修改时刻';

COMMENT ON TABLE "tutoring_turns" IS '答疑轮次和完整性结算；owner M3；设计基线2026-10-24';

COMMENT ON COLUMN "tutoring_turns"."id" IS '记录标识';

COMMENT ON COLUMN "tutoring_turns"."session_id" IS '所属会话';

COMMENT ON COLUMN "tutoring_turns"."seq" IS '会话内轮次';

COMMENT ON COLUMN "tutoring_turns"."request_id" IS '创建请求号';

COMMENT ON COLUMN "tutoring_turns"."student_content" IS '学生问题';

COMMENT ON COLUMN "tutoring_turns"."assistant_content" IS '已生成正文或中断部分';

COMMENT ON COLUMN "tutoring_turns"."stage" IS '本轮冻结阶段';

COMMENT ON COLUMN "tutoring_turns"."status" IS '持久化轮次状态';

COMMENT ON COLUMN "tutoring_turns"."abort_reason" IS '内部中断原因';

COMMENT ON COLUMN "tutoring_turns"."is_complete" IS '完整回答标志';

COMMENT ON COLUMN "tutoring_turns"."is_mock" IS 'Mock来源标志';

COMMENT ON COLUMN "tutoring_turns"."emotion" IS '冻结情绪';

COMMENT ON COLUMN "tutoring_turns"."action" IS '冻结动作';

COMMENT ON COLUMN "tutoring_turns"."follow_ups" IS '追问建议';

COMMENT ON COLUMN "tutoring_turns"."prompt_version_id" IS '提示词版本';

COMMENT ON COLUMN "tutoring_turns"."model_config_version_id" IS '模型配置版本';

COMMENT ON COLUMN "tutoring_turns"."input_tokens" IS '输入token量';

COMMENT ON COLUMN "tutoring_turns"."output_tokens" IS '输出token量';

COMMENT ON COLUMN "tutoring_turns"."duration_ms" IS '耗时毫秒';

COMMENT ON COLUMN "tutoring_turns"."error_code" IS '错误码';

COMMENT ON COLUMN "tutoring_turns"."error_reason" IS '内部原因码';

COMMENT ON COLUMN "tutoring_turns"."created_at" IS '创建时刻';

COMMENT ON COLUMN "tutoring_turns"."settled_at" IS '终态时刻';

COMMENT ON TABLE "turn_citations" IS '轮次引用与证据快照；owner M3；设计基线2026-10-24';

COMMENT ON COLUMN "turn_citations"."turn_id" IS '轮次';

COMMENT ON COLUMN "turn_citations"."citation_id" IS '轮内标签';

COMMENT ON COLUMN "turn_citations"."document_id" IS '文档版本';

COMMENT ON COLUMN "turn_citations"."chunk_id" IS '原片段';

COMMENT ON COLUMN "turn_citations"."document_title_snapshot" IS '引用时标题';

COMMENT ON COLUMN "turn_citations"."document_version" IS '引用时版本';

COMMENT ON COLUMN "turn_citations"."page_number" IS '页码';

COMMENT ON COLUMN "turn_citations"."snippet" IS '证据片段';

COMMENT ON COLUMN "turn_citations"."created_at" IS '创建时刻';

COMMENT ON TABLE "documents" IS '版本化课程文档元数据；owner M3；设计基线2026-10-24';

COMMENT ON COLUMN "documents"."id" IS '记录标识';

COMMENT ON COLUMN "documents"."course_id" IS '课程';

COMMENT ON COLUMN "documents"."uploader_user_id" IS '上传者';

COMMENT ON COLUMN "documents"."title" IS '文档标题';

COMMENT ON COLUMN "documents"."storage_key" IS '受控文件存储键';

COMMENT ON COLUMN "documents"."file_sha256" IS '文件摘要';

COMMENT ON COLUMN "documents"."mime_type" IS '媒体类型';

COMMENT ON COLUMN "documents"."byte_size" IS '文件字节数';

COMMENT ON COLUMN "documents"."version" IS '文档版本';

COMMENT ON COLUMN "documents"."previous_document_id" IS '前一版本';

COMMENT ON COLUMN "documents"."status" IS '可检索状态';

COMMENT ON COLUMN "documents"."created_at" IS '创建时刻';

COMMENT ON COLUMN "documents"."updated_at" IS '修改时刻';

COMMENT ON TABLE "document_chunks" IS '可定位文档片段；owner M3；设计基线2026-10-24';

COMMENT ON COLUMN "document_chunks"."id" IS '记录标识';

COMMENT ON COLUMN "document_chunks"."document_id" IS '文档版本';

COMMENT ON COLUMN "document_chunks"."chunk_index" IS '文档内序号';

COMMENT ON COLUMN "document_chunks"."page_number" IS '页码';

COMMENT ON COLUMN "document_chunks"."char_start" IS '页内起点';

COMMENT ON COLUMN "document_chunks"."char_end" IS '页内终点';

COMMENT ON COLUMN "document_chunks"."text" IS '片段正文';

COMMENT ON COLUMN "document_chunks"."text_sha256" IS '正文摘要';

COMMENT ON COLUMN "document_chunks"."created_at" IS '创建时刻';

COMMENT ON TABLE "document_grants" IS '文档例外授权及班级授权；owner M3；设计基线2026-10-24';

COMMENT ON COLUMN "document_grants"."id" IS '记录标识';

COMMENT ON COLUMN "document_grants"."document_id" IS '文档';

COMMENT ON COLUMN "document_grants"."user_id" IS '被授权个人';

COMMENT ON COLUMN "document_grants"."class_id" IS '被授权班级';

COMMENT ON COLUMN "document_grants"."granted_by_user_id" IS '授权操作人';

COMMENT ON COLUMN "document_grants"."granted_at" IS '授权时刻';

COMMENT ON COLUMN "document_grants"."revoked_at" IS '撤销时刻';

COMMENT ON TABLE "document_import_jobs" IS '课件解析任务与重试；owner M3；设计基线2026-10-24';

COMMENT ON COLUMN "document_import_jobs"."id" IS '记录标识';

COMMENT ON COLUMN "document_import_jobs"."document_id" IS '输入文档版本';

COMMENT ON COLUMN "document_import_jobs"."parser_version" IS '解析器版本';

COMMENT ON COLUMN "document_import_jobs"."idempotency_key" IS '重试幂等键';

COMMENT ON COLUMN "document_import_jobs"."status" IS '任务状态';

COMMENT ON COLUMN "document_import_jobs"."request_id" IS '请求追踪号';

COMMENT ON COLUMN "document_import_jobs"."attempts" IS '尝试次数';

COMMENT ON COLUMN "document_import_jobs"."error_code" IS '脱敏失败码';

COMMENT ON COLUMN "document_import_jobs"."pages_without_text" IS '无文字页报告';

COMMENT ON COLUMN "document_import_jobs"."created_at" IS '创建时刻';

COMMENT ON COLUMN "document_import_jobs"."started_at" IS '开始时刻';

COMMENT ON COLUMN "document_import_jobs"."finished_at" IS '结束时刻';

COMMENT ON TABLE "prompt_versions" IS '提示词发布版本目录；owner M3；设计基线2026-10-24';

COMMENT ON COLUMN "prompt_versions"."id" IS '记录标识';

COMMENT ON COLUMN "prompt_versions"."series" IS '模板系列';

COMMENT ON COLUMN "prompt_versions"."version_label" IS 'API提示词版本';

COMMENT ON COLUMN "prompt_versions"."template_path" IS '仓库相对路径';

COMMENT ON COLUMN "prompt_versions"."content_sha256" IS '正文摘要';

COMMENT ON COLUMN "prompt_versions"."status" IS '发布状态';

COMMENT ON COLUMN "prompt_versions"."created_by_user_id" IS '登记人';

COMMENT ON COLUMN "prompt_versions"."created_at" IS '创建时刻';

COMMENT ON COLUMN "prompt_versions"."activated_at" IS '启用时刻';

COMMENT ON COLUMN "prompt_versions"."retired_at" IS '退役时刻';

COMMENT ON TABLE "model_config_versions" IS '模型配置版本；owner M3；设计基线2026-10-24';

COMMENT ON COLUMN "model_config_versions"."id" IS '记录标识';

COMMENT ON COLUMN "model_config_versions"."config_key" IS '配置用途';

COMMENT ON COLUMN "model_config_versions"."version" IS '版本号';

COMMENT ON COLUMN "model_config_versions"."provider" IS '受控供应商代码';

COMMENT ON COLUMN "model_config_versions"."model_name" IS '模型名';

COMMENT ON COLUMN "model_config_versions"."is_mock" IS 'Mock配置';

COMMENT ON COLUMN "model_config_versions"."temperature" IS '采样温度';

COMMENT ON COLUMN "model_config_versions"."max_output_tokens" IS '最大输出token';

COMMENT ON COLUMN "model_config_versions"."timeout_seconds" IS '总超时秒';

COMMENT ON COLUMN "model_config_versions"."status" IS '配置状态';

COMMENT ON COLUMN "model_config_versions"."created_by_user_id" IS '创建人';

COMMENT ON COLUMN "model_config_versions"."created_at" IS '创建时刻';

COMMENT ON COLUMN "model_config_versions"."activated_at" IS '发布时间';

COMMENT ON COLUMN "model_config_versions"."retired_at" IS '退役时间';

COMMENT ON TABLE "avatar_config_versions" IS '数字人教学风格版本；owner M4；设计基线2026-10-24';

COMMENT ON COLUMN "avatar_config_versions"."id" IS '记录标识';

COMMENT ON COLUMN "avatar_config_versions"."config_key" IS '风格用途';

COMMENT ON COLUMN "avatar_config_versions"."version" IS '版本';

COMMENT ON COLUMN "avatar_config_versions"."name" IS '风格名';

COMMENT ON COLUMN "avatar_config_versions"."config" IS '形象和教学参数';

COMMENT ON COLUMN "avatar_config_versions"."status" IS '发布状态';

COMMENT ON COLUMN "avatar_config_versions"."created_by_user_id" IS '创建人';

COMMENT ON COLUMN "avatar_config_versions"."created_at" IS '创建时刻';

COMMENT ON TABLE "avatar_profiles" IS '个人数字人和语音偏好；owner M4；设计基线2026-10-24';

COMMENT ON COLUMN "avatar_profiles"."id" IS '记录标识';

COMMENT ON COLUMN "avatar_profiles"."user_id" IS '偏好所属用户';

COMMENT ON COLUMN "avatar_profiles"."config_version_id" IS '风格版本';

COMMENT ON COLUMN "avatar_profiles"."auto_play" IS '自动播报';

COMMENT ON COLUMN "avatar_profiles"."volume" IS '音量';

COMMENT ON COLUMN "avatar_profiles"."speech_rate" IS '语速';

COMMENT ON COLUMN "avatar_profiles"."subtitles_enabled" IS '字幕';

COMMENT ON COLUMN "avatar_profiles"."created_at" IS '创建时刻';

COMMENT ON COLUMN "avatar_profiles"."updated_at" IS '修改时刻';

COMMENT ON TABLE "media_assets" IS '媒体文件和录音授权元数据；owner M4；设计基线2026-10-24';

COMMENT ON COLUMN "media_assets"."id" IS '记录标识';

COMMENT ON COLUMN "media_assets"."owner_user_id" IS '文件owner';

COMMENT ON COLUMN "media_assets"."course_id" IS '课程';

COMMENT ON COLUMN "media_assets"."storage_key" IS '私有存储键';

COMMENT ON COLUMN "media_assets"."sha256" IS '文件摘要';

COMMENT ON COLUMN "media_assets"."mime_type" IS '实际媒体类型';

COMMENT ON COLUMN "media_assets"."byte_size" IS '字节大小';

COMMENT ON COLUMN "media_assets"."kind" IS '资产类型';

COMMENT ON COLUMN "media_assets"."status" IS '资产生命周期';

COMMENT ON COLUMN "media_assets"."consent_version" IS '录音/处理同意版本';

COMMENT ON COLUMN "media_assets"."consented_at" IS '同意时刻';

COMMENT ON COLUMN "media_assets"."expires_at" IS '到期时刻';

COMMENT ON COLUMN "media_assets"."deleted_at" IS '完成删除时刻';

COMMENT ON COLUMN "media_assets"."created_at" IS '创建时刻';

COMMENT ON COLUMN "media_assets"."updated_at" IS '修改时刻';

COMMENT ON TABLE "media_jobs" IS '语音与媒体处理任务；owner M4；设计基线2026-10-24';

COMMENT ON COLUMN "media_jobs"."id" IS '记录标识';

COMMENT ON COLUMN "media_jobs"."owner_user_id" IS '任务owner';

COMMENT ON COLUMN "media_jobs"."input_asset_id" IS '输入资产';

COMMENT ON COLUMN "media_jobs"."output_asset_id" IS '输出资产';

COMMENT ON COLUMN "media_jobs"."job_type" IS '处理类型';

COMMENT ON COLUMN "media_jobs"."processor_version" IS '处理器版本';

COMMENT ON COLUMN "media_jobs"."is_mock" IS 'Mock标识';

COMMENT ON COLUMN "media_jobs"."idempotency_key" IS '重试键';

COMMENT ON COLUMN "media_jobs"."request_hash" IS '请求摘要';

COMMENT ON COLUMN "media_jobs"."params" IS '非敏感处理参数';

COMMENT ON COLUMN "media_jobs"."status" IS '任务状态';

COMMENT ON COLUMN "media_jobs"."attempts" IS '尝试次数';

COMMENT ON COLUMN "media_jobs"."error_code" IS '脱敏错误码';

COMMENT ON COLUMN "media_jobs"."request_id" IS '请求号';

COMMENT ON COLUMN "media_jobs"."created_at" IS '创建时刻';

COMMENT ON COLUMN "media_jobs"."started_at" IS '开始时刻';

COMMENT ON COLUMN "media_jobs"."finished_at" IS '结束时刻';

COMMENT ON TABLE "playback_records" IS '播报标识与唯一终态；owner M4；设计基线2026-10-24';

COMMENT ON COLUMN "playback_records"."id" IS '记录标识';

COMMENT ON COLUMN "playback_records"."utterance_id" IS '前端播报标识';

COMMENT ON COLUMN "playback_records"."user_id" IS '播报用户';

COMMENT ON COLUMN "playback_records"."turn_id" IS '完整答疑来源';

COMMENT ON COLUMN "playback_records"."media_job_id" IS '语音任务';

COMMENT ON COLUMN "playback_records"."config_version_id" IS '风格版本';

COMMENT ON COLUMN "playback_records"."is_mock" IS '是否Mock';

COMMENT ON COLUMN "playback_records"."status" IS '播报状态';

COMMENT ON COLUMN "playback_records"."stop_reason" IS '停止原因';

COMMENT ON COLUMN "playback_records"."error_code" IS '错误码';

COMMENT ON COLUMN "playback_records"."started_at" IS '开始时刻';

COMMENT ON COLUMN "playback_records"."ended_at" IS '终态时刻';

COMMENT ON COLUMN "playback_records"."duration_ms" IS '耗时毫秒';

COMMENT ON TABLE "focus_sessions" IS '主动专注计时；owner M4；设计基线2026-10-24';

COMMENT ON COLUMN "focus_sessions"."id" IS '记录标识';

COMMENT ON COLUMN "focus_sessions"."user_id" IS '学生';

COMMENT ON COLUMN "focus_sessions"."course_id" IS '课程';

COMMENT ON COLUMN "focus_sessions"."started_at" IS '开始时刻';

COMMENT ON COLUMN "focus_sessions"."ended_at" IS '结束时刻';

COMMENT ON COLUMN "focus_sessions"."duration_seconds" IS '有效秒数';

COMMENT ON COLUMN "focus_sessions"."status" IS '计时状态';

COMMENT ON COLUMN "focus_sessions"."idempotency_key" IS '创建重试键';

COMMENT ON TABLE "analytics_consumers" IS '消费者与算法发布状态；owner M6；设计基线2026-10-24';

COMMENT ON COLUMN "analytics_consumers"."id" IS '记录标识';

COMMENT ON COLUMN "analytics_consumers"."consumer_key" IS '消费者名称';

COMMENT ON COLUMN "analytics_consumers"."algorithm_version" IS '算法版本';

COMMENT ON COLUMN "analytics_consumers"."status" IS '消费者状态';

COMMENT ON COLUMN "analytics_consumers"."last_poll_at" IS '最近扫描时间';

COMMENT ON COLUMN "analytics_consumers"."last_observed_at" IS '最近观察事件时刻';

COMMENT ON COLUMN "analytics_consumers"."processed_count" IS '累计处理量';

COMMENT ON COLUMN "analytics_consumers"."created_at" IS '创建时刻';

COMMENT ON COLUMN "analytics_consumers"."updated_at" IS '修改时刻';

COMMENT ON TABLE "analytics_processed_events" IS '已处理事件账本；owner M6；设计基线2026-10-24';

COMMENT ON COLUMN "analytics_processed_events"."consumer_id" IS '消费者版本';

COMMENT ON COLUMN "analytics_processed_events"."event_id" IS '源事件';

COMMENT ON COLUMN "analytics_processed_events"."processed_at" IS '成功处理时刻';

COMMENT ON COLUMN "analytics_processed_events"."source_hash" IS '源事实摘要';

COMMENT ON TABLE "analytics_daily_metrics" IS '学生班级日统计；owner M6；设计基线2026-10-24';

COMMENT ON COLUMN "analytics_daily_metrics"."id" IS '记录标识';

COMMENT ON COLUMN "analytics_daily_metrics"."consumer_id" IS '算法消费者';

COMMENT ON COLUMN "analytics_daily_metrics"."student_user_id" IS '学生';

COMMENT ON COLUMN "analytics_daily_metrics"."course_id" IS '课程';

COMMENT ON COLUMN "analytics_daily_metrics"."class_id" IS '发生时班级';

COMMENT ON COLUMN "analytics_daily_metrics"."metric_date" IS '统计本地日';

COMMENT ON COLUMN "analytics_daily_metrics"."timezone" IS '日界时区';

COMMENT ON COLUMN "analytics_daily_metrics"."study_seconds" IS '推断学习秒';

COMMENT ON COLUMN "analytics_daily_metrics"."submission_count" IS '提交数';

COMMENT ON COLUMN "analytics_daily_metrics"."wrong_count" IS '已判错数量';

COMMENT ON COLUMN "analytics_daily_metrics"."sample_count" IS '有效样本数';

COMMENT ON COLUMN "analytics_daily_metrics"."data_state" IS '数据状态';

COMMENT ON COLUMN "analytics_daily_metrics"."data_through" IS '本范围纳入最新发生时间';

COMMENT ON COLUMN "analytics_daily_metrics"."created_at" IS '创建时刻';

COMMENT ON COLUMN "analytics_daily_metrics"."updated_at" IS '修改时刻';

COMMENT ON TABLE "analytics_report_snapshots" IS '个人和班级成长报告快照；owner M6；设计基线2026-10-24';

COMMENT ON COLUMN "analytics_report_snapshots"."id" IS '记录标识';

COMMENT ON COLUMN "analytics_report_snapshots"."consumer_id" IS '算法版本';

COMMENT ON COLUMN "analytics_report_snapshots"."student_user_id" IS '个人报告主体';

COMMENT ON COLUMN "analytics_report_snapshots"."class_id" IS '班级报告范围';

COMMENT ON COLUMN "analytics_report_snapshots"."period_start" IS '周期起点';

COMMENT ON COLUMN "analytics_report_snapshots"."period_end" IS '周期终点';

COMMENT ON COLUMN "analytics_report_snapshots"."metrics" IS '指标与知识点掌握度';

COMMENT ON COLUMN "analytics_report_snapshots"."sample_count" IS '样本数';

COMMENT ON COLUMN "analytics_report_snapshots"."data_through" IS '纳入最新发生时间';

COMMENT ON COLUMN "analytics_report_snapshots"."generated_at" IS '生成时间';

COMMENT ON TABLE "report_jobs" IS '周月报告生成任务；owner M6；设计基线2026-10-24';

COMMENT ON COLUMN "report_jobs"."id" IS '记录标识';

COMMENT ON COLUMN "report_jobs"."requested_by_user_id" IS '请求者';

COMMENT ON COLUMN "report_jobs"."student_user_id" IS '个人目标';

COMMENT ON COLUMN "report_jobs"."class_id" IS '班级目标';

COMMENT ON COLUMN "report_jobs"."consumer_id" IS '算法版本';

COMMENT ON COLUMN "report_jobs"."period_start" IS '开始';

COMMENT ON COLUMN "report_jobs"."period_end" IS '结束';

COMMENT ON COLUMN "report_jobs"."status" IS '生成状态';

COMMENT ON COLUMN "report_jobs"."idempotency_key" IS '请求重试键';

COMMENT ON COLUMN "report_jobs"."error_code" IS '脱敏错误码';

COMMENT ON COLUMN "report_jobs"."report_id" IS '结果快照';

COMMENT ON COLUMN "report_jobs"."created_at" IS '创建时刻';

COMMENT ON COLUMN "report_jobs"."finished_at" IS '终态时间';

COMMENT ON TABLE "analytics_quarantined_events" IS '毒事件隔离与审计重放；owner M6；设计基线2026-10-24';

COMMENT ON COLUMN "analytics_quarantined_events"."id" IS '记录标识';

COMMENT ON COLUMN "analytics_quarantined_events"."consumer_id" IS '消费者';

COMMENT ON COLUMN "analytics_quarantined_events"."event_id" IS '源事件';

COMMENT ON COLUMN "analytics_quarantined_events"."error_code" IS '脱敏失败码';

COMMENT ON COLUMN "analytics_quarantined_events"."status" IS '处理状态';

COMMENT ON COLUMN "analytics_quarantined_events"."attempts" IS '失败次数';

COMMENT ON COLUMN "analytics_quarantined_events"."resolved_by_user_id" IS '人工处理者';

COMMENT ON COLUMN "analytics_quarantined_events"."first_failed_at" IS '首次失败';

COMMENT ON COLUMN "analytics_quarantined_events"."last_failed_at" IS '最近失败';

COMMENT ON COLUMN "analytics_quarantined_events"."resolved_at" IS '重放解决时刻';

COMMIT;
