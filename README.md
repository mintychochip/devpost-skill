# Devpost CLI

Browse, scout, and manage hackathons on Devpost from the command line.

## Install

```bash
cd devpost-mcp
pip install -e .
playwright install chromium
```

## Authentication (for Submissions)

To submit projects or manage your submissions, set environment variables:

```bash
export DEVPOST_EMAIL="your@email.com"
export DEVPOST_PASSWORD="your_password"
```

Or add to `~/.hermes/.env` or your shell profile.

Check auth status:
```bash
devpost auth status
```

## Usage

### Browse Hackathons (No Auth Required)

```bash
# List open hackathons
devpost list

# List closed hackathons (for scouting past events)
devpost list --state closed

# Search for AI hackathons
devpost search "AI"

# Sort by prize amount
devpost list --sort prize-amount

# Get hackathon info by slug
devpost info zervehack
devpost info datahacks-2025
```

### Submit Projects (Auth Required)

```bash
# Submit to a hackathon (dry run first)
devpost submit zervehack \
  --title "My Awesome Project" \
  --tagline "An AI-powered solution for X" \
  --description "Full markdown description here..." \
  --built-with "Python,FastAPI,OpenAI" \
  --github "https://github.com/user/repo" \
  --demo "https://example.com" \
  --dry-run

# Actually submit (remove --dry-run)
devpost submit zervehack \
  --title "My Awesome Project" \
  --tagline "An AI-powered solution for X" \
  --built-with "Python,OpenAI" \
  --github "https://github.com/user/repo"

# List your submissions
devpost my-submissions

# Update a submission
devpost update https://devpost.com/software/my-project \
  --tagline "Updated tagline"
```

### Deep Scrape (Partially Working)

```bash
# Scrape hackathon page (may be blocked by Cloudflare)
devpost scrape https://datahacks-2025.devpost.com/

# List projects from gallery (may be blocked)
devpost projects https://datahacks-2025.devpost.com/
devpost projects https://datahacks-2025.devpost.com/ --winners

# Get project details
devpost project https://devpost.com/software/onlydance
```

**Note:** Deep scraping is blocked by Devpost's Cloudflare protection. API-based commands (`list`, `info`, `search`) work fine.

## CLI Reference

### Public Commands (No Auth)
| Command | Description |
|---------|-------------|
| `devpost list` | List hackathons |
| `devpost info <slug>` | Get hackathon by slug |
| `devpost search <query>` | Search hackathons |
| `devpost scrape <url>` | Scrape hackathon page (blocked) |
| `devpost projects <url>` | List gallery projects (blocked) |
| `devpost project <url>` | Get project details (blocked) |

### Authenticated Commands (Requires Auth)
| Command | Description |
|---------|-------------|
| `devpost auth status` | Check authentication |
| `devpost submit <slug>` | Submit project to hackathon |
| `devpost my-submissions` | List your projects |
| `devpost update <url>` | Update existing submission |

## Examples

### Full Submission Workflow

```bash
# 1. Find a hackathon
devpost list --state open --sort submission-deadline

# 2. Get details
devpost info zervehack

# 3. Submit (dry run first)
devpost submit zervehack \
  --title "Hermes Devpost CLI" \
  --tagline "Command line tool for managing Devpost submissions" \
  --built-with "Python,Click,Playwright" \
  --github "https://github.com/mintychochip/devpost-mcp" \
  --dry-run

# 4. Actually submit
devpost submit zervehack \
  --title "Hermes Devpost CLI" \
  --tagline "Command line tool for managing Devpost submissions" \
  --built-with "Python,Click,Playwright" \
  --github "https://github.com/mintychochip/devpost-mcp"

# 5. Check your submissions
devpost my-submissions
```

### Managing Submissions

```bash
# List all your projects
devpost my-submissions

# Update a project's tagline
devpost update https://devpost.com/software/hermes-devpost-cli \
  --tagline "Updated: Now with authentication support!"

# Update multiple fields
devpost update https://devpost.com/software/hermes-devpost-cli \
  --title "Hermes Devpost CLI v2" \
  --description "## New Features\n\n- Authentication\n- Submit projects\n- Update submissions"
```

## Known Issues

1. **Scraping blocked:** Devpost uses Cloudflare which blocks automated browsers. API commands work, but scraping past hackathons doesn't.

2. **Screenshot uploads:** Not yet implemented (form interaction is complex).

## License

MIT
