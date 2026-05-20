"""Standalone build-info generator.

Walks up from this file looking for a .git directory, parses HEAD to
get the current commit SHA + timestamp, and writes the result to
`inventory-hub/.build_info`. No git binary required — reads .git/HEAD
and .git/logs/HEAD directly.

Use cases:
  - app.py runs this at startup so the dashboard badge always reflects
    the current commit when .git is reachable on the host filesystem
    (dev case where Docker bind-mounts include the repo root).
  - A git post-commit hook can invoke it to keep the file fresh.
  - Run manually before a prod image build to bake the current commit
    into the image:  python inventory-hub/_gen_build_info.py

Falls back silently when .git isn't accessible (e.g. inside the prod
container which only has /app from the bind-mount). app.py's
fallback chain handles the absent-file case.
"""
from __future__ import annotations

import os
import sys


def find_git_dir(start_path: str):
    """Walk up from start_path looking for a .git directory.
    Returns the absolute path of `.git/` or None."""
    current = os.path.abspath(start_path)
    while True:
        candidate = os.path.join(current, '.git')
        if os.path.isdir(candidate):
            return candidate
        # A worktree's .git is a *file* whose contents point to the real gitdir.
        if os.path.isfile(candidate):
            try:
                with open(candidate, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                if content.startswith('gitdir:'):
                    gitdir = content.split(':', 1)[1].strip()
                    if not os.path.isabs(gitdir):
                        gitdir = os.path.join(current, gitdir)
                    if os.path.isdir(gitdir):
                        return os.path.abspath(gitdir)
            except OSError:
                pass
        parent = os.path.dirname(current)
        if parent == current:  # filesystem root
            return None
        current = parent


def resolve_head_sha(git_dir: str):
    """Parse .git/HEAD → ref → SHA. Returns short SHA (8 chars) or None."""
    head_path = os.path.join(git_dir, 'HEAD')
    if not os.path.isfile(head_path):
        return None
    try:
        with open(head_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
    except OSError:
        return None
    if content.startswith('ref: '):
        ref = content[5:].strip()
        ref_path = os.path.join(git_dir, ref)
        if os.path.isfile(ref_path):
            try:
                with open(ref_path, 'r', encoding='utf-8') as f:
                    sha = f.read().strip()
                if len(sha) >= 7:
                    return sha[:8]
            except OSError:
                pass
        # Packed refs fallback — many newer git installs pack refs into a
        # single file once they exceed N references.
        packed = os.path.join(git_dir, 'packed-refs')
        if os.path.isfile(packed):
            try:
                with open(packed, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and line.endswith(ref):
                            sha = line.split()[0]
                            if len(sha) >= 7:
                                return sha[:8]
            except OSError:
                pass
        return None
    # Detached HEAD — content itself is the SHA.
    if len(content) >= 7 and all(c in '0123456789abcdef' for c in content[:7].lower()):
        return content[:8]
    return None


def resolve_head_timestamp(git_dir: str):
    """Read the LAST line of .git/logs/HEAD for the most recent HEAD-move
    timestamp. Returns unix timestamp (int) or None."""
    log_path = os.path.join(git_dir, 'logs', 'HEAD')
    if not os.path.isfile(log_path):
        return None
    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except OSError:
        return None
    if not lines:
        return None
    # Format: <old_sha> <new_sha> <author_name> <email> <unix_ts> <tz> action: ...
    last = lines[-1].strip()
    # Find the unix timestamp — the first 10-digit-plus token after the email.
    parts = last.split()
    for tok in parts:
        if tok.isdigit() and len(tok) >= 10:
            try:
                return int(tok)
            except ValueError:
                continue
    return None


def write_build_info(output_path: str) -> bool:
    """Generate the .build_info file. Returns True on success."""
    here = os.path.dirname(os.path.abspath(__file__))
    git_dir = find_git_dir(here)
    if not git_dir:
        return False
    sha = resolve_head_sha(git_dir)
    if not sha:
        return False
    ts = resolve_head_timestamp(git_dir)
    # File format: SHA  (single line; optional second token = unix timestamp)
    line = sha if ts is None else f"{sha}|{ts}"
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(line + '\n')
        return True
    except OSError:
        return False


if __name__ == '__main__':
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, '.build_info')
    ok = write_build_info(out)
    if ok:
        with open(out, 'r', encoding='utf-8') as f:
            print(f"wrote {out}: {f.read().strip()}")
        sys.exit(0)
    print(".git not found or HEAD unreadable; nothing written.", file=sys.stderr)
    sys.exit(1)
