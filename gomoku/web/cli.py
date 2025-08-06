"""CLI commands for the web interface."""

import click
import os
from .app import create_app


@click.group()
def web():
    """Web interface commands."""
    pass


@web.command()
@click.option('--host', default='127.0.0.1', help='Host to bind to')
@click.option('--port', default=5000, help='Port to bind to')
@click.option('--debug', is_flag=True, help='Run in debug mode')
def run(host, port, debug):
    """Run the web development server."""
    app = create_app()
    app.run(host=host, port=port, debug=debug)


@web.command()
def init_db():
    """Initialize the database."""
    app = create_app()
    with app.app_context():
        from .models import db
        db.create_all()
        click.echo("Database initialized successfully!")


if __name__ == '__main__':
    web()