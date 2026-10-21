"""Baseline schema.

Revision ID: 20260527_0001
Revises:
Create Date: 2026-05-27
"""

from alembic import op
import datetime
import sqlalchemy as sa

revision = "20260527_0001"
down_revision = None
branch_labels = None
depends_on = None

_SCHEMA_CACHE = {
    "tables": None,
    "columns": {},
    "indexes": {},
    "unique_constraints": {},
}


def _reset_schema_cache() -> None:
    _SCHEMA_CACHE["tables"] = None
    _SCHEMA_CACHE["columns"] = {}
    _SCHEMA_CACHE["indexes"] = {}
    _SCHEMA_CACHE["unique_constraints"] = {}


def _create_table(*args, **kwargs) -> None:
    op.create_table(*args, **kwargs)
    _reset_schema_cache()


def _existing_tables() -> set[str]:
    tables = _SCHEMA_CACHE["tables"]
    if tables is None:
        tables = set(sa.inspect(op.get_bind()).get_table_names())
        _SCHEMA_CACHE["tables"] = tables
    return set(tables)


def _existing_indexes(table_name: str) -> set[str]:
    if table_name not in _existing_tables():
        return set()
    indexes_by_table = _SCHEMA_CACHE["indexes"]
    if table_name not in indexes_by_table:
        indexes_by_table[table_name] = {
            str(item.get("name") or "")
            for item in sa.inspect(op.get_bind()).get_indexes(table_name)
        }
    return set(indexes_by_table[table_name])


def _existing_unique_constraints(table_name: str) -> set[str]:
    if table_name not in _existing_tables():
        return set()
    unique_constraints_by_table = _SCHEMA_CACHE["unique_constraints"]
    if table_name not in unique_constraints_by_table:
        unique_constraints_by_table[table_name] = {
            str(item.get("name") or "")
            for item in sa.inspect(op.get_bind()).get_unique_constraints(table_name)
        }
    return set(unique_constraints_by_table[table_name])


def _existing_columns(table_name: str) -> set[str]:
    if table_name not in _existing_tables():
        return set()
    columns_by_table = _SCHEMA_CACHE["columns"]
    if table_name not in columns_by_table:
        columns_by_table[table_name] = {
            str(item.get("name") or "")
            for item in sa.inspect(op.get_bind()).get_columns(table_name)
        }
    return set(columns_by_table[table_name])


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if table_name not in _existing_tables():
        return
    existing_columns = _existing_columns(table_name)
    column_name = str(column.name)
    if column_name in existing_columns:
        return
    op.add_column(table_name, column)
    existing_columns.add(column_name)
    _SCHEMA_CACHE["columns"][table_name] = existing_columns


def _create_index_if_missing(name: str, table_name: str, columns: list[str]) -> None:
    if table_name not in _existing_tables():
        return
    existing_columns = _existing_columns(table_name)
    if any(column not in existing_columns for column in columns):
        return
    if name in _existing_indexes(table_name):
        return
    op.create_index(name, table_name, columns)
    existing_indexes = _existing_indexes(table_name)
    existing_indexes.add(name)
    _SCHEMA_CACHE["indexes"][table_name] = existing_indexes


def _drop_unique_if_exists(name: str, table_name: str) -> None:
    if name not in _existing_unique_constraints(table_name):
        return
    if op.get_bind().dialect.name == "sqlite":
        return
    op.drop_constraint(name, table_name, type_="unique")
    existing_constraints = _existing_unique_constraints(table_name)
    existing_constraints.discard(name)
    _SCHEMA_CACHE["unique_constraints"][table_name] = existing_constraints


def _create_unique_if_missing(name: str, table_name: str, columns: list[str]) -> None:
    if table_name not in _existing_tables():
        return
    if name in _existing_unique_constraints(table_name):
        return
    existing_columns = _existing_columns(table_name)
    if any(column not in existing_columns for column in columns):
        return
    if op.get_bind().dialect.name == "sqlite":
        return
    op.create_unique_constraint(name, table_name, columns)
    existing_constraints = _existing_unique_constraints(table_name)
    existing_constraints.add(name)
    _SCHEMA_CACHE["unique_constraints"][table_name] = existing_constraints


