# Workflow: Find and Evaluate Hackathons

**Goal:** Discover open hackathons and evaluate whether they're worth entering.

---

## Step 1: List Open Hackathons

```bash
devpost hackathons --state open --sort prize-amount --limit 20 --json
```

**Output shape:**

```json
{
  "hackathons": [
    {
      "title": "AI Hackathon 2026",
      "url": "https://ai-hack-2026.devpost.com/",
      "open_state": "open",
      "prize_amount": "$50,000",
      "ends_at": "21 days left",
      "submissions_count": 120,
      "registrations_count": 890,
      "featured": true,
      "themes": [{"name": "Artificial Intelligence"}, {"name": "Machine Learning"}]
    }
  ],
  "meta": {"total_count": 156, "total_pages": 18}
}
```

**Decision logic:**
- Filter by `prize_amount` (parse `$XX,XXX` → integer)
- Check `ends_at` for time pressure
- Note `featured` hackathons (higher visibility)
- Extract `slug` from `url` (e.g., `ai-hack-2026` from `https://ai-hack-2026.devpost.com/`)

---

## Step 2: Get Detailed Overview

```bash
devpost overview ai-hack-2026 --json
```

**Output shape:**

```json
{
  "title": "AI Hackathon 2026",
  "url": "https://ai-hack-2026.devpost.com/",
  "open_state": "open",
  "featured": true,
  "prize_amount": "$50,000",
  "prizes_counts": {"cash": 15, "other": 5},
  "submissions_count": 120,
  "registrations_count": 890,
  "ends_at": "21 days left",
  "submission_period_dates": "Jan 1 - Feb 15, 2026",
  "invite_only": false,
  "organization_name": "TechCorp",
  "managed_by_devpost_badge": true,
  "themes": [{"name": "Artificial Intelligence"}, {"name": "Machine Learning"}],
  "submission_gallery_url": "https://ai-hack-2026.devpost.com/project-gallery",
  "tagline": "Build the next generation of AI-powered applications"
}
```

**Decision logic:**
- `invite_only: true` → skip (cannot join without invite)
- `managed_by_devpost_badge: true` → higher quality, better support
- High `registrations_count` vs low `submissions_count` → wide open opportunity

---

## Step 3: Evaluate Hackathon

```bash
devpost evaluate ai-hack-2026 --skills "Python,AI,GCP,React" --json
```

**Output shape:**

```json
{
  "success": true,
  "verdict": "Enter",
  "verdict_reason": "Favorable: high prize density, low competition, good skill/theme fit",
  "basics": {
    "title": "AI Hackathon 2026",
    "prize": "$50,000",
    "status": "open",
    "dates": "Jan 1 - Feb 15, 2026",
    "organization": "TechCorp",
    "themes": ["Artificial Intelligence", "Machine Learning"]
  },
  "competition": {
    "registrants": 890,
    "submissions": 120,
    "prize_per_project": 3333,
    "registrants_per_prize": 59
  },
  "signals": {
    "time_pressure": {"level": "low", "days_left": 21, "detail": "21 days left"},
    "prize_density": {"level": "high", "per_project": 3333, "detail": "$3,333 per project — very high"},
    "competition_density": {"level": "low", "registrants_per_prize": 59, "detail": "59 registrants per prize — less crowded"},
    "submission_gap": {"level": "wide_open", "detail": "Only 120 submissions from 890 registrants (13%)"},
    "theme_fit": {"level": "high", "matched_skills": ["AI", "Python"], "detail": "Your skills match: AI, Python"}
  },
  "eligibility": ["Open to all ages", "Individuals and teams allowed"],
  "requirements": ["Must use cloud platform", "Project must be original"],
  "judging_criteria": ["Innovation", "Technical complexity", "Presentation"],
  "sponsor_apis": ["Google Cloud API", "OpenAI API", "Anthropic API"],
  "prize_categories": ["1st Place: $25,000", "2nd Place: $15,000", "3rd Place: $10,000"],
  "key_dates": [{"name": "Submission Deadline", "date": "Feb 15, 2026"}]
}
```

