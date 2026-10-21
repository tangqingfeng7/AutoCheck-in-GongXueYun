import argparse

from server.backup import export_database_json, import_database_json
from server.database import engine


def main() -> None:
    parser = argparse.ArgumentParser(description="Export or import AutoMoGuDing database JSON backups.")
    sub = parser.add_subparsers(dest="command", required=True)

    export_parser = sub.add_parser("export", help="Export database to a JSON backup file.")
    export_parser.add_argument("path")
    export_parser.add_argument("--encryption-key", default=None)

    import_parser = sub.add_parser("import", help="Import database from a JSON backup file.")
    import_parser.add_argument("path")
    import_parser.add_argument("--replace-existing", action="store_true")
    import_parser.add_argument("--encryption-key", default=None)

    args = parser.parse_args()
    if args.command == "export":
        summary = export_database_json(engine, args.path, encryption_key=args.encryption_key)
    else:
        summary = import_database_json(
            engine,
            args.path,
            replace_existing=bool(args.replace_existing),
            encryption_key=args.encryption_key,
        )
    print(summary)


if __name__ == "__main__":
    main()
