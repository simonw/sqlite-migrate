import click
import pathlib
import sqlite_utils
from sqlite_migrate import Migrations


@sqlite_utils.hookimpl
def register_commands(cli):
    @cli.command()
    @click.argument("path", type=click.Path(dir_okay=False))
    @click.option(
        "list_", "--list", is_flag=True, help="List migrations without running them"
    )
    def migrate(path, list_):
        """
        Apply pending database migrations.

        Usage:

            sqlite-utils migrate path/to/database.db

        This will find the migrations.py file in the current directory
        or subdirectories and apply any pending migrations.

        Pass --list to see which migrations would be applied without
        actually applying them.

        Pass -m path/to/migrations.py to use a specific migrations file:

            sqlite-utils migrate database.db -m path/to/migrations.py
        """
        # Find the migrations.py file
        files = pathlib.Path(".").rglob("migrations.py")
        migration_sets = []
        for filepath in files:
            code = filepath.read_text()
            namespace = {}
            exec(code, namespace)
            # Find all instances of Migrations
            for obj in namespace.values():
                if isinstance(obj, Migrations):
                    migration_sets.append(obj)
        if not migration_sets:
            raise click.ClickException(
                "No migrations.py file found in current or subdirectories"
            )
        db = sqlite_utils.Database(path)
        for migration_set in migration_sets:
            if list_:
                click.echo(
                    "Pending migrations for {}:\n{}".format(
                        path,
                        "\n".join(
                            "- {}".format(m.name) for m in migration_set.pending(db)
                        ),
                    )
                )
            else:
                migration_set.apply(db)
