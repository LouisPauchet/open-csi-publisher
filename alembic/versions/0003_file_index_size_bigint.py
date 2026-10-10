"""file_index: widen size to BigInteger

ThingsBoard's change token (the latest telemetry timestamp in epoch
milliseconds, ~1.8e12) is stored in file_index.size; the baseline migration
created it as a 32-bit INTEGER even though the model declares BigInteger.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("file_index") as batch:
        batch.alter_column("size", existing_type=sa.Integer(), type_=sa.BigInteger(), existing_nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("file_index") as batch:
        batch.alter_column("size", existing_type=sa.BigInteger(), type_=sa.Integer(), existing_nullable=False)
