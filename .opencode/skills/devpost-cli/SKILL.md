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

# Devpost CLI Skill

The `devpost` CLI lets you browse hackathons, scout winning projects, and submit your own — all from the command line.

## Quick Start

```bash
devpost list --json                      # List open hackathons (JSON for parsing)
devpost search "AI" --json               # Search by keyword
devpost info zervehack --json            # Get hackathon details by slug
devpost deadlines --json                 # Hackathons sorted by deadline
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

### List hackathons
```bash
devpost list --json                      # Top 20 recently-added
devpost list --state open --json         # Only open hackathons
devpost list --state closed --json       # Closed/ended hackathons (for scouting)
devpost list --state ended --json        # Same as closed (API uses "ended")
devpost list --sort prize-amount --json  # Sort by prize
devpost list --limit 5 --json            # Limit results
devpost list -q "AI" --json              # Search query
```

States: `open`, `closed` (alias for `ended`), `ended`, `upcoming`, `judging`, `submitting`
Sort: `recently-added`, `submission-deadline`, `prize-amount`, `popularity`

**Note:** The Devpost API doesn't support filtering by closed/ended state. The CLI works around this by paging through results and filtering client-side. This may be slower than other list commands.

### Get hackathon info
```bash
devpost info <slug> --json
```
The slug is the subdomain from the hackathon URL (e.g., `zervehack` from `zervehack.devpost.com`).

### Search hackathons (enhanced)
```bash
# Global search
devpost search "AI" --json
devpost search "AI" --min-prize 10000 --json       # Min $10k prize
devpost search "AI" --closing-within 7 --json        # Closing within 7 days
devpost search "AI" --theme "Machine Learning" --json
devpost search "AI" --featured --json               # Featured only
devpost search "AI" --online --json                  # Online only
devpost search "RAG" --deep --json                  # Search cached descriptions/rules too

# In-hackathon search (search projects within a hackathon)
devpost search "RAG" --in medo --json               # Search projects in MeDo hackathon
devpost search "agent" --in medo --winners --json    # Only winning projects
devpost search "OpenAI" --in medo --tech --json      # Search tech stacks
devpost search "requirement" --in medo --include-rules --json  # Also search description/rules
```

### Deadlines
```bash
devpost deadlines --json                # All hackathons, soonest deadline first
devpost deadlines --this-week --json     # Closing within 7 days
devpost deadlines --today --json         # Closing today
```

### Scrape hackathon page (may be blocked by Cloudflare)
```bash
devpost scrape <url> --json
devpost scrape <url> -o data.json       # Save to file
```

### List project gallery
```bash
devpost projects <hackathon-url> --json
devpost projects <hackathon-url> --winners --json
devpost projects <hackathon-url> --limit 50 --json
```

### Get project details (requires Playwright)
```bash
devpost project <project-url> --json
```

### Extract hackathon rules
```bash
devpost rules <slug> --json              # Structured rules extraction
devpost rules <slug> --no-cache          # Force fresh fetch
```

Parses the hackathon's `/rules` page into structured sections: eligibility, requirements, judging criteria, prize categories, key dates, and sponsor API requirements. Cached for 5 minutes.

### List hackathon winners
```bash
devpost winners <slug> --json            # List winning projects
devpost winners <slug> --no-cache        # Force fresh fetch
```

Tries the project gallery (filtered to winners), then falls back to scraping the `/winners` page.

### Evaluate a hackathon (hero command)
```bash
devpost evaluate <slug> --json          # Full evaluation report
devpost evaluate <slug> --skills "Python,AI,GCP"  # Include theme-fit signal
devpost evaluate <slug> --no-cache       # Force fresh fetch
```

Combines info, scrape, rules, and projects into a decision report with:
- **Verdict**: Enter / Maybe / Skip
- **Basics**: title, prize, status, dates, org, themes
- **Competition**: registrants, submissions, prize per project, density
- **Structured rules**: eligibility, requirements, judging criteria, prize categories, key dates, sponsor APIs
- **Signals**: time pressure, prize density, competition density, submission gap, theme fit

## Authenticated Commands

### Join a hackathon
```bash
devpost join <slug>
```

### Submit a project
```bash
devpost submit project <slug> \
  --title "My Project" \
  --tagline "Short description" \
  --built-with "Python,React,OpenAI" \
  --github "https://github.com/user/repo" \
  --demo "https://example.com" \
  --dry-run
```
Always use `--dry-run` first, then remove it to actually submit.

### Manage submissions
```bash
devpost my-submissions --json           # List your projects
devpost submission <url> --json         # Get submission details
devpost update <url> --tagline "New"    # Update fields
devpost links <url> --github "https://" # Update links only
devpost upload <url> img1.png img2.png   # Upload screenshots
devpost delete <url> --confirm          # Permanent delete
```

### Team management
```bash
devpost team add <url> <username>
devpost team remove <url> <username>
devpost team create <slug> --name "Team" --invite "user1,user2"
devpost team join <slug> --invite-url "https://..."
```

### Other
```bash
devpost leave <slug> --confirm
devpost like <project-url>
```

## Common Workflows

### Find and join a hackathon
```bash
devpost list --state open --sort prize-amount --json
devpost info <slug> --json
devpost join <slug>
```

### Find hackathons closing soon
```bash
devpost deadlines --this-week --json
devpost search "AI" --closing-within 7 --min-prize 10000 --json
```

### Full submission flow
```bash
devpost auth status
devpost join <slug>
devpost submit project <slug> --title "X" --tagline "Y" --built-with "Z" --dry-run
devpost submit project <slug> --title "X" --tagline "Y" --built-with "Z"
devpost my-submissions --json
```

### Scout competition
```bash
devpost list --state closed --json
devpost winners <slug> --json
devpost projects <url> --winners --json
devpost project <project-url> --json
```

### Evaluate a hackathon
```bash
devpost evaluate <slug> --json
devpost evaluate <slug> --skills "Python,AI,React" --json
devpost rules <slug> --json
```

### Search within a hackathon
```bash
devpost search "RAG" --in <slug> --json
devpost search "agent" --in <slug> --winners --tech --json
devpost search "API" --in <slug> --include-rules --json
```

## Known Issues

1. **Scraping may be blocked:** Devpost uses AWS WAF/Cloudflare. API commands (`list`, `info`, `search`) always work. Deep scraping (`scrape`, `projects`, `project`) may fail for past/closed hackathons.
2. **Playwright required:** Authenticated commands and project details need `playwright` with Chromium installed (`pip install playwright && playwright install chromium`).
3. **Credentials:** Stored at `~/.devpost/.env`. Use `devpost auth logout` to clear.
4. **In-hackathon search** requires the project gallery to be accessible (may be blocked by Cloudflare for closed hackathons).

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Auth required |
| 3 | Not found |
