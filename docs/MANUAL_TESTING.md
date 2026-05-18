# Manual Testing Guide: Team Email Invites

This guide provides step-by-step instructions for manually testing the new email invite functionality for team creation.

## Prerequisites

- [ ] Devpost account with credentials
- [ ] A hackathon you control (or one accepting team formation)
- [ ] 2-3 test email addresses (can use `@example.com` for testing)
- [ ] 2-3 test Devpost usernames (optional, for mixed testing)

## Setup

### 1. Verify Authentication

```bash
cd devpost-mcp
python -m devpost_cli auth status
```

Expected output:
```json
{
  "authenticated": true,
  "email": "your@email.com",
  "password_set": true,
  "auth_method": "password"
}
```

If not authenticated:
```bash
python -m devpost_cli auth login
```

### 2. Choose Test Hackathon

Identify a hackathon where you can create teams:
```bash
python -m devpost_cli hackathons --state open -l 10
```

Note the slug (e.g., `zervehack`, `test-hackathon`).

---

## Test Scenarios

### Scenario A: Username Invites Only (Baseline)

**Purpose:** Verify existing functionality still works.

**Command:**
```bash
python -m devpost_cli team create <HACKATHON_SLUG> \
  --name "Test Team Usernames" \
  --invite "user1,user2" \
  --verbose
```

**Replace:**
- `<HACKATHON_SLUG>` with your test hackathon
- `user1,user2` with real Devpost usernames

**Expected Output:**
```
✓ Team created successfully
hackathon: <slug>
team: Test Team Usernames
url: https://<slug>.devpost.com/teams/...

Invites sent (2):
  ✓ user1 (username)
  ✓ user2 (username)

Steps:
  Navigating to <slug> team page
  Looking for create team option
  Clicked create team
  Filling team name
  Adding 2 invitees
  Added username invite: user1
  Added username invite: user2
  Submitting team creation
```

**Success Criteria:**
- [ ] Team created successfully
- [ ] Both username invites sent
- [ ] Team URL provided

---

### Scenario B: Email Invites Only (NEW FEATURE)

**Purpose:** Test new email invite functionality.

**Command:**
```bash
python -m devpost_cli team create <HACKATHON_SLUG> \
  --name "Test Team Emails" \
  --invite-email "alice@example.com,bob@example.com" \
  --verbose
```

**Replace:**
- `<HACKATHON_SLUG>` with your test hackathon
- Email addresses with real test emails

**Expected Output:**
```
✓ Team created successfully
hackathon: <slug>
team: Test Team Emails
url: https://<slug>.devpost.com/teams/...

Invites sent (2):
  ✓ alice@example.com (email)
  ✓ bob@example.com (email)

Steps:
  Navigating to <slug> team page
  Looking for create team option
  Clicked create team
  Filling team name
  Adding 2 invitees
  Added email invite: alice@example.com
  Added email invite: bob@example.com
  Submitting team creation
```

**Success Criteria:**
- [ ] Team created successfully
- [ ] Email invites processed (may show as "email" type)
- [ ] No errors about email format
- [ ] Team URL provided

**Possible Outcomes:**
1. ✅ **Email invites accepted** - Devpost UI supports email invites
2. ⚠️ **Email invites failed** - Devpost UI only accepts usernames (expected limitation)
3. ❌ **Error** - Bug in email detection/handling

---

### Scenario C: Mixed Invites (NEW FEATURE)

**Purpose:** Test combining username and email invites.

**Command:**
```bash
python -m devpost_cli team create <HACKATHON_SLUG> \
  --name "Test Team Mixed" \
  --invite "testuser1" \
  --invite-email "test@example.com" \
  --verbose
```

**Expected Output:**
```
✓ Team created successfully
hackathon: <slug>
team: Test Team Mixed
url: https://<slug>.devpost.com/teams/...

Invites sent (2):
  ✓ testuser1 (username)
  ✓ test@example.com (email)

Steps:
  ...
  Adding 2 invitees
  Added username invite: testuser1
  Added email invite: test@example.com
  ...
```

