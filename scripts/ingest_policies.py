import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.rag_service import rag_service  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest policy docs for a hospital.")
    parser.add_argument("--hospital", required=True, help="hospital_id (tenant namespace)")
    parser.add_argument("--dir", required=True, help="directory of policy files (.pdf/.txt)")
    parser.add_argument("--payer", default=None)
    parser.add_argument("--code-system", default=None, dest="code_system")
    parser.add_argument("--force", action="store_true", help="rebuild even if unchanged")
    args = parser.parse_args()

    if not os.path.isdir(args.dir):
        raise SystemExit(f"Not a directory: {args.dir}")

    items = []
    for name in sorted(os.listdir(args.dir)):
        path = os.path.join(args.dir, name)
        if os.path.isfile(path):
            items.append(
                {
                    "path": path,
                    "source_doc": name,
                    "payer": args.payer,
                    "code_system": args.code_system,
                }
            )
    if not items:
        raise SystemExit(f"No files found in {args.dir}")

    result = rag_service.ingest_paths(args.hospital, items, force=args.force)
    print(f"Ingested {len(items)} file(s) for hospital {args.hospital}: {result}")


if __name__ == "__main__":
    main()
