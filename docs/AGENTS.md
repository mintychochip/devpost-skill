# Devpost Skill — Agent Reference

**Purpose:** AI agent skill for hackathon discovery, competition scouting, project submission, and team management on Devpost.

---

## Prerequisites

```bash
pip install devpost-cli
playwright install chromium
```

---

## Quick Reference

| Command | Description | Key Flags |
|---------|-------------|-----------|
| `devpost hackathons` | List/browse hackathons | `--state`, `--sort`, `--query`, `--limit`, `--json` |
| `devpost overview <slug>` | Hackathon details | `--json` |
| `devpost evaluate <slug>` | Decision report (Enter/Maybe/Skip) | `--skills`, `--json` |
| `devpost search <query>` | Global project search | `--playwright`, `--across`, `--limit`, `--json` |
| `devpost gallery <slug>` | Project gallery | `--winners`, `--limit`, `--json` |
| `devpost project <url>` | Project details | `--json` |
| `devpost user <username>` | Full user profile | `--json` |
| `devpost search-users <query>` | Search users | `--limit`, `--json` |
| `devpost participants <slug>` | Hackathon participants | `--limit`, `--json` |
| `devpost rules <slug>` | Structured rules | `--json` |
| `devpost winners <slug>` | Winning projects | `--json` |
| `devpost deadlines` | Hackathons by deadline | `--this-week`, `--today`, `--json` |
| `devpost rss` | Hackathon feed | `--json` |
| `devpost join <slug>` | Register for hackathon | (requires auth) |
| `devpost submit project <slug>` | Submit project | `--title`, `--tagline`, `--dry-run` |
| `devpost index build` | Build local search index | `--projects`, `--limit` |
| `devpost index search <query>` | Search local index | `--type`, `--limit` |

**All commands support `--json` flag.** When stdout is not a TTY (piped), JSON is auto-detected.

---

## Output Format

All commands return structured JSON when `--json` flag is set or stdout is piped:

```bash
devpost overview zervehack --json
```

```json
{
  "title": "Zerve Hackathon",
  "url": "https://zervehack.devpost.com/",
  "open_state": "open",
  "prize_amount": "$10,000",
  "ends_at": "14 days left",
  "submissions_count": 45,
  "registrations_count": 230
}
```

---

## Common Patterns

### WAF Bypass

Global project search (`/software/search`) is AWS WAF-protected. Use Playwright:

```bash
devpost search "AI" --playwright --json
```

### Cache Control

Commands use local HTTP cache by default. Force fresh fetch:

```bash
devpost rules medo --no-cache --json
```

### Pagination

Some commands auto-paginate. For manual control:

```bash
devpost hackathons --page 2 --per-page 50 --json
```

### Authenticated Commands

Set credentials via environment:

```bash
export DEVPOST_EMAIL="your@email.com"
export DEVPOST_PASSWORD="your_password"
```

Or use interactive login:

```bash
devpost auth login
```

---

## Decision Signals

### Evaluate Verdict

`devpost evaluate` returns a verdict with reasoning:

| Verdict | Meaning | Action |
|---------|---------|--------|
| `Enter` | Favorable signals | Proceed with submission |
| `Maybe` | Mixed signals | Review rules/competition manually |
| `Skip` | Unfavorable signals | Look for other hackathons |

### Signal Levels

- **time_pressure:** `critical` (<1 day), `high` (<5 days), `medium` (<14 days), `low`
- **prize_density:** `high` (≥$5k/project), `medium` (≥$1k), `low`, `none`
- **competition_density:** `high` (≥500/prize), `medium` (≥100), `low`
- **submission_gap:** `wide_open` (<10% submitted), `moderate`, `filling`
- **theme_fit:** `high` (skills match themes/APIs), `low`, `unknown`

---

## Error Handling

| Error Code | Meaning | Recovery |
|------------|---------|----------|
| `NOT_FOUND` | Resource not found | Verify slug/URL, try alternative |
| `RATE_LIMITED` | HTTP 429 | Retry after delay (check `Retry-After` header) |
| `SERVER_ERROR` | HTTP 5xx | Retry with exponential backoff |
| `TIMEOUT` | Request timeout | Retry or use `--playwright` |
| `DEPENDENCY_MISSING` | Playwright not installed | Run `playwright install chromium` |
| `VALIDATION_ERROR` | Invalid slug/URL | Check format (e.g., `zervehack` not `https://...`) |

---

## Workflow Files

- [`find-and-evaluate.md`](workflows/find-and-evaluate.md) — Discover and evaluate hackathons
- [`scout-competition.md`](workflows/scout-competition.md) — Analyze projects, tech stacks, winners
- [`find-teammates.md`](workflows/find-teammates.md) — Search participants, check profiles
- [`submit-project.md`](workflows/submit-project.md) — End-to-end submission flow
- [`monitor-deadlines.md`](workflows/monitor-deadlines.md) — Time-sensitive workflows
- [`build-search-index.md`](workflows/build-search-index.md) — Local index for fast queries

---

## Performance Notes

- **Cache:** First call fetches, subsequent calls use cache (TTL varies by endpoint)
- **Playwright:** Slower but reliable for WAF-protected endpoints
- **Index:** Local search index provides instant offline queries
- **Rate limits:** Devpost API rate-limits; use `--no-cache` sparingly
