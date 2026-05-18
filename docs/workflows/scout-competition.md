# Workflow: Scout Competition

**Goal:** Analyze existing projects, tech stacks, and winning entries to understand competition landscape.

---

## Step 1: Browse Project Gallery

```bash
devpost gallery ai-hack-2026 --limit 50 --json
```

**Output shape:**

```json
{
  "success": true,
  "hackathon_url": "https://ai-hack-2026.devpost.com/",
  "hackathon_title": "AI Hackathon 2026",
  "projects": [
    {
      "title": "AI Code Reviewer",
      "url": "https://devpost.com/software/ai-code-reviewer",
      "tagline": "Automated code review using LLMs",
      "is_winner": false,
      "built_with": ["Python", "OpenAI API", "GitHub API"]
    }
  ],
  "count": 50
}
```

**Analysis points:**
- Count total projects (`count` field)
- Note common tech stacks (`built_with` arrays)
- Identify project types from titles/taglines

---

## Step 2: View Winning Projects

```bash
devpost gallery ai-hack-2026 --winners --json
```

**Output shape:**

```json
{
  "success": true,
  "projects": [
    {
      "title": "MediBot AI",
      "url": "https://devpost.com/software/medibot-ai",
      "tagline": "Healthcare chatbot with diagnostic assistance",
      "is_winner": true,
      "prize": "1st Place - $25,000",
      "built_with": ["React", "Python", "TensorFlow", "AWS"]
    },
    {
      "title": "CodeAssist Pro",
      "url": "https://devpost.com/software/codeassist-pro",
      "tagline": "AI pair programmer for enterprise",
      "is_winner": true,
      "prize": "2nd Place - $15,000",
      "built_with": ["TypeScript", "OpenAI API", "Docker"]
    }
  ],
  "count": 3
}
```

**Analysis points:**
- What themes win? (healthcare, productivity, etc.)
- What tech stacks are common among winners?
- Prize distribution (how many winning categories?)

---

## Step 3: Deep-Dive Specific Project

```bash
devpost project https://devpost.com/software/medibot-ai --json
```

**Output shape:**

```json
{
  "success": true,
  "url": "https://devpost.com/software/medibot-ai",
  "data": {
    "title": "MediBot AI",
    "tagline": "Healthcare chatbot with diagnostic assistance",
    "description": "MediBot AI is a healthcare chatbot that uses advanced LLMs...",
    "built_with": ["React", "Python", "TensorFlow", "AWS"],
    "links": {
      "github": "https://github.com/user/medibot-ai",
      "demo": "https://medibot.example.com",
      "video": "https://youtube.com/watch?v=..."
    },
    "team": [
      {"username": "alice-dev", "name": "Alice Chen"},
      {"username": "bob-ml", "name": "Bob Smith"}
    ],
    "screenshots": ["https://..."],
    "hackathon": {"name": "AI Hackathon 2026", "url": "https://ai-hack-2026.devpost.com/"},
    "is_winner": true,
    "prize": "1st Place - $25,000"
  }
}
```

**Analysis points:**
- Team size (solo vs team)
- Tech stack depth
- Presentation quality (screenshots, video, demo)
- GitHub activity (check repo separately)

---

## Step 4: Search Projects by Keyword

```bash
devpost search "chatbot" --in ai-hack-2026 --json
```

**Output shape:**

```json
{
  "success": true,
  "hackathon_slug": "ai-hack-2026",
  "total_matches": 12,
  "matches": {
    "projects": [
      {
        "title": "MediBot AI",
        "tagline": "Healthcare chatbot with diagnostic assistance",
        "url": "https://devpost.com/software/medibot-ai",
        "is_winner": true,
        "matched_in": ["title", "tagline"]
      }
    ],
    "description": [
      {"snippet": "...our chatbot uses advanced NLP..."}
    ],
    "rules": []
  }
}
```

**Analysis points:**
- How many similar projects exist?
- What's the quality bar?
- Any gaps in the market?

---

## Step 5: Search by Tech Stack

```bash
devpost search "OpenAI" --in ai-hack-2026 --tech --json
```

**Output shape:**

```json
{
  "success": true,
  "hackathon_slug": "ai-hack-2026",
  "total_matches": 45,
  "matches": {
    "projects": [
      {
        "title": "AI Code Reviewer",
        "tagline": "Automated code review using LLMs",
        "url": "https://devpost.com/software/ai-code-reviewer",
        "is_winner": false,
        "built_with": ["Python", "OpenAI API", "GitHub API"],
        "matched_in": ["tech_stack"]
      }
    ]
  }
}
```

