# Devpost MCP - Complete Tools Reference

## 📖 PUBLIC TOOLS (No Auth Required)

### 1. `list_hackathons`
Browse active hackathons with filters.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | No | 20 | Number of hackathons to return |
| `open_state` | string | No | - | Filter: `open`, `closed`, `upcoming`, `judging`, `submitting` |
| `sort_by` | string | No | `recently-added` | Sort: `recently-added`, `submission-deadline`, `prize-amount`, `popularity` |
| `query` | string | No | - | Search query string |

**Example:**
```json
{
  "limit": 10,
  "open_state": "open",
  "sort_by": "prize-amount"
}
```

---

### 2. `search_hackathons`
Search hackathons by keyword.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | string | **Yes** | - | Search term (e.g., "AI", "healthcare", "blockchain") |
| `limit` | integer | No | 10 | Number of results |

**Example:**
```json
{
  "query": "machine learning",
  "limit": 5
}
```

---

### 3. `get_hackathon_by_url`
Get hackathon by its URL slug.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `slug` | string | **Yes** | - | URL slug (e.g., "zervehack" from zervehack.devpost.com) |

**Example:**
```json
{
  "slug": "datahacks-25"
}
```

---

### 4. `get_hackathon_details`
Scrape detailed info from hackathon page.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `url` | string | **Yes** | - | Full hackathon URL |

**Example:**
```json
{
  "url": "https://zervehack.devpost.com/"
}
```

---

### 5. `scrape_hackathon_page`
Deep scrape any hackathon page (works for past/closed events).

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `url` | string | **Yes** | - | Full hackathon URL |

**Example:**
```json
{
  "url": "https://datahacks-25.devpost.com/"
}
```

---

### 6. `list_hackathon_projects`
List all projects from a hackathon's gallery with pagination support.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `hackathon_url` | string | **Yes** | - | Hackathon URL |
| `limit` | integer | No | 50 | Max projects (0 = unlimited, get all) |
| `include_winners_only` | boolean | No | false | Only return winning projects |
| `fetch_all_pages` | boolean | No | true | Auto-fetch all pages of results |

**Example:**
```json
{
  "hackathon_url": "https://datahacks-25.devpost.com/",
  "limit": 0,
  "fetch_all_pages": true,
  "include_winners_only": false
}
```

---

### 7. `get_project_details`
Get detailed info about a specific project (uses browser automation).

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `project_url` | string | **Yes** | - | Full project URL |

**Example:**
```json
{
  "project_url": "https://devpost.com/software/onlydance"
}
```

---

## 🔒 AUTHENTICATED TOOLS (DEVPOST_EMAIL + DEVPOST_PASSWORD Required)

### 8. `submit_project`
Submit a new project to a hackathon.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `hackathon_slug` | string | **Yes** | - | Hackathon URL slug |
| `project_title` | string | **Yes** | - | Project name |
| `project_tagline` | string | **Yes** | - | Short tagline (max 140 chars) |
| `project_description` | string | No | - | Full markdown description |
| `built_with` | array[string] | No | [] | Technologies used |
| `links` | object | No | {} | Links: `github`, `demo`, `video`, `website` |
| `dry_run` | boolean | No | false | Test without actually submitting |

**Example:**
```json
{
  "hackathon_slug": "datahacks-25",
  "project_title": "OnlyDance",
  "project_tagline": "Interactive dance training app",
  "project_description": "Real-time dance training using pose detection...",
  "built_with": ["Python", "React", "OpenCV", "MediaPipe"],
  "links": {
    "github": "https://github.com/user/repo",
    "demo": "https://demo.example.com"
  },
  "dry_run": false
}
```

---

### 9. `list_my_submissions`
List all projects you've submitted.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | No | 20 | Maximum number to return |

**Example:**
```json
{
  "limit": 10
}
```

---

### 10. `get_submission_details`
Get detailed info about your specific project submission.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `project_url` | string | **Yes** | - | Full project URL |

**Example:**
```json
{
  "project_url": "https://devpost.com/software/my-project"
}
```

---

### 11. `update_submission`
Update an existing project (patch-style - only changed fields).

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `project_url` | string | **Yes** | - | Project to update |
| `project_title` | string | No | - | New title (omit to keep current) |
| `project_tagline` | string | No | - | New tagline (omit to keep current) |
| `project_description` | string | No | - | New description (omit to keep current) |
| `built_with` | array[string] | No | - | New tech stack (omit to keep current) |
| `links` | object | No | - | New links (omit to keep current) |
| `dry_run` | boolean | No | false | Test without saving |

**Example:**
```json
{
  "project_url": "https://devpost.com/software/my-project",
  "project_tagline": "Updated tagline",
  "dry_run": false
}
```

---

### 12. `add_team_member`
Add a team member to your project.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `project_url` | string | **Yes** | - | Project URL |
| `username` | string | **Yes** | - | Devpost username or email to add |

**Example:**
```json
{
  "project_url": "https://devpost.com/software/my-project",
  "username": "teammate_username"
}
```

---

### 13. `remove_team_member`
Remove a team member from your project.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `project_url` | string | **Yes** | - | Project URL |
| `username` | string | **Yes** | - | Username to remove |

**Example:**
```json
{
  "project_url": "https://devpost.com/software/my-project",
  "username": "old_teammate"
}
```

---

### 14. `upload_screenshots`
Upload screenshots/images to your project.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `project_url` | string | **Yes** | - | Project URL |
| `image_paths` | array[string] | **Yes** | - | Local file paths to images |
| `set_main_image` | integer | No | 0 | Which image should be main (0-based) |

**Example:**
```json
{
  "project_url": "https://devpost.com/software/my-project",
  "image_paths": [
    "/home/user/screenshot1.png",
    "/home/user/screenshot2.jpg"
  ],
  "set_main_image": 0
}
```

---

### 15. `delete_submission`
Permanently delete a project submission.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `project_url` | string | **Yes** | - | Project URL to delete |
| `confirm` | boolean | No | false | **MUST BE TRUE** to actually delete |

**Example:**
```json
{
  "project_url": "https://devpost.com/software/old-project",
  "confirm": true
}
```

---

## Common Parameter Types

### `links` Object Structure
```json
{
  "github": "https://github.com/username/repo",
  "demo": "https://demo.example.com",
  "video": "https://youtube.com/watch?v=...",
  "website": "https://project.com"
}
```

### `built_with` Array
```json
["Python", "React", "OpenAI", "FastAPI", "TailwindCSS"]
```

---

## Quick Reference by Use Case

**Find hackathons:**
- `list_hackathons` / `search_hackathons`

**Explore past events:**
- `scrape_hackathon_page` → `list_hackathon_projects` → `get_project_details`

**Submit new project:**
- `submit_project` (with dry_run first!)

**Manage existing project:**
- `list_my_submissions` → `update_submission` / `add_team_member` / `upload_screenshots`

**Cleanup:**
- `delete_submission` (confirm: true)
