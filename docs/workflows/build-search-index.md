# Workflow: Build Search Index

**Goal:** Create a local full-text search index for fast offline queries across hackathons, projects, and users.

---

## Overview

The local search index provides:
- **Instant search** — No API calls, results in milliseconds
- **Offline access** — Search cached data without internet
- **Full-text search** — Search titles, descriptions, tech stacks, skills
- **Multi-type** — Search hackathons, projects, and users simultaneously

---

## Step 1: Build Index (Hackathons Only)

```bash
devpost index build
```

**Output:**

```
Building search index...
Fetching hackathons...
Indexed 156 hackathons

Index stats:
  hackathons: 156
  projects: 0
  users: 0
```

**What it does:**
- Fetches all open hackathons via API
- Extracts text fields (title, tagline, description, themes, org)
- Builds inverted index for full-text search
- Saves to `~/.devpost/index/search_index.json`

---

## Step 2: Build Index (With Projects)

```bash
devpost index build --projects --limit 500
```

**Output:**

```
Building search index...
Fetching hackathons...
Indexed 156 hackathons
Fetching projects from open hackathons...
Indexed 342 projects

Index stats:
  hackathons: 156
  projects: 342
  users: 0
```

**Notes:**
- `--projects` also indexes projects from open hackathons
- `--limit` controls max items to index
- Takes longer (fetches project galleries)

---

## Step 3: Search Index (All Types)

```bash
devpost index search "AI" --json
```

**Output shape:**

```json
{
  "hackathons": [
    {
      "slug": "ai-hack-2026",
      "title": "AI Hackathon 2026",
      "url": "https://ai-hack-2026.devpost.com/",
      "tagline": "Build the next generation of AI applications",
      "prize_amount": "$50,000",
      "open_state": "open"
    }
  ],
  "projects": [
    {
      "project_id": "abc123",
      "title": "AI Code Reviewer",
      "url": "https://devpost.com/software/ai-code-reviewer",
      "tagline": "Automated code review using LLMs",
      "built_with": ["Python", "OpenAI API"],
      "is_winner": false,
      "hackathon_slug": "ai-hack-2026"
    }
  ],
  "users": []
}
```

**Notes:**
- Searches hackathons, projects, and users
- Results scored by relevance (word match count)
- Returns up to 20 results per type

---

## Step 4: Search Index (Specific Type)

### Hackathons Only

```bash
devpost index search "machine learning" -t hackathons --json
```

### Projects Only

```bash
devpost index search "chatbot" -t projects --json
```

### Users Only

```bash
devpost index search "python" -t users --json
```

---

## Step 5: Search with Filters

```bash
# Search projects, winners only
devpost index search "AI" -t projects --json | \
  jq '[.projects[] | select(.is_winner == true)]'

# Search projects by tech stack
devpost index search "AI" -t projects --json | \
  jq '[.projects[] | select(.built_with | any(. == "Python"))]'

# Search hackathons, open only
devpost index search "hackathon" -t hackathons --json | \
  jq '[.hackathons[] | select(.open_state == "open")]'
```

---

## Step 6: View Index Stats

```bash
devpost index stats
```

**Output:**

```
Index Statistics:
  hackathons: 156
  projects: 342
  users: 0
  created: 2026-01-15T10:30:00+00:00
  updated: 2026-01-18T14:22:00+00:00
```

---

## Step 7: Rebuild Index

When to rebuild:
- New hackathons announced
- Want fresher project data
- Index corruption (rare)

```bash
# Clear and rebuild
devpost index clear --confirm
devpost index build --projects --limit 500
```

---

## Index Structure

The index is stored at `~/.devpost/index/search_index.json`:

