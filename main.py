"""
JARVIS OS — CLI entry point (Phase 9 refactor).

Usage:
    python main.py                 # interactive REPL
    python main.py --dry-run       # supervisor dry-run (log only)
    python main.py --config x.yaml # custom config
    python main.py --once "list files"   # single-shot
"""

import argparse
import json
import logging
import os
import sys
from typing import Optional

import yaml

from core.agent import Agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


def load_config(path: Optional[str]) -> dict:
    """Load config from config.yaml (or .jarvis/config.json fallback)."""
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    # default candidate paths
    for cand in ("config.yaml", os.path.join("config", "config.yaml"), ".jarvis/config.json"):
        if os.path.exists(cand):
            if cand.endswith(".json"):
                with open(cand, "r", encoding="utf-8") as f:
                    return json.load(f)
            with open(cand, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    return {}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="JARVIS OS — Phase 9")
    parser.add_argument("--config", default=None, help="path to config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="log actions but don't execute")
    parser.add_argument("--once", default=None, help="run a single message and exit")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    if args.dry_run:
        cfg["dry_run"] = True

    agent = Agent(config=cfg)

    if args.once:
        print(agent.process(args.once))
        return 0

    print("JARVIS OS (Phase 9) — type 'exit' to quit. (offline fallback active if no LLM)")
    try:
        while True:
            line = input("\nYou: ").strip()
            if line.lower() in ("exit", "quit", "q"):
                break
            if not line:
                continue
            reply = agent.process(line)
            print(f"JARVIS: {reply}")
    except (KeyboardInterrupt, EOFError):
        print("\nGoodbye.")
    return 0


if __name__ == "__main__":
    sys.exit(main())