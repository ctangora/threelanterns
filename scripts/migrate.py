from pathlib import Path

from sqlalchemy import text

from app.database import engine


def apply_sql_migration(path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    version = path.stem
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"))
        exists = connection.execute(text("SELECT version FROM schema_migrations WHERE version = :version"), {"version": version}).first()
        if exists:
            return
        connection.execute(text(sql))
        connection.execute(text("INSERT INTO schema_migrations(version) VALUES (:version)"), {"version": version})


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    migrations_dir = root / "migrations"
    for path in sorted(migrations_dir.glob("*.sql")):
        apply_sql_migration(path)
        print(f"applied {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