```json
{
  "hackathons": {
    "ai-hack-2026": {
      "slug": "ai-hack-2026",
      "title": "AI Hackathon 2026",
      "url": "https://ai-hack-2026.devpost.com/",
      "tagline": "...",
      "prize_amount": "$50,000",
      "open_state": "open",
      "search_words": ["ai", "hackathon", "2026", "build", "generation", ...],
      "indexed_at": "2026-01-15T10:30:00+00:00"
    }
  },
  "projects": {
    "abc123": {
      "project_id": "abc123",
      "title": "AI Code Reviewer",
      "url": "https://devpost.com/software/ai-code-reviewer",
      "tagline": "...",
      "built_with": ["Python", "OpenAI API"],
      "is_winner": false,
      "hackathon_slug": "ai-hack-2026",
      "search_words": ["ai", "code", "reviewer", "automated", "llm", ...],
      "indexed_at": "2026-01-15T10:30:00+00:00"
    }
  },
  "users": {...},
  "metadata": {
    "created_at": "...",
    "updated_at": "...",
    "hackathon_count": 156,
    "project_count": 342,
    "user_count": 0
  }
}
```

---

## Search Algorithm

The index uses **bag-of-words** matching:

1. Query is normalized (lowercase, punctuation removed)
2. Query words are matched against `search_words` in index
3. Results scored by word match count
4. Results sorted by score (descending)

**Word extraction rules:**
- Words must be ≥2 characters (allows "AI", "ML", "VR")
- Punctuation removed
- Lowercase normalization
- Duplicate words removed

---

## Performance Comparison

| Method | Speed | Accuracy | Offline |
|--------|-------|----------|---------|
| `devpost index search` | ~10ms | Good (cached) | ✅ |
| `devpost search` (HTTP) | ~2s | Best (live) | ❌ |
| `devpost search --playwright` | ~10s | Best (WAF bypass) | ❌ |

**Recommendation:**
- Use index for exploration/prototyping
- Use live search for final verification

---

## Use Cases

### 1. Rapid Prototyping

```bash
# Quickly test search queries
devpost index search "chatbot" -t projects

# Refine query based on results
devpost index search "healthcare chatbot" -t projects
```

### 2. Batch Analysis

```bash
# Find all AI-related hackathons
devpost index search "AI" -t hackathons --json | \
  jq '.hackathons[] | {title, prize: .prize_amount, deadline: .ends_at}'
```

### 3. Tech Stack Analysis

```bash
# Find all projects using Python
devpost index search "python" -t projects --json | \
  jq '[.projects[].built_with] | flatten | group_by(.) | map({tech: .[0], count: length}) | sort_by(-.count)'
```

### 4. User Discovery

```bash
# Find users with ML skills
devpost index search "machine learning" -t users --json | \
  jq '.users[] | {username, skills: .skills}'
```

---

## Error Handling

| Error | Recovery |
|-------|----------|
| `Index not found` | Run `devpost index build` first |
| No results found | Try broader query or different keywords |
| Empty index | Rebuild with `devpost index build --projects` |

---

## Full Example (Agent Flow)

```bash
#!/bin/bash

# Build index if not exists
if ! devpost index stats >/dev/null 2>&1; then
  echo "Building index..."
  devpost index build --projects --limit 300
fi

# Search for AI hackathons
echo "=== AI Hackathons ==="
devpost index search "AI" -t hackathons --json | \
  jq -r '.hackathons[] | "\(.title): \(.prize_amount) (\(.open_state))"'

# Search for AI projects
echo "=== AI Projects ==="
devpost index search "AI" -t projects --json | \
  jq -r '.projects[] | "\(.title) [\(.hackathon_slug)]"'

# Find Python projects that are winners
echo "=== Winning Python Projects ==="
devpost index search "python" -t projects --json | \
  jq -r '.projects[] | select(.is_winner == true) | "\(.title) - \(.tagline)"'
```

---

## Cache vs Index

| Feature | HTTP Cache | Search Index |
|---------|------------|--------------|
| Location | `~/.devpost/cache/` | `~/.devpost/index/` |
| Format | Individual JSON files | Single inverted index |
| Query | Exact match only | Full-text search |
| Speed | Fast (disk read) | Faster (in-memory) |
| Cross-type | No | Yes (hackathons + projects + users) |

**Recommendation:** Use both — cache for API calls, index for search.

---

## Related Workflows

- [`find-and-evaluate.md`](find-and-evaluate.md) — Evaluate hackathons
- [`scout-competition.md`](scout-competition.md) — Analyze projects
