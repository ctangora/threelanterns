import argparse
import time

from app.config import get_settings
from app.database import SessionLocal
from app.services.workflows.ingestion import run_worker_cycle


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Three Lanterns ingestion worker")
    parser.add_argument("--once", action="store_true", help="Run a single worker cycle and exit")
    return parser.parse_args()


def main() -> int:
    settings = get_settings()
    args = parse_args()

    while True:
        with SessionLocal() as db:
            job = run_worker_cycle(db, actor=settings.operator_id)
            db.commit()
            if args.once:
                return 0 if job else 1
        if args.once:
            return 1
        time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())

