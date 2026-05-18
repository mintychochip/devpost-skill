# Devpost CLI

CLI for Devpost hackathons.

## Install

```bash
curl -sSL https://raw.githubusercontent.com/mintychochip/devpost-skill/main/install.sh | bash
```

Windows:

```powershell
iwr https://raw.githubusercontent.com/mintychochip/devpost-skill/main/install.ps1 -UseBasicParsing | iex
```

## Usage

```bash
devpost hackathons                    # Browse
devpost search "AI"                   # Search
devpost submit rapid-agent -t "Project" --tagline "Tagline"  # Submit
devpost my-submissions                # List yours
```

## Commands

| Command | Description |
|---------|-------------|
| `hackathons` | Browse hackathons |
| `overview <slug>` | Get details |
| `search <query>` | Search projects |
| `gallery <slug>` | List projects |
| `get <slug> -t <type>` | Get winners, rules, etc |
| `user <username>` | User profile |
| `evaluate <slug>` | Evaluate hackathon |
| `submit <slug>` | Submit project |
| `team create <slug>` | Create team |
| `my-submissions` | Your projects |

## Auth

```bash
devpost auth login
```

Or: `DEVPOST_EMAIL`, `DEVPOST_PASSWORD` env vars.

## Flags

```bash
--headed          # Visible browser
--verbose         # Debug logs
--debug-screenshots  # Save error screenshots
```
