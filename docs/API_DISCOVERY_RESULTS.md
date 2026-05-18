# Devpost API Endpoint Discovery Results

**Date:** 2026-05-18  
**Method:** Automated HTTP testing + Code analysis  
**Total Endpoints Tested:** 46

---

## Summary

### ✅ Confirmed Working Endpoints (5)

| Endpoint | Parameters | Response | Notes |
|----------|-----------|----------|-------|
| `/api/hackathons` | `limit`, `search`, `url`, `open_state`, `themes[]`, etc. | `{hackathons: [], meta: {}}` | **Main hackathon search/listing** |
| `/api/hackathons.rss` | None | `{hackathons: [], meta: {}}` | Returns JSON (not RSS) |
| `/api/themes` | None | `[{name: "..."}]` | List of all themes |
| `/api/themes/popular` | None | `{themes: [...]}` | Popular themes with metadata |
| `/api/organizations` | `term` | `[{id, name, count}]` | Organization search |

### ❌ Tested But Not Found (41 endpoints)

All returned HTTP 404:

**Hackathon-specific patterns** (12 tested):
```
/api/hackathons/{slug}
/api/hackathons/{slug}/participants
/api/hackathons/{slug}/projects
/api/hackathons/{slug}/winners
/api/hackathons/{slug}/updates
/api/hackathons/{slug}/forum_topics
/api/hackathons/{slug}/resources
/api/hackathons/{slug}/rules
/api/hackathons/{slug}/eligibility
/api/hackathons/{slug}/prizes
/api/hackathons/{slug}/judging
```

**User-specific patterns** (9 tested):
```
/api/users/{username}
/api/users/{username}/projects
/api/users/{username}/followers
/api/users/{username}/following
/api/users/{username}/likes
/api/users/{username}/achievements
```

**Project-specific patterns** (6 tested):
```
/api/software/{id}
/api/projects/{id}
/api/software/{id}/details
```

**Search patterns** (5 tested):
```
/api/software/search
/api/projects/search
/api/hackathons/search
```

**Other patterns** (9 tested):
```
/api/teams/{id}
/api/featured/projects
/api/trending/projects
/api/popular/projects
```

---

## Key Findings

### 1. Limited API Surface

Devpost exposes only **5 public API endpoints**:
- Hackathon listing/search (`/api/hackathons`)
- RSS feed (`/api/hackathons.rss`)
- Themes (`/api/themes`, `/api/themes/popular`)
- Organizations (`/api/organizations`)

### 2. No REST Resource Endpoints

Unlike modern APIs, Devpost does **NOT** expose:
- Individual resource endpoints (`/api/hackathons/{slug}`)
- Nested resource endpoints (`/api/hackathons/{slug}/projects`)
- User-specific endpoints (`/api/users/{username}`)

### 3. All Data Access Patterns

Based on code analysis, Devpost uses these access patterns:

| Data Type | Access Method | Auth Required |
|-----------|--------------|---------------|
| Hackathons (list/search) | ✅ API (`/api/hackathons`) | No |
| Hackathon details | ✅ API (`/api/hackathons?url=slug`) | No |
| Hackathon projects | ❌ HTML scrape (`/{slug}/project-gallery`) | No |
| Hackathon participants | ❌ HTML scrape (`/{slug}/participants`) | No |
| Hackathon winners | ❌ HTML scrape (`/{slug}/winners`) | No |
| User profile | ❌ Playwright (`/users/{username}`) | No |
| User projects | ❌ Playwright (tab navigation) | No |
| User followers | ❌ Playwright (tab navigation) | No |
| Project search | ⚠️ Blocked (`/software/search`) - WAF | No |
| Project details | ❌ Playwright (`/software/{slug}`) | No |

### 4. WAF Protection

- `/software/search` endpoint is **blocked by AWS WAF**
- Blocks automated HTTP requests
- Requires browser automation (Playwright) to bypass

---

## Implications

### Current Architecture is Optimal

