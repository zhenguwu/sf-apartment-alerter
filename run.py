#!/usr/bin/env python3
"""Apartment scraper entry point.

Usage:
    python run.py                # poll forever
    python run.py --once         # run a single iteration and exit (smoke test)
    python run.py --config foo.yaml
"""
from __future__ import annotations

import argparse
import logging

from apt_scraper import config as config_mod
from apt_scraper.runner import Runner


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--once", action="store_true", help="run one cycle then exit")
    p.add_argument("--no-notify", action="store_true",
                   help="dry run — extract & log but don't send notifications")
    args = p.parse_args()

    cfg = config_mod.load(args.config)

    logging.basicConfig(
        level=cfg.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.no_notify:
        class _NoopNotifier:
            def send(self, unit):
                logging.getLogger("dryrun").info("[DRY RUN] would notify: %s", unit.to_dict())
        runner = Runner(cfg, notifier=_NoopNotifier())
    else:
        runner = Runner(cfg)

    try:
        if args.once:
            runner.run_once()
        else:
            runner.run_forever()
    except KeyboardInterrupt:
        logging.info("Interrupted, shutting down.")
    finally:
        runner.close()


if __name__ == "__main__":
    main()
