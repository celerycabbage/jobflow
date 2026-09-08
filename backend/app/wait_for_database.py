import time

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from .config import get_settings
from .database import engine


def main() -> None:
    deadline = time.monotonic() + get_settings().database_wait_seconds
    while True:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            print("Database connection is ready", flush=True)
            return
        except OperationalError as exc:
            if time.monotonic() >= deadline:
                raise SystemExit(f"Database did not become ready: {exc}") from exc
            print("Waiting for database connection...", flush=True)
            time.sleep(2)


if __name__ == "__main__":
    main()
