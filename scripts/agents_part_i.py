#!/usr/bin/env python3
"""Check or synchronize the canonical Part I of downstream AGENTS.md files.

Default mode checks only. --write requires an explicitly supplied GitHub token.
The replacement spans exclusively from the Part I heading to its END marker.
All project-specific content outside that span is kept byte-for-byte unchanged.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

OWNER = "Grinch27"
REPOS = (
    "twrp_builder",
    "openwrt-compiler",
    "docker-builder",
    "uboot-mtk-compiler",
    "aosp-builder",
)
HEADING = "# Part I — GitHub Actions 通用规范"
END_MARKER = "<!-- END: NEW WORKFLOW RULES -->"
CANONICAL = Path(__file__).resolve().parent.parent / "docs/agents/part-i.md"
BASE = "https://api.github.com/repos"


def span(document):
    start = document.find(HEADING)
    end = document.find(END_MARKER, start if start >= 0 else 0)
    if start < 0 or end < 0:
        raise ValueError("Part I heading or END marker not found")
    if document.find(HEADING, start + len(HEADING)) >= 0:
        raise ValueError("Duplicate Part I heading")
    if document.find(END_MARKER, end + len(END_MARKER)) >= 0:
        raise ValueError("Duplicate Part I END marker")
    return start, end + len(END_MARKER)


def request_json(url, token, method="GET", payload=None):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "grinch27-agents-part-i-sync",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError("GitHub HTTP %s for %s" % (exc.code, url)) from exc
    except URLError as exc:
        raise RuntimeError("GitHub connection failed for %s: %s" % (url, exc.reason)) from exc


def read_remote(repo, token):
    url = "%s/%s/%s/contents/AGENTS.md?ref=main" % (BASE, OWNER, repo)
    data = request_json(url, token)
    if data.get("type") != "file" or data.get("encoding") != "base64":
        raise RuntimeError("%s: expected a base64 encoded AGENTS.md file" % repo)
    raw = base64.b64decode(data["content"], validate=False)
    return raw.decode("utf-8"), data["sha"]


def sync_remote(repo, old_sha, updated, token):
    url = "%s/%s/%s/contents/AGENTS.md" % (BASE, OWNER, repo)
    payload = {
        "message": "docs: sync canonical GitHub Actions agent rules Part I",
        "branch": "main",
        "sha": old_sha,
        "content": base64.b64encode(updated.encode("utf-8")).decode("ascii"),
    }
    data = request_json(url, token, method="PUT", payload=payload)
    return data["commit"]["sha"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Check drift (default; read-only)")
    mode.add_argument("--write", action="store_true", help="Synchronize changed Part I (remote writes)")
    parser.add_argument("--repo", choices=REPOS, action="append", help="Restrict to named repositories")
    args = parser.parse_args()

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if args.write and not token:
        parser.error("--write requires GH_TOKEN or GITHUB_TOKEN with Contents: write on target repos")

    canonical_document = CANONICAL.read_text(encoding="utf-8").rstrip("\n")
    if span(canonical_document) != (0, len(canonical_document)):
        parser.error("Canonical file must contain only the complete Part I with boundary markers")
    if "COMMON_RULES_VERSION:" not in canonical_document:
        parser.error("Canonical Part I must have an explicit version")
    digest = hashlib.sha256(canonical_document.encode("utf-8")).hexdigest()
    print("Canonical Part I SHA256: %s" % digest)

    failures = 0
    for repo in args.repo or REPOS:
        try:
            original, old_sha = read_remote(repo, token)
            start, end = span(original)
            existing = original[start:end]
            if existing == canonical_document:
                print("%s: OK" % repo)
                continue

            if not args.write:
                print("%s: DRIFT" % repo)
                failures += 1
                continue

            updated = original[:start] + canonical_document + original[end:]
            commit = sync_remote(repo, old_sha, updated, token)
            confirmed, _ = read_remote(repo, token)
            if confirmed != updated:
                raise RuntimeError("Remote content differs after synchronization")
            print("%s: SYNCED %s" % (repo, commit))
        except (ValueError, RuntimeError, OSError, KeyError, UnicodeError) as exc:
            print("%s: ERROR %s" % (repo, exc), file=sys.stderr)
            failures += 1

    if failures:
        print("%s target(s) did not pass" % failures, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
