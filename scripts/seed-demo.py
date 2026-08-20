import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "hermes-plugin"))

from aishop.runtime import get_demo_flow_service


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the deterministic AIShop demo task")
    parser.add_argument("--data-dir", help="Override the AIShop local data directory")
    arguments = parser.parse_args()
    if arguments.data_dir:
        os.environ["AISHOP_DATA_DIR"] = arguments.data_dir
        get_demo_flow_service.cache_clear()
    print(json.dumps(get_demo_flow_service().reset(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
