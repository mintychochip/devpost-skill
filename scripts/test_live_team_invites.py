#!/usr/bin/env python
"""Live test script for team email invite functionality.

Run this script to test team creation with email invites on real Devpost.

Usage:
    python scripts/test_live_team_invites.py

Prerequisites:
    - Valid Devpost credentials (set via `devpost auth login`)
    - A hackathon where you can create teams
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from devpost_cli.core import AuthenticatedClient


async def test_username_invites(hackathon_slug: str):
    """Test 1: Create team with username invites only."""
    print("\n" + "="*60)
    print("TEST 1: Username Invites (Baseline)")
    print("="*60)
    
    team_name = f"Test Team Usernames"
    
    async with AuthenticatedClient(headed=True) as client:
        result = await client.create_team(
            hackathon_slug=hackathon_slug,
            team_name=team_name,
            invite_usernames=["testuser1", "testuser2"],
            invite_emails=None,
        )
    
    print(f"\nResult:")
    print(f"  Success: {result.get('success')}")
    print(f"  Team: {team_name}")
    print(f"  Invites sent: {result.get('invites_sent', [])}")
    print(f"  Invites failed: {result.get('invites_failed', [])}")
    print(f"  Error: {result.get('error', 'None')}")
    
    if result.get('team_url'):
        print(f"  Team URL: {result['team_url']}")
    
    return result.get('success')


async def test_email_invites(hackathon_slug: str):
    """Test 2: Create team with email invites only."""
    print("\n" + "="*60)
    print("TEST 2: Email Invites (NEW FEATURE)")
    print("="*60)
    
    team_name = f"Test Team Emails"
    
    async with AuthenticatedClient(headed=True) as client:
        result = await client.create_team(
            hackathon_slug=hackathon_slug,
            team_name=team_name,
            invite_usernames=None,
            invite_emails=["test1@example.com", "test2@example.com"],
        )
    
    print(f"\nResult:")
    print(f"  Success: {result.get('success')}")
    print(f"  Team: {team_name}")
    
    # Analyze invites
    invites_sent = result.get('invites_sent', [])
    invites_failed = result.get('invites_failed', [])
    
    email_sent = [i for i in invites_sent if '@' in i]
    email_failed = [i for i in invites_failed if '@' in i]
    
    print(f"  Email invites sent: {email_sent}")
    print(f"  Email invites failed: {email_failed}")
    print(f"  Error: {result.get('error', 'None')}")
    
    if result.get('team_url'):
        print(f"  Team URL: {result['team_url']}")
    
    # Check if Devpost supports email invites
    if email_sent:
        print("\n  [SUCCESS] Devpost UI accepts email invites!")
    elif email_failed:
        print("\n  [INFO] Devpost UI may not support email invites (expected)")
    
    return result.get('success')


async def test_mixed_invites(hackathon_slug: str):
    """Test 3: Create team with mixed username and email invites."""
    print("\n" + "="*60)
    print("TEST 3: Mixed Invites (NEW FEATURE)")
    print("="*60)
    
    team_name = f"Test Team Mixed"
    
    async with AuthenticatedClient(headed=True) as client:
        result = await client.create_team(
            hackathon_slug=hackathon_slug,
            team_name=team_name,
            invite_usernames=["testuser1"],
            invite_emails=["test@example.com"],
        )
    
    print(f"\nResult:")
    print(f"  Success: {result.get('success')}")
    print(f"  Team: {team_name}")
    
    invites_sent = result.get('invites_sent', [])
    invites_failed = result.get('invites_failed', [])
    
    email_invites = [i for i in invites_sent if '@' in i]
    username_invites = [i for i in invites_sent if '@' not in i]
    
    print(f"  Username invites sent: {username_invites}")
    print(f"  Email invites sent: {email_invites}")
    print(f"  Failed: {invites_failed}")
    print(f"  Error: {result.get('error', 'None')}")
    
    if result.get('team_url'):
        print(f"  Team URL: {result['team_url']}")
    
    return result.get('success')


async def test_debug_screenshots(hackathon_slug: str):
    """Test 4: Test debug screenshot functionality."""
    print("\n" + "="*60)
    print("TEST 4: Debug Screenshots (NEW FEATURE)")
    print("="*60)
    
    async with AuthenticatedClient(headed=True, debug_screenshots=True) as client:
        result = await client.create_team(
            hackathon_slug="invalid-hackathon-xyz",  # Will fail
            team_name="Test Team Debug",
            invite_usernames=None,
            invite_emails=None,
        )
    
    print(f"\nResult:")
    print(f"  Success: {result.get('success')}")
    print(f"  Error: {result.get('error', 'None')}")
    print(f"  Debug screenshot: {result.get('debug_screenshot', 'Not captured')}")
    
    # Check for screenshot files
    import glob
    screenshots = glob.glob("/tmp/playwright_error_*.png")
    if screenshots:
        print(f"\n  [SUCCESS] Screenshots found: {screenshots}")
    else:
        print(f"\n  [INFO] No screenshots saved (only saved on Playwright errors)")
    
    return True  # This test always "passes" - just checking it doesn't crash


async def main():
    """Run all live tests."""
    print("\n" + "="*60)
    print("LIVE TEST: Team Email Invite Functionality")
    print("="*60)
    print("\nThis script will test team creation on real Devpost.")
    print("A browser window will open for each test.")
    print("\nIMPORTANT: These tests create real teams on Devpost!")
    print("You may need to clean up test teams afterward.\n")
    
    # Get hackathon slug from user
    hackathon_slug = input("Enter hackathon slug (or press Enter for 'test-hackathon'): ").strip()
    if not hackathon_slug:
        hackathon_slug = "test-hackathon"
    
    print(f"\nUsing hackathon: {hackathon_slug}")
    print("\nStarting tests...\n")
    
    results = {}
    
    # Run tests
    try:
        results['username_invites'] = await test_username_invites(hackathon_slug)
    except Exception as e:
        print(f"\n[ERROR] Username invites test failed: {e}")
        results['username_invites'] = False
    
    input("\nPress Enter to continue to email invites test...")
    
    try:
        results['email_invites'] = await test_email_invites(hackathon_slug)
    except Exception as e:
        print(f"\n[ERROR] Email invites test failed: {e}")
        results['email_invites'] = False
    
    input("\nPress Enter to continue to mixed invites test...")
    
    try:
        results['mixed_invites'] = await test_mixed_invites(hackathon_slug)
    except Exception as e:
        print(f"\n[ERROR] Mixed invites test failed: {e}")
        results['mixed_invites'] = False
    
    input("\nPress Enter to continue to debug screenshots test...")
    
    try:
        results['debug_screenshots'] = await test_debug_screenshots(hackathon_slug)
    except Exception as e:
        print(f"\n[ERROR] Debug screenshots test failed: {e}")
        results['debug_screenshots'] = False
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    for test_name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {test_name}: {status}")
    
    print("\n" + "="*60)
    print("CLEANUP")
    print("="*60)
    print("Remember to delete test teams from Devpost if needed:")
    print(f"  1. Go to https://{hackathon_slug}.devpost.com/team")
    print(f"  2. Find your test teams")
    print(f"  3. Click 'Delete team' or 'Leave team'\n")


if __name__ == "__main__":
    asyncio.run(main())
