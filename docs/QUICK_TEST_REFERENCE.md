# Quick Test Reference

## One-Line Test Commands

### Test Email Detection (Unit Test)
```bash
python -c "print('Email detection:', '@' in 'test@example.com')"
```

### Test Team Creation with Email Invites
```bash
python -m devpost_cli team create HACKATHON_SLUG --name "Test" --invite-email "test@example.com" --verbose
```

### Test Mixed Invites
```bash
python -m devpost_cli team create HACKATHON_SLUG --name "Test" --invite "user1" --invite-email "test@example.com" --verbose
```

### Test Debug Screenshots
```bash
python -m devpost_cli --debug-screenshots team create HACKATHON_SLUG --name "Test" --invite "nonexistent" --verbose
```

## Run All Tests

### Unit Tests (No Credentials Needed)
```bash
pytest tests/test_integration_team_invites.py::TestEmailInviteDetection -v -s
```

### Integration Tests (Requires Credentials)
```powershell
# PowerShell
$env:RUN_INTEGRATION_TESTS=1
pytest tests/test_integration_team_invites.py -v -s

# Bash (Linux/Mac)
export RUN_INTEGRATION_TESTS=1
pytest tests/test_integration_team_invites.py -v -s
```

### Interactive Live Test
```bash
python scripts/test_live_team_invites.py
```

## Expected Results

| Test | Expected Outcome |
|------|-----------------|
| Email detection | ✅ Correctly identifies emails vs usernames |
| Username invites | ✅ Works (baseline) |
| Email invites | ⚠️ May fail if Devpost doesn't support (expected) |
| Mixed invites | ✅ Processes both types |
| Debug screenshots | ✅ Saves on error |

## Quick Cleanup

```powershell
# Delete test teams (manual)
# Go to https://HACKATHON_SLUG.devpost.com/team and delete

# Remove debug screenshots
Remove-Item $env:TEMP\playwright_error_*.png -ErrorAction SilentlyContinue
```

## Test Files Created

1. `tests/test_integration_team_invites.py` - Integration tests
2. `docs/MANUAL_TESTING.md` - Step-by-step manual testing guide
3. `docs/TESTING_SUMMARY.md` - Complete testing overview
4. `scripts/test_live_team_invites.py` - Interactive test script
5. `docs/QUICK_TEST_REFERENCE.md` - This file
