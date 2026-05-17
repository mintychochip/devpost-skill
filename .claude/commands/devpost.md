You are helping the user interact with Devpost hackathons via the `devpost` CLI.

Based on the user's request: $ARGUMENTS

Determine the appropriate `devpost` CLI command to run and execute it. Always add `--json` flag for commands that support it so output is parseable.

## Command Reference (v0.3.0)

**Public (no auth):**
- `devpost hackathons [--state open|closed|ended|upcoming] [--sort recently-added|submission-deadline|prize-amount|popularity] [--limit N] [-q QUERY] --json` — List hackathons
- `devpost overview <slug> --json` — Get hackathon details by slug
- `devpost search <query> [-l N] [--in SLUG] [--winners] [--tech] [--include-rules] --json` — Search PROJECTS (global or within hackathon)
- `devpost projects search <query> --json` — Search projects explicitly
- `devpost projects popular --json` — Popular projects
- `devpost projects built-with <tech> --json` — Projects using a technology
- `devpost projects featured --json` — Staff picks
- `devpost gallery <slug> [--winners] [--limit N] --json` — Project gallery from hackathon
- `devpost project <url> --json` — Get project details (needs Playwright)
- `devpost participants <slug> [-l N] --json` — List hackathon participants
- `devpost resources <slug> --json` — List hackathon resources
- `devpost updates <slug> [-l N] --json` — List hackathon updates
- `devpost discussions <slug> [-l N] --json` — List forum discussions
- `devpost deadlines [--this-week] [--today] --json` — Hackathons by deadline
- `devpost scrape <url> --json` — Deep scrape hackathon page (may be blocked)
- `devpost rules <slug> --json` — Structured rules (eligibility, requirements, judging, prizes, dates, sponsor APIs)
- `devpost winners <slug> --json` — Winning projects
- `devpost evaluate <slug> [--skills "Python,AI,GCP"] --json` — Verdict + competition analysis + rules + signals

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

## Legacy Aliases (still work but deprecated)
- `devpost list` → `devpost hackathons`
- `devpost info` → `devpost overview`
- `devpost projects <url>` → `devpost gallery <slug>`

## Guidelines

1. For browsing/searching, use public commands with `--json`.
2. For submissions, always run with `--dry-run` first unless the user explicitly says to submit for real.
3. If an authenticated command fails with exit code 2, tell the user to run `devpost auth login` first.
4. The slug is the subdomain from the hackathon URL (e.g., `zervehack` from `zervehack.devpost.com`).
5. Deep scraping may be blocked by Cloudflare — prefer API commands (`hackathons`, `overview`, `search`) when possible.
6. Use `--in <slug>` with `search` to search within a specific hackathon's projects/tech stacks.
7. Use `devpost deadlines --this-week` to find hackathons closing soon.
8. Use `--no-cache` to bypass cache and fetch fresh data if results seem stale.
9. Use `devpost evaluate <slug>` to get a quick decision report on whether a hackathon is worth entering.
10. Use `devpost rules <slug>` to see structured eligibility, requirements, judging criteria, and sponsor APIs.
11. Use `devpost winners <slug>` to scout winning projects from past hackathons.
12. Use `devpost search` for PROJECT search; use `devpost hackathons -q` for hackathon search.