**Success Criteria:**
- [ ] Both invite types processed
- [ ] Correct type labels (username vs email)
- [ ] No crashes or errors

---

### Scenario D: Debug Screenshots (NEW FEATURE)

**Purpose:** Verify debug screenshots are saved on errors.

**Command:**
```bash
python -m devpost_cli \
  --debug-screenshots \
  team create <HACKATHON_SLUG> \
  --name "Test Team Debug" \
  --invite "nonexistent_user_xyz123" \
  --verbose
```

**Expected Behavior:**
1. Command attempts to invite non-existent user
2. May fail or show warning
3. If Playwright error occurs, screenshot saved to `/tmp/playwright_error_*.png`

**Check for Screenshots:**
```bash
# On Windows (WSL or Git Bash)
ls /tmp/playwright_error_*.png

# On Windows (PowerShell)
Get-ChildItem C:\tmp\playwright_error_*.png 2>$null

# Or check temp directory
ls $env:TEMP\playwright_error_*.png
```

**Success Criteria:**
- [ ] Command completes (may have warnings)
- [ ] If error occurred, screenshot file exists
- [ ] Screenshot shows browser state at error time

---

### Scenario E: Edge Cases

**Test invalid email format:**
```bash
python -m devpost_cli team create <HACKATHON_SLUG> \
  --name "Test Invalid Email" \
  --invite-email "not-an-email" \
  --verbose
```

**Test empty invites:**
```bash
python -m devpost_cli team create <HACKATHON_SLUG> \
  --name "Test No Invites" \
  --verbose
```

**Test very long email list:**
```bash
python -m devpost_cli team create <HACKATHON_SLUG> \
  --name "Test Many Invites" \
  --invite-email "a@x.com,b@x.com,c@x.com,d@x.com,e@x.com" \
  --verbose
```

---

## Results Template

Copy this template and fill in your results:

```markdown
## Test Results

**Date:** YYYY-MM-DD
**Tester:** [Your name]
**Hackathon:** [slug]

### Scenario A: Username Invites
- [ ] Passed / [ ] Failed
- Notes: ...

### Scenario B: Email Invites
- [ ] Passed / [ ] Failed
- Notes: ...
- Devpost UI behavior: (accepted emails? showed error?)

### Scenario C: Mixed Invites
- [ ] Passed / [ ] Failed
- Notes: ...

### Scenario D: Debug Screenshots
- [ ] Passed / [ ] Failed
- Screenshot saved: [Yes/No]
- Screenshot location: ...

### Issues Found
1. ...
2. ...

### Recommendations
- ...
```

---

## Troubleshooting

### "Create team option not found"
- You may already be in a team for this hackathon
- Team formation may be closed
- Try a different hackathon

### "Invite input not found"
- Devpost UI may have changed
- Email invites may not be supported on this hackathon
- Check browser window (if --headed) for actual UI state

### No screenshots saved
- Debug screenshots only save on Playwright errors
- Check `/tmp/` or `$env:TEMP` directory
- Ensure `--debug-screenshots` flag is used

### Email invites fail
- **Expected:** Devpost may only support username invites
- This is a Devpost UI limitation, not a bug
- The code handles this gracefully (adds to failed list)

---

## Cleanup

After testing, you may want to:

1. **Delete test teams** (if Devpost allows):
   - Go to hackathon team page
   - Look for "Delete team" or "Leave team" option

2. **Clear test data**:
   ```bash
   python -m devpost_cli auth logout
   python -m devpost_cli auth login
   ```

3. **Remove test files**:
   ```bash
   # Remove debug screenshots
   rm /tmp/playwright_error_*.png
   ```

---

## Next Steps

After manual testing:

1. **Report results** using the template above
2. **Update README** if behavior differs from documentation
3. **Fix any bugs** found during testing
4. **Run integration tests** if all manual tests pass:
   ```bash
   RUN_INTEGRATION_TESTS=1 pytest tests/test_integration_team_invites.py -v -s
   ```
