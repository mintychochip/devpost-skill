#!/usr/bin/env python
"""
Devpost API Endpoint Discovery Script

Systematically tests 50+ endpoint patterns to discover open APIs.
Logs results to console and exports to JSON for analysis.

Usage:
    python scripts/discover_endpoints.py
    
Output:
    - Console: Real-time results
    - File: endpoint_discovery_results.json
"""

import httpx
import asyncio
import json
from datetime import datetime
from typing import List, Dict
from pathlib import Path

# Configuration
BASE_URL = "https://devpost.com"
API_BASE = "https://devpost.com/api"

# Test data (real accounts/pages on Devpost)
TEST_HACKATHON_SLUG = "zervehack"  # Active hackathon
TEST_USERNAME = "tech-dawg015"     # Real user with projects
TEST_PROJECT_ID = "123456"         # Placeholder

# HTTP headers to mimic browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# Endpoint categories to test
ENDPOINT_CATEGORIES = {
    "hackathon": [
        "hackathons/{slug}",
        "hackathons/{slug}/participants",
        "hackathons/{slug}/projects",
        "hackathons/{slug}/projects/gallery",
        "hackathons/{slug}/winners",
        "hackathons/{slug}/updates",
        "hackathons/{slug}/forum_topics",
        "hackathons/{slug}/resources",
        "hackathons/{slug}/rules",
        "hackathons/{slug}/eligibility",
        "hackathons/{slug}/prizes",
        "hackathons/{slug}/judging",
    ],
    "user": [
        "users/{username}",
        "users/{username}/profile",
        "users/{username}/projects",
        "users/{username}/hackathons",
        "users/{username}/followers",
        "users/{username}/following",
        "users/{username}/likes",
        "users/{username}/achievements",
        "users/{username}/challenges",
    ],
    "project": [
        "software/{id}",
        "projects/{id}",
        "software/{id}/details",
        "software/{id}/comments",
        "software/{id}/likes",
        "software/{id}/team",
    ],
    "search": [
        "software/search",
        "projects/search",
        "hackathons/search",
        "search/projects",
        "search/hackathons",
    ],
    "team": [
        "teams/{id}",
        "teams/{id}/members",
        "teams/{id}/projects",
        "teams/{id}/hackathon",
    ],
    "misc": [
        "featured/projects",
        "trending/projects",
        "popular/projects",
        "recent/projects",
        "technologies/trending",
    ],
}

# Rate limiting configuration
REQUEST_DELAY = 0.5  # seconds between requests
TIMEOUT = 10.0  # seconds per request


def get_status_icon(status_code: int) -> str:
    """Get icon for status code."""
    if status_code == 200:
        return "[OK]"
    elif status_code in [403, 429]:
        return "[BLK]"
    elif status_code == 404:
        return "[404]"
    elif status_code >= 500:
        return "[ERR]"
    else:
        return "[?]"


async def test_endpoint(
    client: httpx.AsyncClient,
    category: str,
    endpoint_pattern: str,
) -> Dict:
    """Test a single endpoint and return detailed results."""
    
    # Substitute test values into pattern
    url = endpoint_pattern.format(
        slug=TEST_HACKATHON_SLUG,
        username=TEST_USERNAME,
        id=TEST_PROJECT_ID,
    )
    
    full_url = f"{API_BASE}/{url}"
    
    result = {
        "endpoint": f"{category}/{endpoint_pattern}",
        "url": full_url,
        "status_code": 0,
        "response_time_ms": 0,
        "response_size": 0,
        "is_json": False,
        "preview": "",
        "error": None,
    }
    
    try:
        start_time = asyncio.get_event_loop().time()
        
        response = await client.get(full_url, headers=HEADERS, timeout=TIMEOUT)
        
        end_time = asyncio.get_event_loop().time()
        result["status_code"] = response.status_code
        result["response_time_ms"] = round((end_time - start_time) * 1000, 2)
        result["response_size"] = len(response.content)
        
        # Try to parse as JSON
        try:
            data = response.json()
            result["is_json"] = True
            
            # Create preview
            if isinstance(data, dict):
                keys = list(data.keys())[:5]
                result["preview"] = f"Dict with keys: {keys}"
            elif isinstance(data, list):
                result["preview"] = f"List with {len(data)} items"
            else:
                result["preview"] = str(data)[:200]
                
        except json.JSONDecodeError:
            result["preview"] = response.text[:200]
        
        # Log status
        status_icon = get_status_icon(response.status_code)
        print(f"{status_icon} {result['endpoint']:60} -> {response.status_code} ({result['response_time_ms']}ms)")
        
        if response.status_code == 200 and result["preview"]:
            print(f"    {result['preview']}")
        
    except httpx.ConnectError as e:
        result["error"] = f"Connect error: {e}"
        print(f"[ERR] {result['endpoint']:60} -> Connection failed")
        
    except httpx.TimeoutException as e:
        result["error"] = f"Timeout: {e}"
        print(f"[ERR] {result['endpoint']:60} -> Timeout")
        
    except Exception as e:
        result["error"] = f"Error: {e}"
        print(f"[ERR] {result['endpoint']:60} -> {type(e).__name__}")
    
    return result