def _ensure_existing_table_columns() -> None:
    _add_column_if_missing("user", sa.Column("tenant_id", sa.String(length=255), nullable=False, server_default="default"))
    _add_column_if_missing("user", sa.Column("remark", sa.String(length=255), nullable=True))
    _add_column_if_missing("user", sa.Column("app_password_hash", sa.Text(), nullable=True))
    _add_column_if_missing("user", sa.Column("app_enabled", sa.Boolean(), nullable=True))
    _add_column_if_missing("user", sa.Column("clockIn", sa.JSON(), nullable=True))
    _add_column_if_missing("user", sa.Column("reportSettings", sa.JSON(), nullable=True))
    _add_column_if_missing("user", sa.Column("ai", sa.JSON(), nullable=True))
    _add_column_if_missing("user", sa.Column("pushNotifications", sa.JSON(), nullable=True))
    _add_column_if_missing("user", sa.Column("device", sa.Text(), nullable=True))
    _add_column_if_missing("user", sa.Column("enable_clockin", sa.Boolean(), nullable=True))
    _add_column_if_missing("user", sa.Column("last_run_time", sa.String(length=255), nullable=True))
    _add_column_if_missing("user", sa.Column("last_status", sa.String(length=255), nullable=True))
    _add_column_if_missing("user", sa.Column("logs", sa.JSON(), nullable=True))
    _add_column_if_missing("user", sa.Column("last_execution_result", sa.JSON(), nullable=True))
    _add_column_if_missing("user", sa.Column("userInfo", sa.JSON(), nullable=True))
    _add_column_if_missing("user", sa.Column("planInfo", sa.JSON(), nullable=True))
    _add_column_if_missing("user", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("user", sa.Column("deleted_by", sa.String(length=255), nullable=True))
    _add_column_if_missing("user", sa.Column("delete_reason", sa.Text(), nullable=True))

    _add_column_if_missing("auditlog", sa.Column("tenant_id", sa.String(length=255), nullable=False, server_default="default"))
    _add_column_if_missing("batchjob", sa.Column("tenant_id", sa.String(length=255), nullable=False, server_default="default"))
    _add_column_if_missing("batchjob", sa.Column("cancel_requested", sa.Boolean(), nullable=True))
    _add_column_if_missing("batchjob", sa.Column("paused", sa.Boolean(), nullable=True))
    _add_column_if_missing("batchjobitem", sa.Column("tenant_id", sa.String(length=255), nullable=False, server_default="default"))
    _add_column_if_missing("batchjobitem", sa.Column("attempts", sa.Integer(), nullable=True))
    _add_column_if_missing("batchjobitem", sa.Column("max_attempts", sa.Integer(), nullable=True))
    _add_column_if_missing("batchjobitem", sa.Column("next_run_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("batchjobitem", sa.Column("locked_by", sa.String(length=255), nullable=True))
    _add_column_if_missing("batchjobitem", sa.Column("lock_token", sa.String(length=255), nullable=True))
    _add_column_if_missing("batchjobitem", sa.Column("lease_until", sa.DateTime(), nullable=True))
    _add_column_if_missing("batchjobitem", sa.Column("heartbeat_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("adminuser", sa.Column("tenant_id", sa.String(length=255), nullable=False, server_default="default"))
    _add_column_if_missing("adminuser", sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))
    _add_column_if_missing("adminuser", sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"))
    _add_column_if_missing("adminuser", sa.Column("locked_until", sa.DateTime(), nullable=True))
    _add_column_if_missing("adminuser", sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    _add_column_if_missing("adminuser", sa.Column("mfa_totp_secret", sa.Text(), nullable=True))
    _add_column_if_missing("adminuser", sa.Column("mfa_confirmed_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("appuser", sa.Column("tenant_id", sa.String(length=255), nullable=False, server_default="default"))
    _add_column_if_missing("appuser", sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))
    _add_column_if_missing("appuser", sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"))
    _add_column_if_missing("appuser", sa.Column("locked_until", sa.DateTime(), nullable=True))
    _add_column_if_missing("systemsetting", sa.Column("tenant_id", sa.String(length=255), nullable=False, server_default="default"))
    _add_column_if_missing("taskexecutionlock", sa.Column("tenant_id", sa.String(length=255), nullable=False, server_default="default"))
    _add_column_if_missing("taskexecutionevent", sa.Column("tenant_id", sa.String(length=255), nullable=False, server_default="default"))
    _add_column_if_missing("taskexecutionevent", sa.Column("request_id", sa.String(length=128), nullable=True))
    _add_column_if_missing("httprequestmetric", sa.Column("tenant_id", sa.String(length=255), nullable=False, server_default="default"))
    _add_column_if_missing("httprequestmetric", sa.Column("request_id", sa.String(length=128), nullable=True))


def _seed_default_tenant() -> None:
    if "tenant" not in _existing_tables():
        return
    exists = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM tenant WHERE id = 'default'")).scalar()
    if exists:
        return
    op.get_bind().execute(
        sa.text(
            "INSERT INTO tenant (id, name, status, created_at, settings) "
            "VALUES (:id, :name, :status, :created_at, :settings)"
        ),
        {
            "id": "default",
            "name": "Default Tenant",
            "status": "active",
            "created_at": datetime.datetime.now(datetime.timezone.utc),
            "settings": "{}",
        },
    )


def upgrade() -> None:
    existing = _existing_tables()
    if "tenant" not in existing:
        _create_table(
            "tenant",
            sa.Column("id", sa.String(length=255), primary_key=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("settings", sa.JSON(), nullable=True),
        )

    if "user" not in existing:
        _create_table(
            "user",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=255), nullable=False, server_default="default"),
            sa.Column("phone", sa.String(length=255), nullable=False),
            sa.Column("password", sa.Text(), nullable=False),
            sa.Column("remark", sa.String(length=255), nullable=True),
            sa.Column("app_password_hash", sa.Text(), nullable=True),
            sa.Column("app_enabled", sa.Boolean(), nullable=False),
            sa.Column("clockIn", sa.JSON(), nullable=True),
            sa.Column("reportSettings", sa.JSON(), nullable=True),
            sa.Column("ai", sa.JSON(), nullable=True),
            sa.Column("pushNotifications", sa.JSON(), nullable=True),
            sa.Column("device", sa.Text(), nullable=False),
            sa.Column("enable_clockin", sa.Boolean(), nullable=False),
            sa.Column("last_run_time", sa.String(length=255), nullable=True),
            sa.Column("last_status", sa.String(length=255), nullable=True),
            sa.Column("logs", sa.JSON(), nullable=True),
            sa.Column("last_execution_result", sa.JSON(), nullable=True),
            sa.Column("userInfo", sa.JSON(), nullable=True),
            sa.Column("planInfo", sa.JSON(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            sa.Column("deleted_by", sa.String(length=255), nullable=True),
            sa.Column("delete_reason", sa.Text(), nullable=True),
            sa.UniqueConstraint("tenant_id", "phone", name="uq_user_tenant_phone"),
        )

    if "auditlog" not in existing:
        _create_table(
            "auditlog",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=255), nullable=False, server_default="default"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("actor", sa.String(length=255), nullable=False),
            sa.Column("action", sa.String(length=255), nullable=False),
            sa.Column("target_user_id", sa.Integer(), nullable=True),
            sa.Column("detail", sa.JSON(), nullable=True),
        )

    if "batchjob" not in existing:
        _create_table(
            "batchjob",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=255), nullable=False, server_default="default"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("created_by", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=64), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("total", sa.Integer(), nullable=False),
            sa.Column("completed", sa.Integer(), nullable=False),
            sa.Column("success", sa.Integer(), nullable=False),
            sa.Column("fail", sa.Integer(), nullable=False),
            sa.Column("concurrency", sa.Integer(), nullable=False),
            sa.Column("user_ids", sa.JSON(), nullable=True),
            sa.Column("last_errors", sa.JSON(), nullable=True),
            sa.Column("cancel_requested", sa.Boolean(), nullable=False),
            sa.Column("paused", sa.Boolean(), nullable=False),
        )

    if "batchjobitem" not in existing:
        _create_table(
            "batchjobitem",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=255), nullable=False, server_default="default"),
            sa.Column("job_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=False),
            sa.Column("max_attempts", sa.Integer(), nullable=False),
            sa.Column("next_run_at", sa.DateTime(), nullable=True),
            sa.Column("locked_by", sa.String(length=255), nullable=True),
            sa.Column("lock_token", sa.String(length=255), nullable=True),
            sa.Column("lease_until", sa.DateTime(), nullable=True),
            sa.Column("heartbeat_at", sa.DateTime(), nullable=True),
        )

    if "adminuser" not in existing:
        _create_table(
            "adminuser",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=255), nullable=False, server_default="default"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("username", sa.String(length=255), nullable=False),
            sa.Column("password_hash", sa.Text(), nullable=False),
            sa.Column("role", sa.String(length=64), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("locked_until", sa.DateTime(), nullable=True),
            sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("mfa_totp_secret", sa.Text(), nullable=True),
            sa.Column("mfa_confirmed_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("tenant_id", "username", name="uq_adminuser_tenant_username"),
        )

    if "appuser" not in existing:
        _create_table(
            "appuser",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=255), nullable=False, server_default="default"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("phone", sa.String(length=255), nullable=False),
            sa.Column("password_hash", sa.Text(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("bound_user_id", sa.Integer(), nullable=True),
            sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("locked_until", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("tenant_id", "phone", name="uq_appuser_tenant_phone"),
        )

    if "systemsetting" not in existing:
        _create_table(
            "systemsetting",
            sa.Column("key", sa.String(length=255), primary_key=True),
            sa.Column("tenant_id", sa.String(length=255), nullable=False, server_default="default"),
            sa.Column("value", sa.JSON(), nullable=True),
        )

    if "ratelimitevent" not in existing:
        _create_table(
            "ratelimitevent",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("bucket_key", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.Float(), nullable=False),
        )

    if "ratelimitbucket" not in existing:
        _create_table(
            "ratelimitbucket",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("bucket_key", sa.String(length=255), nullable=False),
            sa.Column("window_start", sa.Float(), nullable=False),
            sa.Column("count", sa.Integer(), nullable=False),
            sa.Column("updated_at", sa.Float(), nullable=False),
            sa.UniqueConstraint("bucket_key", name="uq_ratelimitbucket_bucket_key"),
        )

    if "taskexecutionlock" not in existing:
        _create_table(
            "taskexecutionlock",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=255), nullable=False, server_default="default"),
            sa.Column("lock_key", sa.String(length=255), nullable=False),
            sa.Column("owner", sa.String(length=255), nullable=False),
            sa.Column("acquired_at", sa.DateTime(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("detail", sa.JSON(), nullable=True),
            sa.UniqueConstraint("lock_key", name="uq_taskexecutionlock_lock_key"),
        )

    if "taskexecutionevent" not in existing:
        _create_table(
            "taskexecutionevent",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=255), nullable=False, server_default="default"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("source", sa.String(length=255), nullable=False),
            sa.Column("event", sa.String(length=255), nullable=False),
            sa.Column("task_key", sa.String(length=255), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=64), nullable=True),
            sa.Column("request_id", sa.String(length=128), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("detail", sa.JSON(), nullable=True),
        )

    if "httprequestmetric" not in existing:
        _create_table(
            "httprequestmetric",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=255), nullable=False, server_default="default"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("method", sa.String(length=16), nullable=False),
            sa.Column("path", sa.String(length=500), nullable=False),
            sa.Column("status_code", sa.Integer(), nullable=False),
            sa.Column("request_id", sa.String(length=128), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=False),
        )

    _ensure_existing_table_columns()
    _drop_unique_if_exists("uq_user_phone", "user")
    _drop_unique_if_exists("uq_adminuser_username", "adminuser")
    _drop_unique_if_exists("uq_appuser_phone", "appuser")
    _create_unique_if_missing("uq_user_tenant_phone", "user", ["tenant_id", "phone"])
    _create_unique_if_missing("uq_adminuser_tenant_username", "adminuser", ["tenant_id", "username"])
    _create_unique_if_missing("uq_appuser_tenant_phone", "appuser", ["tenant_id", "phone"])
    _seed_default_tenant()

    _create_index_if_missing("ix_tenant_name", "tenant", ["name"])
    _create_index_if_missing("ix_tenant_status", "tenant", ["status"])
    _create_index_if_missing("ix_tenant_created_at", "tenant", ["created_at"])
    _create_index_if_missing("ix_user_tenant_id", "user", ["tenant_id"])
    _create_index_if_missing("ix_user_phone", "user", ["phone"])
    _create_index_if_missing("ix_user_remark", "user", ["remark"])
    _create_index_if_missing("ix_user_app_enabled", "user", ["app_enabled"])
    _create_index_if_missing("ix_user_deleted_at", "user", ["deleted_at"])
    _create_index_if_missing("ix_user_deleted_by", "user", ["deleted_by"])
    _create_index_if_missing("ix_auditlog_created_at", "auditlog", ["created_at"])
    _create_index_if_missing("ix_auditlog_tenant_id", "auditlog", ["tenant_id"])
    _create_index_if_missing("ix_auditlog_actor", "auditlog", ["actor"])
    _create_index_if_missing("ix_auditlog_action", "auditlog", ["action"])
    _create_index_if_missing("ix_auditlog_target_user_id", "auditlog", ["target_user_id"])
    _create_index_if_missing("ix_batchjob_tenant_id", "batchjob", ["tenant_id"])
    _create_index_if_missing("ix_batchjob_status_id", "batchjob", ["status", "id"])
    _create_index_if_missing("ix_batchjobitem_tenant_id", "batchjobitem", ["tenant_id"])
    _create_index_if_missing("ix_batchjobitem_job_status_id", "batchjobitem", ["job_id", "status", "id"])
    _create_index_if_missing("ix_batchjobitem_job_status_next_run_id", "batchjobitem", ["job_id", "status", "next_run_at", "id"])
    _create_index_if_missing("ix_batchjobitem_locked_by", "batchjobitem", ["locked_by"])
    _create_index_if_missing("ix_batchjobitem_lock_token", "batchjobitem", ["lock_token"])
    _create_index_if_missing("ix_batchjobitem_lease_until", "batchjobitem", ["lease_until"])
    _create_index_if_missing("ix_batchjobitem_heartbeat_at", "batchjobitem", ["heartbeat_at"])
    _create_index_if_missing("ix_adminuser_tenant_id", "adminuser", ["tenant_id"])
    _create_index_if_missing("ix_adminuser_token_version", "adminuser", ["token_version"])
    _create_index_if_missing("ix_adminuser_failed_login_count", "adminuser", ["failed_login_count"])
    _create_index_if_missing("ix_adminuser_locked_until", "adminuser", ["locked_until"])
    _create_index_if_missing("ix_adminuser_mfa_enabled", "adminuser", ["mfa_enabled"])
    _create_index_if_missing("ix_adminuser_mfa_confirmed_at", "adminuser", ["mfa_confirmed_at"])
    _create_index_if_missing("ix_appuser_tenant_id", "appuser", ["tenant_id"])
    _create_index_if_missing("ix_appuser_token_version", "appuser", ["token_version"])
    _create_index_if_missing("ix_appuser_failed_login_count", "appuser", ["failed_login_count"])
    _create_index_if_missing("ix_appuser_locked_until", "appuser", ["locked_until"])
    _create_index_if_missing("ix_systemsetting_tenant_id", "systemsetting", ["tenant_id"])
    _create_index_if_missing("ix_ratelimitevent_bucket_created", "ratelimitevent", ["bucket_key", "created_at"])
    _create_index_if_missing("ix_ratelimitbucket_bucket_key", "ratelimitbucket", ["bucket_key"])
    _create_index_if_missing("ix_ratelimitbucket_updated", "ratelimitbucket", ["updated_at"])
    _create_index_if_missing("ix_taskexecutionlock_tenant_id", "taskexecutionlock", ["tenant_id"])
    _create_index_if_missing("ix_taskexecutionlock_expires_at", "taskexecutionlock", ["expires_at"])
    _create_index_if_missing("ix_taskexecutionevent_tenant_id", "taskexecutionevent", ["tenant_id"])
    _create_index_if_missing("ix_taskexecutionevent_source_created", "taskexecutionevent", ["source", "created_at"])
    _create_index_if_missing("ix_taskexecutionevent_status_created", "taskexecutionevent", ["status", "created_at"])
    _create_index_if_missing("ix_taskexecutionevent_user_created", "taskexecutionevent", ["user_id", "created_at"])
    _create_index_if_missing("ix_taskexecutionevent_request_created", "taskexecutionevent", ["request_id", "created_at"])
    _create_index_if_missing("ix_httprequestmetric_tenant_id", "httprequestmetric", ["tenant_id"])
    _create_index_if_missing("ix_httprequestmetric_status_created", "httprequestmetric", ["status_code", "created_at"])
    _create_index_if_missing("ix_httprequestmetric_path_created", "httprequestmetric", ["path", "created_at"])
    _create_index_if_missing("ix_httprequestmetric_request_created", "httprequestmetric", ["request_id", "created_at"])


def downgrade() -> None:
    for table_name in [
        "httprequestmetric",
        "taskexecutionevent",
        "taskexecutionlock",
        "ratelimitbucket",
        "ratelimitevent",
        "systemsetting",
        "appuser",
        "adminuser",
        "batchjobitem",
        "batchjob",
        "auditlog",
        "user",
        "tenant",
    ]:
        if table_name in _existing_tables():
            op.drop_table(table_name)
