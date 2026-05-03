#!/usr/bin/env python3
"""
SpectraPyle CLI entry point.

Usage:
  python run_cli.py --config ../configs/YAML/default.yaml [--log-level INFO]
"""

import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from spectraPyle.stacking.stacking import main
from spectraPyle.utils.log import setup_logging
from spectraPyle.runtime.runtime_adapter import build_config_from_yaml, build_config_from_json, flatten_schema_model
from datetime import datetime
import yaml
import json


def main_cli():
    parser = argparse.ArgumentParser(description="SpectraPyle spectral stacking")
    parser.add_argument("--config", required=True, help="Path to config YAML/JSON file")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING"],
        help="Logging level (default: INFO)",
    )

    args = parser.parse_args()

    # Load config to extract output_dir
    config_path = Path(args.config)
    try:
        if config_path.suffix.lower() in ['.yaml', '.yml']:
            cfg = build_config_from_yaml(str(config_path))
        elif config_path.suffix.lower() == '.json':
            cfg = build_config_from_json(str(config_path))
        else:
            raise ValueError(f"Unsupported config format: {config_path.suffix}")
    except Exception as e:
        print(f"❌ Config load failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Setup logging to output_dir
    flat_cfg = flatten_schema_model(cfg)
    output_dir = Path(flat_cfg.get("output_dir", "."))
    output_dir.mkdir(parents=True, exist_ok=True)
    log_file = output_dir / f"spectraPyle_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    setup_logging(level=args.log_level, log_file=log_file, gui_output=None)

    # Run stacking
    try:
        main(str(config_path))
    except Exception as e:
        print(f"❌ Stacking failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main_cli()
