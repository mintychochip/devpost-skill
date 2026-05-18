# Workflow: Submit Project

**Goal:** End-to-end project submission flow, from joining hackathon to uploading screenshots.

---

## Prerequisites

### Authentication Setup

**Option 1: Environment variables (recommended for agents)**

```bash
export DEVPOST_EMAIL="your@email.com"
export DEVPOST_PASSWORD="your_password"
```

**Option 2: Interactive login**

```bash
devpost auth login
```

---

## Step 1: Join Hackathon

```bash
devpost join ai-hack-2026
```

**Output:**

```
Successfully joined!
hackathon: ai-hack-2026
```

**Note:** Must be joined before submitting.

---

## Step 2: Prepare Project Details

Gather required information:

| Field | Required | Max Length | Notes |
|-------|----------|------------|-------|
| `title` | Yes | 60 chars | Clear, descriptive |
| `tagline` | Yes | 140 chars | One-sentence pitch |
| `description` | No | 10,000 chars | Markdown supported |
| `built_with` | No | - | Comma-separated tech list |
| `github` | No | - | Repository URL |
| `demo` | No | - | Live demo URL |
| `video` | No | - | YouTube/Vimeo URL |

---

## Step 3: Dry Run Submission

**Always test with `--dry-run` first!**

```bash
devpost submit project ai-hack-2026 \
  --title "AI Code Reviewer" \
  --tagline "Automated code review using LLMs" \
  --description "Our project uses GPT-4 to analyze code..." \
  --built-with "Python,OpenAI API,GitHub API,FastAPI" \
  --github "https://github.com/user/ai-code-reviewer" \
  --demo "https://ai-code-reviewer.example.com" \
  --dry-run
```

**Output:**

```
DRY RUN
hackathon: ai-hack-2026
title: AI Code Reviewer
tagline: Automated code review using LLMs
```

**Check:**
- Title/tagline formatting
- Tech stack spelling
- URL validity

---

## Step 4: Actual Submission

```bash
devpost submit project ai-hack-2026 \
  --title "AI Code Reviewer" \
  --tagline "Automated code review using LLMs" \
  --description "Our project uses GPT-4 to analyze code..." \
  --built-with "Python,OpenAI API,GitHub API,FastAPI" \
  --github "https://github.com/user/ai-code-reviewer" \
  --demo "https://ai-code-reviewer.example.com"
```

**Output:**

```
Successfully submitted!
url: https://devpost.com/software/ai-code-reviewer
title: AI Code Reviewer
```

**Save the project URL for后续 steps.**

---

## Step 5: Upload Screenshots

```bash
devpost upload https://devpost.com/software/ai-code-reviewer \
  screenshot1.png screenshot2.png screenshot3.png \
  --set-main 0
```

**Output:**

```
Uploaded 3 images
  screenshot1.png
  screenshot2.png
  screenshot3.png
```

**Notes:**
- First image (`--set-main 0`) is the thumbnail
- Recommended: 3-5 screenshots
- Supported formats: PNG, JPG, GIF
- Max size: 10MB per image

---

## Step 6: Add Team Members (if applicable)

```bash
# Add teammate
devpost team add https://devpost.com/software/ai-code-reviewer alice-dev

# Add another teammate
devpost team add https://devpost.com/software/ai-code-reviewer bob-ml
```

**Output:**

```
Successfully added alice-dev to team
project: https://devpost.com/software/ai-code-reviewer
user: alice-dev
```

**Notes:**
- Teammate must have Devpost account
- They'll receive a notification to accept

---

## Step 7: Verify Submission

```bash
devpost submission https://devpost.com/software/ai-code-reviewer --json
```

**Output shape:**

```json
{
  "success": true,
  "url": "https://devpost.com/software/ai-code-reviewer",
  "details": {
    "title": "AI Code Reviewer",
    "tagline": "Automated code review using LLMs",
    "description": "Our project uses GPT-4 to analyze code...",
    "built_with": ["Python", "OpenAI API", "GitHub API", "FastAPI"],
    "team_members": [
      {"username": "you", "role": "owner"},
      {"username": "alice-dev", "role": "member"}
    ]
  }
}
```

