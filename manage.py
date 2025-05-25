import click
from flask.cli import with_appcontext
from app import app, db
from app.models import User

app.cli.add_command(create_admin)

@click.command("create-admin")
@click.argument("username")
@click.argument("password")
@click.option("--role",    default="admin",    help="Role nového uživatele")
@click.option("--sklad",   default="Pardubice", help="Výchozí sklad")
@with_appcontext
def create_admin(username, password, role, sklad):
    """
    CLI příkaz: flask create-admin USERNAME PASSWORD [--role] [--sklad]
    """
    if User.query.filter_by(username=username).first():
        click.echo(f"⚠️ Uživatel '{username}' už existuje, nic se nevytváří.")
        return

    u = User(
        username=username,
        role=role,
        sklad=sklad
    )
    # metoda u.set_password() musí existovat ve vašem User modelu a zapsat hash do u.password
    u.set_password(password)
    db.session.add(u)
    db.session.commit()

    click.echo(f"✅ Admin '{username}' vytvořen s rolí '{role}' a skladem '{sklad}'.")
