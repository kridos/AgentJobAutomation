# Internship Automation Pipeline

Scrapes SimplifyJobs → cross-references Gmail → researches companies → generates tailored resumes + cover letters via local Ollama. Zero paid APIs.

## Setup

```bash
# dev extra is only needed to run the test suite; research extra pulls in browser-use/playwright
pip install -e ".[dev,research]"
playwright install chromium
```

Make sure Ollama is running with your model pulled:
```bash
ollama serve
ollama pull qwen2.5
```

Authenticate the `gh` CLI:
```bash
gh auth login
```

## Context Files

Drop your context files into `/context/` before running:

- `resume_master.md` — all experience and projects, with `[tags]` for filtering
- `voice.md` — cover letter tone rules and what to avoid
- `preferences.md` — target roles, locations, filters

Two more are optional and created on first use — they let you quick-capture recent
accomplishments so generation stays up to date without editing `resume_master.md`:

- `recent_updates.md` — staging area for entries logged via `automator log`
- `accomplishments.md` — permanent record of accomplishments promoted via `automator flush`

## Usage

```bash
# Run once
automator run

# Dry run — scrape and filter only, no generation
automator run --dry-run

# Stop after N listings (replaces the old controlled_batch_run.py / larger_batch_run.py scripts)
automator run --limit 5

# Run on a 24h schedule
automator run --schedule

# Custom schedule interval
automator run --schedule --interval-hours 12

# Manually enter a single job listing
automator manual

# Quick-capture a recent accomplishment
automator log "Shipped RGB-D fusion milestone" --tags robotics,ai-ml

# Promote staged accomplishments into the permanent record
automator flush

# Archive processed.json (clears it by default)
automator archive
automator archive --keep   # archive without clearing

# GUI (not yet implemented)
automator gui
```

## Output

Each run saves to `output/YYYY-MM-DD/company_name/`:
- `resume.md`
- `cover_letter.md`
- `listing.json`

And `output/YYYY-MM-DD/summary.md` — counts and status for every listing.

`processed.json` tracks all processed listing IDs to avoid regenerating on future runs.

## Testing Individual Modules

```bash
automator test scraper                    # test scraping
automator test gmail company Google        # test Gmail MCP
automator test generator                   # test Ollama generation
automator test researcher Stripe "SWE Intern"  # test web research
```

## Configuration

Edit `config.yaml` to change the Ollama model, research timeout, or schedule interval.
