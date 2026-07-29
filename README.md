# Internship Automation Pipeline

Scrapes SimplifyJobs → cross-references Gmail → researches companies → generates tailored resumes + cover letters via local Ollama. Zero paid APIs.

## Setup

```bash
pip install -r requirements.txt
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

Drop your three context files into `/context/` before running:

- `resume_master.md` — all experience and projects, with `[tags]` for filtering
- `voice.md` — cover letter tone rules and what to avoid
- `preferences.md` — target roles, locations, filters

## Usage

```bash
# Run once
python run.py

# Dry run — scrape and filter only, no generation
python run.py --dry-run

# Run on a 24h schedule
python run.py --schedule

# Custom schedule interval
python run.py --schedule --interval-hours 12
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
python scraper.py                               # test scraping
python gmail_reader.py "Google"                 # test Gmail MCP
python generator.py                             # test Ollama generation
python researcher.py "Stripe" "SWE Intern"     # test web research
```

## Configuration

Edit `config.yaml` to change the Ollama model, research timeout, or schedule interval.
