"""Deduplicate Stock entries and add unique constraint

Revision ID: 9d71045ad2f0
Revises: 6d654f1d2be7
Create Date: 2025-06-15 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '9d71045ad2f0'
down_revision = '6d654f1d2be7'
branch_labels = None
depends_on = None

def upgrade():
    conn = op.get_bind()

    duplicates = conn.execute(sa.text(
        """SELECT product_id, sklad, size, COUNT(*) as cnt
           FROM stock
           GROUP BY product_id, sklad, size
           HAVING cnt > 1"""
    )).mappings().all()

    for row in duplicates:
        if row['size'] is None:
            rows = conn.execute(sa.text(
                "SELECT id, quantity, note FROM stock WHERE product_id=:pid AND sklad=:sklad AND size IS NULL"),
                dict(pid=row['product_id'], sklad=row['sklad'])).mappings().all()
        else:
            rows = conn.execute(sa.text(
                "SELECT id, quantity, note FROM stock WHERE product_id=:pid AND sklad=:sklad AND size=:size"),
                dict(pid=row['product_id'], sklad=row['sklad'], size=row['size'])).mappings().all()

        keep_id = rows[0]['id']
        total_qty = sum(r['quantity'] or 0 for r in rows)
        notes = "\n".join([r['note'] for r in rows if r['note']]) or None

        conn.execute(sa.text("UPDATE stock SET quantity=:qty, note=:note WHERE id=:id"),
                     dict(qty=total_qty, note=notes, id=keep_id))

        ids_to_delete = [r['id'] for r in rows[1:]]
        if ids_to_delete:
            conn.execute(sa.text(f"DELETE FROM stock WHERE id IN ({','.join(map(str, ids_to_delete))})"))

    with op.batch_alter_table('stock') as batch_op:
        batch_op.create_unique_constraint('uq_stock_product_sklad_size',
                                          ['product_id', 'sklad', 'size'])

def downgrade():
    with op.batch_alter_table('stock') as batch_op:
        batch_op.drop_constraint('uq_stock_product_sklad_size', type_='unique')
