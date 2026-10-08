from __future__ import annotations

import argparse

from app.db.session import SessionLocal, init_db
from app.services.pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(prog="lead-engine")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db")
    demo = sub.add_parser("demo")
    demo.add_argument("--no-reset", action="store_true")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        if args.cmd == "init-db":
            print("Database initialized.")
        elif args.cmd == "demo":
            run = run_pipeline(db, reset=not args.no_reset)
            print("Pipeline completed:", run.status)
            print("Funnel:", run.funnel_json)
    finally:
        db.close()


if __name__ == "__main__":
    main()
