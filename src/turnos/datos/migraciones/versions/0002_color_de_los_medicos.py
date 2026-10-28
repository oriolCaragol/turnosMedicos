"""Color de los médicos (para distinguirlos en el calendario)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('medico', schema=None) as batch_op:
        batch_op.add_column(sa.Column('color', sa.String(length=7), nullable=True))



def downgrade() -> None:
    with op.batch_alter_table('medico', schema=None) as batch_op:
        batch_op.drop_column('color')

