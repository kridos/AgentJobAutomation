"""Argparse-based dispatcher for the automator CLI."""

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="automator", description="Internship automation pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
