"""Standalone build-info generator.

Walks up from this file looking for a .git directory, parses HEAD to
get the current commit SHA + timestamp, and writes the result to
`inventory-hub/.build_info`. No git binary required — reads .git/HEAD
and .git/logs/HEAD directly.

Use cases:
  - app.py runs this at import and on every dashboard render, so the
    badge reflects the current commit wherever .git is reachable: a host
    run (a test's `import app`, a round-trip bridge, a script). Dev's
    container mounts only inventory-hub/ at /app, with no .git, so there
    it reads the file the host keeps fresh.
  - A git post-commit hook can invoke it to keep the file fresh.
  - Run manually before a prod image build to bake the current commit
    into the image:  python inventory-hub/_gen_build_info.py
    (it says whether it wrote the file or found it up to date).

Falls back silently when .git isn't accessible (inside dev's or prod's
container, which have only /app from the bind-mount). app.py's
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


def update_build_info(output_path: str):
    """Bring the .build_info file up to date. Returns 'written' when it wrote
    the file, 'unchanged' when the file already held these bytes (nothing is
    written), or None when .git or HEAD can't be read or the write failed."""
    here = os.path.dirname(os.path.abspath(__file__))
    git_dir = find_git_dir(here)
    if not git_dir:
        return None
    sha = resolve_head_sha(git_dir)
    if not sha:
        return None
    ts = resolve_head_timestamp(git_dir)
    # File format: SHA  (single line; optional second token = unix timestamp)
    line = sha if ts is None else f"{sha}|{ts}"
    # Written only when its bytes would change (Group 45.9). Every host
    # `import app` (each test run, each round-trip bridge, a script that imports
    # it) rewrote it with a truncating write, on dev's bind mount (inventory-hub/
    # is the container's /app), which the container reads on every dashboard
    # render; the bytes were the same unless HEAD had moved. A render calls this
    # too, but it writes only where .git can be reached: never in dev's or prod's
    # container (neither mounts the repo's .git, so find_git_dir answers None
    # there), only in an FCC run on the host. Nothing reads its mtime:
    # app._compute_build_mtime skips it by name.
    # These are the bytes the text-mode write below puts on disk.
    new_bytes = (line + os.linesep).encode('utf-8')
    try:
        with open(output_path, 'rb') as f:
            if f.read() == new_bytes:
                return 'unchanged'
    except OSError:
        pass  # missing or unreadable: write it
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(line + '\n')
        return 'written'
    except OSError:
        return None


def write_build_info(output_path: str) -> bool:
    """Generate the .build_info file. Returns True on success: written, or
    already up to date (see update_build_info)."""
    return update_build_info(output_path) is not None


def main(out=None) -> int:
    """The command line: says whether it wrote the file or found it up to date.
    Returns the exit code."""
    if out is None:
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.build_info')
    outcome = update_build_info(out)
    if outcome:
        with open(out, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        if outcome == 'written':
            print(f"wrote {out}: {content}")
        else:
            print(f"{out} is up to date, nothing written: {content}")
        return 0
    print(".git not found or HEAD unreadable; nothing written.", file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
