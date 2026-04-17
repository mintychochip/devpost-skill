# Devpost MCP Server

MCP server for browsing, searching, and submitting to Devpost hackathons.

## Tools

### Read-Only (No Auth Required)

- **list_hackathons** - Browse hackathons with filters
  - `limit`: Number to return (default: 20)
  - `open_state`: Filter by state (`open`, `closed`, `upcoming`, `judging`, `submitting`)
  - `sort_by`: Sort order (`recently-added`, `submission-deadline`, `prize-amount`, `popularity`)
  
- **search_hackathons** - Search by keyword
  - `query`: Search term (e.g., "AI", "healthcare")
  - `limit`: Number of results

- **get_hackathon_by_url** - Get hackathon by slug
  - `slug`: URL slug (e.g., "zervehack" from zervehack.devpost.com)

- **get_hackathon_details** - Scrape full details
  - `url`: Full hackathon URL

- **scrape_hackathon_page** - DEEP SCRAPE any hackathon by URL (works for past/closed hackathons the API doesn't return)
  - `url`: Full hackathon URL (e.g., https://datahacks-2025.devpost.com/)
  - Extracts: title, description, dates, prize, stats, themes, winners status, gallery/rules links

- **list_hackathon_projects** - List projects from a hackathon's gallery (works for closed hackathons!)
  - `hackathon_url`: Hackathon URL
  - `limit`: Max projects to return
  - `include_winners_only`: Only return winning projects

- **get_project_details** - Get detailed info about a specific project
  - `project_url`: Full project URL
  - Returns: title, tagline, description, tech stack, links, team, screenshots, winner status

### Write - Project Submission (Requires Auth)

- **submit_project** - SUBMIT a new project to a hackathon
  - `hackathon_slug`: URL slug (e.g., "zervehack")
  - `project_title`: Your project name
  - `project_tagline`: Short description (max 140 chars)
  - `project_description`: Full markdown description (optional)
  - `built_with`: List of tech used (e.g., `["Python", "React", "OpenAI"]`)
  - `links`: Object with `github`, `demo`, `video`, `website`
  - `dry_run`: Test without actually submitting

### Write - Project Management (Requires Auth)

- **list_my_submissions** - List all YOUR submitted projects
  - `limit`: Max number to return

- **get_submission_details** - Get full details about a specific project
  - `project_url`: Full project URL

- **update_submission** - UPDATE existing project (patch-style, only send changed fields)
  - `project_url`: Project to update
  - `project_title`: New title (optional)
  - `project_tagline`: New tagline (optional)
  - `project_description`: New description (optional)
  - `built_with`: New tech stack (optional)
  - `links`: New links (optional)
  - `dry_run`: Test without saving

- **add_team_member** - Add someone to your project
  - `project_url`: Project URL
  - `username`: Devpost username or email to add

- **remove_team_member** - Remove someone from your project
  - `project_url`: Project URL
  - `username`: Username to remove

- **upload_screenshots** - Add images to your project
  - `project_url`: Project URL
  - `image_paths`: List of local file paths
  - `set_main_image`: Which image should be main (0-based index)

- **delete_submission** - PERMANENTLY delete a project (requires `confirm: true`)

## Auth Setup

Set your Devpost credentials:

```bash
export DEVPOST_EMAIL="your@email.com"
export DEVPOST_PASSWORD="yourpassword"
```

Or add to `~/.hermes/.env`:
```
DEVPOST_EMAIL=your@email.com
DEVPOST_PASSWORD=yourpassword
```

## Install

```bash
pip install -e .
playwright install chromium
```

## Usage with Hermes

Add to `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  devpost:
    command: "python"
    args: ["-m", "devpost_mcp.server"]
    cwd: "/home/justin-lo/devpost-mcp"
```

## Example Queries

- "Find open AI hackathons with prizes"
- "Show me hackathons ending this week"
- "Get details for zervehack"

### Finding Past/Historical Hackathons

The API only returns currently active hackathons. To find past hackathons like DataHacks 2025:

```bash
# Direct URL scraping for past hackathons
python -m devpost_mcp.server scrape_hackathon_page \
  --url "https://datahacks-2025.devpost.com/"

# Try variations of the URL
python -m devpost_mcp.server scrape_hackathon_page \
  --url "https://datahacks.devpost.com/"
```

### Via Hermes

```
Scrape https://datahacks-2025.devpost.com/ and show me what you find
```

```
Find info on past UC San Diego datathon hackathon
```

### Browsing Past Project Galleries

```bash
# List all projects from a past hackathon
python -m devpost_mcp.server list_hackathon_projects \
  --hackathon_url "https://datahacks.devpost.com/" \
  --limit 10

# Only show winners
python -m devpost_mcp.server list_hackathon_projects \
  --hackathon_url "https://datahacks.devpost.com/" \
  --include_winners_only true

# Get details on a specific project
python -m devpost_mcp.server get_project_details \
  --project_url "https://devpost.com/software/project-name"
```

### Via Hermes

```
Show me projects from DataHacks hackathon
```

```
List the winning projects from https://datahacks.devpost.com/
```

```
Get details on https://devpost.com/software/that-cool-project
```

## Submitting Projects

```bash
# Dry run (test without actually submitting)
devpost-mcp submit_project \
  --hackathon_slug zervehack \
  --project_title "My AI Project" \
  --project_tagline "An amazing AI-powered app" \
  --dry_run

# Actually submit
devpost-mcp submit_project \
  --hackathon_slug zervehack \
  --project_title "Hermes Agent Devpost Integration" \
  --project_tagline "MCP server that lets AI agents browse and submit to hackathons" \
  --built_with '["Python", "MCP", "Playwright"]' \
  --links '{"github": "https://github.com/user/repo", "demo": "https://example.com"}'
```

Or via Hermes:
```
Submit my project "AI Code Assistant" to the zervehack hackathon. 
Tagline: "AI-powered coding assistant that actually works"
Built with: Python, FastAPI, OpenAI
GitHub: https://github.com/myusername/ai-code-assistant
```

## Granular Project Management

```bash
# List all your projects
python -m devpost_mcp.server list_my_submissions

# Get details about a specific project  
python -m devpost_mcp.server get_submission_details \
  --project_url "https://devpost.com/software/my-cool-project"

# Update just the tagline (patch-style - only changes what you specify)
python -m devpost_mcp.server update_submission \
  --project_url "https://devpost.com/software/my-cool-project" \
  --project_tagline "Updated tagline with more details"

# Update multiple fields
python -m devpost_mcp.server update_submission \
  --project_url "https://devpost.com/software/my-cool-project" \
  --project_title "New Project Name" \
  --links '{"github": "https://github.com/user/new-repo"}'

# Add team member
python -m devpost_mcp.server add_team_member \
  --project_url "https://devpost.com/software/my-cool-project" \
  --username "teammate_username"

# Upload screenshots
python -m devpost_mcp.server upload_screenshots \
  --project_url "https://devpost.com/software/my-cool-project" \
  --image_paths '["/path/to/screenshot1.png", "/path/to/screenshot2.jpg"]' \
  --set_main_image 0

# Delete project (permanent!)
python -m devpost_mcp.server delete_submission \
  --project_url "https://devpost.com/software/old-project" \
  --confirm true
```

### Via Hermes

```
List all my devpost submissions
```

```
Update my project at https://devpost.com/software/xyz with new tagline: "AI-powered dev tools"
```

```
Add user "alice_dev" to my project https://devpost.com/software/xyz
```

```
Upload /home/user/screenshot.png to my project https://devpost.com/software/xyz
```
