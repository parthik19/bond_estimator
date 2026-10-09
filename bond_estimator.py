"""Expected IRR of a bond fund over 2 × duration − 1 years. See README.md."""

from __future__ import annotations

import argparse
import sys

from estimator import report, selftest
from estimator.config import ConfigError, load


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Expected IRR of a bond fund over 2 × duration − 1 years, for each "
        "default/recovery case in the fund file.",
    )
    parser.add_argument("fund_file", help="TOML file with the fund's numbers and cases (see funds/)")
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="override a value without editing the file: a fund field (yield_to_worst=0.075) "
        "or a case field (benign.default_rate=0.02); repeatable",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    tests = selftest.run()
    if not tests.passed:
        sys.stderr.write(tests.output)
        print("\nSelf-tests failed, so no estimate was produced.", file=sys.stderr)
        return 1
    print(f"Self-tests: {tests.summary}\n")

    try:
        config = load(args.fund_file, args.set)
    except ConfigError as e:
        print(f"Problem with the inputs:\n{e}", file=sys.stderr)
        return 2
    print(report.render(config))
    return 0


if __name__ == "__main__":
    sys.exit(main())
