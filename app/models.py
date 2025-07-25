from app import db
from flask_login import UserMixin
from app import login
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import backref

class User(UserMixin, db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    role     = db.Column(db.String(10), nullable=False)
    sklad    = db.Column(db.String(20), nullable=True)

    def set_password(self, raw_password):
        self.password = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password, raw_password)


@login.user_loader
def load_user(id):
    return User.query.get(int(id))


class Product(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(64), nullable=False)
    category      = db.Column(db.String(20), nullable=False, default="saty")
    color         = db.Column(db.String(32), nullable=True)
    back_solution = db.Column(db.String(64), nullable=True)

    # vztah na Stock, potlačí SAWarning ohledně "stocks" a "product"
    stock = db.relationship(
        'Stock',
        backref=backref('product_vztah', overlaps='stocks,product'),
        lazy=True,
        overlaps='stocks,product'
    )

    @property
    def variant_label(self):
        parts = [self.name]
        if self.color:
            parts.append(self.color)
        if self.back_solution:
            parts.append(self.back_solution)
        return "-".join(parts)


class Stock(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    sklad      = db.Column(db.String(50), nullable=False)
    size       = db.Column(db.Integer, nullable=True)
    quantity   = db.Column(db.Integer, default=0)
    note       = db.Column(db.Text, nullable=True)

    # TOTO JE KLÍČOVÝ ŘÁDEK, KTERÝ PŘIDÁVÁ POJISTKU PROTI DUPLICITÁM
    __table_args__ = (db.UniqueConstraint('product_id', 'sklad', 'size', name='_product_sklad_size_uc'),)

    # vztah na Product, potlačí SAWarning ohledně "product_vztah"
    product = db.relationship(
        "Product",
        backref=backref('stocks', overlaps='stock,product_vztah'),
        overlaps='stock,product_vztah'
    )


class History(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    user        = db.Column(db.String(50))
    sklad       = db.Column(db.String(50))
    product_id  = db.Column(db.Integer)
    size        = db.Column(db.Integer)
    change_type = db.Column(db.String(50))
    amount      = db.Column(db.Integer)
    timestamp   = db.Column(db.DateTime, default=datetime.utcnow)
    note        = db.Column(db.Text)


class Sales(db.Model):
    id     = db.Column(db.Integer, primary_key=True)
    user   = db.Column(db.String(64), nullable=False)
    year   = db.Column(db.Integer, nullable=False)
    month  = db.Column(db.Integer, nullable=False)
    tries  = db.Column(db.Integer, default=0)
    sales  = db.Column(db.Integer, default=0)


class Overtime(db.Model):
    id      = db.Column(db.Integer, primary_key=True)
    user    = db.Column(db.String(50), nullable=False)
    year    = db.Column(db.Integer, nullable=False)
    month   = db.Column(db.Integer, nullable=False)
    classic = db.Column(db.Integer, default=0)
    deluxe  = db.Column(db.Integer, default=0)


class Transfer(db.Model):
    __tablename__ = "transfer"

    id            = db.Column(db.Integer, primary_key=True)
    source_sklad  = db.Column(db.String(50), nullable=False)
    target_sklad  = db.Column(db.String(50), nullable=False)
    created_by    = db.Column(db.String(50), nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.now)
    confirmed_by  = db.Column(db.String(50), nullable=True)
    confirmed_at  = db.Column(db.DateTime, nullable=True)
    status        = db.Column(db.String(20), default="v_tranzitu")

    items = db.relationship(
        "TransferItem",
        backref="transfer",
        cascade="all, delete-orphan",
        lazy=True
    )


class TransferItem(db.Model):
    __tablename__ = "transfer_item"

    id          = db.Column(db.Integer, primary_key=True)
    transfer_id = db.Column(
        db.Integer,
        db.ForeignKey("transfer.id", ondelete="CASCADE"),
        nullable=False
    )
    product_id  = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    size        = db.Column(db.Integer, nullable=True)
    quantity    = db.Column(db.Integer, nullable=False)
