# `automator` CLI — Design Spec

## Context

This repo (`AgentJobAutomation`) is a set of standalone scripts (`run.py`,
`manual_run.py`, `archive_processed.py`, `controlled_batch_run.py`,
`larger_batch_run.py`, plus module self-tests like `python scraper.py`) that
each require `python <script>.py` invocation from the repo root.

This is the first of several planned improvements to the project (more job
sources, hallucination hardening, interview prep, cold-email outreach, a
living self-profile, and eventually a GUI). All of those will be exposed as
commands under one CLI rather than more standalone scripts, so this sub-project
builds that foundation first.

## Goal

A single installable command, `automator`, callable from anywhere on the
system, with subcommands wrapping the pipeline's existing entry points.
Deterministic subcommand dispatch — no LLM/agent in the routing path.

## Non-goals

- No real GUI implementation yet — `gui` is a stub reserving the command name.
- No new business logic — every subcommand calls existing functions.
- No natural-language command interpretation.

## Packaging & entry point

Add `pyproject.toml` at repo root:

```toml
[project]
name = "automator"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "PyYAML>=6.0",
    "httpx>=0.25.0",
    "APScheduler>=3.10.0",
    "python-dotenv>=1.0.0",
]

[project.scripts]
automator = "automator.cli:main"

[tool.setuptools]
py-modules = [
    "pipeline", "generator", "researcher", "scraper", "gmail_reader",
    "job_fetcher", "factual_validator", "scorer", "archive_processed",
    "manual_run", "crawl4ai_scraper",
]
packages = ["automator"]
```

Existing top-level modules stay in place as flat modules (referenced via
`py-modules`); only the new `automator/` package is added, containing
`cli.py`. Install with `pip install -e .` — this puts `automator` on PATH in
whatever environment it's installed into, same as any pip package.

`browser-use` and `playwright` stay as optional/extra dependencies (research
already degrades gracefully without them) rather than hard requirements of
the CLI package.

## Command dispatch

`automator/cli.py` — `argparse` with subparsers, mirroring the flag style
`run.py` already uses. `main()` builds the parser, dispatches to a handler
function per subcommand. Each handler does a local import of the module it
wraps (matching the lazy-import convention already used throughout
`pipeline.py`) and calls into existing functions. `cli.py` contains no
pipeline logic itself.

```
automator run [--dry-run] [--schedule] [--interval-hours N] [--limit N]
automator manual
automator archive [--clear]
automator test <scraper|gmail|generator|researcher> [args...]
automator gui
```

## Behavior changes to existing code

- **`run --limit N`**: `pipeline.run_pipeline` gains an optional `limit: int
  | None` parameter. When set, processing stops after `limit` listings have
  been processed (checked in the same place `stats["processed"]` is
  incremented across all three source loops). `controlled_batch_run.py` and
  `larger_batch_run.py` are deleted — they were identical except for a
  hardcoded `BATCH_SIZE` constant, now replaced by the flag.
- **`manual`**: calls `manual_run.run_manual()` unchanged.
- **`archive`**: calls `archive_processed.archive(clear=args.clear)`.
- **`test <module>`**: dispatches to the existing `if __name__ ==
  "__main__"` behavior of `scraper.py`, `gmail_reader.py`, `generator.py`,
  and `researcher.py` by calling their existing top-level functions directly
  (e.g. `scraper.scrape()`, `gmail_reader.search_emails(company)`,
  `researcher.research(company, role)`), passing through any extra
  positional args (e.g. `automator test gmail "Google"`). No new test logic
  is written — this only relocates the entry point.
- **`gui`**: prints `"GUI not built yet — coming in a later update"` and
  exits 0.

`test_crawl4ai.py` and `debug_violations.py` remain standalone dev scripts,
not wrapped by the CLI.

## Error handling

No new error-handling logic. Subcommands inherit whatever the underlying
module already does (e.g. `pipeline.py`'s per-listing non-fatal
try/excepts). `cli.py` only needs the same `ImportError` guard `run.py`
already has around APScheduler for `--schedule`.

## Testing

`test_cli.py`: build the `argparse` parser directly (no subprocess) and
assert each subcommand string parses to the expected handler/flags —
covers the new routing logic without re-testing the pipeline itself.

## README updates

Replace `python run.py` / `python manual_run.py` / etc. usage examples with
`automator run` / `automator manual` / etc., and add the one-time `pip
install -e .` setup step.
