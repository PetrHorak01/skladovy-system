#!/usr/bin/env python
import os
import click
from flask.cli import FlaskGroup, with_appcontext
from app import app, db
from app.models import User
from flask_migrate import Migrate

# --- 1) Inicializace Flask-Migrate ---
migrate = Migrate(app, db)

# --- 2) Vlastní CLI příkaz ---
@click.command("create-admin")
@click.argument("username")
@click.argument("password")
@click.option("--role",  default="admin",    help="Role nového uživatele")
@click.option("--sklad", default="Pardubice", help="Výchozí sklad")
@with_appcontext
def create_admin(username, password, role, sklad):
    """
    Vytvoří nového uživatele s rolí admin.
    Použití: python manage.py create-admin USERNAME PASSWORD [--role] [--sklad]
    """
    if User.query.filter_by(username=username).first():
        click.secho(f"⚠️ Uživatel '{username}' už existuje, přeskočeno.", fg="yellow")
        return

    u = User(username=username, role=role, sklad=sklad)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    click.secho(f"✅ Admin '{username}' vytvořen s rolí '{role}' a skladem '{sklad}'.", fg="green")

# --- 3) Sestavení CLI skupiny ---
def main():
    # zaregistrujeme náš příkaz
    app.cli.add_command(create_admin)
    # vytvoříme FlaskGroup, který zpřístupní všechny 'flask db' & 'flask run' příkazy
    cli = FlaskGroup(create_app=lambda info: app)
    cli()

if __name__ == "__main__":
    main()
