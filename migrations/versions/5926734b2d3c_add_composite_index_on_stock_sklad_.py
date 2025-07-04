from alembic import op

def upgrade():
    op.create_index(
        "ix_stock_sklad_product_id_size",
        "stock",
        ["sklad", "product_id", "size"],
        unique=False
    )

def downgrade():
    op.drop_index(
        "ix_stock_sklad_product_id_size",
        table_name="stock"
    )
