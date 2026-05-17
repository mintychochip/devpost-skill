---
name: devpost-cli
allowed-tools: Bash(devpost:*)
description: >-
  Use when the user mentions Devpost, hackathons, submitting projects to
  Devpost, browsing hackathons, scouting competition, managing Devpost
  submissions, or any task involving the `devpost` CLI. Trigger on keywords
  like devpost, hackathon, prize, submission, project gallery. Use ONLY for
  Devpost-related tasks, not general project management.
---

# Devpost CLI Skill (v0.3.0)

The `devpost` CLI lets you browse hackathons, scout winning projects, search projects, and submit your own — all from the command line.

## Quick Start

```bash
devpost hackathons --json                  # List open hackathons
devpost hackathons -q "AI" --json          # Search hackathons by keyword
devpost overview zervehack --json          # Get hackathon details by slug
devpost deadlines --json                   # Hackathons sorted by deadline
devpost search "chatbot" --json            # Search projects (NEW in v0.3.0)
devpost gallery medo --json                # View project gallery
```

Always prefer `--json` flags when running commands so output is machine-parseable. The CLI auto-detects non-TTY and outputs JSON, but passing `--json` explicitly is safer.

## Caching

The CLI caches API responses at `~/.devpost/cache/` with 1-hour TTL by default. This makes repeat queries instant and enables `--deep` search across cached data. Configure TTL with `DEVPOST_CACHE_TTL` env var (seconds).

```bash
devpost cache status                     # Show cache stats
devpost cache clear                      # Wipe all cached data
```

Use `--no-cache` on any command to bypass cache and fetch fresh data.

## Authentication

Authenticated commands (submit, join, team, etc.) require credentials:

```bash
devpost auth login                       # Interactive login (saves to ~/.devpost/.env)
devpost auth status                      # Check if authenticated
devpost auth logout                      # Clear credentials
```

Or set environment variables:
```bash
export DEVPOST_EMAIL="your@email.com"
export DEVPOST_PASSWORD="your_password"
```

If auth is not set, authenticated commands will fail with exit code 2. Check auth first with `devpost auth status`.

## Public Commands (No Auth Required)

### Browse Hackathons

```bash
devpost hackathons --json                      # Top 20 recently-added
devpost hackathons --state open --json         # Only open hackathons
devpost hackathons --state closed --json       # Closed/ended hackathons (for scouting)
devpost hackathons --state ended --json        # Same as closed (API uses "ended")
devpost hackathons --sort prize-amount --json  # Sort by prize
devpost hackathons --limit 5 --json            # Limit results
devpost hackathons -q "AI" --json              # Search hackathons by query
```

States: `open`, `closed` (alias for `ended`), `ended`, `upcoming`, `judging`, `submitting`
Sort: `recently-added`, `submission-deadline`, `prize-amount`, `popularity`

**Note:** The Devpost API doesn't support filtering by closed/ended state. The CLI works around this by paging through results and filtering client-side. This may be slower than other list commands.

**Legacy alias:** `devpost list` (deprecated, still works)

### Get Hackathon Overview

```bash
devpost overview <slug> --json
```

The slug is the subdomain from the hackathon URL (e.g., `zervehack` from `zervehack.devpost.com`).

**Legacy alias:** `devpost info` (deprecated, still works)

### Search Projects (NEW in v0.3.0)

```bash
# Global project search (matches /software/search)
devpost search "AI" --json
devpost search "chatbot" -l 30 --json          # More results

# In-hackathon search (search projects within a hackathon)
devpost search "RAG" --in medo --json          # Search projects in MeDo hackathon
devpost search "agent" --in medo --winners --json   # Only winning projects
devpost search "OpenAI" --in medo --tech --json     # Search tech stacks
devpost search "requirement" --in medo --include-rules --json  # Also search description/rules
```

**Note:** To search hackathons (not projects), use `devpost hackathons -q "AI"`.

### Browse Projects

```bash
# Search projects
devpost projects search "AI" --json

# Popular projects
devpost projects popular --json

# Projects by technology
devpost projects built-with Python --json
devpost projects built-with "React" --json
devpost projects built-with "OpenAI" --json

# Staff picks / featured
devpost projects featured --json
```

### View Project Gallery

```bash
devpost gallery <slug> --json                # All projects from hackathon
devpost gallery <slug> --winners --json      # Only winning projects
devpost gallery <slug> -l 50 --json          # More results
```

**Legacy alias:** `devpost projects <url>` (deprecated, still works)

### Get Project Details

```bash
devpost project <url> --json
```

