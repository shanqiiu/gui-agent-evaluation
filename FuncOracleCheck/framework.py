import argparse
import os

from GUI_TestFramework_v1 import scripts
from oracle_service import run_sequence, run_single_step
from utils import json_utils


def sequence_test(config: scripts.Config):
    if config.project.PREDICATE_MODE == "test":
        saved_path = os.path.join(config.data.OUTPUT_DIR, f"{os.path.basename(config.data.DATA_DIR)}.json")
        if os.path.exists(saved_path):
            print(f"path: {saved_path} already exists, skip this task!")
            return

        print(f"running single sequence bench-test from: {config.data.DATA_DIR}...")

    print(run_sequence(config))


def page_test(sample_dict: dict):
    print(run_single_step(sample_dict))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a Darwin oracle sequence check.")
    parser.add_argument("--metadata", help="Production-format metadata JSON path.")
    parser.add_argument("--data-dir", help="Benchmark single-sample directory used in test mode.")
    args = parser.parse_args()

    if args.metadata and args.data_dir:
        parser.error("--metadata and --data-dir cannot be used together")

    config_main = scripts.Config()
    if args.metadata:
        config_main.project.PREDICATE_MODE = "production"
        config_main.data.METADATA = json_utils.load_json(args.metadata)
    elif args.data_dir:
        config_main.data.DATA_DIR = args.data_dir
    elif config_main.project.PREDICATE_MODE == "test" and not config_main.data.DATA_DIR:
        parser.error("--data-dir is required in test mode")

    sequence_test(config_main)
