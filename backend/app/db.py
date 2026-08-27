from __future__ import annotations

import sqlite3
from pathlib import Path

MIGRATIONS: tuple[tuple[str, str], ...] = (
    (
        "001_foundation",
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('PATIENT', 'CLINICIAN', 'ADMIN')),
            mfa_secret TEXT,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            revoked_at TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS sessions_active_idx ON sessions(token_hash, expires_at);
        CREATE TABLE IF NOT EXISTS audit_logs (
            id TEXT PRIMARY KEY,
            occurred_at TEXT NOT NULL,
            request_id TEXT NOT NULL,
            actor_id TEXT,
            action TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            resource_id TEXT,
            outcome TEXT NOT NULL CHECK(outcome IN ('SUCCESS', 'DENIED', 'FAILURE')),
            metadata TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS audit_logs_occurred_idx ON audit_logs(occurred_at);
        """,
    ),
    (
        "002_patient_platform",
        """
        CREATE TABLE IF NOT EXISTS profiles (
            user_id TEXT PRIMARY KEY REFERENCES users(id),
            display_name TEXT NOT NULL DEFAULT '',
            onboarding_completed_at TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS consents (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            purpose TEXT NOT NULL CHECK(purpose IN ('CARE', 'LEARNING')),
            version TEXT NOT NULL,
            granted_at TEXT NOT NULL,
            revoked_at TEXT,
            UNIQUE(user_id, purpose, version)
        );
        CREATE TABLE IF NOT EXISTS deletion_requests (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            status TEXT NOT NULL CHECK(status IN ('OPEN', 'COMPLETED', 'CANCELLED')),
            created_at TEXT NOT NULL,
            UNIQUE(user_id, status)
        );
        """,
    ),
    ("003_phq9", """
        CREATE TABLE IF NOT EXISTS phq9_assessments (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), instrument_version TEXT NOT NULL,
            answers_json TEXT NOT NULL, total_score INTEGER NOT NULL CHECK(total_score BETWEEN 0 AND 27),
            item9_score INTEGER NOT NULL CHECK(item9_score BETWEEN 0 AND 3), completed_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS phq9_user_time_idx ON phq9_assessments(user_id, completed_at DESC);
    """),
    ("004_alerts", """
        CREATE TABLE IF NOT EXISTS alerts (id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES users(id), level TEXT NOT NULL CHECK(level IN ('GREEN','ORANGE','RED')), status TEXT NOT NULL CHECK(status IN ('OPEN','ACKNOWLEDGED','IN_REVIEW','ESCALATED','RESOLVED','CLOSED','CANCELLED')), idempotency_key TEXT NOT NULL UNIQUE, score REAL NOT NULL, policy_version TEXT NOT NULL, created_at TEXT NOT NULL, acknowledged_at TEXT);
        CREATE INDEX IF NOT EXISTS alerts_status_idx ON alerts(status, level, created_at DESC);
        CREATE TABLE IF NOT EXISTS alert_actions (id TEXT PRIMARY KEY, alert_id TEXT NOT NULL REFERENCES alerts(id), actor_id TEXT REFERENCES users(id), action TEXT NOT NULL, justification TEXT, created_at TEXT NOT NULL);
    """),
    ("005_crisis_and_notifications", """
        CREATE TABLE IF NOT EXISTS risk_assessments (
            id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES users(id), input_reference TEXT NOT NULL,
            score REAL NOT NULL CHECK(score BETWEEN 0 AND 1), confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),
            model_version TEXT NOT NULL, model_available INTEGER NOT NULL CHECK(model_available IN (0,1)), created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS risk_assessments_patient_idx ON risk_assessments(patient_id, created_at DESC);
        CREATE TABLE IF NOT EXISTS crisis_events (
            id TEXT PRIMARY KEY, risk_assessment_id TEXT NOT NULL REFERENCES risk_assessments(id), patient_id TEXT NOT NULL REFERENCES users(id),
            level TEXT NOT NULL CHECK(level IN ('GREEN','ORANGE','RED')), reasons TEXT NOT NULL,
            rules_version TEXT NOT NULL, policy_version TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS crisis_events_patient_idx ON crisis_events(patient_id, created_at DESC);
        ALTER TABLE alerts ADD COLUMN crisis_event_id TEXT REFERENCES crisis_events(id);
        CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY, alert_id TEXT NOT NULL REFERENCES alerts(id), channel TEXT NOT NULL, template_version TEXT NOT NULL,
            delivery_status TEXT NOT NULL CHECK(delivery_status IN ('PENDING','SENT','FAILED','SKIPPED_NO_CHANNEL')),
            provider_ref TEXT, attempt_count INTEGER NOT NULL DEFAULT 0, idempotency_key TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS notifications_alert_idx ON notifications(alert_id, channel);
    """),
    ("006_patient_clinician_relationships", """
        CREATE TABLE IF NOT EXISTS patient_clinician_relationships (
            id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES users(id), clinician_id TEXT NOT NULL REFERENCES users(id),
            status TEXT NOT NULL CHECK(status IN ('ACTIVE','ENDED')), created_by TEXT NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL, ends_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS relationships_active_pair_idx ON patient_clinician_relationships(patient_id, clinician_id) WHERE status='ACTIVE';
        CREATE INDEX IF NOT EXISTS relationships_clinician_idx ON patient_clinician_relationships(clinician_id, status);
        CREATE INDEX IF NOT EXISTS relationships_patient_idx ON patient_clinician_relationships(patient_id, status);
    """),
    ("007_conversations", """
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES users(id),
            status TEXT NOT NULL CHECK(status IN ('ACTIVE','CLOSED')), created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS conversations_patient_idx ON conversations(patient_id, created_at DESC);
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id),
            author_type TEXT NOT NULL CHECK(author_type IN ('PATIENT','ASSISTANT')),
            content TEXT NOT NULL, sequence_no INTEGER NOT NULL,
            responder_version TEXT, crisis_event_id TEXT REFERENCES crisis_events(id),
            created_at TEXT NOT NULL,
            UNIQUE(conversation_id, sequence_no)
        );
        CREATE INDEX IF NOT EXISTS messages_conversation_idx ON messages(conversation_id, sequence_no);
    """),
    ("008_emotion_observability", """
        ALTER TABLE risk_assessments ADD COLUMN emotion_label TEXT;
        ALTER TABLE risk_assessments ADD COLUMN emotion_confidence REAL;
        ALTER TABLE risk_assessments ADD COLUMN emotion_model_version TEXT;
    """),
    ("009_notification_retry_scheduling", """
        ALTER TABLE notifications ADD COLUMN next_retry_at TEXT;
    """),
    ("010_continuous_learning", """
        CREATE TABLE IF NOT EXISTS human_feedback (
            id TEXT PRIMARY KEY, message_id TEXT NOT NULL REFERENCES messages(id) UNIQUE,
            anonymized_content TEXT NOT NULL, anonymization_version TEXT NOT NULL,
            review_status TEXT NOT NULL CHECK(review_status IN ('PENDING','APPROVED','REJECTED')),
            reviewed_by TEXT REFERENCES users(id), review_justification TEXT, reviewed_at TEXT,
            sampled_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS human_feedback_status_idx ON human_feedback(review_status, sampled_at);

        CREATE TABLE IF NOT EXISTS training_datasets (
            id TEXT PRIMARY KEY, version TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL CHECK(status IN ('DRAFT','FINALIZED')),
            created_by TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
            item_count INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS training_dataset_items (
            dataset_id TEXT NOT NULL REFERENCES training_datasets(id),
            human_feedback_id TEXT NOT NULL REFERENCES human_feedback(id),
            PRIMARY KEY (dataset_id, human_feedback_id)
        );

        CREATE TABLE IF NOT EXISTS model_versions (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('LLM','EMOTION','RISK','CRISIS')),
            version TEXT NOT NULL, dataset_id TEXT REFERENCES training_datasets(id),
            status TEXT NOT NULL CHECK(status IN ('DRAFT','PENDING_REVIEW','APPROVED','DEPLOYED','ROLLED_BACK','REJECTED')),
            metrics_json TEXT NOT NULL DEFAULT '{}',
            created_by TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
            UNIQUE(kind, version)
        );
        CREATE TABLE IF NOT EXISTS model_approvals (
            id TEXT PRIMARY KEY, model_version_id TEXT NOT NULL REFERENCES model_versions(id),
            approver_id TEXT NOT NULL REFERENCES users(id),
            decision TEXT NOT NULL CHECK(decision IN ('APPROVED','REJECTED')),
            justification TEXT NOT NULL, created_at TEXT NOT NULL,
            UNIQUE(model_version_id, approver_id)
        );
    """),
)


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    for version, script in MIGRATIONS:
        exists = conn.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (version,)).fetchone()
        if exists:
            continue
        # version comes only from the hardcoded MIGRATIONS tuple above, never from user input
        conn.executescript("BEGIN;" + script + "INSERT INTO schema_migrations(version, applied_at) VALUES ('" + version + "', strftime('%Y-%m-%dT%H:%M:%fZ','now')); COMMIT;")  # nosec B608
