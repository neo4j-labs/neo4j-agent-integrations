#!/usr/bin/env python3
"""Check that the labs-pages navigation and the slug map agree.

The Antora build fails hard on an ``xref`` to a page that does not exist, so the
navigation in labs-pages and the pages generated from ``slug-map.yml`` have to
stay in step. This compares four sources:

  * ``scripts/slug-map.yml``            -- what we intend to publish
  * generated ``genai-frameworks/*.adoc`` -- what the converter actually produced
  * ``modules/genai-ecosystem/nav.adoc``  -- the sidebar
  * ``agent-frameworks.adoc`` / ``agent-platforms.adoc`` -- landing pages that
    enumerate the same integrations and drift out of sync easily

Errors (exit 1):
  N-01  nav xref with no generated page          -> breaks the Antora build
  N-02  landing-page xref with no generated page -> breaks the Antora build
  N-03  nav links a page marked ``thin: true``   -> flag and page disagree

Warnings (exit 0):
  N-04  slug is generated but nothing links to it

Usage:
    check-nav.py --pages-dir <generated> [--nav-dir <labs-pages checkout>]
"""
import argparse
import os
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).parent.parent))
SLUG_MAP = REPO_ROOT / "scripts" / "slug-map.yml"

XREF_RE = re.compile(r'xref:genai-frameworks/([\w.-]+)\.adoc')
LANDING_PAGES = ("agent-frameworks.adoc", "agent-platforms.adoc")

# labs-pages is a separate repository -- locally usually a symlink or sibling
# checkout, in CI an explicit clone. It is never vendored into this repo.
LABS_PAGES_REPO = "neo4j-documentation/labs-pages"
LABS_PAGES_BRANCH = "publish"


def _module_dir(nav_dir):
    return Path(nav_dir) / "modules" / "genai-ecosystem"


def load_slug_map():
    with open(SLUG_MAP) as f:
        entries = yaml.safe_load(f)["integrations"]
    slugs, thin = set(), set()
    for entry in entries:
        slugs.add(entry["slug"])
        if entry.get("thin"):
            thin.add(entry["slug"])
        for sub in entry.get("sub_pages", []) or []:
            slugs.add(sub["slug"])
    return slugs, thin


def scan_xrefs(path):
    """Return (active, commented) xref slugs found in an AsciiDoc file."""
    active, commented = set(), set()
    if not path.exists():
        return active, commented
    for line in path.read_text().splitlines():
        bucket = commented if line.lstrip().startswith("//") else active
        bucket.update(XREF_RE.findall(line))
    return active, commented


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pages-dir", required=True,
                        help="directory holding the generated genai-frameworks/*.adoc")
    parser.add_argument("--nav-dir",
                        default=os.environ.get("LABS_PAGES_DIR",
                                               str(REPO_ROOT / "labs-pages")),
                        help=f"checkout of {LABS_PAGES_REPO} (branch "
                             f"'{LABS_PAGES_BRANCH}') containing "
                             f"modules/genai-ecosystem/; defaults to "
                             f"$LABS_PAGES_DIR or ./labs-pages")
    parser.add_argument("--strict", action="store_true",
                        help="treat warnings as errors")
    args = parser.parse_args()

    pages_dir = Path(args.pages_dir)
    generated = {p.stem for p in pages_dir.glob("*.adoc")}
    if not generated:
        print(f"ERROR  no generated pages found in {pages_dir}", file=sys.stderr)
        return 1

    module = _module_dir(args.nav_dir)
    nav_file = module / "nav.adoc"
    if not nav_file.exists():
        print(f"ERROR  nav.adoc not found at {nav_file}\n"
              f"       labs-pages is not part of this repository. Point --nav-dir\n"
              f"       (or $LABS_PAGES_DIR) at a checkout of\n"
              f"       {LABS_PAGES_REPO} (branch '{LABS_PAGES_BRANCH}'):\n"
              f"         git clone -b {LABS_PAGES_BRANCH} "
              f"https://github.com/{LABS_PAGES_REPO}.git",
              file=sys.stderr)
        return 1

    slugs, thin = load_slug_map()
    nav_active, nav_commented = scan_xrefs(nav_file)

    errors, warnings = [], []

    for slug in sorted(nav_active - generated):
        errors.append(f"N-01  nav.adoc links '{slug}' but no page was generated")

    landing_active = set()
    for name in LANDING_PAGES:
        active, _ = scan_xrefs(module / "pages" / name)
        landing_active |= active
        for slug in sorted(active - generated):
            errors.append(f"N-02  {name} links '{slug}' but no page was generated")

    for slug in sorted(nav_active & thin):
        errors.append(f"N-03  nav.adoc links '{slug}' but slug-map marks it thin: true")

    linked = nav_active | nav_commented | landing_active
    for slug in sorted(generated - linked):
        warnings.append(f"N-04  '{slug}' is generated but not referenced in nav or landing pages")

    for line in errors:
        print(f"ERROR  {line}")
    for line in warnings:
        print(f"WARN   {line}")

    print(f"\nChecked {len(generated)} generated pages, {len(slugs)} slug-map entries, "
          f"{len(nav_active)} active nav xrefs: "
          f"{len(errors)} error(s), {len(warnings)} warning(s)")

    if errors or (args.strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
