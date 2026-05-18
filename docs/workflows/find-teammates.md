# Workflow: Find Teammates

**Goal:** Discover and evaluate potential teammates from hackathon participants and Devpost users.

---

## Step 1: List Hackathon Participants

```bash
devpost participants ai-hack-2026 --limit 100 --json
```

**Output shape:**

```json
{
  "success": true,
  "hackathon_slug": "ai-hack-2026",
  "participants": [
    {
      "username": "alice-dev",
      "name": "Alice Chen",
      "url": "https://devpost.com/users/alice-dev"
    },
    {
      "username": "bob-ml",
      "name": "Bob Smith",
      "url": "https://devpost.com/users/bob-ml"
    }
  ],
  "count": 100
}
```

**Analysis points:**
- Total participants (`count` field)
- Extract usernames for profile lookup

---

## Step 2: Search Users by Skill

```bash
devpost search-users "python" --limit 20 --json
```

**Output shape:**

```json
[
  {
    "username": "alice-dev",
    "name": "Alice Chen",
    "url": "https://devpost.com/users/alice-dev"
  },
  {
    "username": "pythonista",
    "name": "Python Developer",
    "url": "https://devpost.com/users/pythonista"
  }
]
```

**Note:** Searches usernames and names from hackathon participant lists.

---

## Step 3: Get Full User Profile

```bash
devpost user alice-dev --json
```

**Output shape:**

```json
{
  "success": true,
  "data": {
    "name": "Alice Chen",
    "username": "alice-dev",
    "bio": "Full-stack developer passionate about AI/ML",
    "location": "San Francisco, CA",
    "skills": ["Python", "React", "TensorFlow", "AWS", "Docker"],
    "links": {
      "github": "https://github.com/alice-dev",
      "twitter": "https://twitter.com/alice_dev",
      "linkedin": "https://linkedin.com/in/alicechen",
      "website": "https://alice.dev"
    },
    "projects": [
      {
        "title": "AI Code Reviewer",
        "url": "https://devpost.com/software/ai-code-reviewer",
        "hackathon": "AI Hackathon 2026",
        "stats": "👍 45  👁 1.2k"
      }
    ],
    "project_count": 8,
    "hackathons": [
      {"name": "AI Hackathon 2026", "url": "https://ai-hack-2026.devpost.com/"},
      {"name": "Startup Challenge", "url": "https://startup-challenge.devpost.com/"}
    ],
    "hackathon_count": 5,
    "achievements": [
      {"title": "1st Place Winner", "description": "AI Hackathon 2025", "earned": "Jan 2025", "badge_url": "..."}
    ],
    "achievement_count": 3,
    "followers": [...],
    "follower_count": 150,
    "following": [...],
    "following_count": 80,
    "likes": [...],
    "like_count": 45
  }
}
```

**Evaluation criteria:**

| Field | What to look for |
|-------|------------------|
| `skills` | Match with your tech stack needs |
| `project_count` | Experience level (3+ = active) |
| `hackathon_count` | Hackathon experience (2+ = familiar) |
| `achievement_count` | Track record (winners have achievements) |
| `bio` | Interests alignment |
| `location` | Timezone compatibility |
| `links.github` | Check code quality separately |

---

## Step 4: Check User's Projects

From the profile, examine their projects:

```bash
devpost project https://devpost.com/software/ai-code-reviewer --json
```

**Look for:**
- Code quality (GitHub link)
- Role in team (solo vs team member)
- Tech stack used
- Project completeness

---

## Step 5: Check User's Hackathon History

From the profile, see which hackathons they've joined:

```bash
# Extract hackathons from user profile
USER_DATA=$(devpost alice-dev --json)
echo "$USER_DATA" | jq '.data.hackathons'
```

**Look for:**
- Repeated participation (shows commitment)
- Similar hackathon types (domain expertise)
- Recent activity (active vs inactive)

---

## Step 6: Search Multiple Candidates

Batch search for candidates with specific skills:

