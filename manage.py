# manage.py

import os
import click
from flask.cli import with_appcontext

# důležité: nejprve import tvé Flask aplikace
from app import app, db
from app.models import User

@click.command("create-admin")
@click.argument("username")
@click.argument("password")
@click.option("--role",  default="admin",    help="Role nového uživatele")
@click.option("--sklad", default="Pardubice", help="Výchozí sklad")
@with_appcontext
def create_admin(username, password, role, sklad):
    """
    Vytvoří nového uživatele s rolí admin.
    Použití: flask create-admin USERNAME PASSWORD [--role] [--sklad]
    """
    if User.query.filter_by(username=username).first():
        click.secho(f"⚠️  Uživatel '{username}' už existuje, přeskočeno.", fg="yellow")
        return

    u = User(
        username=username,
        role=role,
        sklad=sklad
    )
    # metoda set_password uloží hash do sloupce password
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    click.secho(f"✅ Admin '{username}' vytvořen s rolí '{role}' a skladem '{sklad}'.", fg="green")

# registrujeme náš příkaz pod Flask CLI
app.cli.add_command(create_admin)


if __name__ == "__main__":
    # pokud bys chtěl spustit tuto appku
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