async def test_category(
    client: httpx.AsyncClient,
    category: str,
    endpoints: List[str],
) -> List[Dict]:
    """Test all endpoints in a category."""
    
    print(f"\n{'='*80}")
    print(f"Testing {category.upper()} endpoints...")
    print(f"{'='*80}")
    
    results = []
    
    for endpoint in endpoints:
        result = await test_endpoint(client, category, endpoint)
        results.append(result)
        
        # Rate limiting
        await asyncio.sleep(REQUEST_DELAY)
    
    return results


def generate_summary(all_results: List[Dict]) -> Dict:
    """Generate summary statistics."""
    
    working = [r for r in all_results if r["status_code"] == 200]
    blocked = [r for r in all_results if r["status_code"] in [403, 429]]
    not_found = [r for r in all_results if r["status_code"] == 404]
    errors = [r for r in all_results if r["status_code"] == 0]
    server_errors = [r for r in all_results if r["status_code"] >= 500]
    
    summary = {
        "total_tested": len(all_results),
        "working": len(working),
        "blocked": len(blocked),
        "not_found": len(not_found),
        "errors": len(errors),
        "server_errors": len(server_errors),
        "success_rate": round(len(working) / len(all_results) * 100, 2) if all_results else 0,
        "working_endpoints": working,
        "blocked_endpoints": blocked,
    }
    
    return summary


def print_summary(summary: Dict):
    """Print summary to console."""
    
    print(f"\n{'='*80}")
    print("DISCOVERY SUMMARY")
    print(f"{'='*80}")
    print(f"Total endpoints tested: {summary['total_tested']}")
    print(f"[OK] Working (200):      {summary['working']} ({summary['success_rate']}%)")
    print(f"[BLK] Blocked (403/429):  {summary['blocked']}")
    print(f"[404] Not Found (404):    {summary['not_found']}")
    print(f"[ERR] Server Errors:      {summary['server_errors']}")
    print(f"[?] Connection Errors:  {summary['errors']}")
    
    if summary["working_endpoints"]:
        print(f"\n[OK] WORKING ENDPOINTS ({len(summary['working_endpoints'])}):")
        for endpoint in summary["working_endpoints"]:
            print(f"  - {endpoint['endpoint']}")
            print(f"    URL: {endpoint['url']}")
            print(f"    Response: {endpoint['preview'][:100]}")
            print()
    
    if summary["blocked_endpoints"]:
        print(f"\n[BLK] BLOCKED ENDPOINTS (WAF/Rate Limit):")
        for endpoint in summary["blocked_endpoints"]:
            print(f"  - {endpoint['endpoint']} ({endpoint['status_code']})")


async def main():
    """Main discovery function."""
    
    print(f"{'='*80}")
    print("Devpost API Endpoint Discovery")
    print(f"{'='*80}")
    print(f"Base URL: {API_BASE}")
    print(f"Test hackathon: {TEST_HACKATHON_SLUG}")
    print(f"Test user: {TEST_USERNAME}")
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}")
    
    all_results = []
    
    async with httpx.AsyncClient(headers=HEADERS) as client:
        # Test each category
        for category, endpoints in ENDPOINT_CATEGORIES.items():
            results = await test_category(client, category, endpoints)
            all_results.extend(results)
    
    # Generate and print summary
    summary = generate_summary(all_results)
    print_summary(summary)
    
    # Export results to JSON
    output_file = Path("endpoint_discovery_results.json")
    output_data = {
        "timestamp": datetime.now().isoformat(),
        "test_config": {
            "hackathon_slug": TEST_HACKATHON_SLUG,
            "username": TEST_USERNAME,
            "base_url": API_BASE,
        },
        "summary": summary,
        "all_results": all_results,
    }
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*80}")
    print(f"Results exported to: {output_file.absolute()}")
    print(f"{'='*80}")
    
    return summary


if __name__ == "__main__":
    summary = asyncio.run(main())
    
    # Exit with appropriate code
    if summary["working"] > 0:
        exit(0)  # Success - found working endpoints
    else:
        exit(1)  # No working endpoints found
