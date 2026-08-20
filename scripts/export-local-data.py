import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "hermes-plugin"))

from aishop.runtime import get_maintenance_service


def main() -> None:
    parser = argparse.ArgumentParser(description="Export redacted AIShop local metadata")
    parser.add_argument("--output", required=True)
    parser.add_argument("--data-dir")
    arguments = parser.parse_args()
    if arguments.data_dir:
        os.environ["AISHOP_DATA_DIR"] = arguments.data_dir
        get_maintenance_service.cache_clear()
    output = Path(arguments.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(get_maintenance_service().export_redacted(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
