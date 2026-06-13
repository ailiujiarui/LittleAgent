import sqlite3
from pathlib import Path


MIGRATIONS_DIR = Path(__file__).with_name("migrations")


def apply_migrations(db_path: Path) -> None:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            create table if not exists schema_migrations (
                version text primary key,
                applied_at text not null default current_timestamp
            )
            """
        )

        applied = {
            row[0]
            for row in conn.execute("select version from schema_migrations").fetchall()
        }

        for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = migration.stem
            if version in applied:
                continue
            conn.executescript(migration.read_text(encoding="utf-8"))
            conn.execute(
                "insert into schema_migrations (version) values (?)",
                (version,),
            )
        conn.commit()
