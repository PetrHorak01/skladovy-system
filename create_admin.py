from app import app, db
from app.models import User

with app.app_context():
    admin = User(username="admin", password="admin", role="admin", sklad=None)
    db.session.add(admin)
    db.session.commit()
    print("✅ Admin účet byl vytvořen (admin/admin)")
