# sqlite-migrate

[![PyPI](https://img.shields.io/pypi/v/sqlite-migrate.svg)](https://pypi.org/project/sqlite-migrate/)
[![Changelog](https://img.shields.io/github/v/release/simonw/sqlite-migrate?include_prereleases&label=changelog)](https://sqlite-migrate.datasette.io/en/stable/changelog.html)
[![Tests](https://github.com/simonw/sqlite-migrate/workflows/Test/badge.svg)](https://github.com/simonw/sqlite-migrate/actions?query=workflow%3ATest)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/simonw/sqlite-migrate/blob/main/LICENSE)

A simple database migration system for SQLite, based on sqlite-utils

**This project is an early alpha. Expect breaking changes.**

## Installation

This tool works as a plugin for [sqlite-utils](https://sqlite-utils.datasette.io/). First install that:

```bash
pip install sqlite-utils
```
Then install this plugin like so:
```bash
sqlite-utils install sqlite-migrate
```
## Usage

This tool works against migration files. A migration file looks like this:

```python
from sqlite_migrate import Migrations

# Pick a unique name here - it must not clash with other migration sets that
# the user might run against the same database.

migration = Migrations("myapp")

# Use this decorator against functions that implement migrations
@migration()
def m001_create_table(db):
    # db is a sqlite-utils Database instance
    db["creatures"].create(
        {"id": int, "name": str, "species": str},
        pk="id"
    )

@migration()
def m002_add_weight(db):
    # db is a sqlite-utils Database instance
    db["creatures"].add_column("weight", float)
```
Running this command will execute those migrations in sequence against the specified database file:
```bash
sqlite-utils migrate creatures.db
```
Running it multiple times will have no additional affect, unless you add more migration functions to the file.

Here is [documentation on the Database instance](https://sqlite-utils.datasette.io/en/stable/python-api.html) passed to each migration function.
