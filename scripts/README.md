# Repository Scripts

## Link Validation

### validate-links.py

Validates all URLs in README files to ensure none are broken.

**Usage:**

```bash
# Install dependencies
pip install -r scripts/requirements.txt

# Run validation
python scripts/validate-links.py
```

**Features:**
- Extracts all URLs from markdown files
- Checks HTTP status codes
- Handles redirects
- Concurrent checking for speed
- Reports line numbers for broken links
- Provides summary of results

**Exit codes:**
- `0` - All links valid
- `1` - Some links broken

**Example output:**

```
Found 21 README files to check
================================================================================

Checking 15 URLs in aws-agentcore/README.md...
  ✓ https://aws.amazon.com/bedrock/agentcore/... (OK)
  ✗ https://invalid-url.example.com... (Connection error) [Line 42]

================================================================================
SUMMARY
================================================================================

aws-agentcore/README.md
  Total: 15 | Valid: 14 | Invalid: 1
    Line 42: https://invalid-url.example.com
      Error: Connection error

================================================================================
Total URLs checked: 287
Valid: 285
Invalid: 2

⚠️  Some links are broken. Please fix them.
```
