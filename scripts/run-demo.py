import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "hermes-plugin"))

from aishop.demo_flows import FLOWS
from aishop.runtime import get_demo_flow_service


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an AIShop Phase 1 demo flow")
    parser.add_argument("--flow", choices=[*FLOWS, "all"], required=True)
    parser.add_argument("--mode", choices=["simulated", "device"], default="simulated")
    parser.add_argument(
        "--fault", choices=["none", "offline", "captcha", "unknown-page"], default="none"
    )
    parser.add_argument("--data-dir")
    arguments = parser.parse_args()
    if arguments.data_dir:
        os.environ["AISHOP_DATA_DIR"] = arguments.data_dir
    flow_ids = list(FLOWS) if arguments.flow == "all" else [arguments.flow]
    results = [
        get_demo_flow_service().run(
            flow_id, arguments.mode.upper(), arguments.fault.replace("_", "-")
        )
        for flow_id in flow_ids
    ]
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
