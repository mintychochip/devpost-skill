# Devpost CLI

Browse hackathons, scout winning projects, and submit your own — all from the command line.

A powerful CLI tool for interacting with Devpost hackathons:
- **Browse** open, closed, and upcoming hackathons
- **Search** by keyword or category
- **Scrape** detailed info from any hackathon page (even past events)
- **Explore** project galleries and winning submissions
- **Submit** your own projects with full metadata
- **Manage** teams, members, and project updates

## Install

```bash
cd devpost-mcp
pip install -e .
playwright install chromium
```

## Authentication (for Submissions)

To submit projects or manage your submissions, you need to authenticate:

### Option 1: Interactive Login (Recommended)

```bash
devpost auth login
```

This will prompt for your email and password, then save them securely to `~/.devpost/.env`.

### Option 2: Environment Variables

```bash
export DEVPOST_EMAIL="your@email.com"
export DEVPOST_PASSWORD="your_password"
```

Or add to `~/.bashrc`, `~/.zshrc`, or `~/.devpost/.env`.

### Check Auth Status

```bash
devpost auth status
```

### Logout

```bash
devpost auth logout
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

### Join a Hackathon (Auth Required)

Before you can submit, you need to join the hackathon:

```bash
devpost join zervehack
```

### Submit Projects (Auth Required)

```bash
# Submit to a hackathon (dry run first)
devpost submit project zervehack \
  --title "My Awesome Project" \
  --tagline "An AI-powered solution for X" \
  --description "Full markdown description here..." \
  --built-with "Python,FastAPI,OpenAI" \
  --github "https://github.com/user/repo" \
  --demo "https://example.com" \
  --dry-run

# Actually submit (remove --dry-run)
devpost submit project zervehack \
  --title "My Awesome Project" \
  --tagline "An AI-powered solution for X" \
  --built-with "Python,OpenAI" \
  --github "https://github.com/user/repo"
```

### Manage Submissions (Auth Required)

```bash
# List your submissions
devpost my-submissions

# Get details about a submission
devpost submission https://devpost.com/software/my-project

# Update a submission
devpost update https://devpost.com/software/my-project \
  --tagline "Updated tagline"

# Update only links (granular control)
devpost links https://devpost.com/software/my-project \
  --github "https://github.com/new-repo" \
  --demo "https://new-demo.com"

# Upload screenshots
devpost upload https://devpost.com/software/my-project \
  screenshot1.png screenshot2.png screenshot3.png \
  --set-main 0

# Delete a submission (CANNOT BE UNDONE)
devpost delete https://devpost.com/software/my-project --confirm
```

### Team Management (Auth Required)

```bash
# Add a team member
devpost team add https://devpost.com/software/my-project username

# Remove a team member
devpost team remove https://devpost.com/software/my-project username

# Create a team for a hackathon
devpost team create zervehack --name "My Team" --invite "user1,user2"

# Join a team
devpost team join zervehack --invite-url "https://..."
```

### Leave a Hackathon (Auth Required)

```bash
# Leave a hackathon you joined
devpost leave zervehack --confirm
```

### Like a Project (Auth Required)

```bash
# Like/bookmark a project
devpost like https://devpost.com/software/project-name
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

**Note:** Deep scraping may be blocked by Devpost's Cloudflare protection. API-based commands (`list`, `info`, `search`) work fine.

## CLI Reference

### Public Commands (No Auth)

| Command | Description |
|---------|-------------|
| `devpost list` | List hackathons |
| `devpost info <slug>` | Get hackathon by slug |
| `devpost search <query>` | Search hackathons |
| `devpost scrape <url>` | Scrape hackathon page |
| `devpost projects <url>` | List gallery projects |
| `devpost project <url>` | Get project details |

### Authenticated Commands

| Command | Description |
|---------|-------------|
| `devpost auth login` | Interactive authentication |
| `devpost auth status` | Check authentication |
| `devpost auth logout` | Clear credentials |
| `devpost join <slug>` | Join a hackathon |
| `devpost leave <slug>` | Leave a hackathon |
| `devpost submit project <slug>` | Submit project |
| `devpost my-submissions` | List your projects |
| `devpost submission <url>` | Get submission details |
| `devpost update <url>` | Update submission |
| `devpost links <url>` | Update project links |
| `devpost upload <url> <images>` | Upload screenshots |
| `devpost delete <url>` | Delete submission |
| `devpost team add <url> <user>` | Add team member |
| `devpost team remove <url> <user>` | Remove team member |
| `devpost team create <slug>` | Create team |
| `devpost team join <slug>` | Join team |
| `devpost like <url>` | Like project |

## Examples

### Full Submission Workflow

```bash
# 1. Find a hackathon
devpost list --state open --sort submission-deadline

# 2. Get details
devpost info zervehack

# 3. Join the hackathon
devpost join zervehack

# 4. Submit (dry run first)
devpost submit project zervehack \
  --title "Hermes Devpost CLI" \
  --tagline "Command line tool for managing Devpost submissions" \
  --built-with "Python,Click,Playwright" \
  --github "https://github.com/mintychochip/devpost-mcp" \
  --dry-run

# 5. Actually submit
devpost submit project zervehack \
  --title "Hermes Devpost CLI" \
  --tagline "Command line tool for managing Devpost submissions" \
  --built-with "Python,Click,Playwright" \
  --github "https://github.com/mintychochip/devpost-mcp"

# 6. Check your submissions
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

# Update just the links
devpost links https://devpost.com/software/hermes-devpost-cli \
  --github "https://github.com/new-repo" \
  --demo "https://new-demo.com"

# Upload screenshots
devpost upload https://devpost.com/software/hermes-devpost-cli \
  screenshots/demo1.png screenshots/demo2.png \
  --set-main 0
```

### Team Management

```bash
# Create a team for a hackathon
devpost team create zervehack --name "Team Awesome" --invite "alice,bob"

# Add someone to your project
devpost team add https://devpost.com/software/my-project charlie

# Remove someone from your project
devpost team remove https://devpost.com/software/my-project charlie
```

## Known Issues

1. **Scraping may be blocked:** Devpost uses AWS WAF/Cloudflare which can block automated browsers. API-based commands (`list`, `info`, `search`) always work, but deep scraping (`scrape`, `projects`, `project`) may occasionally fail for past/closed hackathons.

2. **Credentials:** Saved to `~/.devpost/.env` with appropriate permissions. Use `devpost auth logout` to clear.

## License

MIT
