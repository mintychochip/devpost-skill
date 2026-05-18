# Workflow: Monitor Deadlines

**Goal:** Track hackathon deadlines and time-sensitive opportunities.

---

## Step 1: View All Deadlines

```bash
devpost deadlines --json
```

**Output shape:**

```json
[
  {
    "title": "AI Hackathon 2026",
    "url": "https://ai-hack-2026.devpost.com/",
    "prize_amount": "$50,000",
    "open_state": "open",
    "ends_at": "2 days left",
    "time_left_to_submission": "48 hours"
  },
  {
    "title": "Startup Challenge",
    "url": "https://startup-challenge.devpost.com/",
    "prize_amount": "$25,000",
    "open_state": "open",
    "ends_at": "5 days left",
    "time_left_to_submission": "120 hours"
  }
]
```

**Notes:**
- Sorted by soonest deadline first
- `ends_at` shows human-readable time remaining
- `time_left_to_submission` shows exact hours

---

## Step 2: Filter by Urgency

### Closing Today

```bash
devpost deadlines --today --json
```

**Output:**

```json
[
  {
    "title": "Flash Hackathon",
    "url": "https://flash-hack.devpost.com/",
    "prize_amount": "$5,000",
    "ends_at": "6 hours left"
  }
]
```

### Closing This Week

```bash
devpost deadlines --this-week --json
```

**Output:**

```json
[
  {
    "title": "AI Hackathon 2026",
    "url": "https://ai-hack-2026.devpost.com/",
    "prize_amount": "$50,000",
    "ends_at": "3 days left"
  }
]
```

---

## Step 3: Parse Days Left Programmatically

```bash
# Get deadlines and parse days left
devpost deadlines --json | jq -r '.[] | "\(.title): \(.ends_at)"'
```

**Example output:**

```
AI Hackathon 2026: 2 days left
Startup Challenge: 5 days left
Flash Hackathon: 6 hours left
```

### Time Pressure Interpretation

| Time Remaining | Action |
|----------------|--------|
| < 24 hours | Critical — submit ASAP or skip |
| 1-3 days | High — prioritize if interested |
| 4-7 days | Medium — time to build something solid |
| 7+ days | Low — comfortable timeline |

---

## Step 4: RSS Feed for New Hackathons

```bash
devpost rss --json
```

**Output shape:**

```json
{
  "success": true,
  "channel": "Devpost Hackathons",
  "count": 50,
  "items": [
    {
      "title": "AI Hackathon 2026",
      "url": "https://ai-hack-2026.devpost.com/",
      "prize_amount": "$50,000",
      "time_left_to_submission": "21 days"
    }
  ]
}
```

**Use case:** Monitor for newly announced hackathons.

---

## Step 5: Sort by Prize vs Deadline

```bash
# High prize, urgent deadline
devpost hackathons --state open --sort prize-amount --limit 20 --json | \
  jq '[.hackathons[] | select(.ends_at != null) | {title, prize_amount, ends_at}]'
```

**Output:**

```json
[
  {"title": "AI Hackathon 2026", "prize_amount": "$50,000", "ends_at": "2 days left"},
  {"title": "Startup Challenge", "prize_amount": "$25,000", "ends_at": "14 days left"}
]
```

---

## Step 6: Evaluate Urgent Opportunities

For hackathons closing soon, quickly evaluate:

```bash
# Get deadline hackathons
DEADLINES=$(devpost deadlines --this-week --json)

# For each, get slug and evaluate
echo "$DEADLINES" | jq -r '.[].url' | while read url; do
  SLUG=$(echo "$url" | sed 's|https://||; s|\.devpost.com/||')
  echo "Evaluating: $SLUG"
  devpost evaluate "$SLUG" --json | jq '{title: .basics.title, verdict, prize: .basics.prize, deadline: .basics.dates}'
done
```

**Sample output:**

```
Evaluating: ai-hack-2026
{
  "title": "AI Hackathon 2026",
  "verdict": "Enter",
  "prize": "$50,000",
  "deadline": "Feb 15, 2026"
}
```

---

## Decision Matrix

| Days Left | Prize | Competition | Verdict |
|-----------|-------|-------------|---------|
| < 1 day | Any | Any | Skip (unless已有 project) |
| 1-3 days | High ($10k+) | Low | Enter (fast build) |
| 1-3 days | Low | Any | Skip |
| 4-7 days | High | Low | Enter |
| 4-7 days | High | High | Maybe |
| 7+ days | Any | Any | Evaluate normally |

---

## Alert System (Agent Implementation)

Set up periodic checks:

```python
# Pseudocode for agent alert system
def check_deadlines():
    deadlines = run_command("devpost deadlines --this-week --json")
    
    for hack in deadlines:
        days_left = parse_days(hack['ends_at'])
        prize = parse_prize(hack['prize_amount'])
        
        # Alert conditions
        if days_left <= 3 and prize >= 10000:
            send_alert(f"🚨 {hack['title']}: ${prize} prize, {days_left} days left!")
        elif days_left <= 1:
            send_alert(f"⏰ {hack['title']}: Closing in {days_left} day!")
```

---

## Time Zone Considerations

Devpost deadlines are typically in **EST (Eastern Standard Time)**.

```bash
# Get hackathon details with exact deadline
devpost overview ai-hack-2026 --json | jq '.submission_period_dates'
```

**Output:**

```
"Jan 1 - Feb 15, 2026 11:59 PM EST"
```

**Convert to your timezone:**
- PST: Subtract 3 hours
- UTC: Add 5 hours
- IST: Add 10.5 hours

---

## Last-Minute Submission Strategy

If deadline is < 24 hours:

1. **Check if you have existing project** that fits theme
2. **Focus on presentation** over features
3. **Submit MVP** with clear value prop
4. **Polish post-submission** (updates allowed until deadline)

```bash
# Quick submission flow
devpost join ai-hack-2026
devpost submit project ai-hack-2026 \
  --title "Existing Project" \
  --tagline "Clear value proposition" \
  --github "https://github.com/user/existing-project" \
  --dry-run  # Verify first!
```

---

## Error Handling

| Error | Recovery |
|-------|----------|
| No hackathons found | No deadlines match filter; broaden search |
| `RATE_LIMITED` | Wait 60 seconds, retry |
| Deadline already passed | Hackathon closed; skip |

---

## Full Example (Agent Flow)

```bash
#!/bin/bash

# Daily deadline check script

# Get deadlines closing this week
DEADLINES=$(devpost deadlines --this-week --json)

# Count urgent deadlines
URGENT_COUNT=$(echo "$DEADLINES" | jq '[.[] | select(.ends_at | test("1 day|hours"))] | length')

if [ "$URGENT_COUNT" -gt 0 ]; then
  echo "🚨 $URGENT_COUNT hackathons closing soon!"
  echo "$DEADLINES" | jq -r '.[] | select(.ends_at | test("1 day|hours")) | "\(.title): \(.ends_at) - \(.prize_amount)"'
fi

# Evaluate top 3 by prize
echo "$DEADLINES" | jq -r '.[:3][] | .url' | while read url; do
  SLUG=$(echo "$url" | sed 's|https://||; s|\.devpost.com/||')
  VERDICT=$(devpost evaluate "$SLUG" --json 2>/dev/null | jq -r '.verdict')
  echo "$SLUG: $VERDICT"
done
```

---

## Related Workflows

- [`find-and-evaluate.md`](find-and-evaluate.md) — Evaluate hackathons
- [`submit-project.md`](submit-project.md) — Submit before deadline
