# Devpost CLI

Browse, scout, and manage hackathons on Devpost from the command line.

## Install

```bash
cd devpost-mcp
pip install -e .
```

## Usage

### Browse Hackathons

```bash
# List open hackathons
devpost list

# List closed hackathons (for scouting past events)
devpost list --state closed

# Search for AI hackathons
devpost search "AI"

# Sort by prize amount
devpost list --sort prize-amount
```

### Deep Scrape (Works for Past Hackathons)

```bash
# Scrape any hackathon by URL - works even for closed events
devpost scrape https://datahacks-2025.devpost.com/

# Save to JSON
devpost scrape https://datahacks-2025.devpost.com/ --json

# Save to file
devpost scrape https://datahacks-2025.devpost.com/ -o datahacks.json
```

### Get Hackathon Info

```bash
# By slug (the part before .devpost.com)
devpost info zervehack
devpost info datahacks-2025

# Output as JSON
devpost info datahacks-2025 --json
```

### Browse Projects

```bash
# List projects from a hackathon
devpost projects https://datahacks-2025.devpost.com/

# Only show winners
devpost projects https://datahacks-2025.devpost.com/ --winners

# Get more projects
devpost projects https://datahacks-2025.devpost.com/ --limit 50

# Export as JSON
devpost projects https://datahacks-2025.devpost.com/ --json
```

### Get Project Details

```bash
# Deep dive into a specific project
devpost project https://devpost.com/software/onlydance

# Export as JSON
devpost project https://devpost.com/software/onlydance --json
```

## Use Cases

### Competition Scouting

```bash
# Find last year's winners
devpost list --state closed --sort submission-deadline | head -20
devpost scrape https://datahacks-2025.devpost.com/ --winners
devpost projects https://datahacks-2025.devpost.com/ --winners --limit 10
```

### Track Analysis

```bash
# Get all projects from a specific hackathon
devpost projects https://some-hackathon.devpost.com/ --json > projects.json

# Analyze with jq
cat projects.json | jq '.[] | select(.is_winner)' | jq -s 'length'
```

### Prize Comparison

```bash
# Find hackathons with big prizes
devpost list --sort prize-amount --limit 20
```

## Authentication (for Submissions)

Not yet implemented. For now, this is read-only scouting.

```bash
# Check auth status
devpost auth status
```

## Examples

### Scout DataHacks 2025

```bash
# Get hackathon overview
devpost scrape https://datahacks-2025.devpost.com/

# List all projects
devpost projects https://datahacks-2025.devpost.com/ --limit 50

# Deep dive on a winner
devpost project https://devpost.com/software/onlydance
```

### Find Upcoming AI Hackathons

```bash
devpost search "AI" --limit 20
devpost list --state upcoming --query "machine learning"
```

### Export Data for Analysis

```bash
# Get all projects as JSON
devpost projects https://datahacks-2025.devpost.com/ --limit 100 --json > datahacks.json

# Get hackathon metadata
devpost scrape https://datahacks-2025.devpost.com/ --json > datahacks_meta.json
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `devpost list` | List hackathons |
| `devpost info <slug>` | Get hackathon by slug |
| `devpost scrape <url>` | Deep scrape hackathon page |
| `devpost projects <url>` | List projects from gallery |
| `devpost project <url>` | Get project details |
| `devpost search <query>` | Search hackathons |
| `devpost auth status` | Check authentication |

## Global Options

- `--json` - Output as JSON instead of pretty tables
- `--output, -o <path>` - Save to file

## License

MIT