---

## Step 8: Update Submission (if needed)

```bash
# Update tagline only
devpost update https://devpost.com/software/ai-code-reviewer \
  --tagline "AI-powered code review with GPT-4"

# Update multiple fields
devpost update https://devpost.com/software/ai-code-reviewer \
  --description "Updated description with more details..." \
  --built-with "Python,OpenAI API,GitHub API,FastAPI,React" \
  --demo "https://new-demo.example.com"
```

**Output:**

```
Successfully updated!
updated: tagline, description, built_with, demo
```

**Note:** Use `--dry-run` to preview changes.

---

## Submission Checklist

- [ ] Joined hackathon
- [ ] Title (clear, <60 chars)
- [ ] Tagline (compelling, <140 chars)
- [ ] Description (markdown, explains what/why/how)
- [ ] Tech stack (accurate, relevant technologies)
- [ ] GitHub repo (public, working link)
- [ ] Live demo (if applicable)
- [ ] Screenshots (3-5, high quality)
- [ ] Team members added (if team)
- [ ] Verified submission details

---

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `Not authenticated` | Missing credentials | Set `DEVPOST_EMAIL`/`DEVPOST_PASSWORD` |
| `Hackathon not found` | Invalid slug | Check hackathon URL |
| `Already submitted` | Duplicate submission | Use `update` command instead |
| `User not found` | Invalid username for teammate | Verify username exists |
| `Upload failed` | Invalid image path/format | Check file exists and is PNG/JPG |

---

## Submission Best Practices

### Title
- ✅ "AI Code Reviewer" — clear and descriptive
- ❌ "My Awesome Project" — vague
- ❌ "The Best Code Reviewer Ever!!!" — unprofessional

### Tagline
- ✅ "Automated code review using LLMs" — specific value prop
- ❌ "A code reviewer" — too generic
- ❌ "Revolutionary AI that will change coding forever" — hype without substance

### Description
Structure:
1. **Problem** — What problem are you solving?
2. **Solution** — How does your project solve it?
3. **Tech** — What technologies did you use?
4. **Demo** — How can judges try it?

### Screenshots
- Show the UI in action
- Include before/after comparisons
- Highlight key features
- Use high-resolution images

### Tech Stack
- List only technologies actually used
- Order by importance
- Use standard names (e.g., "React" not "react.js")

---

## Full Example (Agent Flow)

```bash
# Step 1: Set credentials
export DEVPOST_EMAIL="dev@example.com"
export DEVPOST_PASSWORD="secure_password"

# Step 2: Join hackathon
devpost join ai-hack-2026

# Step 3: Submit with dry run
devpost submit project ai-hack-2026 \
  --title "AI Code Reviewer" \
  --tagline "Automated code review using LLMs" \
  --built-with "Python,OpenAI API,GitHub API" \
  --github "https://github.com/user/repo" \
  --dry-run

# Step 4: Actual submission
PROJECT_URL=$(devpost submit project ai-hack-2026 \
  --title "AI Code Reviewer" \
  --tagline "Automated code review using LLMs" \
  --built-with "Python,OpenAI API,GitHub API" \
  --github "https://github.com/user/repo" \
  2>&1 | grep "url:" | awk '{print $2}')

echo "Project URL: $PROJECT_URL"

# Step 5: Upload screenshots
devpost upload "$PROJECT_URL" screenshot1.png screenshot2.png

# Step 6: Add teammate
devpost team add "$PROJECT_URL" alice-dev

# Step 7: Verify
devpost submission "$PROJECT_URL" --json | jq '.details'
```

---

## Post-Submission

After submitting:

1. **Share** — Post project URL on social media
2. **Iterate** — Update based on feedback (`devpost update`)
3. **Monitor** — Watch for comments/questions
4. **Prepare demo** — Have live demo ready for judging

---

## Related Workflows

- [`find-and-evaluate.md`](find-and-evaluate.md) — Evaluate hackathons before entering
- [`find-teammates.md`](find-teammates.md) — Find collaborators