Uses browser automation to extract title, description, tech stack, team members, links, and screenshots.

### Hackathon Sub-Pages (NEW in v0.3.0)

```bash
# Participants
devpost participants <slug> --json
devpost participants <slug> -l 100 --json

# Resources
devpost resources <slug> --json

# Updates
devpost updates <slug> --json
devpost updates <slug> -l 50 --json

# Discussions / Forum Topics
devpost discussions <slug> --json
devpost discussions <slug> -l 50 --json
```

### Deadlines

```bash
devpost deadlines --json                # All hackathons, soonest deadline first
devpost deadlines --this-week --json    # Closing within 7 days
devpost deadlines --today --json        # Closing today
devpost deadlines -l 10 --json          # Limit results
```

### Rules

```bash
devpost rules <slug> --json             # Parse rules page into structured sections
devpost rules <slug> --no-cache --json  # Force fresh fetch
```

Extracts: eligibility, requirements, judging criteria, prize categories, key dates, sponsor APIs.

### Winners

```bash
devpost winners <slug> --json           # List winning projects
devpost winners <slug> --no-cache --json
```

### Evaluate Hackathon

```bash
devpost evaluate <slug> --json          # Get verdict (Enter/Maybe/Skip)
devpost evaluate <slug> --skills "Python,AI,GCP" --json  # With theme-fit signal
devpost evaluate <slug> --no-cache --json
```

Combines info, scrape, rules, and projects into a decision report with signals for time pressure, prize density, competition density, submission gap, and theme fit.

### Deep Scrape

```bash
devpost scrape <url> --json             # Deep scrape any hackathon page
devpost scrape <url> -o data.json       # Save to file
```

Works for active AND past/closed hackathons that the API doesn't return.

## Authenticated Commands

### Submit Project

```bash
devpost submit project <slug> \
  --title "My Project" \
  --tagline "AI-powered solution" \
  --description "Full description" \
  --built-with "Python,React,OpenAI" \
  --github "https://github.com/user/repo" \
  --demo "https://demo.example.com" \
  --dry-run                              # Test without submitting
```

### Update Submission

```bash
devpost update <project_url> \
  --tagline "New tagline" \
  --github "https://new-repo" \
  --dry-run
```

### List My Submissions

```bash
devpost my-submissions --json
devpost my-submissions -l 5 --json
```

### Get Submission Details

```bash
devpost submission <project_url> --json
```

### Team Management

```bash
devpost team add <project_url> <username>
devpost team remove <project_url> <username>
devpost team create <slug> --name "Team Awesome"
devpost team join <slug> --invite-url "https://..."
```

### Join/Leave Hackathon

```bash
devpost join <slug>
devpost leave <slug> --confirm           # Requires confirmation
```

### Like Project

```bash
devpost like <project_url>
```

### Upload Screenshots

```bash
devpost upload <project_url> img1.png img2.png --set-main 0
```

### Delete Project

```bash
devpost delete <project_url> --confirm   # CANNOT BE UNDONE
```

## Exit Codes

- `0`: Success
- `1`: General error
- `2`: Authentication required/failed
- `3`: Resource not found

## Common Patterns

### Find high-prize hackathons closing soon

```bash
devpost hackathons --state open --sort prize-amount --json | \
  jq '.[] | select(.prize_amount != null) | {title, prize: .prize_amount, ends: .ends_at}'
```

### Scout winning projects for inspiration

```bash
devpost winners <slug> --json | \
  jq '.winners[] | {title, prize, url}'
```

### Search for projects using specific tech

```bash
devpost projects built-with "OpenAI" --json | \
  jq '.[] | {title, built_with}'
```

### Evaluate multiple hackathons

```bash
for slug in medo rapid-agent zervehack; do
  devpost evaluate $slug --json | jq '{slug: "'$slug'", verdict, prize: .basics.prize}'
done
```

## Troubleshooting

**"Rate limited by Devpost (HTTP 429)"** — Wait a few minutes and retry. The CLI has built-in retry logic with exponential backoff.

**"Access denied (HTTP 403)"** — Some pages may be blocked by Cloudflare. Try `--no-cache` or use the API-based commands instead of scraping.

**"Playwright not installed"** — Run `pip install playwright && playwright install chromium`.

**No winners found** — Winners may not be announced yet, or the page may be blocked by Cloudflare. Try `devpost gallery <slug> --winners` as an alternative.

**Closed hackathons slow** — The API doesn't support filtering by `ended` state, so the CLI pages through results client-side. This is expected behavior.
