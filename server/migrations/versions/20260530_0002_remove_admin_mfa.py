"""Remove admin MFA columns.

Revision ID: 20260530_0002
Revises: 20260527_0001
Create Date: 2026-05-30
"""

from alembic import op
import sqlalchemy as sa

revision = "20260530_0002"
down_revision = "20260527_0001"
branch_labels = None
depends_on = None

MFA_COLUMNS = ("mfa_enabled", "mfa_totp_secret", "mfa_confirmed_at")
MFA_INDEXES = ("ix_adminuser_mfa_enabled", "ix_adminuser_mfa_confirmed_at")


def _table_exists(table_name: str) -> bool:
    return table_name in set(sa.inspect(op.get_bind()).get_table_names())


def _existing_columns(table_name: str) -> set[str]:
    if not _table_exists(table_name):
        return set()
    return {str(item.get("name") or "") for item in sa.inspect(op.get_bind()).get_columns(table_name)}


def _existing_indexes(table_name: str) -> set[str]:
    if not _table_exists(table_name):
        return set()
    return {str(item.get("name") or "") for item in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _drop_index_if_exists(index_name: str) -> None:
    if index_name in _existing_indexes("adminuser"):
        op.drop_index(index_name, table_name="adminuser")


def upgrade() -> None:
    if not _table_exists("adminuser"):
        return

    for index_name in MFA_INDEXES:
        _drop_index_if_exists(index_name)

    columns = _existing_columns("adminuser")
    columns_to_drop = [column for column in MFA_COLUMNS if column in columns]
    if not columns_to_drop:
        return

    with op.batch_alter_table("adminuser") as batch_op:
        for column in columns_to_drop:
            batch_op.drop_column(column)


def downgrade() -> None:
    if not _table_exists("adminuser"):
        return

    columns = _existing_columns("adminuser")
    with op.batch_alter_table("adminuser") as batch_op:
        if "mfa_enabled" not in columns:
            batch_op.add_column(sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
        if "mfa_totp_secret" not in columns:
            batch_op.add_column(sa.Column("mfa_totp_secret", sa.Text(), nullable=True))
        if "mfa_confirmed_at" not in columns:
            batch_op.add_column(sa.Column("mfa_confirmed_at", sa.DateTime(), nullable=True))

    indexes = _existing_indexes("adminuser")
    if "ix_adminuser_mfa_enabled" not in indexes:
        op.create_index("ix_adminuser_mfa_enabled", "adminuser", ["mfa_enabled"])
    if "ix_adminuser_mfa_confirmed_at" not in indexes:
        op.create_index("ix_adminuser_mfa_confirmed_at", "adminuser", ["mfa_confirmed_at"])
