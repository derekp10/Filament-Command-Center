#!/usr/bin/env bash
# Install a one-line post-commit hook that refreshes inventory-hub/.build_info
# after every commit so the dashboard badge always advertises the current SHA.
#
# Per-clone setup (git doesn't ship hooks via the repo). Run once after
# cloning. Idempotent — safe to re-run.
#
# Usage:  bash inventory-hub/setup-and-rebuild/install_build_info_hook.sh

set -e

repo_root="$(git rev-parse --show-toplevel)"
hook_path="$repo_root/.git/hooks/post-commit"
helper_rel="inventory-hub/_gen_build_info.py"
helper_abs="$repo_root/$helper_rel"

if [ ! -f "$helper_abs" ]; then
  echo "ERROR: $helper_abs not found — wrong repo?" >&2
  exit 1
fi

cat > "$hook_path" <<EOF
#!/usr/bin/env bash
# Auto-installed by inventory-hub/setup-and-rebuild/install_build_info_hook.sh
# Refreshes the dashboard badge SHA after every commit. Safe to delete.
python3 "$helper_abs" >/dev/null 2>&1 || true
EOF
chmod +x "$hook_path"

echo "Installed $hook_path"
echo "Test it by making a trivial commit; inventory-hub/.build_info will tick."
