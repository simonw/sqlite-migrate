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
    @click.option("--stop-before", help="Stop before applying this migration")
    @click.option(
        "list_", "--list", is_flag=True, help="List migrations without running them"
    )
    @click.option("-v", "--verbose", is_flag=True, help="Show verbose output")
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Show what migrations would be applied without applying them",
    )
    def migrate(db_path, migrations, stop_before, list_, verbose, dry_run):
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

        if stop_before and len(migration_sets) > 1:
            raise click.ClickException(
                "--stop-before can only be used with a single migrations.py file"
            )

        db = sqlite_utils.Database(db_path)

        if list_:
            display_list(db, migration_sets)
            return

        if dry_run:
            display_dry_run(db, migration_sets, stop_before=stop_before)
            return

        prev_schema = db.schema
        if verbose:
            click.echo("Migrating {}".format(db_path))
            click.echo("\nSchema before:\n")
            click.echo(textwrap.indent(prev_schema, "  ") or "  (empty)")
            click.echo()
        for migration_set in migration_sets:
            migration_set.apply(db, stop_before=stop_before)
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


def display_dry_run(db, migration_sets, stop_before=None):
    """Display what migrations would be applied without actually applying them."""
    all_applied = []
    combined_before = None
    combined_after = None

    for migration_set in migration_sets:
        result = migration_set.apply(db, stop_before=stop_before, dry_run=True)
        all_applied.extend(result.applied)
        # Use the first before_schema and last after_schema
        if combined_before is None:
            combined_before = result.before_schema
        combined_after = result.after_schema

    click.echo("Dry run - no changes applied\n")

    if not all_applied:
        click.echo("No pending migrations")
        return

    click.echo(
        "Would apply {} migration{}:".format(
            len(all_applied), "s" if len(all_applied) != 1 else ""
        )
    )
    for name in all_applied:
        click.echo("  - {}".format(name))
    click.echo()

    click.echo("Schema before:\n")
    click.echo(textwrap.indent(combined_before, "  ") or "  (empty)")
    click.echo()

    click.echo("Schema after:\n")
    if combined_after == combined_before:
        click.echo("  (unchanged)")
    else:
        click.echo(textwrap.indent(combined_after, "  "))
        click.echo("\nSchema diff:\n")
        diff = list(
            difflib.unified_diff(
                combined_before.splitlines(), combined_after.splitlines()
            )
        )
        # Skip the first three lines (filenames and @@ markers)
        click.echo("\n".join(diff[3:]))
