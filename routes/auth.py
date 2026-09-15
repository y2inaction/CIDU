from flask import Blueprint, request, redirect, url_for, render_template, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from urllib.parse import quote
from models import db, User
import logging

logger = logging.getLogger(__name__)
auth = Blueprint("auth", __name__)

@auth.route("/login", methods=["GET","POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("api.dashboard"))
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            logger.info(f"Login: {username}")
            return redirect(request.args.get("next") or url_for("api.dashboard"))
        logger.warning(f"Failed login: {username}")
        return redirect(url_for("auth.login") + "?msg=" + quote("Invalid username or password"))
    return render_template("login.html")

@auth.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))

@auth.route("/api/me")
@login_required
def me():
    return jsonify({"username":current_user.username,"role":current_user.role,"state":current_user.state})

def register_cli(app):
    @app.cli.command("create-admin")
    def create_admin():
        import click
        username = click.prompt("Username", default="admin")
        email    = click.prompt("Email",    default="admin@vcdp.gov.ng")
        password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
        if User.query.filter_by(username=username).first():
            click.echo(f"User '{username}' already exists."); return
        u = User(username=username, email=email, role="admin")
        u.set_password(password); db.session.add(u); db.session.commit()
        click.echo(f"Admin '{username}' created.")

    @app.cli.command("create-spmu")
    def create_spmu():
        import click
        from config import Config
        username = click.prompt("Username")
        email    = click.prompt("Email")
        state    = click.prompt("State", type=click.Choice(Config.VALID_STATES))
        password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
        if User.query.filter_by(username=username).first():
            click.echo(f"User '{username}' already exists."); return
        u = User(username=username, email=email, role="spmu", state=state)
        u.set_password(password); db.session.add(u); db.session.commit()
        click.echo(f"SPMU user '{username}' for {state} created.")

    @app.cli.command("trigger-broadcast")
    def trigger_broadcast():
        """Send scheduled weather SMS broadcast (run via cron on Mon/Thu at 7AM WAT)."""
        import click
        from services.scheduler import run_scheduled_broadcast
        click.echo(f"[VCDP CIDU] Running scheduled broadcast at {__import__('datetime').datetime.now()}...")
        try:
            result = run_scheduled_broadcast(app)
            click.echo(f"[VCDP CIDU] Broadcast complete: {result}")
        except Exception as e:
            click.echo(f"[VCDP CIDU] Broadcast error: {e}", err=True)
            raise SystemExit(1)

    @app.cli.command("change-password")
    def change_password():
        """Change a user's password from the command line."""
        import click
        username = click.prompt("Username")
        user = User.query.filter_by(username=username).first()
        if not user:
            click.echo(f"User '{username}' not found."); return
        password = click.prompt("New password", hide_input=True, confirmation_prompt=True)
        user.set_password(password); db.session.commit()
        click.echo(f"Password updated for '{username}'.")

    @app.cli.command("list-users")
    def list_users():
        """List all users in the system."""
        import click
        users = User.query.order_by(User.role, User.username).all()
        click.echo(f"\n{'USERNAME':<20} {'ROLE':<10} {'STATE':<20} {'EMAIL'}")
        click.echo("-"*70)
        for u in users:
            click.echo(f"{u.username:<20} {u.role:<10} {(u.state or 'All'):<20} {u.email or ''}")
        click.echo(f"\nTotal: {len(users)} users")