**Analysis points:**
- How saturated is this tech stack?
- What unique angles exist?

---

## Step 6: Cross-Hackathon Search

Search for similar projects across ALL open hackathons:

```bash
devpost search "chatbot" --across --limit 30 --json
```

**Output shape:**

```json
[
  {
    "title": "MediBot AI",
    "tagline": "Healthcare chatbot with diagnostic assistance",
    "url": "https://devpost.com/software/medibot-ai",
    "is_winner": true,
    "built_with": ["React", "Python", "TensorFlow", "AWS"],
    "hackathon": {"name": "AI Hackathon 2026", "url": "https://ai-hack-2026.devpost.com/"}
  },
  {
    "title": "CustomerBot",
    "tagline": "Customer support automation",
    "url": "https://devpost.com/software/customerbot",
    "is_winner": false,
    "built_with": ["Node.js", "Dialogflow"],
    "hackathon": {"name": "Startup Challenge", "url": "https://startup-challenge.devpost.com/"}
  }
]
```

**Analysis points:**
- Is this idea overdone across multiple hackathons?
- What hackathons have similar projects?

---

## Step 7: Trending Technologies

```bash
devpost trending --json
```

**Output shape:**

```json
{
  "success": true,
  "technologies": [
    "OpenAI API",
    "React",
    "Python",
    "Node.js",
    "TensorFlow",
    "AWS",
    "Docker",
    "MongoDB"
  ]
}
```

**Analysis points:**
- What's popular right now?
- Should you use trending tech or differentiate?

---

## Step 8: Projects by Tech Stack

```bash
devpost projects built-with "OpenAI API" --sort trending --limit 20 --json
```

**Output shape:**

```json
[
  {
    "title": "AI Code Reviewer",
    "tagline": "Automated code review using LLMs",
    "url": "https://devpost.com/software/ai-code-reviewer",
    "built_with": ["Python", "OpenAI API", "GitHub API"]
  }
]
```

**Analysis points:**
- See all projects using a specific technology
- Identify saturation level

---

## Decision Framework

### Market Saturation

| Similar Projects | Recommendation |
|------------------|----------------|
| 0-5 | Green light — unique idea |
| 6-15 | Yellow light — need differentiation |
| 16+ | Red light — consider pivot |

### Tech Stack Analysis

| Stack Pattern | Recommendation |
|---------------|----------------|
| All winners use X | Consider using X |
| No winners use X | Avoid X (or innovate with it) |
| Your stack is unique | Highlight as differentiator |

### Presentation Quality

Check winning projects for:
- Number of screenshots (more = better presentation)
- Video presence (winners often have demo videos)
- Live demo availability
- GitHub repo quality (stars, commits, README)

---

## Error Handling

| Error | Recovery |
|-------|----------|
| `NOT_FOUND` | Verify hackathon slug or project URL |
| `DEPENDENCY_MISSING` | Run `playwright install chromium` |
| No projects found | Hackathon may have no submissions yet; check back later |

---

## Full Example (Agent Flow)

```bash
# Step 1: Get all projects from hackathon
PROJECTS=$(devpost gallery ai-hack-2026 --limit 100 --json)

# Step 2: Count and analyze
TOTAL=$(echo "$PROJECTS" | jq '.count')
echo "Total projects: $TOTAL"

# Step 3: Extract tech stacks
TECHS=$(echo "$PROJECTS" | jq -r '.projects[].built_with[]' | sort | uniq -c | sort -rn | head -10)
echo "Top tech stacks:"
echo "$TECHS"

# Step 4: Get winners
WINNERS=$(devpost gallery ai-hack-2026 --winners --json)
echo "Winning projects:"
echo "$WINNERS" | jq -r '.projects[] | "\(.title) - \(.prize)"'

# Step 5: Deep-dive top winner
TOP_WINNER=$(echo "$WINNERS" | jq -r '.projects[0].url')
devpost project "$TOP_WINNER" --json | jq '.data.built_with, .data.team, .data.description'
```

---

## Related Workflows

- [`find-and-evaluate.md`](find-and-evaluate.md) — Evaluate hackathons before entering
- [`find-teammates.md`](find-teammates.md) — Find collaborators based on skills
- [`submit-project.md`](submit-project.md) — Submit your project
