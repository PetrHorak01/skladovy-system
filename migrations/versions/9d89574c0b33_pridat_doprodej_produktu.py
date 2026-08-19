"""Pridat doprodej produktu

Revision ID: 9d89574c0b33
Revises: 9141bdbca17c
Create Date: 2026-08-19
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9d89574c0b33"
down_revision = "9141bdbca17c"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("product", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "doprodej",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False
            )
        )


def downgrade():
    with op.batch_alter_table("product", schema=None) as batch_op:
        batch_op.drop_column("doprodej")