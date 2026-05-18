# Testing Summary: Team Email Invite Functionality

## Overview

This document summarizes the testing approach for the new email invite feature in team creation.

## Files Created

### 1. Integration Tests
**Location:** `tests/test_integration_team_invites.py`

**Test Classes:**
- `TestEmailInviteDetection` - Unit tests for email detection logic
- `TestTeamCreateIntegration` - Live tests requiring Devpost credentials
- `TestDebugScreenshots` - Tests for debug screenshot functionality

**Run Integration Tests:**
```bash
# Set environment variable to enable integration tests
$env:RUN_INTEGRATION_TESTS=1  # PowerShell
export RUN_INTEGRATION_TESTS=1  # Linux/Mac

# Run all integration tests
pytest tests/test_integration_team_invites.py -v -s

# Run specific test
pytest tests/test_integration_team_invites.py::TestEmailInviteDetection -v -s
```

### 2. Manual Testing Guide
**Location:** `docs/MANUAL_TESTING.md`

Comprehensive step-by-step guide with:
- Prerequisites checklist
- 5 test scenarios (A-E)
- Expected outputs
- Results template
- Troubleshooting section

### 3. Live Test Script
**Location:** `scripts/test_live_team_invites.py`

Interactive script for live testing:
```bash
python scripts/test_live_team_invites.py
```

Features:
- Runs all 4 test scenarios sequentially
- Opens browser for each test (headed mode)
- Prompts for hackathon slug
- Shows real-time results
- Provides cleanup instructions

---

## Test Results

### Unit Tests (Completed ✅)

**Email Detection Logic:**
```
PASS user@example.com: is_email=True (expected True)
PASS test.user@domain.org: is_email=True (expected True)
PASS user+tag@example.co.uk: is_email=True (expected True)
PASS username: is_email=False (expected False)
PASS user_name: is_email=False (expected False)
PASS user123: is_email=False (expected False)

All tests passed: True
```

**Mixed Invite List:**
```
alice -> username
bob@example.com -> email
charlie -> username
dave@test.org -> email
```

✅ **Email detection logic works correctly**

### Integration Tests (Pending 🔶)

**Status:** Requires valid Devpost credentials

**To Run:**
1. Ensure you're logged in: `devpost auth status`
2. Set env var: `$env:RUN_INTEGRATION_TESTS=1`
3. Run: `pytest tests/test_integration_team_invites.py -v -s`

**Tests Will Verify:**
- [ ] Team creation with username invites (baseline)
- [ ] Team creation with email invites (NEW)
- [ ] Team creation with mixed invites (NEW)
- [ ] Debug screenshot capture on errors

### Manual Testing (Pending 🔶)

**For You to Run:**

See `docs/MANUAL_TESTING.md` for detailed instructions.

**Quick Start:**
```bash
# Test 1: Username invites (baseline)
python -m devpost_cli team create <slug> --name "Test 1" --invite "user1,user2" --verbose

# Test 2: Email invites (NEW)
python -m devpost_cli team create <slug> --name "Test 2" --invite-email "a@ex.com,b@ex.com" --verbose

# Test 3: Mixed invites (NEW)
python -m devpost_cli team create <slug> --name "Test 3" --invite "user1" --invite-email "test@ex.com" --verbose

# Test 4: Debug screenshots
python -m devpost_cli --debug-screenshots team create <slug> --name "Test 4" --invite "nonexistent" --verbose
```

---

## Expected Behavior

### Scenario 1: Devpost Supports Email Invites ✅

If Devpost UI accepts email addresses:
- Email invites sent successfully
- Invites appear in `invites_sent` list
- Team members receive email invitations
- Both username and email invites work in mixed mode

### Scenario 2: Devpost Only Supports Usernames ⚠️

If Devpost UI only accepts usernames (EXPECTED):
- Email invites fail gracefully
- Failed emails appear in `invites_failed` list
- Username invites still work
- No crashes or errors
- Code handles limitation gracefully

### Scenario 3: Debug Screenshots ✅

When `--debug-screenshots` flag is used:
- Screenshots saved on Playwright errors
- Location: `/tmp/playwright_error_*.png` or `$env:TEMP\`
- Shows browser state at error time
- Useful for debugging UI changes

---

## Next Steps

### Immediate Actions

1. **Review Test Files**
   - Check `tests/test_integration_team_invites.py`
   - Review `docs/MANUAL_TESTING.md`
   - Examine `scripts/test_live_team_invites.py`

2. **Run Manual Tests** (Recommended)
   ```bash
   # Follow guide in docs/MANUAL_TESTING.md
   python scripts/test_live_team_invites.py
   ```

3. **Report Results**
   - Fill in results template from manual testing guide
   - Note any Devpost UI limitations
   - Document unexpected behaviors

### Follow-up Actions

Based on test results:

**If Email Invites Work:**
- Update README with success confirmation
- Add email invite examples to documentation
- Consider promoting feature in release notes

**If Email Invites Don't Work (Expected):**
- Document Devpost UI limitation in README
- Keep code for future compatibility
- Add note: "Email invites supported if Devpost UI allows"

**If Bugs Found:**
- Create issue with reproduction steps
- Fix and re-test
- Update tests to prevent regression

---

## Test Coverage Summary

| Component | Status | Notes |
|-----------|--------|-------|
| Email detection logic | ✅ Tested | Unit tests pass |
| Mixed invite list processing | ✅ Tested | Unit tests pass |
| CLI option parsing | ✅ Tested | `--invite-email` flag works |
| Live team creation (usernames) | 🔶 Pending | Requires credentials |
| Live team creation (emails) | 🔶 Pending | Requires credentials |
| Debug screenshots | 🔶 Pending | Requires error trigger |
| Integration tests | 🔶 Pending | Run with `RUN_INTEGRATION_TESTS=1` |

---

## Contact

For questions or issues with testing:
1. Check `docs/MANUAL_TESTING.md` troubleshooting section
2. Review integration test code for expected behavior
3. Run live test script for interactive testing