**Verdict interpretation:**

| Verdict | Action |
|---------|--------|
| `Enter` | Proceed to submission workflow |
| `Maybe` | Review `signals` manually; check rules/competition |
| `Skip` | Look for other hackathons |

**Signal levels:**

| Signal | Levels | Meaning |
|--------|--------|---------|
| `time_pressure` | `critical`, `high`, `medium`, `low`, `unknown`, `closed` | Days until deadline |
| `prize_density` | `high`, `medium`, `low`, `none` | $ per project |
| `competition_density` | `high`, `medium`, `low` | Registrants per prize |
| `submission_gap` | `wide_open`, `moderate`, `filling`, `unknown`, `closed` | Submission rate |
| `theme_fit` | `high`, `low`, `unknown` | Skill/theme match |

---

## Step 4: Review Rules (if needed)

```bash
devpost rules ai-hack-2026 --json
```

**Output shape:**

```json
{
  "success": true,
  "hackathon_slug": "ai-hack-2026",
  "eligibility": ["Open to all ages", "Individuals and teams allowed", "No professional developers"],
  "requirements": ["Must use Google Cloud Platform", "Project must be original work", "Code must be open source"],
  "judging_criteria": ["Innovation (30%)", "Technical complexity (30%)", "Presentation (20%)", "Theme fit (20%)"],
  "sponsor_apis": ["Google Cloud API required", "OpenAI API recommended"],
  "key_dates": [{"name": "Submission Deadline", "date": "Feb 15, 2026 11:59 PM EST"}],
  "prize_categories": ["1st Place: $25,000", "2nd Place: $15,000", "3rd Place: $10,000", "Best Use of GCP: $5,000"]
}
```

**Check for blockers:**
- Eligibility restrictions (age, location, professional status)
- Required technologies you don't have
- Submission format requirements

---

## Step 5: Join Hackathon

```bash
devpost join ai-hack-2026
```

**Output:**

```
Successfully joined!
hackathon: ai-hack-2026
```

**Note:** Requires authentication (`DEVPOST_EMAIL` + `DEVPOST_PASSWORD` env vars or `devpost auth login`).

---

## Error Handling

| Error | Recovery |
|-------|----------|
| `NOT_FOUND` | Verify slug; try `devpost hackathons --query "name"` to find correct slug |
| `ACCESS_DENIED` | Hackathon is invite-only; skip |
| `RATE_LIMITED` | Wait 60 seconds, retry |
| `DEPENDENCY_MISSING` | Run `playwright install chromium` |

---

## Full Example (Agent Flow)

```bash
# Step 1: Find high-prize open hackathons
HACKATHONS=$(devpost hackathons --state open --sort prize-amount --limit 10 --json)

# Step 2: Parse and pick top candidate
SLUG=$(echo "$HACKATHONS" | jq -r '.hackathons[0].url' | sed 's|https://||; s|\.devpost\.com/||')

# Step 3: Evaluate
EVAL=$(devpost evaluate "$SLUG" --skills "Python,AI,GCP" --json)

# Step 4: Check verdict
VERDICT=$(echo "$EVAL" | jq -r '.verdict')

if [ "$VERDICT" = "Enter" ]; then
  echo "Proceeding to submission..."
  devpost join "$SLUG"
elif [ "$VERDICT" = "Maybe" ]; then
  echo "Reviewing rules..."
  devpost rules "$SLUG" --json | jq '.eligibility, .requirements'
else
  echo "Skipping; looking for next hackathon..."
fi
```

---

## Related Workflows

- [`scout-competition.md`](scout-competition.md) — Analyze existing projects before building
- [`submit-project.md`](submit-project.md) — Submit your project
- [`monitor-deadlines.md`](monitor-deadlines.md) — Track closing hackathons
