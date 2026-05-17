You are helping the user interact with Devpost hackathons via the `devpost` CLI.

Based on the user's request: $ARGUMENTS

Determine the appropriate `devpost` CLI command to run and execute it. Always add `--json` flag for commands that support it so output is parseable.

## Command Reference

**Public (no auth):**
- `devpost list [--state open|closed|ended|upcoming] [--sort recently-added|submission-deadline|prize-amount|popularity] [--limit N] [-q QUERY] --json` — List hackathons (closed=ended, pages through API)
- `devpost info <slug> --json` — Get hackathon details by slug
- `devpost search <query> [--min-prize N] [--closing-within N] [--theme T] [--featured] [--online] [--deep] [--in SLUG] [--winners] [--tech] [--include-rules] --json` — Search hackathons (global) or within a hackathon (--in)
- `devpost deadlines [--this-week] [--today] --json` — Show hackathons sorted by soonest deadline
- `devpost scrape <url> --json` — Deep scrape hackathon page (may be blocked)
- `devpost projects <url> [--winners] [--limit N] --json` — List project gallery
- `devpost project <url> --json` — Get project details (needs Playwright)
- `devpost rules <slug> --json` — Extract structured rules (eligibility, requirements, judging, prizes, dates, sponsor APIs)
- `devpost winners <slug> --json` — List winning projects from a hackathon
- `devpost evaluate <slug> [--skills "Python,AI,GCP"] --json` — Full evaluation: verdict + competition analysis + rules + signals

**Cache:**
- `devpost cache status` — Show cache stats
- `devpost cache clear` — Wipe cached data

**Auth:**
- `devpost auth status` — Check auth
- `devpost auth login` — Interactive login
- `devpost auth logout` — Clear credentials

**Authenticated:**
- `devpost join <slug>` — Join a hackathon
- `devpost leave <slug> --confirm` — Leave a hackathon
- `devpost submit project <slug> --title T --tagline T [--built-with T] [--github URL] [--demo URL] [--dry-run]` — Submit project (always --dry-run first)
- `devpost my-submissions --json` — List your submissions
- `devpost submission <url> --json` — Get submission details
- `devpost update <url> [--title T] [--tagline T] [--description D] [--built-with T] [--dry-run]` — Update submission
- `devpost links <url> [--github URL] [--demo URL] [--video URL] [--website URL] [--dry-run]` — Update links only
- `devpost upload <url> <images...> [--set-main N]` — Upload screenshots
- `devpost delete <url> --confirm` — Delete submission permanently
- `devpost team add|remove <url> <username>` — Team member management
- `devpost team create <slug> --name N [--invite users]` — Create team
- `devpost team join <slug> [--invite-url URL]` — Join team
- `devpost like <url>` — Like a project

## Guidelines

1. For browsing/searching, use public commands with `--json`.
2. For submissions, always run with `--dry-run` first unless the user explicitly says to submit for real.
3. If an authenticated command fails with exit code 2, tell the user to run `devpost auth login` first.
4. The slug is the subdomain from the hackathon URL (e.g., `zervehack` from `zervehack.devpost.com`).
5. Deep scraping may be blocked by Cloudflare — prefer API commands (`list`, `info`, `search`) when possible.
6. Use `--in <slug>` to search within a specific hackathon's projects/tech stacks.
7. Use `devpost deadlines --this-week` to find hackathons closing soon.
8. Use `--no-cache` to bypass cache and fetch fresh data if results seem stale.
9. Use `devpost evaluate <slug>` to get a quick decision report on whether a hackathon is worth entering.
10. Use `devpost rules <slug>` to see structured eligibility, requirements, judging criteria, and sponsor APIs.
11. Use `devpost winners <slug>` to scout winning projects from past hackathons.
