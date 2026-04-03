#!/usr/bin/env python3
"""
Validate all URLs in README files to check for broken links.
"""

import re
import sys
from pathlib import Path
from urllib.parse import urlparse
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple

# Timeout for HTTP requests (seconds)
REQUEST_TIMEOUT = 10

# User agent to avoid being blocked
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
}

def extract_urls_from_markdown(content: str, filepath: str) -> List[Tuple[str, int]]:
    """Extract all URLs from markdown content with line numbers."""
    urls = []

    # Match markdown links: [text](url)
    markdown_links = re.finditer(r'\[([^\]]+)\]\(([^)]+)\)', content)
    for match in markdown_links:
        url = match.group(2)
        # Skip anchors and relative links
        if not url.startswith('#') and not url.startswith('./') and not url.startswith('../'):
            line_num = content[:match.start()].count('\n') + 1
            urls.append((url, line_num))

    # Match bare URLs
    bare_urls = re.finditer(r'https?://[^\s\)]+', content)
    for match in bare_urls:
        url = match.group(0)
        line_num = content[:match.start()].count('\n') + 1
        # Avoid duplicates from markdown links
        if not any(u[0] == url for u in urls):
            urls.append((url, line_num))

    return urls

def check_url(url: str) -> Tuple[str, bool, str]:
    """Check if a URL is accessible. Returns (url, is_valid, error_message)."""
    try:
        # Clean up URL (remove trailing punctuation that might be part of markdown)
        url = url.rstrip('.,;:')

        # Handle special cases
        parsed = urlparse(url)

        # Skip invalid schemes
        if parsed.scheme not in ['http', 'https']:
            return (url, True, 'Skipped (not HTTP/HTTPS)')

        response = requests.head(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True
        )

        # Some servers don't support HEAD, try GET
        if response.status_code in [405, 404]:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True
            )

        if response.status_code == 200:
            return (url, True, 'OK')
        elif 300 <= response.status_code < 400:
            return (url, True, f'Redirect ({response.status_code})')
        else:
            return (url, False, f'HTTP {response.status_code}')

    except requests.exceptions.Timeout:
        return (url, False, 'Timeout')
    except requests.exceptions.ConnectionError:
        return (url, False, 'Connection error')
    except requests.exceptions.TooManyRedirects:
        return (url, False, 'Too many redirects')
    except Exception as e:
        return (url, False, f'Error: {str(e)}')

def validate_links_in_file(filepath: Path) -> Dict:
    """Validate all links in a single file."""
    content = filepath.read_text(encoding='utf-8')
    urls = extract_urls_from_markdown(content, str(filepath))

    if not urls:
        return {
            'file': str(filepath),
            'total': 0,
            'valid': 0,
            'invalid': 0,
            'issues': []
        }

    results = {
        'file': str(filepath),
        'total': len(urls),
        'valid': 0,
        'invalid': 0,
        'issues': []
    }

    print(f"\nChecking {len(urls)} URLs in {filepath.name}...")

    # Check URLs concurrently
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {
            executor.submit(check_url, url): (url, line_num)
            for url, line_num in urls
        }

        for future in as_completed(future_to_url):
            url, line_num = future_to_url[future]
            checked_url, is_valid, message = future.result()

            if is_valid:
                results['valid'] += 1
                print(f"  ✓ {checked_url[:60]}... ({message})")
            else:
                results['invalid'] += 1
                results['issues'].append({
                    'url': checked_url,
                    'line': line_num,
                    'error': message
                })
                print(f"  ✗ {checked_url[:60]}... ({message}) [Line {line_num}]")

    return results

def main():
    """Main function to validate all links in README files."""
    repo_root = Path(__file__).parent.parent

    # Find all README files
    readme_files = list(repo_root.glob('**/README.md'))

    if not readme_files:
        print("No README files found!")
        return 1

    print(f"Found {len(readme_files)} README files to check")
    print("=" * 80)

    all_results = []
    total_urls = 0
    total_valid = 0
    total_invalid = 0

    for readme_file in sorted(readme_files):
        result = validate_links_in_file(readme_file)
        all_results.append(result)
        total_urls += result['total']
        total_valid += result['valid']
        total_invalid += result['invalid']

    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    for result in all_results:
        if result['invalid'] > 0:
            print(f"\n{result['file']}")
            print(f"  Total: {result['total']} | Valid: {result['valid']} | Invalid: {result['invalid']}")
            for issue in result['issues']:
                print(f"    Line {issue['line']}: {issue['url']}")
                print(f"      Error: {issue['error']}")

    print("\n" + "=" * 80)
    print(f"Total URLs checked: {total_urls}")
    print(f"Valid: {total_valid}")
    print(f"Invalid: {total_invalid}")

    if total_invalid > 0:
        print("\n⚠️  Some links are broken. Please fix them.")
        return 1
    else:
        print("\n✓ All links are valid!")
        return 0

if __name__ == '__main__':
    sys.exit(main())
