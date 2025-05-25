import os
from datetime import datetime
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_migrate import Migrate     # ← přidáno
from config import Config

# cesta k šablonám
template_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "templates")
)

# aplikace
app = Flask(__name__, template_folder=template_path)
# ... po app = Flask(...)
app.config.from_object(Config)

# vypneme třídění klíčů ve vestavěném JSON provideru
app.json.sort_keys = False

# databáze + migrace
db = SQLAlchemy(app)
migrate = Migrate(app, db)            # ← inicializace migrací

# přihlašování
login = LoginManager(app)
login.login_view = "login"

# -------------------------------------------------------------
#  GLOBAL CONTEXT – kolik přeskladnění je na cestě ke mně?
# -------------------------------------------------------------
from app.models import Transfer  # (import až po vytvoření db)

@app.context_processor
def inject_transfers_badge():
    if not current_user.is_authenticated:
        return dict(transfers_na_ceste=0)

    if current_user.role == "admin":
        cnt = Transfer.query.filter_by(status="v_tranzitu").count()
    else:
        cnt = Transfer.query.filter_by(
            status="v_tranzitu",
            target_sklad=current_user.sklad
        ).count()

    return dict(transfers_na_ceste=cnt)

# -------------------------------------------------------------
#  importy rout a modelů
# -------------------------------------------------------------
from app import routes, models