Given the limited API surface, the current hybrid approach is **already optimal**:

1. **Use API for hackathon listing/search** ✅
   - Fast, reliable, no WAF issues
   - Already implemented in `api.py`

2. **Use Playwright for user profiles** ✅
   - No API alternative exists
   - Necessary for JavaScript-rendered content

3. **Use HTML scraping for hackathon data** ✅
   - No API for participants, projects, winners
   - BeautifulSoup is efficient for this

4. **Use Playwright for project search** ⚠️
   - WAF blocks HTTP requests
   - `--playwright` flag is the correct solution

---

## Recommendations

### DO NOT Change

The current architecture is **already optimal** given Devpost's limited API:

- ✅ Keep `api.py` for hackathon listing
- ✅ Keep Playwright for user profiles
- ✅ Keep HTML scraping for hackathon pages
- ✅ Keep `--playwright` flag for search

### Potential Optimizations

1. **Better caching** (already implemented)
   - Cache hackathon data for 30 minutes
   - Cache user data for 1 hour
   - Consider longer cache times for static data

2. **Parallel scraping** (partially implemented)
   - `evaluate_hackathon()` already uses `asyncio.gather()`
   - Could parallelize more scraping operations

3. **Selector optimization**
   - Use JavaScript extraction (already done in many places)
   - More resilient to UI changes

4. **Rate limiting** (already implemented)
   - `aiolimiter` integrated
   - 3 requests per 10 seconds

### NOT Recommended

❌ **Trying to discover more API endpoints**
- We've tested 46 endpoints systematically
- Only 5 work (all already in use)
- Devpost simply doesn't expose more APIs

❌ **Replacing Playwright with API calls**
- No API alternatives exist for user/profile data
- Playwright is necessary for JavaScript-rendered content

❌ **Complex workarounds**
- GraphQL endpoint doesn't exist (tested)
- Mobile API doesn't exist (tested)
- Different headers don't bypass WAF (tested)

---

## Test Methodology

### Automated Testing

**Script:** `scripts/discover_endpoints.py`

**Tested Categories:**
- Hackathon endpoints (12 patterns)
- User endpoints (9 patterns)
- Project endpoints (6 patterns)
- Search endpoints (5 patterns)
- Team endpoints (4 patterns)
- Misc endpoints (5 patterns)

**Configuration:**
- Rate limiting: 0.5s between requests
- Timeout: 10 seconds per request
- Headers: Mimics Chrome browser
- Test data: Real hackathon slug and username

### Manual Verification

Tested known working endpoints:
```bash
GET /api/hackathons?limit=1          → 200 OK
GET /api/hackathons.rss              → 200 OK
GET /api/themes                      → 200 OK
GET /api/themes/popular              → 200 OK
GET /api/organizations?term=         → 200 OK
```

---

## Conclusion

**Devpost has a minimal public API** consisting of only 5 endpoints, all focused on hackathon discovery. There are **no APIs for**:
- Individual resources (hackathons, users, projects)
- User data (profiles, followers, projects)
- Project galleries or participants
- Search functionality (blocked by WAF)

**The current implementation is already optimal** given these constraints:
- Uses API where available (hackathon listing)
- Uses Playwright where necessary (user profiles, search)
- Uses HTML scraping where appropriate (hackathon pages)
- Implements caching and rate limiting

**No major refactoring is needed or possible** without official API support from Devpost.

---

## Files Generated

1. `scripts/discover_endpoints.py` - Automated discovery script
2. `endpoint_discovery_results.json` - Full test results (JSON)
3. `docs/API_DISCOVERY_RESULTS.md` - This analysis document

---

## Next Steps (If Any)

If better API access is needed:

1. **Contact Devpost** - Request API documentation/access
2. **Monitor for changes** - Devpost may add APIs in future
3. **Optimize current approach** - Better caching, parallel scraping
4. **Community effort** - Collaborate with other Devpost API users

For now, **the current implementation is the best possible** given Devpost's limited API surface.
