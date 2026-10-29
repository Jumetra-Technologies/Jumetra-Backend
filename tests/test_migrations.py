"""Migrations: a fresh database, and one created by the old create_all path."""

from __future__ import annotations

import sqlite3

from sqlalchemy import inspect, text

from api.db.init_db import init_db


def _tables(factory) -> set[str]:
    return set(inspect(factory.kw["bind"]).get_table_names())


def _version(factory) -> str:
    with factory.kw["bind"].connect() as conn:
        return conn.execute(text("select version_num from alembic_version")).scalar_one()


def test_fresh_database_gets_every_migration(tmp_path):
    factory = init_db(tmp_path)
    tables = _tables(factory)
    assert {"users", "refresh_tokens", "devices", "desktop_auth_codes", "user_projects", "lab_sessions"} <= tables
    assert _version(factory) == "0002_desktop_sign_in"
    columns = {c["name"] for c in inspect(factory.kw["bind"]).get_columns("refresh_tokens")}
    assert {"client", "device_id"} <= columns


def test_database_from_before_migrations_is_adopted(tmp_path):
    # The shape the Render disk has: create_all from the September models, no alembic_version,
    # and a users table that predates firebase_uid / photo_url / last_login_at.
    db = tmp_path / "platform.db"
    con = sqlite3.connect(db)
    con.executescript(
        """
        CREATE TABLE organizations (id VARCHAR(32) PRIMARY KEY, name VARCHAR(255) NOT NULL, slug VARCHAR(64) NOT NULL UNIQUE, created_at DATETIME);
        CREATE TABLE users (id VARCHAR(32) PRIMARY KEY, email VARCHAR(255) NOT NULL UNIQUE, display_name VARCHAR(255) NOT NULL,
                            role VARCHAR(32), organization_id VARCHAR(32) NOT NULL REFERENCES organizations(id), created_at DATETIME);
        INSERT INTO organizations VALUES ('org1', 'Old Lab', 'old-lab', '2026-09-01 00:00:00');
        INSERT INTO users VALUES ('u1', 'old@example.test', 'Old Person', 'RESEARCHER', 'org1', '2026-09-01 00:00:00');
        """
    )
    con.commit()
    con.close()

    factory = init_db(tmp_path)
    assert _version(factory) == "0002_desktop_sign_in"
    assert {"devices", "desktop_auth_codes", "user_profiles", "refresh_tokens"} <= _tables(factory)
    columns = {c["name"] for c in inspect(factory.kw["bind"]).get_columns("users")}
    assert {"firebase_uid", "photo_url", "last_login_at"} <= columns
    with factory() as session:
        assert session.execute(text("select display_name from users where id='u1'")).scalar_one() == "Old Person"

    # Starting again on the same file is a no-op.
    again = init_db(tmp_path)
    assert _version(again) == "0002_desktop_sign_in"
