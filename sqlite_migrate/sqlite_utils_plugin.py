import click
import difflib
import pathlib
import sqlite_utils
from sqlite_migrate import Migrations
import textwrap


@sqlite_utils.hookimpl
def register_commands(cli):
    @cli.command()
    @click.argument(
        "db_path", type=click.Path(dir_okay=False, readable=True, writable=True)
    )
    @click.argument("migrations", type=click.Path(dir_okay=True, exists=True), nargs=-1)
    @click.option(
        "list_", "--list", is_flag=True, help="List migrations without running them"
    )
    @click.option("-v", "--verbose", is_flag=True, help="Show verbose output")
    def migrate(db_path, migrations, list_, verbose):
        """
        Apply pending database migrations.

        Usage:

            sqlite-utils migrate database.db

        This will find the migrations.py file in the current directory
        or subdirectories and apply any pending migrations.

        Or pass paths to one or more migrations.py files directly:

            sqlite-utils migrate database.db path/to/migrations.py

        Pass --list to see a list of applied and pending migrations
        without applying them.
        """
        if not migrations:
            # Scan current directory for migrations.py files
            migrations = [pathlib.Path(".").resolve()]
        files = set()
        for path_str in migrations:
            path = pathlib.Path(path_str)
            if path.is_dir():
                files.update(path.rglob("migrations.py"))
            else:
                files.add(path)
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
            raise click.ClickException("No migrations.py files found")
        db = sqlite_utils.Database(db_path)

        if list_:
            display_list(db, migration_sets)
            return

        prev_schema = db.schema
        if verbose:
            click.echo("Migrating {}".format(db_path))
            click.echo("\nSchema before:\n")
            click.echo(textwrap.indent(prev_schema, "  ") or "  (empty)")
            click.echo()
        for migration_set in migration_sets:
            migration_set.apply(db)
        if verbose:
            click.echo("Schema after:\n")
            post_schema = db.schema
            if post_schema == prev_schema:
                click.echo("  (unchanged)")
            else:
                click.echo(textwrap.indent(post_schema, "  "))
                click.echo("\nSchema diff:\n")
                # Calculate and display a diff
                diff = list(
                    difflib.unified_diff(
                        prev_schema.splitlines(), post_schema.splitlines()
                    )
                )
                # Skipping the first two lines since they only make
                # sense if we provided filenames, and the next one
                # because it is just @@ -0,0 +1,15 @@
                click.echo("\n".join(diff[3:]))


def display_list(db, migration_sets):
    applied = set()
    for migration_set in migration_sets:
        print("Migrations for: {}".format(migration_set.name))
        print()
        print("  Applied:")
        for migration in migration_set.applied(db):
            print("    {} - {}".format(migration.name, migration.applied_at))
            applied.add(migration.name)
        print()
        print("  Pending:")
        output = False
        for migration in migration_set.pending(db):
            output = True
            if migration.name not in applied:
                print("    {}".format(migration.name))
        if not output:
            print("    (none)")
        print()
