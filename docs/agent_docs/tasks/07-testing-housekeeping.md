# Group 7: Testing Housekeeping

**Branch name:** `feature/testing-housekeeping`
**Estimated effort:** ~1–1.5 hours
**Risk:** Low — test infrastructure only, no production code changes

## Goal

Fix the broken test and migrate existing test files to use shared `conftest.py` fixtures.

## Items to Complete

### 7.1 — Fix `test_return_and_breadcrumb.py` mock signature
**Buglist ref:** L153
**What:** Test fails with `TypeError: fake_move() got an unexpected keyword argument 'confirm_active_print'`. The `perform_smart_move` function gained a `confirm_active_print` parameter but the test's mock wasn't updated.

**Fix:** Open `inventory-hub/tests/test_return_and_breadcrumb.py`, find the `fake_move` lambda/function, add `confirm_active_print=None` (or `**kwargs`). Verify the test then passes and asserts correct behavior.

**Acceptance criteria:**
- [ ] `test_return_and_breadcrumb.py` passes
- [ ] Mock signature matches current `perform_smart_move` signature

### 7.2 — Migrate test files to shared conftest.py fixtures
**Buglist ref:** L152
**What:** `conftest.py` has shared fixtures (`page`, `api_base_url`, `snapshot`, `scan`, `seed_dryer_box`, `with_held_spool`, `require_server`). Existing test files still duplicate setup.

**Files to migrate:**
- All `test_*.py` under `inventory-hub/tests/`
- Root-level `test_*.py` files in `inventory-hub/` (evaluate moving to `tests/` dir)

**Process per file:**
1. Identify duplicated setup code
2. Replace with `conftest.py` fixture usage
3. Run to verify

**Acceptance criteria:**
- [ ] No duplicated setup sequences across test files
- [ ] All tests use shared fixtures
- [ ] All tests pass after migration

## Testing Checklist

- [ ] `pytest inventory-hub/tests/ -v` — all pass
- [ ] `test_return_and_breadcrumb.py` specifically passes

## Dependencies

- None.