```bash
# Search for React developers
devpost search-users "react" --limit 10 --json > react-devs.json

# Search for ML engineers
devpost search-users "machine learning" --limit 10 --json > ml-engs.json

# Search for designers
devpost search-users "design" --limit 10 --json > designers.json
```

---

## Step 7: Evaluate Candidate Fit

Create a scoring system:

```python
# Example scoring logic
def score_candidate(user_data, needed_skills):
    score = 0
    
    # Skill match (0-5 points)
    user_skills = set(s.lower() for s in user_data.get('skills', []))
    needed = set(s.lower() for s in needed_skills)
    matched = len(user_skills & needed)
    score += min(matched * 2, 10)
    
    # Experience (0-3 points)
    project_count = user_data.get('project_count', 0)
    if project_count >= 5:
        score += 3
    elif project_count >= 2:
        score += 2
    elif project_count >= 1:
        score += 1
    
    # Hackathon experience (0-3 points)
    hackathon_count = user_data.get('hackathon_count', 0)
    if hackathon_count >= 3:
        score += 3
    elif hackathon_count >= 1:
        score += 1
    
    # Achievements (0-4 points)
    achievement_count = user_data.get('achievement_count', 0)
    if achievement_count >= 3:
        score += 4
    elif achievement_count >= 1:
        score += 2
    
    return score
```

---

## Team Composition Guide

### Ideal Team Roles

| Role | Skills to look for |
|------|-------------------|
| Backend | Python, Node.js, APIs, Databases |
| Frontend | React, TypeScript, CSS, UX |
| ML/AI | TensorFlow, PyTorch, OpenAI API |
| DevOps | Docker, AWS, CI/CD |
| Designer | Figma, UI/UX, Prototyping |

### Team Size Recommendations

| Hackathon Duration | Ideal Team Size |
|-------------------|-----------------|
| 24-48 hours | 2-3 people |
| 1 week | 3-4 people |
| 2+ weeks | 4-5 people |

---

## Outreach Template

When contacting potential teammates:

```
Hi [username]! I saw your profile on Devpost and was impressed by your work on [project]. 

I'm building a [project type] for [hackathon] using [tech stack]. Your experience with [their skill] would be a great fit.

Would you be interested in collaborating? I can share more details about the project idea.

Thanks!
[your name]
```

---

## Error Handling

| Error | Recovery |
|-------|----------|
| `NOT_FOUND` | User doesn't exist or profile is private |
| `DEPENDENCY_MISSING` | Run `playwright install chromium` |
| No participants found | Hackathon may not have public participant list |

---

## Full Example (Agent Flow)

```bash
# Step 1: Get participants from target hackathon
PARTICIPANTS=$(devpost participants ai-hack-2026 --limit 50 --json)

# Step 2: Extract usernames
USERNAMES=$(echo "$PARTICIPANTS" | jq -r '.participants[].username')

# Step 3: Search for Python developers
PYTHON_DEVS=$(devpost search-users "python" --limit 10 --json)

# Step 4: Get full profile for top candidate
TOP_USER=$(echo "$PYTHON_DEVS" | jq -r '.[0].username')
PROFILE=$(devpost user "$TOP_USER" --json)

# Step 5: Evaluate fit
SKILLS=$(echo "$PROFILE" | jq -r '.data.skills[]')
PROJECTS=$(echo "$PROFILE" | jq '.data.project_count')
ACHIEVEMENTS=$(echo "$PROFILE" | jq '.data.achievement_count')

echo "Candidate: $TOP_USER"
echo "Skills: $SKILLS"
echo "Projects: $PROJECTS"
echo "Achievements: $ACHIEVEMENTS"

# Step 6: Score (simple heuristic)
SCORE=$((PROJECTS * 2 + ACHIEVEMENTS * 3))
echo "Fit score: $SCORE"
```

---

## Privacy Notes

- Some users may have private profiles
- Not all hackathons expose participant lists
- Respect userER privacy; don't spam outreach

---

## Related Workflows

- [`scout-competition.md`](scout-competition.md) — Analyze projects before building
- [`submit-project.md`](submit-project.md) — Submit with your team
