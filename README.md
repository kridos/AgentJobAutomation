# Internship Automation Pipeline

Scrapes SimplifyJobs → cross-references Gmail → researches companies → generates tailored resumes + cover letters via local Ollama. Zero paid APIs.

## Setup

```bash
# dev extra is only needed to run the test suite; research extra pulls in playwright (used as a fallback for JS-heavy job pages)
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

### Gmail API setup (optional — used for recruiter-email cross-referencing/sourcing and cold-email drafts)

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project (or use an existing one), enable the **Gmail API**, and create an OAuth 2.0 Client ID of type **Desktop app**.
2. Download the client's JSON and save it as `credentials.json` in the repo root (gitignored — never commit this).
3. Run the one-time login:
   ```bash
   automator gmail auth
   ```
   This opens your browser for Google's consent screen. After you approve, it saves a refreshable token to `token.json` (also gitignored). Every later run refreshes it silently — no need to repeat this unless the token is revoked or deleted.

Without this setup, Gmail-dependent steps (recruiter cross-referencing in `automator run`, and `automator outreach run`'s drafting) fail non-fatally and are skipped — everything else still works.

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

# Add a cold-outreach contact
automator outreach add

# Generate + draft cold emails for pending contacts (creates Gmail drafts, never sends)
automator outreach run

# Show outreach contact status (drafted/pending, confirmed/unconfirmed)
automator outreach list

# Discover new startup contacts from YC's directory (guesses + SMTP-verifies emails)
# Note: verification needs outbound port 25 (SMTP), which most residential ISPs and
# cloud providers block by default. If blocked, all contacts come back unconfirmed
# and need `automator outreach confirm`.
automator outreach discover

# Manually confirm/override a discovered contact's email
automator outreach confirm <contact-id> <email>

# Generate interview prep for an application you already made (research,
# likely questions with resume talking points, and practice problems)
automator prep "Acme Corp"
automator prep "Acme Corp" --role "ML Intern"   # disambiguate multiple matches

# Quick-capture a recent accomplishment
automator log "Shipped RGB-D fusion milestone" --tags robotics,ai-ml

# Promote staged accomplishments into the permanent record
automator flush

# Archive processed.json (clears it by default)
automator archive
automator archive --keep   # archive without clearing
```

### Review applications and mark status

```bash
automator gui
```

Starts a local dashboard at http://127.0.0.1:8420/ — browse generated
applications (resume, cover letter, job description), mark each as
applied/skipped/pending, view outreach contact status, and view generated
interview prep material. Local-only (binds to 127.0.0.1); does not submit
applications or trigger generation — run `automator run`/`outreach`/`prep`
for that.

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
automator test gmail company Google        # test Gmail search (needs `automator gmail auth` first)
automator test generator                   # test Ollama generation
automator test researcher Stripe "SWE Intern"  # test web research
```

## Configuration

Edit `config.yaml` to change the Ollama model, research timeout, or schedule interval.
