"""baseline: config_versions, file_index, publish_log

Matches state/models.py's Base.metadata as of this revision — the schema
Base.metadata.create_all() would already produce for a brand-new database.

Revision ID: 0001
Revises:
Create Date: 2026-07-26

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "config_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dataset_id", sa.String(), nullable=False),
        sa.Column("hash", sa.String(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        op.f("ix_config_versions_dataset_id"), "config_versions", ["dataset_id"], unique=False
    )

    op.create_table(
        "file_index",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dataset_id", sa.String(), nullable=False),
        sa.Column("file_name", sa.String(), nullable=False),
        sa.Column("file_role", sa.String(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("time_start", sa.DateTime(), nullable=True),
        sa.Column("time_end", sa.DateTime(), nullable=True),
        sa.Column("variables", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "last_checked_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("dataset_id", "file_name", name="uq_file_index_dataset_file"),
    )
    op.create_index(op.f("ix_file_index_dataset_id"), "file_index", ["dataset_id"], unique=False)

    op.create_table(
        "publish_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dataset_id", sa.String(), nullable=False),
        sa.Column("period", sa.String(), nullable=False),
        sa.Column("config_hash", sa.String(), nullable=False),
        sa.Column("software_version", sa.String(), nullable=False),
        sa.Column("generated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("cached_file_path", sa.String(), nullable=False),
    )
    op.create_index(op.f("ix_publish_log_dataset_id"), "publish_log", ["dataset_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_publish_log_dataset_id"), table_name="publish_log")
    op.drop_table("publish_log")
    op.drop_index(op.f("ix_file_index_dataset_id"), table_name="file_index")
    op.drop_table("file_index")
    op.drop_index(op.f("ix_config_versions_dataset_id"), table_name="config_versions")
    op.drop_table("config_versions")
