"""Group 66.9: Merge manufacturer, the page half.

The manufacturer editor's 🔗 Merge… opens the merge window (inv_vendor_merge.js): the
possible duplicates first, then every manufacturer; a row opens the question, whose words
are the server's dry-run plan; its yes posts the merge. After a merge, vendor:merged
{from, into, vendor, moved} goes out first, so every open window stops holding the deleted
id: the editor, the Filament window, Edit Filament, the wizard and the weigh-out list.

Hermetic, on the shared Edit Filament page (tests/edit_filament_harness.py: the real
modals_details.html, overlay_mount.js, inv_core.js, inv_details.js, now with
inv_vendor_merge.js), the wizard's page (test_wizard_price_mark_54_8's `wiz`) and the
weigh-out page (test_weigh_out_scan_focus_js's `wo`), so it runs under --offline. Derek's
Sunlu pair is the data (#4 with 42 filaments and 167 g; #35 with 4 and External ID
"Sunlu"); tests may name his setup.

Not here: a scan's Enter on a row or the question (the scan accumulator's shared rule,
enterIsAScan, pinned by its own tests), and the contrast and text-size guards (the
browser run, tests/test_contrast_guard.py).

RED on the base (dev c5cb19ff): the editor has no 🔗 Merge… and no same-name note, the
module doesn't exist, and nothing listens for vendor:merged.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from edit_filament_harness import errors, filament, load, open_form, posts_to
from test_weigh_out_scan_focus_js import wo  # noqa: F401 (the weigh-out page)
from test_wizard_price_mark_54_8 import wiz  # noqa: F401 (the wizard's page)
from test_scanner_safe_dialogs_61_js import page61  # noqa: F401 (the real processScan)

HIDDEN_VENDOR = "#wiz-fil-vendor-sel"

SUNLU4 = {"id": 4, "name": "Sunlu", "empty_spool_weight": 167.0, "external_id": "", "extra": {},
          "registered": "2026-02-11T10:00:00Z"}
SUNLU35 = {"id": 35, "name": "Sunlu", "empty_spool_weight": None, "external_id": "Sunlu", "extra": {},
           "registered": "2026-02-25T10:00:00Z"}
OVERTURE = {"id": 1, "name": "Overture", "empty_spool_weight": None, "external_id": "", "extra": {},
            "registered": "2026-02-11T09:00:00Z"}
ACME = {"id": 50, "name": "<b>Acme & Co</b>", "empty_spool_weight": None, "external_id": "", "extra": {},
        "registered": "2026-03-01T00:00:00Z"}
VENDORS = {"success": True, "vendors": [SUNLU4, SUNLU35, OVERTURE, ACME]}
SUNLU4_AFTER = dict(SUNLU4, external_id="Sunlu")


def row(v, filaments):
    return {"id": v["id"], "name": v["name"], "filaments": filaments,
            "empty_spool_weight": v["empty_spool_weight"], "external_id": v["external_id"] or "",
            "registered": v["registered"]}


ROWS = {4: row(SUNLU4, 42), 35: row(SUNLU35, 4), 1: row(OVERTURE, 9), 50: row(ACME, 0)}


def options(vid, groups=None):
    others = [ROWS[i] for i in (4, 35) if i != vid and vid in (4, 35)]
    return {"success": True, "vendor": ROWS[vid], "twins": others,
            "groups": [{"kind": "same_name", "ids": [4, 35], "keep": 4, "mine": vid in (4, 35)}] if groups is None else groups,
            "vendors": sorted(ROWS.values(), key=lambda r: (r["name"].lower(), r["id"]))}


PLAN = {"success": True, "dry_run": True, "default_keep": 4, "plan": {
    "source": ROWS[35], "target": ROWS[4],
    "filaments": [{"id": 160, "name": "Orange", "material": "PETG"}, {"id": 161, "name": "Pink", "material": "PETG"},
                  {"id": 162, "name": "Green", "material": "PETG"}, {"id": 163, "name": "Yellow", "material": "PETG"}],
    "carry": {"external_id": "Sunlu"}, "carry_words": ["External ID “Sunlu”"],
    "kept_own": {}, "kept_own_words": [], "label_change": False, "weight_note": None}}
MERGED = {"success": True, "source_vendor_id": 35, "target_vendor_id": 4, "vendor": SUNLU4_AFTER,
          "moved_filament_ids": [160, 161, 162, 163], "carried": ["external_id"], "kept_own": {},
          "label_change": False, "labels_flagged": None,
          "msg": "Merged Sunlu #35 into Sunlu #4: 4 filaments moved, Sunlu #35 deleted."}
PARTIAL = {"success": False, "source_kept": True, "moved_filament_ids": [160, 161, 163], "still_on_source": [162],
           "vendor": SUNLU4_AFTER, "labels_flagged": None,
           "filament_errors": [{"filament_id": 162, "error": "Spoolman refused it: database is locked"}],
           "msg": ("Moved 3 of 4 filaments onto Sunlu #4. Sunlu #35 still holds #162, so it was kept. "
                   "#162: Spoolman refused it: database is locked. Press Merge again to finish.")}


@pytest.fixture
def vm(isolated_page):
    page = load(isolated_page, {
        "/api/vendors": VENDORS,
        "/api/vendors/35/merge_options": options(35),
        "/api/vendors/4/merge_options": options(4),
        "/api/vendors/1/merge_options": options(1, groups=[]),
    }, extra_modules=("inv_vendor_merge.js",))
    page.evaluate("""() => { window.__ev = [];
        ['vendor:merged', 'vendor:updated', 'inventory:sync-pulse'].forEach((t) =>
            document.addEventListener(t, (e) => window.__ev.push([t, e.detail || null]))); }""")
    return page


@pytest.fixture
def ef(isolated_page):
    """The same page without the merge module: the listeners need none (the tests send
    vendor:merged themselves), so on the base they run and fail because nothing listens."""
    return load(isolated_page, {"/api/vendors": VENDORS})


def _answer_merge(page, plan=PLAN, merge=MERGED, src=35, dst=4):
    """POST /api/vendors/<src>/merge_into/<dst>: the plan for a dry run, else `merge`
    ('__hold__' / '__reject__' pass through as the harness reads them)."""
    page.evaluate("""(a) => { window.__answers['POST /api/vendors/' + a.src + '/merge_into/' + a.dst] =
        (req) => (req.body && req.body.dry_run) ? a.plan : a.merge; }""",
                  {"plan": plan, "merge": merge, "src": src, "dst": dst})


def _open_editor(page, vid=35):
    page.evaluate("(v) => window.openVendorEditModal(v)", vid)
    page.wait_for_function("() => document.getElementById('vendorEditModal').classList.contains('show')")
    page.wait_for_timeout(60)


def _note(page):
    return page.evaluate("""() => { const n = document.getElementById('vendoredit-twin-note');
        return n.classList.contains('d-none') ? '' : n.textContent; }""")


def _merge_button_shown(page):
    return page.evaluate("() => !document.getElementById('vendoredit-merge').classList.contains('d-none')")


def _open_window(page, vid=35):
    _open_editor(page, vid)
    page.locator("#vendoredit-merge").click()
    page.wait_for_function("() => !!document.querySelector('#fcc-vendor-merge [data-vm-body][data-vm-state=\"ready\"]')")


def _rows(page):
    return page.evaluate("""() => Array.from(document.querySelectorAll('#fcc-vendor-merge button.fcc-vm-row'))
        .map((r) => ({ src: r.dataset.vmSrc, dst: r.dataset.vmDst, text: r.innerText.replace(/\\s+/g, ' ').trim(),
                       active: r.classList.contains('kb-active'), tab: r.tabIndex }))""")


def _question_up(page):
    return page.evaluate("() => !!(window.getOverlay && window.getOverlay('fcc-vendor-merge-confirm'))")


def _q(page):
    return page.evaluate("""() => { const el = document.querySelector('#fcc-vendor-merge-confirm');
        if (!el) return null;
        const b = (w) => { const x = el.querySelector('[data-vmq=\"' + w + '\"]'); return x ? { text: x.textContent, off: x.disabled } : null; };
        return { title: el.querySelector('[data-vmq-title]').textContent,
                 lines: Array.from(el.querySelectorAll('[data-vmq-lines] li')).map((li) => li.textContent),
                 flash: el.querySelector('[data-vmq-flash]').textContent,
                 cancel: b('cancel'), swap: b('swap'), yes: b('yes'),
                 focus: document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.vmq || null : null }; }""")


def _plan_painted(page):
    page.wait_for_function("""() => { const y = document.querySelector('#fcc-vendor-merge-confirm [data-vmq=\"yes\"]');
        return !!y && !y.disabled; }""")


def _merge_posts(page, src=35, dst=4):
    return [p for p in posts_to(page, f"/api/vendors/{src}/merge_into/{dst}") if not (p["body"] or {}).get("dry_run")]


# --- the editor ---------------------------------------------------------------------

def test_merge_shows_for_an_existing_manufacturer_and_names_its_twin(vm):
    _open_editor(vm, 35)
    assert _merge_button_shown(vm)
    assert _note(vm) == "⚠️ Another manufacturer has this name: Sunlu #4 (42 filaments). 🔗 Merge… combines them."
    vm.evaluate("() => window.openVendorCreateModal({})")
    vm.wait_for_timeout(40)
    assert not _merge_button_shown(vm) and _note(vm) == ""
    assert errors(vm) == []


def test_no_note_without_a_twin_or_when_the_list_couldnt_be_read(vm):
    _open_editor(vm, 1)
    assert _merge_button_shown(vm) and _note(vm) == ""
    vm.evaluate("() => { window.__answers['/api/vendors/35/merge_options'] = { __status: 502, __body: { success: false, msg: 'x' } }; }")
    _open_editor(vm, 35)
    assert _note(vm) == ""            # no claim either way


def test_merge_is_refused_with_unsaved_changes_and_during_a_save(vm):
    _open_editor(vm, 35)
    vm.fill("#vendoredit-comment", "typed but not saved")
    vm.locator("#vendoredit-merge").click()
    vm.wait_for_timeout(40)
    assert not vm.evaluate("() => !!window.getOverlay('fcc-vendor-merge')")
    assert "Save or Cancel your changes first" in vm.locator("#vendoredit-error").inner_text()
    vm.fill("#vendoredit-comment", "")
    vm.evaluate("() => { window.__answers['PATCH /api/vendors/35'] = '__hold__'; }")
    vm.locator("#vendoredit-save").click()
    vm.wait_for_timeout(30)
    vm.evaluate("() => { document.getElementById('vendoredit-merge').click(); }")
    vm.wait_for_timeout(40)
    assert not vm.evaluate("() => !!window.getOverlay('fcc-vendor-merge')")
    assert vm.locator("#vendoredit-error").inner_text() == "The manufacturer is saving: wait for it, then merge."


# --- the window ---------------------------------------------------------------------

def test_the_window_lists_the_pair_first_then_every_manufacturer(vm):
    _open_window(vm, 35)
    assert vm.evaluate("() => document.activeElement && document.activeElement.matches('[data-vm-box]')")
    rows = _rows(vm)
    assert rows[0]["src"] == "35" and rows[0]["dst"] == "4"
    assert "keep Sunlu #4" in rows[0]["text"] and "42 filaments · 167 g empty" in rows[0]["text"]
    assert "merge Sunlu #35" in rows[0]["text"] and "4 filaments · no empty weight" in rows[0]["text"]
    assert "open in the editor" in rows[0]["text"] and "same name" in rows[0]["text"]
    # Every other manufacturer, by name; the open one is listed but is no button.
    assert [(r["src"], r["dst"]) for r in rows[1:]] == [("50", "35"), ("1", "35"), ("4", "35")]
    body = vm.evaluate("() => document.querySelector('#fcc-vendor-merge [data-vm-body]').innerHTML")
    assert "&lt;b&gt;Acme &amp; Co&lt;/b&gt; #50" in body and "<b>Acme" not in body
    assert vm.evaluate("() => !!document.querySelector('#fcc-vendor-merge .fcc-vm-row-open')")
    assert errors(vm) == []


def test_a_read_that_fails_says_so_and_never_no_duplicates(vm):
    for answer in ({"__status": 502, "__body": {"success": False,
                    "msg": "Couldn't read the manufacturers from Spoolman, so the list can't be shown. Try again in a moment."}},
                   "__reject__"):
        vm.evaluate("(a) => { window.__answers['/api/vendors/35/merge_options'] = a; }", answer)
        _open_editor(vm, 35)
        vm.locator("#vendoredit-merge").click()
        vm.wait_for_function("() => !!document.querySelector('#fcc-vendor-merge [data-vm-fail]')")
        text = vm.locator("#fcc-vendor-merge [data-vm-body]").inner_text()
        assert text.startswith("⚠️ Couldn't read the manufacturers: ") and "No two manufacturers" not in text
        assert vm.locator("#fcc-vendor-merge [data-vm-retry]").count() == 1
        vm.keyboard.press("Escape")
        vm.wait_for_timeout(750)   # past the double-click shield its press armed (Group 62.3)


def test_only_the_newest_read_paints(vm):
    _open_editor(vm, 35)
    vm.evaluate("() => { window.__answers['/api/vendors/35/merge_options'] = '__hold__'; }")
    vm.locator("#vendoredit-merge").click()
    vm.wait_for_timeout(30)
    assert "Reading the manufacturers" in vm.locator("#fcc-vendor-merge [data-vm-body]").inner_text()
    # Close and open again: the first window's late answer paints nothing anywhere.
    vm.keyboard.press("Escape")
    vm.wait_for_timeout(750)      # past the double-click shield its last press armed (Group 62.3)
    vm.evaluate("(a) => { window.__answers['/api/vendors/35/merge_options'] = a; }", options(35))
    vm.locator("#vendoredit-merge").click()
    vm.wait_for_function("() => !!document.querySelector('#fcc-vendor-merge [data-vm-body][data-vm-state=\"ready\"]')")
    before = len(_rows(vm))
    vm.evaluate("(o) => window.__held['/api/vendors/35/merge_options'](o)", options(35, groups=[]))
    vm.wait_for_timeout(60)
    assert len(_rows(vm)) == before
    assert errors(vm) == []


def test_the_arrows_move_across_both_lists_and_slash_goes_back_to_the_box(vm):
    _open_window(vm, 35)
    vm.keyboard.press("ArrowDown")
    rows = _rows(vm)
    assert rows[0]["active"] and rows[0]["tab"] == 0 and all(r["tab"] == -1 for r in rows[1:])
    vm.keyboard.press("ArrowDown")
    assert _rows(vm)[1]["active"]
    vm.keyboard.press("ArrowUp")
    vm.keyboard.press("ArrowUp")          # wraps to the last
    assert _rows(vm)[-1]["active"]
    vm.keyboard.press("/")
    assert vm.evaluate("() => document.activeElement.matches('[data-vm-box]')")
    vm.keyboard.press("Enter")            # in the box: picks nothing
    vm.wait_for_timeout(40)
    assert not _question_up(vm)


def test_typing_filters_both_lists(vm):
    _open_window(vm, 35)
    vm.locator("#fcc-vendor-merge [data-vm-box]").type("over")
    rows = _rows(vm)
    assert [(r["src"], r["dst"]) for r in rows] == [("1", "35")]
    assert "No possible duplicate matches “over”." in vm.locator("#fcc-vendor-merge [data-vm-body]").inner_text()


# --- the question -------------------------------------------------------------------

def test_a_row_opens_the_question_on_cancel_with_the_servers_plan(vm):
    _answer_merge(vm)
    vm.evaluate("() => { window.__answers['POST /api/vendors/35/merge_into/4'] = ((f) => (req) => "
                "(req.body && req.body.dry_run) ? '__hold__' : f(req))(window.__answers['POST /api/vendors/35/merge_into/4']); }")
    _open_window(vm, 35)
    vm.locator("#fcc-vendor-merge button.fcc-vm-row").first.click()
    vm.wait_for_timeout(40)
    q = _q(vm)
    assert q["lines"] == ["Checking what moves…"] and q["yes"]["off"] and q["focus"] == "cancel"
    vm.evaluate("(p) => window.__held['/api/vendors/35/merge_into/4'](p)", PLAN)
    _plan_painted(vm)
    q = _q(vm)
    assert q["title"] == "🔗 Merge Sunlu #35 into Sunlu #4?"
    assert q["lines"] == [
        "✓ Keep Sunlu #4: 42 filaments, 167 g empty.",
        "🗑️ Delete Sunlu #35: its 4 filaments move to Sunlu #4 (#160 PETG Orange, #161 PETG Pink, #162 PETG Green"
        " and 1 more), their spools with them.",
        "↪ Sunlu #4 takes Sunlu #35's External ID “Sunlu” (its own is blank).",
    ]
    assert q["swap"]["text"] == "⇄ Keep Sunlu #35 instead" and q["yes"]["text"] == "🔗 Merge into Sunlu #4"
    assert vm.locator("#fcc-vendor-merge-confirm .fcc-vmq-final").inner_text() == "A merge can't be undone."
    # It holds scans while it is up.
    assert vm.evaluate("() => (window._fccOpenMoveQuestions || []).some((q) => q.title === 'Merge manufacturers')")
    assert _merge_posts(vm) == []


def test_cancel_and_escape_close_it_and_merge_nothing(vm):
    _answer_merge(vm)
    _open_window(vm, 35)
    vm.locator("#fcc-vendor-merge button.fcc-vm-row").first.click()
    _plan_painted(vm)
    vm.keyboard.press("Escape")
    vm.wait_for_timeout(40)
    assert not _question_up(vm) and vm.evaluate("() => !!window.getOverlay('fcc-vendor-merge')")
    assert vm.evaluate("() => (window._fccOpenMoveQuestions || []).length") == 0
    vm.wait_for_timeout(750)      # past the double-click shield its last press armed (Group 62.3)
    vm.locator("#fcc-vendor-merge button.fcc-vm-row").first.click()
    _plan_painted(vm)
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="cancel"]').click()
    vm.wait_for_timeout(40)
    assert not _question_up(vm)
    assert _merge_posts(vm) == []


def test_the_yes_waits_out_a_double_click_but_a_keyboard_click_goes_at_once(vm):
    _answer_merge(vm)
    vm.evaluate("() => { window.fccQuestionArmMs = 60000; }")      # armed far longer than the test
    _open_window(vm, 35)
    vm.locator("#fcc-vendor-merge button.fcc-vm-row").first.click()
    _plan_painted(vm)
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()       # a pointer, while armed
    vm.wait_for_timeout(40)
    assert _merge_posts(vm) == []
    vm.evaluate("""() => document.querySelector('#fcc-vendor-merge-confirm [data-vmq="yes"]')
        .dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 0 }))""")
    vm.wait_for_timeout(80)
    assert len(_merge_posts(vm)) == 1


def test_swap_asks_the_plan_the_other_way_and_a_late_plan_paints_nothing(vm):
    _answer_merge(vm)
    swapped = {"success": True, "dry_run": True, "default_keep": 4, "plan": dict(
        PLAN["plan"], source=ROWS[4], target=ROWS[35], carry={"empty_spool_weight": 167.0},
        carry_words=["empty spool weight 167 g"], filaments=[{"id": 100, "name": "Black", "material": "PLA"}])}
    vm.evaluate("(p) => { window.__answers['POST /api/vendors/4/merge_into/35'] = (req) => (req.body && req.body.dry_run) ? p : null; }",
                swapped)
    _open_window(vm, 35)
    vm.locator("#fcc-vendor-merge button.fcc-vm-row").first.click()
    _plan_painted(vm)
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="swap"]').click()
    _plan_painted(vm)
    q = _q(vm)
    assert q["title"] == "🔗 Merge Sunlu #4 into Sunlu #35?" and q["focus"] == "swap"
    assert "↪ Sunlu #35 takes Sunlu #4's empty spool weight 167 g (its own is blank)." in q["lines"]
    assert errors(vm) == []


def test_a_full_list_row_the_server_would_keep_the_other_way_is_asked_swapped(vm):
    """Picked from the full list as (Sunlu #4 → the open Sunlu #35); the server keeps #4,
    so the question asks #35 → #4 before drawing anything."""
    _answer_merge(vm)
    vm.evaluate("(p) => { window.__answers['POST /api/vendors/4/merge_into/35'] = (req) => p; }",
                dict(PLAN, plan=dict(PLAN["plan"], source=ROWS[4], target=ROWS[35])))
    _open_window(vm, 35)
    vm.locator('#fcc-vendor-merge button.fcc-vm-row[data-vm-src="4"]').click()
    _plan_painted(vm)
    assert _q(vm)["title"] == "🔗 Merge Sunlu #35 into Sunlu #4?"


# --- outcomes -----------------------------------------------------------------------

def test_a_merge_tells_every_window_then_reads_again_and_says_so(vm):
    _answer_merge(vm)
    _open_window(vm, 35)
    vm.locator("#fcc-vendor-merge button.fcc-vm-row").first.click()
    _plan_painted(vm)
    vm.evaluate("""(a) => { window.__answers['/api/vendors'] = a.vendors;
        window.__answers['/api/vendors/4/merge_options'] = a.after; }""",
                {"vendors": {"success": True, "vendors": [SUNLU4_AFTER, OVERTURE, ACME]},
                 "after": dict(options(4, groups=[]), twins=[], vendors=[ROWS[50], ROWS[1], ROWS[4]])})
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()
    vm.wait_for_timeout(150)
    assert len(_merge_posts(vm)) == 1
    ev = vm.evaluate("window.__ev")
    assert [e[0] for e in ev] == ["vendor:merged", "vendor:updated", "inventory:sync-pulse"]
    assert ev[0][1]["from"] == "35" and ev[0][1]["into"] == "4" and ev[0][1]["moved"] == [160, 161, 162, 163]
    assert ev[1][1]["id"] == "4" and ev[1][1]["vendor"]["external_id"] == "Sunlu"
    assert not _question_up(vm)
    assert vm.evaluate("() => (window._fccOpenMoveQuestions || []).length") == 0
    # The window follows the editor to the kept one, reads again and says the server's words.
    notice = vm.locator("#fcc-vendor-merge [data-vm-notice]")
    assert notice.inner_text() == MERGED["msg"]
    assert vm.locator("#vendoredit-id").input_value() == "4"
    assert vm.locator("#vendoredit-external-id").input_value() == "Sunlu"
    assert errors(vm) == []


def test_a_refused_or_partial_merge_stays_on_the_question_and_can_be_pressed_again(vm):
    _answer_merge(vm, merge={"__status": 502, "__body": PARTIAL})
    _open_window(vm, 35)
    vm.locator("#fcc-vendor-merge button.fcc-vm-row").first.click()
    _plan_painted(vm)
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()
    vm.wait_for_timeout(120)
    _plan_painted(vm)
    q = _q(vm)
    assert q["flash"] == PARTIAL["msg"] and q["focus"] == "cancel"
    assert vm.evaluate("window.__ev.map((e) => e[0])") == ["vendor:updated", "inventory:sync-pulse"]
    assert _question_up(vm)
    notice = vm.locator("#fcc-vendor-merge [data-vm-notice]")
    assert notice.inner_text() == PARTIAL["msg"] and notice.get_attribute("data-tone") == "warn"


def test_after_a_refusal_the_yes_is_armed_again_and_a_keyboard_click_presses_it(vm):
    """The plan asked again after a refusal arms the yes again: a double click's second
    press posts nothing, a keyboard's click goes, and a press again carries the merge on."""
    _answer_merge(vm, merge={"__status": 502, "__body": PARTIAL})
    _open_window(vm, 35)
    vm.locator("#fcc-vendor-merge button.fcc-vm-row").first.click()
    _plan_painted(vm)
    vm.evaluate("() => { window.fccQuestionArmMs = 60000; }")
    vm.evaluate("""() => document.querySelector('#fcc-vendor-merge-confirm [data-vmq="yes"]')
        .dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 0 }))""")
    vm.wait_for_timeout(120)
    _plan_painted(vm)
    n = len(_merge_posts(vm))
    assert n == 1
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()          # armed: nothing
    vm.wait_for_timeout(40)
    assert len(_merge_posts(vm)) == n
    vm.evaluate("""() => document.querySelector('#fcc-vendor-merge-confirm [data-vmq="yes"]')
        .dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 0 }))""")
    vm.wait_for_timeout(60)
    assert len(_merge_posts(vm)) == n + 1
    assert all((p["body"] or {}).get("merge") is True for p in _merge_posts(vm))


def test_no_answer_says_it_may_not_have_finished_and_logs_it(vm):
    _answer_merge(vm, merge="__reject__")
    _open_window(vm, 35)
    vm.locator("#fcc-vendor-merge button.fcc-vm-row").first.click()
    _plan_painted(vm)
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()
    vm.wait_for_timeout(120)
    assert _q(vm)["flash"].startswith("FCC didn't answer, so the merge may not have finished.")
    logged = posts_to(vm, "/api/log_event")
    assert len(logged) == 1 and "may not have finished" in str(logged[0]["body"])


def test_closing_the_editor_closes_both_and_frees_the_scans(vm):
    _answer_merge(vm)
    _open_window(vm, 35)
    vm.locator("#fcc-vendor-merge button.fcc-vm-row").first.click()
    _plan_painted(vm)
    vm.evaluate("() => bootstrap.Modal.getInstance(document.getElementById('vendorEditModal')).hide()")
    vm.wait_for_timeout(80)
    assert not _question_up(vm) and not vm.evaluate("() => !!window.getOverlay('fcc-vendor-merge')")
    assert vm.evaluate("() => (window._fccOpenMoveQuestions || []).length") == 0


def test_another_bootstrap_window_opening_closes_the_window(vm):
    _open_window(vm, 35)
    vm.evaluate("() => bootstrap.Modal.getOrCreateInstance(document.getElementById('filamentModal')).show()")
    vm.wait_for_timeout(40)
    assert not vm.evaluate("() => !!window.getOverlay('fcc-vendor-merge')")


# --- the listeners: nothing holds the deleted id --------------------------------------

def _merged_event(page, frm=35, into=4, vendor=SUNLU4_AFTER):
    page.evaluate("""(a) => document.dispatchEvent(new CustomEvent('vendor:merged', { detail:
        { from: String(a.frm), into: String(a.into), vendor: a.vendor, moved: [] } }))""",
                  {"frm": frm, "into": into, "vendor": vendor})
    page.wait_for_timeout(80)


def test_edit_filament_takes_the_kept_one_and_its_save_sends_no_manufacturer_change(ef):
    open_form(ef, filament(vendor=dict(SUNLU35)))
    assert ef.locator("#editfil-vendor-id").input_value() == "35"
    _merged_event(ef)
    assert ef.locator("#editfil-vendor-id").input_value() == "4"
    assert ef.locator("#editfil-vendor-name").input_value() == "Sunlu"
    assert ef.evaluate("() => document.getElementById('editfil-vendor-new-badge').style.display") == "none"
    ef.fill("#editfil-name", "Red Two")
    ef.locator("#editfil-save").click()
    ef.wait_for_timeout(150)
    sent = posts_to(ef, "/api/update_filament")
    assert len(sent) == 1 and "vendor_id" not in (sent[0]["body"].get("data") or {}), sent
    assert posts_to(ef, "/api/vendors") == []
    assert errors(ef) == []


def test_a_list_read_sent_before_the_merge_never_brings_the_merged_one_back(ef):
    open_form(ef, filament(vendor=dict(SUNLU4)))
    ef.evaluate("() => { window.__answers['/api/vendors'] = '__hold__'; }")
    ef.evaluate("(v) => document.dispatchEvent(new CustomEvent('vendor:updated', { detail: { id: '1', vendor: v } }))", OVERTURE)
    ef.wait_for_timeout(40)
    ef.evaluate("() => { window.__held_before = window.__held['/api/vendors']; window.__answers['/api/vendors'] = '__reject__'; }")
    _merged_event(ef)
    ef.evaluate("(v) => window.__held_before(v)", VENDORS)       # the old list, #35 in it
    ef.wait_for_timeout(80)
    ef.fill("#editfil-vendor-name", "Sun")
    ef.evaluate("() => document.getElementById('editfil-vendor-name').dispatchEvent(new Event('input', { bubbles: true }))")
    ef.wait_for_timeout(40)
    items = ef.evaluate("() => Array.from(document.querySelectorAll('#editfil-vendor-dropdown [data-value]')).map((d) => d.dataset.value)")
    assert "4" in items and "35" not in items, items


def test_the_filament_window_names_the_kept_one(ef):
    ef.evaluate("() => { const b = document.getElementById('fil-detail-vendor'); b.dataset.vendorId = '35'; b.innerText = 'Sunlu'; }")
    _merged_event(ef)
    assert ef.evaluate("() => document.getElementById('fil-detail-vendor').dataset.vendorId") == "4"


def test_the_weigh_out_list_reads_the_kept_ones_weight(wo):
    from test_quick_weigh_scan_js import press
    from test_weigh_out_scan_focus_js import _saved, _updates
    page, open_ = wo
    page.evaluate(r"""() => {
        window.__spools[11] = { id: 11, initial_weight: 1000, used_weight: 0,
            filament: { id: 6, name: 'Grey Two', material: 'PLA', vendor: { id: 35, name: 'Sunlu' } } };
        window.__rows[11] = { id: 11, display: 'Sunlu - PLA - Grey Two', color: '888888', remaining_weight: 1000 };
    }""")
    open_(held=(11,), mode="gross")
    page.evaluate("""() => document.dispatchEvent(new CustomEvent('vendor:merged', { detail: {
        from: '35', into: '4', vendor: { id: 4, name: 'Sunlu', empty_spool_weight: 167 }, moved: [6] } }))""")
    page.focus('.weigh-input[data-id="11"]')
    press(page, "1167", 150)            # 1167 g less the kept Sunlu's 167 g: 1000 g left
    _saved(page)
    ups = _updates(page)
    assert [u["id"] for u in ups] == [11] and ups[0]["updates"]["used_weight"] == 0, ups


def test_the_wizard_takes_the_kept_one_and_follows_its_baselines(wiz):
    from test_wizard_vendor_66_1 import _open_edit_with, _brand, HIDDEN, EDIT
    from test_wizard_label_status_58_5 import _save
    _open_edit_with(wiz, {"success": True, "vendors": [_brand(2), _brand(4, "Other")]})
    assert wiz.locator(HIDDEN).input_value() == "2"
    wiz.evaluate("""() => { window.__answers['/api/external/vendors'] = { success: true, vendors:
        [{ id: 4, name: 'Other', empty_spool_weight: null, external_id: '', extra: {} }] }; }""")
    wiz.evaluate("""() => document.dispatchEvent(new CustomEvent('vendor:merged', { detail: {
        from: '2', into: '4', vendor: { id: 4, name: 'Other', empty_spool_weight: null, external_id: '', extra: {} }, moved: [7] } }))""")
    wiz.wait_for_timeout(200)
    assert wiz.locator(HIDDEN).input_value() == "4"
    assert wiz.evaluate("() => wizardState.editFilamentOriginal.vendor_id") == "4"
    assert not wiz.evaluate("() => (wizardState.vendors || []).some((v) => String(v.id) === '2')")
    body = _save(wiz, EDIT)
    # Unchanged since the merge re-pointed the baseline: left out (Group 66.9 review: Edit
    # Spool sends a manufacturer only when it changed), so the filament keeps #4.
    assert body["filament_data"].get("vendor_id") is None


# --- review round 1 (2026-11-26): the page findings, pinned ---------------------------------

SWAPPED = {"success": True, "dry_run": True, "default_keep": 4, "plan": dict(
    PLAN["plan"], source=ROWS[4], target=ROWS[35], carry={"empty_spool_weight": 167.0},
    carry_words=["empty spool weight 167 g"], filaments=[{"id": 100, "name": "Black", "material": "PLA"}])}


def test_a_double_click_on_swap_swaps_once(vm):
    """P-S1: the plan repaints in a few ms, ⇄ enabled where it was, and a double click's
    second press swapped back."""
    _answer_merge(vm)
    vm.evaluate("(p) => { window.__answers['POST /api/vendors/4/merge_into/35'] = (req) => p; }", SWAPPED)
    _open_window(vm, 35)
    vm.locator("#fcc-vendor-merge button.fcc-vm-row").first.click()
    _plan_painted(vm)
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="swap"]').dblclick()
    vm.wait_for_timeout(150)
    _plan_painted(vm)
    assert _q(vm)["title"] == "🔗 Merge Sunlu #4 into Sunlu #35?"
    dry = [p for p in vm.evaluate("window.__posts") if "/merge_into/" in p["url"] and (p["body"] or {}).get("dry_run")]
    assert [p["url"].split("/api/vendors/")[1] for p in dry] == ["35/merge_into/4", "4/merge_into/35"]


def test_a_merge_whose_answer_was_lost_but_finished_is_told_as_one(vm):
    """P-S9: the source gone and the kept one there after a lost answer means the merge
    finished: the windows hear it, never "nothing was merged"."""
    _answer_merge(vm, merge="__reject__")
    _open_window(vm, 35)
    vm.locator("#fcc-vendor-merge button.fcc-vm-row").first.click()
    _plan_painted(vm)
    vm.evaluate("""(a) => { window.__answers['/api/vendors'] = a.v; window.__answers['/api/vendors/4/merge_options'] = a.o; }""",
                {"v": {"success": True, "vendors": [SUNLU4_AFTER, OVERTURE, ACME]},
                 "o": dict(options(4, groups=[]), twins=[], vendors=[ROWS[50], ROWS[1], ROWS[4]])})
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()
    vm.wait_for_timeout(200)
    ev = vm.evaluate("window.__ev")
    assert [e[0] for e in ev][:1] == ["vendor:merged"] and ev[0][1]["from"] == "35" and ev[0][1]["into"] == "4"
    assert not _question_up(vm)
    assert vm.locator("#fcc-vendor-merge [data-vm-notice]").inner_text() == \
        "Sunlu #35 is gone from Spoolman: the merge into Sunlu #4 finished."
    assert vm.locator("#vendoredit-id").input_value() == "4"


def test_a_delete_fcc_couldnt_confirm_that_landed_is_told_as_a_merge(vm):
    may = {"success": False, "may_have_deleted": True, "moved_filament_ids": [160, 161, 162, 163],
           "vendor": SUNLU4_AFTER, "msg": "All of Sunlu #35's filaments are on Sunlu #4 now, but FCC couldn't tell…"}
    _answer_merge(vm, merge={"__status": 502, "__body": may})
    _open_window(vm, 35)
    vm.locator("#fcc-vendor-merge button.fcc-vm-row").first.click()
    _plan_painted(vm)
    vm.evaluate("(v) => { window.__answers['/api/vendors'] = v; }",
                {"success": True, "vendors": [SUNLU4_AFTER, OVERTURE, ACME]})
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()
    vm.wait_for_timeout(200)
    ev = vm.evaluate("window.__ev")
    assert ev[0][0] == "vendor:merged" and ev[0][1]["moved"] == [160, 161, 162, 163]


def test_a_failed_reread_after_a_merge_keeps_no_stale_list(vm):
    """P-S3: the next key in the box drew the list from before the merge again."""
    _answer_merge(vm)
    _open_window(vm, 35)
    vm.locator("#fcc-vendor-merge button.fcc-vm-row").first.click()
    _plan_painted(vm)
    vm.evaluate("() => { window.__answers['/api/vendors/4/merge_options'] = { __status: 502, __body: { success: false, msg: 'blip' } }; }")
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()
    vm.wait_for_function("() => !!document.querySelector('#fcc-vendor-merge [data-vm-fail]')")
    assert vm.evaluate("() => document.activeElement.matches('[data-vm-box]')")
    vm.keyboard.type("s")
    vm.wait_for_timeout(40)
    assert vm.locator("#fcc-vendor-merge [data-vm-fail]").count() == 1
    assert "Sunlu #35" not in vm.locator("#fcc-vendor-merge [data-vm-body]").inner_text()


def test_the_keyboard_goes_back_to_the_row_the_question_came_from_lit(vm):
    """P-S4: a mouse pick of a row lower down, then Escape: that row has the keyboard and the ring."""
    _answer_merge(vm)
    vm.evaluate("(p) => { window.__answers['POST /api/vendors/1/merge_into/35'] = (req) => p; }",
                dict(PLAN, default_keep=35, plan=dict(PLAN["plan"], source=ROWS[1], target=ROWS[35])))
    _open_window(vm, 35)
    vm.locator('#fcc-vendor-merge button.fcc-vm-row[data-vm-src="1"]').click()
    _plan_painted(vm)
    vm.keyboard.press("Escape")
    vm.wait_for_timeout(60)
    active = vm.evaluate("""() => { const a = document.activeElement;
        return a && a.dataset ? { src: a.dataset.vmSrc, lit: a.classList.contains('kb-active') } : null; }""")
    assert active == {"src": "1", "lit": True}
    assert [r["src"] for r in _rows(vm) if r["active"]] == ["1"]


def test_a_scan_while_the_merge_is_on_its_way_is_refused_in_its_own_words(vm):
    """P-S8: the hold names the merge on its way, and a cancel that closes nothing says so."""
    _answer_merge(vm, merge="__hold__")
    _open_window(vm, 35)
    vm.locator("#fcc-vendor-merge button.fcc-vm-row").first.click()
    _plan_painted(vm)
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()
    vm.wait_for_timeout(40)
    out = vm.evaluate("""() => { const q = (window._fccOpenMoveQuestions || []).find((x) => x.title === 'Merge manufacturers');
        return { routed: q.route('ID:57'), cancelled: q.cancel() }; }""")
    assert out == {"routed": "refused", "cancelled": False}
    assert _q(vm)["flash"] == "The merge is on its way: wait for its answer."
    assert _question_up(vm)
    vm.evaluate("(m) => window.__held['/api/vendors/35/merge_into/4'](m)", MERGED)
    vm.wait_for_timeout(120)
    assert not _question_up(vm)


def test_a_merge_answer_after_the_window_closed_still_tells_every_window(vm):
    """The merge's answer lands after its host closed the question and the window: the
    events still go out, and a toast says it (there is no window to say it on)."""
    _answer_merge(vm, merge="__hold__")
    _open_window(vm, 35)
    vm.locator("#fcc-vendor-merge button.fcc-vm-row").first.click()
    _plan_painted(vm)
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()
    vm.wait_for_timeout(40)
    vm.evaluate("() => bootstrap.Modal.getInstance(document.getElementById('vendorEditModal')).hide()")
    vm.wait_for_timeout(80)
    vm.evaluate("(m) => window.__held['/api/vendors/35/merge_into/4'](m)", MERGED)
    vm.wait_for_timeout(120)
    assert [e[0] for e in vm.evaluate("window.__ev")][:1] == ["vendor:merged"]
    assert MERGED["msg"] in vm.locator("#toast-container").inner_text()


def test_label_trouble_is_said_on_the_window(vm):
    """P-S5: it was only a toast, under the window."""
    _answer_merge(vm, merge=dict(MERGED, labels_flagged={"spools": [], "filaments": [], "errors": [{"spool_id": 205}]}))
    _open_window(vm, 35)
    vm.locator("#fcc-vendor-merge button.fcc-vm-row").first.click()
    _plan_painted(vm)
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()
    vm.wait_for_timeout(150)
    notice = vm.locator("#fcc-vendor-merge [data-vm-notice]")
    assert "couldn't confirm that every label whose Brand changed is marked for a reprint" in notice.inner_text()
    assert notice.get_attribute("data-tone") == "warn"


def test_one_filament_reads_in_the_singular(vm):
    """P-S6."""
    one = dict(PLAN, plan=dict(PLAN["plan"], filaments=[PLAN["plan"]["filaments"][0]], carry={}, carry_words=[],
                               label_change=True,
                               weight_note={"moved_without_own": [160], "from_g": None, "to_g": 167.0,
                                            "kept_without_own": [101]}))
    _answer_merge(vm, plan=one)
    _open_window(vm, 35)
    vm.locator("#fcc-vendor-merge button.fcc-vm-row").first.click()
    _plan_painted(vm)
    lines = _q(vm)["lines"]
    assert "🗑️ Delete Sunlu #35: its 1 filament moves to Sunlu #4 (#160 PETG Orange), its spools with it." in lines
    assert any(l.startswith("🏷️ Its labels print “Sunlu”") for l in lines)
    assert any(l.startswith("⚖️ It has no empty spool weight of its own: FCC reads 167 g for it") for l in lines)
    assert "⚖️ Sunlu #4's 1 filament with no empty spool weight of its own reads 167 g from now on." in lines


def test_the_editor_is_filled_from_the_kept_record_even_when_a_read_fails(vm):
    """P-S2: the editor was emptied and read again after a merge; a failed read left it
    blank under the kept id, and a Save wiped the kept one's fields."""
    _answer_merge(vm)
    _open_window(vm, 35)
    vm.locator("#fcc-vendor-merge button.fcc-vm-row").first.click()
    _plan_painted(vm)
    vm.evaluate("() => { window.__answers['/api/vendors'] = { __status: 502, __body: { success: false, msg: 'blip' } }; }")
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()
    vm.wait_for_timeout(150)
    boxes = vm.evaluate("""() => ['vendoredit-id', 'vendoredit-name', 'vendoredit-external-id', 'vendoredit-empty-weight']
        .map((id) => document.getElementById(id).value)""")
    assert boxes == ["4", "Sunlu", "Sunlu", "167"]
    assert not vm.evaluate("() => document.getElementById('vendoredit-save').disabled")


def test_with_no_record_the_editor_keeps_what_it_shows_and_saves_nothing(ef):
    ef.evaluate("() => window.openVendorEditModal(35)")
    ef.wait_for_function("() => document.getElementById('vendorEditModal').classList.contains('show')")
    ef.wait_for_timeout(60)
    _merged_event(ef, vendor=None)
    assert ef.locator("#vendoredit-id").input_value() == "35"
    assert ef.evaluate("() => document.getElementById('vendoredit-save').disabled")
    assert "was merged into #4" in ef.locator("#vendoredit-error").inner_text()
    ef.evaluate("() => window.openVendorEditModal(4)")
    ef.wait_for_timeout(80)
    assert not ef.evaluate("() => document.getElementById('vendoredit-save').disabled")


def test_edit_filaments_save_never_sends_its_label_status_back(ef):
    """Listeners S2: its copy of the label status, read at the open, undid a mark made since."""
    open_form(ef, filament(extra={"needs_label_print": False, "sample_printed": True}))
    ef.fill("#editfil-product-url", "https://example.com/new")
    ef.locator("#editfil-save").click()
    ef.wait_for_timeout(150)
    sent = posts_to(ef, "/api/update_filament")
    assert len(sent) == 1
    extra = sent[0]["body"]["data"]["extra"]
    assert "product_url" in extra
    assert "needs_label_print" not in extra and "sample_printed" not in extra, extra


def test_a_row_click_that_is_try_agains_second_press_opens_nothing(vm):
    """_secondPress: ↻ Try again's answer paints the rows under the pointer."""
    vm.evaluate("() => { window.__answers['/api/vendors/35/merge_options'] = { __status: 502, __body: { success: false, msg: 'blip' } }; }")
    _open_editor(vm, 35)
    vm.locator("#vendoredit-merge").click()
    vm.wait_for_function("() => !!document.querySelector('#fcc-vendor-merge [data-vm-retry]')")
    vm.evaluate("(o) => { window.__answers['/api/vendors/35/merge_options'] = o; }", options(35))
    box = vm.locator("#fcc-vendor-merge [data-vm-retry]").bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    vm.mouse.click(x, y)
    vm.wait_for_function("() => !!document.querySelector('#fcc-vendor-merge [data-vm-body][data-vm-state=\"ready\"]')")
    vm.evaluate("""([x, y]) => document.querySelector('#fcc-vendor-merge button.fcc-vm-row')
        .dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 1, clientX: x, clientY: y }))""", [x, y])
    vm.wait_for_timeout(60)
    assert not _question_up(vm)


def test_the_list_draws_each_pair_once(vm):
    """S7 / P2: a pair two groups hold is drawn once, with the first group's kind."""
    dup = dict(options(35), groups=[{"kind": "same_name", "ids": [4, 35], "keep": 4, "mine": True},
                                    {"kind": "look_alike", "ids": [4, 35], "keep": 4, "mine": True}])
    vm.evaluate("(o) => { window.__answers['/api/vendors/35/merge_options'] = o; }", dup)
    _open_window(vm, 35)
    pairs = [r for r in _rows(vm) if r["src"] == "35" and r["dst"] == "4"]
    assert len(pairs) == 1 and "same name" in pairs[0]["text"]
    assert "Possible duplicates (1)" in vm.locator("#fcc-vendor-merge [data-vm-body]").inner_text()


# --- review round 2 (2026-11-26): the page findings, pinned ---------------------------------

GONE35 = {"__status": 404, "__body": {"success": False, "gone": 35,
                                      "msg": "Manufacturer #35 isn't in Spoolman any more: it was merged or deleted already."}}
AFTER = {"success": True, "vendors": [SUNLU4_AFTER, OVERTURE, ACME]}


def _yes_by_keyboard(page):
    """The yes, pressed from the keyboard (a click with detail 0, which the arming never holds)."""
    page.evaluate("""() => document.querySelector('#fcc-vendor-merge-confirm [data-vmq="yes"]')
        .dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 0 }))""")


def _ask_pair(page, vid=35):
    _open_window(page, vid)
    # The pair's row (with the editor on #4, #35's row in the full list is the same pair).
    page.locator('#fcc-vendor-merge button.fcc-vm-row[data-vm-src="35"][data-vm-dst="4"]').first.click()
    _plan_painted(page)


def test_a_partial_merge_refills_the_editor_on_the_kept_one_and_its_save_keeps_the_carry(vm):
    """R2P1: the carry copied External ID "Sunlu" onto #4 before a filament's move was
    refused; the editor on #4 still showed it blank, and its Save sent external_id ''."""
    _answer_merge(vm, merge={"__status": 502, "__body": PARTIAL})
    _ask_pair(vm, 4)
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()
    vm.wait_for_timeout(150)
    assert vm.locator("#vendoredit-external-id").input_value() == "Sunlu"
    vm.keyboard.press("Escape")
    vm.wait_for_timeout(60)
    vm.keyboard.press("Escape")
    vm.wait_for_timeout(750)
    vm.evaluate("(v) => { window.__answers['PATCH /api/vendors/4'] = { success: true, vendor: v }; }", SUNLU4_AFTER)
    vm.fill("#vendoredit-comment", "a note")
    vm.locator("#vendoredit-save").click()
    vm.wait_for_timeout(150)
    sent = [x for x in vm.evaluate("window.__posts") if x["url"].endswith("/api/vendors/4")]
    assert len(sent) == 1 and sent[0]["body"]["data"]["external_id"] == "Sunlu", sent
    assert errors(vm) == []


def test_a_merge_fcc_cant_account_for_turns_the_editors_save_off(vm):
    """R2P1: no answer, and the manufacturers couldn't be read: the editor on the kept one
    can't know what the carry did, so it saves nothing until it is opened again."""
    _answer_merge(vm, merge="__reject__")
    _ask_pair(vm, 4)
    vm.evaluate("() => { window.__answers['/api/vendors'] = { __status: 502, __body: { success: false, msg: 'blip' } }; }")
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()
    vm.wait_for_timeout(200)
    assert vm.evaluate("() => document.getElementById('vendoredit-save').disabled")
    assert "FCC couldn't read manufacturer #4" in vm.locator("#vendoredit-error").inner_text()
    assert vm.locator("#vendoredit-id").input_value() == "4"


def test_an_editor_edited_since_it_filled_keeps_its_boxes_and_saves_nothing(ef):
    """R2P1: a change made in the editor isn't overwritten by another write's record, and
    its Save, which would undo that write, is off."""
    ef.evaluate("() => window.openVendorEditModal(4)")
    ef.wait_for_function("() => document.getElementById('vendorEditModal').classList.contains('show')")
    ef.wait_for_timeout(60)
    ef.fill("#vendoredit-comment", "typed")
    ef.evaluate("""(v) => document.dispatchEvent(new CustomEvent('vendor:updated', { detail: { id: '4', vendor: v } }))""",
                SUNLU4_AFTER)
    ef.wait_for_timeout(60)
    assert ef.locator("#vendoredit-comment").input_value() == "typed"
    assert ef.locator("#vendoredit-external-id").input_value() == ""
    assert ef.evaluate("() => document.getElementById('vendoredit-save').disabled")
    assert "changed while this window was open" in ef.locator("#vendoredit-error").inner_text()


def test_the_editors_own_save_is_no_other_write(ef):
    """R2P1's rule leaves the editor's own Save alone: it closes as before."""
    ef.evaluate("() => window.openVendorEditModal(4)")
    ef.wait_for_function("() => document.getElementById('vendorEditModal').classList.contains('show')")
    ef.wait_for_timeout(60)
    ef.evaluate("(v) => { window.__answers['PATCH /api/vendors/4'] = { success: true, vendor: v }; }",
                dict(SUNLU4, comment="typed"))
    ef.fill("#vendoredit-comment", "typed")
    ef.locator("#vendoredit-save").click()
    ef.wait_for_timeout(200)
    assert "changed while this window was open" not in ef.locator("#vendoredit-error").inner_text()
    assert not ef.evaluate("() => document.getElementById('vendorEditModal').classList.contains('show')")


def test_a_gone_answer_after_a_press_with_no_answer_is_told_as_the_merge(vm):
    """R2S8 / R2P3: the first press had no answer (the merge was still running), and the
    press again was answered 404 `gone`: that is this merge, finished."""
    _answer_merge(vm, merge="__reject__")
    _ask_pair(vm, 35)
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()
    vm.wait_for_timeout(200)
    _plan_painted(vm)
    assert _question_up(vm)
    _answer_merge(vm, merge=GONE35)
    vm.evaluate("(a) => { window.__answers['/api/vendors'] = a.v; window.__answers['/api/vendors/4/merge_options'] = a.o; }",
                {"v": AFTER, "o": dict(options(4, groups=[]), twins=[], vendors=[ROWS[50], ROWS[1], ROWS[4]])})
    _yes_by_keyboard(vm)
    vm.wait_for_timeout(200)
    ev = [e for e in vm.evaluate("window.__ev") if e[0] == "vendor:merged"]
    assert len(ev) == 1 and ev[0][1]["from"] == "35" and ev[0][1]["into"] == "4"
    assert ev[0][1]["vendor"]["external_id"] == "Sunlu"
    assert not _question_up(vm)
    assert vm.locator("#fcc-vendor-merge [data-vm-notice]").inner_text() == \
        "Sunlu #35 is gone from Spoolman: the merge into Sunlu #4 finished."
    assert vm.locator("#vendoredit-id").input_value() == "4"
    assert errors(vm) == []


def test_a_replan_answered_gone_after_a_press_with_no_answer_is_told_as_the_merge(vm):
    """R2S8: the same, met by the plan asked again after the lost answer."""
    vm.evaluate("""(a) => { window.__goneNow = false;
        window.__answers['POST /api/vendors/35/merge_into/4'] = (req) => (req.body && req.body.dry_run)
            ? (window.__goneNow ? a.gone : a.plan) : '__reject__'; }""", {"plan": PLAN, "gone": GONE35})
    _ask_pair(vm, 35)
    vm.evaluate("() => { window.__goneNow = true; }")
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()
    vm.wait_for_timeout(250)
    ev = [e for e in vm.evaluate("window.__ev") if e[0] == "vendor:merged"]
    assert len(ev) == 1 and ev[0][1]["from"] == "35"
    assert not _question_up(vm)


def test_a_manufacturer_gone_before_any_press_is_said_and_never_called_a_merge(vm):
    """R2S8: gone at the first plan, which no press of this question can account for (another
    window's merge, or Spoolman's own page): said, with nothing to try again."""
    _answer_merge(vm, plan=GONE35)
    _open_window(vm, 35)
    vm.locator('#fcc-vendor-merge button.fcc-vm-row[data-vm-src="35"][data-vm-dst="4"]').click()
    vm.wait_for_timeout(200)
    q = _q(vm)
    assert q["lines"] == ["⚠️ Couldn't check the merge: Manufacturer #35 isn't in Spoolman any more: "
                          "it was merged or deleted already."]
    assert vm.locator('#fcc-vendor-merge-confirm [data-vmq="retry"]').count() == 0
    assert not q["cancel"]["off"] and q["swap"]["off"] and q["yes"]["off"]
    assert [e for e in vm.evaluate("window.__ev") if e[0] == "vendor:merged"] == []


def test_after_a_merge_the_first_row_takes_the_keyboard_only_from_where_the_merge_left_it(vm):
    """R2P4: a read slower than the person, who typed in the box meanwhile: the keyboard
    stays in the box with what they typed."""
    _answer_merge(vm)
    _ask_pair(vm, 35)
    vm.evaluate("""() => { window.__answers['/api/vendors'] = { success: true, vendors: [] };
        window.__answers['/api/vendors/4/merge_options'] = '__hold__'; }""")
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()
    vm.wait_for_timeout(150)
    assert vm.evaluate("() => document.activeElement.matches('[data-vm-box]')")
    vm.keyboard.type("ov")
    vm.evaluate("(o) => window.__held['/api/vendors/4/merge_options'](o)",
                dict(options(4, groups=[]), twins=[], vendors=[ROWS[50], ROWS[1], ROWS[4]]))
    vm.wait_for_timeout(100)
    assert vm.evaluate("() => document.activeElement.matches('[data-vm-box]')")
    assert vm.locator("#fcc-vendor-merge [data-vm-box]").input_value() == "ov"


def test_after_a_merge_a_question_opened_meanwhile_keeps_the_keyboard(vm):
    """R2P4: a row picked from the list still drawn from before the merge."""
    _answer_merge(vm)
    vm.evaluate("(p) => { window.__answers['POST /api/vendors/1/merge_into/35'] = (req) => p; }",
                dict(PLAN, default_keep=35, plan=dict(PLAN["plan"], source=ROWS[1], target=ROWS[35])))
    _ask_pair(vm, 35)
    vm.evaluate("""() => { window.__answers['/api/vendors'] = { success: true, vendors: [] };
        window.__answers['/api/vendors/4/merge_options'] = '__hold__'; }""")
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()
    vm.wait_for_timeout(750)
    vm.locator('#fcc-vendor-merge button.fcc-vm-row[data-vm-src="1"]').click()
    _plan_painted(vm)
    vm.evaluate("(o) => window.__held['/api/vendors/4/merge_options'](o)",
                dict(options(4, groups=[]), twins=[], vendors=[ROWS[50], ROWS[1], ROWS[4]]))
    vm.wait_for_timeout(100)
    assert vm.evaluate("() => !!document.activeElement.closest('#fcc-vendor-merge-confirm')")


def test_a_keyboard_try_again_keeps_the_keyboard_in_the_question(vm):
    """R2P5: ↻ Try again's lines were replaced under the keyboard, which went to the page."""
    vm.evaluate("""(p) => { window.__planFails = 2;
        window.__answers['POST /api/vendors/35/merge_into/4'] = (req) => (window.__planFails-- > 0)
            ? { __status: 502, __body: { success: false, msg: 'Spoolman refused it: database is locked' } } : p; }""", PLAN)
    _open_window(vm, 35)
    vm.locator('#fcc-vendor-merge button.fcc-vm-row[data-vm-src="35"][data-vm-dst="4"]').click()
    vm.wait_for_selector('#fcc-vendor-merge-confirm [data-vmq="retry"]')
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="retry"]').focus()
    vm.keyboard.press("Enter")                       # fails again: the keyboard on the new Try again
    vm.wait_for_timeout(150)
    assert _q(vm)["focus"] == "retry"
    vm.keyboard.press("Enter")                       # now the plan: the keyboard on Cancel
    _plan_painted(vm)
    vm.wait_for_timeout(60)
    assert _q(vm)["focus"] == "cancel"


def test_a_swap_whose_plan_fails_keeps_the_keyboard_and_names_the_direction_asked(vm):
    """R2P5: ⇄ was off while it had the keyboard, which went to the page, and the title kept
    the old direction."""
    _answer_merge(vm)
    vm.evaluate("""() => { window.__answers['POST /api/vendors/4/merge_into/35'] =
        { __status: 502, __body: { success: false, msg: 'Spoolman refused it: database is locked' } }; }""")
    _ask_pair(vm, 35)
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="swap"]').focus()
    vm.keyboard.press("Enter")
    vm.wait_for_timeout(150)
    q = _q(vm)
    assert q["focus"] == "retry"
    assert q["title"] == "🔗 Merge Sunlu #4 into Sunlu #35?"
    assert q["swap"]["text"] == "⇄ Keep the other" and q["yes"]["text"] == "🔗 Merge"


MERGE_JS = (Path(__file__).resolve().parents[1] / "static" / "js" / "modules" / "inv_vendor_merge.js")


@pytest.fixture
def ms(page61):
    """page61 (the real inv_cmd.js, its processScan, the scan accumulator) with the merge
    window's module; its reads and the merge answered from `window.__vm`."""
    page = page61
    page.evaluate("""(a) => {
        const prior = window.fetch;
        window.__vm = a;
        window.fetch = (url, opts) => {
            const u = String(url);
            const body = opts && opts.body ? JSON.parse(opts.body) : null;
            const key = (opts && opts.method && opts.method !== 'GET' ? opts.method + ' ' : '') + u;
            if (!(key in window.__vm)) return prior(url, opts);
            let ans = window.__vm[key];
            if (typeof ans === 'function') ans = ans({ body });
            const reply = (x) => ({ ok: true, status: 200, json: () => Promise.resolve(x) });
            if (ans === '__hold__') return new Promise((resolve) => { window.__vmRelease = (x) => resolve(reply(x)); });
            return Promise.resolve(reply(ans));
        };
    }""", {"/api/vendors/35/merge_options": options(35),
           "POST /api/vendors/35/merge_into/4": "__plan_or_hold__"})
    page.evaluate("(p) => { window.__vm['POST /api/vendors/35/merge_into/4'] = (req) => "
                  "(req.body && req.body.dry_run) ? p : '__hold__'; }", PLAN)
    page.add_script_tag(content=MERGE_JS.read_text(encoding="utf-8"))
    page.evaluate("() => window.openVendorMerge({ vid: '35' })")
    page.wait_for_function("() => !!document.querySelector('#fcc-vendor-merge [data-vm-body][data-vm-state=\"ready\"]')")
    return page


def test_a_scan_closes_the_window_and_goes_on(ms):
    """R2P7: the window takes no scan (the audit report's rule): it goes, and the scan goes
    on, its answer on top."""
    ms.evaluate("() => window.processScan('ID:57', 'barcode')")
    ms.wait_for_timeout(100)
    assert not ms.evaluate("() => window.isVendorMergeOpen()")
    assert [i["text"] for i in ms.evaluate("window.__ids")] == ["ID:57"]
    assert ms.evaluate("window.__errors") == []


def test_with_its_question_up_a_scan_is_held_and_the_window_stays(ms):
    ms.locator('#fcc-vendor-merge button.fcc-vm-row[data-vm-src="35"][data-vm-dst="4"]').click()
    _plan_painted(ms)
    ms.evaluate("() => window.processScan('ID:57', 'barcode')")
    ms.wait_for_timeout(100)
    assert ms.evaluate("() => window.isVendorMergeOpen()") and _question_up(ms)
    assert ms.evaluate("window.__ids") == []


def test_a_scan_refused_while_the_merge_is_out_is_logged(ms):
    """R2P6: its only trace was the question's line, which went when the merge landed."""
    ms.locator('#fcc-vendor-merge button.fcc-vm-row[data-vm-src="35"][data-vm-dst="4"]').click()
    _plan_painted(ms)
    _yes_by_keyboard(ms)
    ms.wait_for_timeout(60)
    ms.evaluate("() => window.processScan('ID:57', 'barcode')")
    ms.evaluate("() => window.processScan('CMD:CANCEL', 'barcode')")
    ms.wait_for_timeout(100)
    logs = ms.evaluate("window.__logs")
    assert any('Scan "ID:57" ignored: the manufacturer merge is on its way' in m for m in logs), logs
    assert any('Scan "CMD:CANCEL" ignored: the manufacturer merge is on its way' in m for m in logs), logs
    assert _question_up(ms) and ms.evaluate("window.__ids") == []


def _save_n(page, n):
    """The wizard's Save, the n-th of this window, answered: what it posted."""
    page.evaluate("() => { window.wizardSubmit(); }")
    page.wait_for_function("(n) => window.__posts.filter((p) => p.url === '/api/edit_spool_wizard').length >= n", arg=n)
    page.wait_for_function("() => wizardState.saving == null")
    return page.evaluate("(n) => window.__posts.filter((p) => p.url === '/api/edit_spool_wizard')[n - 1].body", n)


def _pick_vendor(page, vid, name):
    page.evaluate("(a) => window.wizardComboboxSet('wiz-fil-vendor-search', 'wiz-fil-vendor-sel', a.vid, a.name)",
                  {"vid": vid, "name": name})


def test_a_manufacturer_changed_back_in_the_same_window_is_sent(wiz):
    """R2P2 / R2X-1: the baseline was the open's, so #4 then back to #2 left #2 out, and
    the filament stayed on #4 under "Success! Spool Updated."."""
    from test_wizard_vendor_66_1 import _open_edit_with, _brand
    _open_edit_with(wiz, {"success": True, "vendors": [_brand(2), _brand(4, "Other")]})
    _pick_vendor(wiz, 4, "Other")
    assert _save_n(wiz, 1)["filament_data"]["vendor_id"] == 4
    _pick_vendor(wiz, 2, "Some Brand")
    assert _save_n(wiz, 2)["filament_data"]["vendor_id"] == 2
    assert _save_n(wiz, 3)["filament_data"].get("vendor_id") is None      # unchanged since it landed
    assert wiz.evaluate("window.__errors") == []


def test_after_a_filament_answer_that_may_have_landed_the_box_is_sent(wiz):
    """R2X-1: the filament write's answer was lost; it may be on #4, so a change back to #2
    must go out."""
    from test_wizard_vendor_66_1 import _open_edit_with, _brand
    _open_edit_with(wiz, {"success": True, "vendors": [_brand(2), _brand(4, "Other")]})
    wiz.evaluate("""() => { window.__answers['/api/edit_spool_wizard'] = { success: false, spool_saved: true,
        msg: 'Spool saved, but filament update rejected: Read timed out.', error: 'Read timed out.',
        filament_may_have_saved: true }; }""")
    _pick_vendor(wiz, 4, "Other")
    assert _save_n(wiz, 1)["filament_data"]["vendor_id"] == 4
    wiz.evaluate("() => { window.__answers['/api/edit_spool_wizard'] = { success: true, spool_id: 57 }; }")
    _pick_vendor(wiz, 2, "Some Brand")
    assert _save_n(wiz, 2)["filament_data"]["vendor_id"] == 2


def test_after_a_filament_write_spoolman_refused_the_open_baseline_stands(wiz):
    """R2X-1: a refusal Spoolman answered wrote nothing, so the filament is on #2 still."""
    from test_wizard_vendor_66_1 import _open_edit_with, _brand
    _open_edit_with(wiz, {"success": True, "vendors": [_brand(2), _brand(4, "Other")]})
    wiz.evaluate("""() => { window.__answers['/api/edit_spool_wizard'] = { success: false, spool_saved: true,
        msg: 'Spool saved, but filament update rejected: HTTP 500: {}', error: 'HTTP 500: {}',
        filament_may_have_saved: false }; }""")
    _pick_vendor(wiz, 4, "Other")
    assert _save_n(wiz, 1)["filament_data"]["vendor_id"] == 4
    wiz.evaluate("() => { window.__answers['/api/edit_spool_wizard'] = { success: true, spool_id: 57 }; }")
    _pick_vendor(wiz, 2, "Some Brand")
    assert _save_n(wiz, 2)["filament_data"].get("vendor_id") is None


def _set_link(page, value):
    """The spool's Product Link box, as typed (its section may be folded)."""
    page.evaluate("""(v) => { const el = document.getElementById('wiz-spool-product_url');
        el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); }""", value)


def test_a_link_saved_then_emptied_in_the_same_window_is_cleared(wiz):
    """R2X-3 (older than 66.9): the emptied box was compared with the open's blank."""
    from test_wizard_vendor_66_1 import _open_edit_with, _brand
    _open_edit_with(wiz, {"success": True, "vendors": [_brand(2)]})
    _set_link(wiz, "https://example.com/a")
    assert _save_n(wiz, 1)["spool_data"]["extra"]["product_url"] == "https://example.com/a"
    _set_link(wiz, "")
    assert _save_n(wiz, 2)["spool_data"]["extra"]["product_url"] == "__FCC_DELETE_EXTRA__"
    assert "product_url" not in _save_n(wiz, 3)["spool_data"]["extra"]      # cleared already


# --- review round 3 (2026-11-26): the page and wizard findings, pinned ---------------------

P9 = {"id": 9, "name": "Prusament", "empty_spool_weight": None, "external_id": "", "extra": {},
      "registered": "2026-02-11T11:00:00Z"}
P34 = {"id": 34, "name": "Prusament", "empty_spool_weight": None, "external_id": "Prusament", "extra": {},
       "registered": "2026-02-20T10:00:00Z"}
VENDORS_502 = {"__status": 502, "__body": {"success": False, "msg": "blip"}}
NOTHING_WRITTEN = {"__status": 502, "__body": {
    "success": False, "nothing_written": True,
    "msg": "Couldn't read manufacturer #35 from Spoolman, so nothing was merged. Try again in a moment."}}
CARRY_UNSURE = {"__status": 502, "__body": {
    "success": False,
    "msg": ("FCC couldn't tell whether Sunlu #35's External ID “Sunlu” was copied onto Sunlu #4: Spoolman didn't "
            "answer in time. Nothing was moved; try again in a moment.")}}
AFTER_OPTIONS = dict(options(4, groups=[]), twins=[], vendors=[ROWS[50], ROWS[1], ROWS[4]])
GONE4 = {"__status": 404, "__body": {"success": False, "gone": 4, "nothing_written": True,
                                     "msg": "Manufacturer #4 isn't in Spoolman any more: it was merged or deleted already."}}


def _editor_state(page):
    return page.evaluate("""() => { const err = document.getElementById('vendoredit-error');
        return { id: document.getElementById('vendoredit-id').value,
                 ext: document.getElementById('vendoredit-external-id').value,
                 weight: document.getElementById('vendoredit-empty-weight').value,
                 saveOff: document.getElementById('vendoredit-save').disabled,
                 banner: err.classList.contains('d-none') ? '' : err.innerText }; }""")


def _merged_events(page):
    return [e for e in page.evaluate("window.__ev") if e[0] == "vendor:merged"]


def _vendors_answer(page, answer):
    page.evaluate("(a) => { window.__answers['/api/vendors'] = a; }", answer)


def _save_editor_with_a_note(page, vid, record):
    page.evaluate("(a) => { window.__answers['PATCH /api/vendors/' + a.vid] = { success: true, vendor: a.v }; }",
                  {"vid": vid, "v": record})
    page.fill("#vendoredit-comment", "a note")
    page.locator("#vendoredit-save").click()
    page.wait_for_timeout(150)
    return [x for x in page.evaluate("window.__posts") if x["url"].endswith(f"/api/vendors/{vid}")]


def test_a_merge_that_lands_after_a_hold_gives_the_editor_its_save_back(vm):
    """R3P1: a hold, then a merge of the same pair that lands: the editor shows the kept
    one's record, Save on, no banner, and its Save keeps the carried External ID."""
    _answer_merge(vm, merge="__reject__")
    _ask_pair(vm, 4)
    _vendors_answer(vm, VENDORS_502)
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()
    vm.wait_for_timeout(250)
    held = _editor_state(vm)
    assert held["saveOff"] and "FCC couldn't read manufacturer #4 after a merge was tried" in held["banner"]
    _plan_painted(vm)
    _answer_merge(vm)
    _vendors_answer(vm, AFTER)
    _yes_by_keyboard(vm)
    vm.wait_for_timeout(250)
    st = _editor_state(vm)
    assert (st["id"], st["ext"], st["saveOff"], st["banner"]) == ("4", "Sunlu", False, "")
    vm.keyboard.press("Escape")
    vm.wait_for_timeout(750)
    sent = _save_editor_with_a_note(vm, 4, SUNLU4_AFTER)
    assert len(sent) == 1 and sent[0]["body"]["data"]["external_id"] == "Sunlu"


def test_a_refusal_that_wrote_nothing_leaves_the_editor_alone(vm):
    """R3P2: "so nothing was merged", and the manufacturers read that follows fails: the
    editor keeps its Save and claims no change."""
    _answer_merge(vm, merge=NOTHING_WRITTEN)
    _ask_pair(vm, 4)
    _vendors_answer(vm, VENDORS_502)
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()
    vm.wait_for_timeout(250)
    st = _editor_state(vm)
    assert not st["saveOff"] and st["banner"] == ""
    assert "so nothing was merged" in _q(vm)["flash"]


@pytest.mark.parametrize("late", ["the record from before the carry", "a read that failed"])
def test_a_slow_read_a_later_merge_overtook_says_nothing(vm, late):
    """R3P3: the kept one's read sent after a refusal lands after the next press merged."""
    _answer_merge(vm, merge=CARRY_UNSURE)
    _ask_pair(vm, 4)
    vm.evaluate("() => { window.__answers['/api/vendors'] = '__hold__'; }")
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()
    vm.wait_for_timeout(200)
    _plan_painted(vm)
    _answer_merge(vm)
    _yes_by_keyboard(vm)
    vm.wait_for_timeout(250)
    assert _editor_state(vm)["ext"] == "Sunlu"
    if late == "a read that failed":
        vm.evaluate("() => window.__held['/api/vendors']({ success: false, msg: 'blip' }, 502)")
    else:
        vm.evaluate("(v) => window.__held['/api/vendors'](v)", VENDORS)
    vm.wait_for_timeout(150)
    st = _editor_state(vm)
    assert (st["ext"], st["saveOff"], st["banner"]) == ("Sunlu", False, "")


def _press_with_no_answer_then_replanned(page):
    """Pair 35 -> 4 pressed with no answer while #35 is still listed: the plan is asked again."""
    _answer_merge(page, merge="__reject__")
    _ask_pair(page, 35)
    page.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()
    page.wait_for_timeout(250)
    _plan_painted(page)


def _merge_finished(page):
    page.evaluate("(a) => { window.__answers['/api/vendors'] = a.v; window.__answers['/api/vendors/4/merge_options'] = a.o; }",
                  {"v": AFTER, "o": AFTER_OPTIONS})


def test_a_merge_finished_after_its_question_was_cancelled_is_told_when_the_row_is_asked_again(vm):
    """R3P4: the memory of a merge FCC couldn't account for outlives its question."""
    _press_with_no_answer_then_replanned(vm)
    vm.keyboard.press("Escape")
    vm.wait_for_timeout(750)
    _answer_merge(vm, plan=GONE35, merge=GONE35)
    _merge_finished(vm)
    vm.locator('#fcc-vendor-merge button.fcc-vm-row[data-vm-src="35"][data-vm-dst="4"]').first.click()
    vm.wait_for_timeout(300)
    ev = _merged_events(vm)
    assert len(ev) == 1 and (ev[0][1]["from"], ev[0][1]["into"]) == ("35", "4")
    assert not _question_up(vm) and vm.locator("#vendoredit-id").input_value() == "4"


def test_a_merge_finished_is_told_when_the_other_way_round_is_asked(vm):
    """R3P4: after ⇄ the merged one is the question's kept side."""
    _press_with_no_answer_then_replanned(vm)
    vm.evaluate("(g) => { window.__answers['POST /api/vendors/4/merge_into/35'] = (req) => g; }", GONE35)
    _merge_finished(vm)
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="swap"]').click()
    vm.wait_for_timeout(300)
    ev = _merged_events(vm)
    assert len(ev) == 1 and (ev[0][1]["from"], ev[0][1]["into"]) == ("35", "4")
    assert not _question_up(vm)


def test_the_window_opened_again_tells_a_merge_an_earlier_question_couldnt_account_for(vm):
    """R3P4: the window's own read of the gone one is the same merge, finished."""
    _press_with_no_answer_then_replanned(vm)
    vm.keyboard.press("Escape")
    vm.wait_for_timeout(750)
    vm.keyboard.press("Escape")
    vm.wait_for_timeout(750)
    vm.evaluate("(g) => { window.__answers['/api/vendors/35/merge_options'] = g; }",
                {"__status": 404, "__body": {"success": False, "gone": 35,
                                             "msg": "Manufacturer #35 isn't in Spoolman any more (merged or deleted?)."}})
    _merge_finished(vm)
    vm.locator("#vendoredit-merge").click()
    vm.wait_for_timeout(300)
    ev = _merged_events(vm)
    assert len(ev) == 1 and (ev[0][1]["from"], ev[0][1]["into"]) == ("35", "4")
    assert vm.locator("#vendoredit-id").input_value() == "4"


def test_a_window_on_a_manufacturer_gone_another_way_offers_no_try_again(vm):
    vm.evaluate("(g) => { window.__answers['/api/vendors/35/merge_options'] = g; }",
                {"__status": 404, "__body": {"success": False, "gone": 35,
                                             "msg": "Manufacturer #35 isn't in Spoolman any more (merged or deleted?)."}})
    _open_editor(vm, 35)
    vm.locator("#vendoredit-merge").click()
    vm.wait_for_selector("#fcc-vendor-merge [data-vm-fail]")
    assert vm.locator("#fcc-vendor-merge [data-vm-retry]").count() == 0
    assert _merged_events(vm) == []


@pytest.mark.parametrize("second", ["good", "fails"])
def test_a_keyboard_try_again_keeps_the_keyboard_in_the_window(vm, second):
    """R3P5: the body Try again sat in was redrawn under the keyboard."""
    vm.evaluate("(a) => { window.__answers['/api/vendors/35/merge_options'] = a; }", VENDORS_502)
    _open_editor(vm, 35)
    vm.locator("#vendoredit-merge").click()
    vm.wait_for_selector("#fcc-vendor-merge [data-vm-retry]")
    vm.evaluate("(a) => { window.__answers['/api/vendors/35/merge_options'] = a; }",
                options(35) if second == "good" else VENDORS_502)
    vm.locator("#fcc-vendor-merge [data-vm-retry]").focus()
    vm.keyboard.press("Enter")
    vm.wait_for_timeout(150)
    assert vm.evaluate("() => document.activeElement.matches('[data-vm-box]')")


def test_after_a_hold_closing_the_window_gives_the_keyboard_to_the_editor(vm):
    """R3P6: the hold hid 🔗 Merge…, the window's opener."""
    vm.add_style_tag(content=".d-none{display:none !important}")
    _answer_merge(vm, merge="__reject__")
    _ask_pair(vm, 4)
    _vendors_answer(vm, VENDORS_502)
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()
    vm.wait_for_timeout(250)
    _plan_painted(vm)
    assert _editor_state(vm)["saveOff"]
    vm.keyboard.press("Escape")
    vm.wait_for_timeout(100)
    vm.keyboard.press("Escape")
    vm.wait_for_timeout(100)
    assert not vm.evaluate("() => !!window.getOverlay('fcc-vendor-merge')")
    assert vm.evaluate("() => !!document.activeElement.closest('#vendorEditModal')")


def test_a_swap_whose_plan_lands_after_the_keyboard_moved_leaves_it_there(vm):
    """R3P7: ⇄ took the keyboard back from Cancel, and the next Enter swapped again."""
    _answer_merge(vm)
    vm.evaluate("() => { window.__answers['POST /api/vendors/4/merge_into/35'] = '__hold__'; }")
    _ask_pair(vm, 35)
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="swap"]').focus()
    vm.keyboard.press("Enter")
    vm.wait_for_timeout(100)
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="cancel"]').focus()     # the person moved on
    vm.evaluate("(p) => window.__held['/api/vendors/4/merge_into/35'](p)", SWAPPED)
    _plan_painted(vm)
    vm.wait_for_timeout(60)
    assert _q(vm)["focus"] == "cancel"


def test_a_question_opened_while_a_gone_answers_read_was_out_keeps_the_keyboard(vm):
    """R3P8: the settled merge put the keyboard in the window's box, under the new question."""
    vm.evaluate("""(a) => { window.__goneNow = false; let n = 0;
        window.__answers['POST /api/vendors/35/merge_into/4'] = (req) => (req.body && req.body.dry_run)
            ? (window.__goneNow ? a.gone : a.plan) : '__reject__';
        window.__answers['POST /api/vendors/1/merge_into/35'] = (req) => a.p1; }""",
                {"plan": PLAN, "gone": GONE35,
                 "p1": dict(PLAN, default_keep=35, plan=dict(PLAN["plan"], source=ROWS[1], target=ROWS[35]))})
    vm.evaluate("(o) => { window.__answers['/api/vendors/4/merge_options'] = o; }", AFTER_OPTIONS)
    _ask_pair(vm, 35)
    # Once the editor is open (its own open reads the list): the check's read answers,
    # the gone answer's read waits.
    vm.evaluate("""(v) => { let n = 0; window.__goneNow = true;
        window.__answers['/api/vendors'] = () => (++n === 1 ? v : '__hold__'); }""", VENDORS)
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()
    # The gone answer's read of the manufacturers is held, and nothing is in flight.
    vm.wait_for_function("() => !!(window.__held && window.__held['/api/vendors'])")
    vm.wait_for_function("() => document.querySelector('#fcc-vendor-merge-confirm [data-vmq=\"cancel\"]') === document.activeElement")
    vm.keyboard.press("Escape")
    vm.wait_for_function("() => !document.querySelector('#fcc-vendor-merge-confirm')")
    vm.wait_for_timeout(750)
    vm.locator('#fcc-vendor-merge button.fcc-vm-row[data-vm-src="1"]').click()
    _plan_painted(vm)
    # The new question's first focus (mountOverlay's initialFocus, a tick after it opens).
    vm.wait_for_function("() => document.querySelector('#fcc-vendor-merge-confirm [data-vmq=\"cancel\"]') === document.activeElement")
    vm.evaluate("(v) => window.__held['/api/vendors'](v)", AFTER)
    vm.wait_for_function("() => window.__ev.some((e) => e[0] === 'vendor:merged')")
    vm.wait_for_timeout(150)
    assert len(_merged_events(vm)) == 1
    assert vm.evaluate("() => !!document.activeElement.closest('#fcc-vendor-merge-confirm')")


@pytest.mark.parametrize("first", ["may_have_deleted", "unreadable"])
def test_an_unaccounted_press_then_a_gone_plan_is_told_as_the_merge(vm, first):
    """R3T2: the may_have_deleted and unreadable branches of the memory."""
    answer = ({"__status": 502, "__body": {"success": False, "may_have_deleted": True,
                                           "moved_filament_ids": [160, 161, 162, 163],
                                           "msg": "Moved 4 of 4 filaments onto Sunlu #4, but FCC couldn't tell…"}}
              if first == "may_have_deleted" else {"__status": 502, "__body": None})
    vm.evaluate("""(a) => { window.__goneNow = false;
        window.__answers['POST /api/vendors/35/merge_into/4'] = (req) => (req.body && req.body.dry_run)
            ? (window.__goneNow ? a.gone : a.plan) : a.first; }""", {"plan": PLAN, "gone": GONE35, "first": answer})
    _ask_pair(vm, 35)
    _vendors_answer(vm, VENDORS_502)
    vm.evaluate("() => { window.__goneNow = true; }")
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()
    vm.wait_for_timeout(300)
    ev = _merged_events(vm)
    assert len(ev) == 1 and (ev[0][1]["from"], ev[0][1]["into"]) == ("35", "4") and ev[0][1]["vendor"] is None
    assert not _question_up(vm)
    st = _editor_state(vm)
    assert st["saveOff"] and "was merged into #4" in st["banner"]


def test_no_answer_with_a_good_read_refills_the_editor_on_the_kept_one(vm):
    """R3T3: R2P1's no-answer half, the read finding the kept one with the carry."""
    _answer_merge(vm, merge="__reject__")
    _ask_pair(vm, 4)
    _vendors_answer(vm, {"success": True, "vendors": [SUNLU4_AFTER, SUNLU35, OVERTURE, ACME]})
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()
    vm.wait_for_timeout(250)
    assert _editor_state(vm)["ext"] == "Sunlu"
    vm.keyboard.press("Escape")
    vm.wait_for_timeout(100)
    vm.keyboard.press("Escape")
    vm.wait_for_timeout(750)
    sent = _save_editor_with_a_note(vm, 4, SUNLU4_AFTER)
    assert len(sent) == 1 and sent[0]["body"]["data"]["external_id"] == "Sunlu"


def test_a_partial_merge_leaves_an_editor_on_the_merged_one_alone(vm):
    """R3T4: the kept one's record never fills an editor showing another manufacturer."""
    _answer_merge(vm, merge={"__status": 502, "__body": PARTIAL})
    _ask_pair(vm, 35)
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()
    vm.wait_for_timeout(200)
    st = _editor_state(vm)
    assert (st["id"], st["weight"], st["saveOff"]) == ("35", "", False)


def test_an_unread_word_of_another_manufacturer_leaves_the_editor_alone(ef):
    ef.evaluate("() => window.openVendorEditModal(35)")
    ef.wait_for_function("() => document.getElementById('vendorEditModal').classList.contains('show')")
    ef.wait_for_timeout(60)
    ef.evaluate("() => document.dispatchEvent(new CustomEvent('vendor:unread', { detail: { id: '4' } }))")
    ef.wait_for_timeout(60)
    st = _editor_state(ef)
    assert (st["id"], st["saveOff"], st["banner"]) == ("35", False, "")


def test_after_a_merge_a_row_the_person_arrowed_to_keeps_the_keyboard(vm):
    """R3T5: the read callback moves the keyboard only from the box."""
    rows = {**ROWS, 9: row(P9, 25), 34: row(P34, 0)}
    listing = sorted(rows.values(), key=lambda r: (r["name"].lower(), r["id"]))
    before = dict(options(35), groups=[{"kind": "same_name", "ids": [4, 35], "keep": 4, "mine": True},
                                       {"kind": "same_name", "ids": [9, 34], "keep": 9, "mine": False}],
                  vendors=listing)
    after = {"success": True, "vendor": rows[4], "twins": [],
             "groups": [{"kind": "same_name", "ids": [9, 34], "keep": 9, "mine": False}],
             "vendors": [r for r in listing if r["id"] != 35]}
    vm.evaluate("(o) => { window.__answers['/api/vendors/35/merge_options'] = o; }", before)
    _answer_merge(vm)
    _ask_pair(vm, 35)
    vm.evaluate("() => { window.__answers['/api/vendors/4/merge_options'] = '__hold__'; }")
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()
    vm.wait_for_timeout(150)
    assert vm.evaluate("() => document.activeElement.matches('[data-vm-box]')")
    vm.keyboard.press("ArrowDown")
    vm.keyboard.press("ArrowDown")
    on = "() => { const a = document.activeElement; return a && a.dataset ? (a.dataset.vmSrc || '') + ':' + (a.dataset.vmDst || '') : ''; }"
    assert vm.evaluate(on) == "34:9"
    vm.evaluate("(o) => window.__held['/api/vendors/4/merge_options'](o)", after)
    vm.wait_for_timeout(120)
    assert vm.evaluate(on) == "34:9"


def test_a_plan_whose_kept_one_is_gone_offers_no_try_again(vm):
    """R3T9 (1)."""
    _answer_merge(vm, plan=GONE4)
    _open_window(vm, 35)
    vm.locator('#fcc-vendor-merge button.fcc-vm-row[data-vm-src="35"][data-vm-dst="4"]').first.click()
    vm.wait_for_timeout(200)
    q = _q(vm)
    assert vm.locator('#fcc-vendor-merge-confirm [data-vmq="retry"]').count() == 0
    assert not q["cancel"]["off"] and q["swap"]["off"] and q["yes"]["off"]
    assert _merged_events(vm) == []


def test_both_gone_after_an_unaccounted_press_tells_no_window(vm):
    """R3T9 (2)."""
    vm.evaluate("""(a) => { window.__goneNow = false; let n = 0;
        window.__answers['POST /api/vendors/35/merge_into/4'] = (req) => (req.body && req.body.dry_run)
            ? (window.__goneNow ? a.gone : a.plan) : '__reject__';
        window.__answers['/api/vendors'] = () => (++n === 1 ? a.before : a.neither); }""",
                {"plan": PLAN, "gone": GONE35, "before": VENDORS,
                 "neither": {"success": True, "vendors": [OVERTURE, ACME]}})
    _ask_pair(vm, 35)
    vm.evaluate("""(a) => { let n = 0; window.__goneNow = true;
        window.__answers['/api/vendors'] = () => (++n === 1 ? a.before : a.neither); }""",
                {"before": VENDORS, "neither": {"success": True, "vendors": [OVERTURE, ACME]}})
    vm.locator('#fcc-vendor-merge-confirm [data-vmq="yes"]').click()
    vm.wait_for_timeout(300)
    assert _merged_events(vm) == []
    assert any("Sunlu #4 isn't in Spoolman either." in line for line in _q(vm)["lines"])


# --- the wizard (R3S1 / R3W1 / R3T1, R3W2-R3W8, R3T6, R3T9 (3)) ---

SAVE_STUB = r"""() => {
    if (window.__saveStub) return;
    window.__saveStub = true;
    const base = window.fetch;
    window.__saveMode = null;
    window.fetch = (url, opts) => {
        if (String(url).split('?')[0] === '/api/edit_spool_wizard' && window.__saveMode) {
            const mode = window.__saveMode;
            window.__saveMode = null;
            window.__posts.push({ url: '/api/edit_spool_wizard', body: opts && opts.body ? JSON.parse(opts.body) : null });
            if (mode === 'reject') return Promise.reject(new TypeError('Failed to fetch'));
            return new Promise((resolve) => { window.__releaseSave = (ans) => resolve({ ok: true, status: 200,
                json: () => Promise.resolve(ans) }); });
        }
        return base(url, opts);
    };
    window.__labelCalls = [];
    window._maybePromptLabelReprint = (fid, name, cn, ce) => { window.__labelCalls.push({ cn, ce }); };
}"""
LOST_ANSWER = {"success": False, "spool_saved": False, "filament_may_have_saved": True, "error": "Read timed out.",
               "msg": "FCC couldn't tell whether filament #7's changes saved: Spoolman didn't answer in time."}


def _wiz_edit(wiz, vendors=None):
    from test_wizard_vendor_66_1 import _open_edit_with, _brand
    _open_edit_with(wiz, {"success": True, "vendors": vendors or [_brand(2), _brand(4, "Other")]})
    wiz.evaluate(SAVE_STUB)


def _answer_saves(wiz, answer):
    wiz.evaluate("(a) => { window.__answers['/api/edit_spool_wizard'] = a; }", answer)


def _posted(wiz, n):
    return wiz.evaluate("(n) => window.__posts.filter((p) => p.url === '/api/edit_spool_wizard')[n - 1].body", n)


@pytest.mark.parametrize("may", [True, False])
def test_a_manufacturer_only_save_whose_filament_answer_was_lost_sends_the_change_back(wiz, may):
    """R3S1 / R3W1 / R3T1: the route answers spool_saved false when the spool's own diff is
    empty; the doubt counts all the same, and only when the answer may have landed."""
    _wiz_edit(wiz)
    _answer_saves(wiz, dict(LOST_ANSWER, filament_may_have_saved=may))
    _pick_vendor(wiz, 4, "Other")
    assert _save_n(wiz, 1)["filament_data"]["vendor_id"] == 4
    _answer_saves(wiz, {"success": True, "spool_id": 57})
    _pick_vendor(wiz, 2, "Some Brand")
    assert _save_n(wiz, 2)["filament_data"].get("vendor_id") == (2 if may else None)


def test_a_save_that_lands_after_a_lost_answer_settles_the_doubt(wiz):
    """R3T6 (a)."""
    _wiz_edit(wiz)
    _answer_saves(wiz, LOST_ANSWER)
    _pick_vendor(wiz, 4, "Other")
    _save_n(wiz, 1)
    _answer_saves(wiz, {"success": True, "spool_id": 57})
    assert _save_n(wiz, 2)["filament_data"]["vendor_id"] == 4
    assert _save_n(wiz, 3)["filament_data"].get("vendor_id") is None


def test_a_generic_save_keeps_the_doubt_of_a_lost_answer(wiz):
    """R3W5: a Save that sent no manufacturer can't settle it."""
    _wiz_edit(wiz)
    _answer_saves(wiz, LOST_ANSWER)
    _pick_vendor(wiz, 4, "Other")
    _save_n(wiz, 1)
    _answer_saves(wiz, {"success": True, "spool_id": 57})
    wiz.evaluate("""() => { document.getElementById('wiz-fil-vendor-sel').value = '';
        document.getElementById('wiz-fil-vendor-search').value = ''; }""")
    assert _save_n(wiz, 2)["filament_data"].get("vendor_id") is None
    _pick_vendor(wiz, 2, "Some Brand")
    assert _save_n(wiz, 3)["filament_data"]["vendor_id"] == 2


def test_a_save_with_no_answer_leaves_only_what_it_sent_unsure(wiz):
    """R3W3 / R3W4 / R3T6 (b): the manufacturer and the link it sent go out again as the
    boxes show them; a link box it didn't send keeps its baseline."""
    _wiz_edit(wiz)
    _pick_vendor(wiz, 4, "Other")
    _set_link(wiz, "https://example.com/a")
    wiz.evaluate("() => { window.__saveMode = 'reject'; }")
    first = _save_n(wiz, 1)
    assert first["filament_data"]["vendor_id"] == 4 and first["spool_data"]["extra"]["product_url"] == "https://example.com/a"
    assert "FCC didn't answer this Save, so it may or may not have landed" in wiz.locator("#wiz-status-msg").inner_text()
    _pick_vendor(wiz, 2, "Some Brand")
    _set_link(wiz, "")
    second = _save_n(wiz, 2)
    assert second["filament_data"]["vendor_id"] == 2
    assert second["spool_data"]["extra"]["product_url"] == "__FCC_DELETE_EXTRA__"
    assert "purchase_url" not in second["spool_data"]["extra"]


def test_a_save_with_no_answer_that_sent_no_link_leaves_the_links_alone(wiz):
    """R3W3: a lost Save that changed only the comment."""
    _wiz_edit(wiz)
    wiz.evaluate("""() => { const c = document.getElementById('wiz-spool-comment'); c.value = 'a note';
        c.dispatchEvent(new Event('input', { bubbles: true })); window.__saveMode = 'reject'; }""")
    first = _save_n(wiz, 1)
    assert "product_url" not in first["spool_data"]["extra"] and first["filament_data"].get("vendor_id") is None
    second = _save_n(wiz, 2)
    assert "product_url" not in second["spool_data"]["extra"] and "purchase_url" not in second["spool_data"]["extra"]
    assert second["filament_data"].get("vendor_id") is None


def test_an_error_after_a_clean_answer_leaves_nothing_unsure(wiz):
    """R3W4: a throw in the page's own code after the Save was answered."""
    _wiz_edit(wiz)
    _pick_vendor(wiz, 4, "Other")
    wiz.evaluate("""() => { const real = window.wizardRenderPostSaveQueueActions;
        window.wizardRenderPostSaveQueueActions = function () { window.wizardRenderPostSaveQueueActions = real;
            throw new Error('boom'); }; }""")
    _save_n(wiz, 1)
    out = wiz.evaluate("() => ({ unsure: wizardState.vendorUnsure, links: wizardState.linkShown, base: wizardState.editFilamentOriginal.vendor_id })")
    assert out["unsure"] is False and out["links"] is not None and out["base"] == "4"
    assert "FCC answered the Save, but this page hit an error showing it" in wiz.locator("#wiz-status-msg").inner_text()


def test_a_link_saved_with_a_refused_filament_write_settles_its_row(wiz):
    """R3W2 / R3T6 (c): the spool's write carried the link; the row says so, and the next
    Save sends nothing for it."""
    _wiz_edit(wiz)
    link = "https://prusament.com/spool/17705/5b1a183b26/"
    _set_link(wiz, link)
    wiz.evaluate("""(l) => { const row = wizardState.spoolRows[0];
        Object.assign(row, { status: 'linked-new', linkValue: l, linkFills: [], errorMsg: 'Links at Save' }); }""", link)
    _answer_saves(wiz, {"success": False, "spool_saved": True, "filament_may_have_saved": False,
                        "msg": "Spool saved, but filament #7's changes weren't saved: Spoolman refused it: nope."})
    assert _save_n(wiz, 1)["spool_data"]["extra"]["product_url"] == link
    row = wiz.evaluate("() => ({ status: wizardState.spoolRows[0].status, msg: wizardState.spoolRows[0].errorMsg })")
    assert row == {"status": "linked", "msg": "Linked to this QR"}
    _answer_saves(wiz, {"success": True, "spool_id": 57})
    assert "product_url" not in _save_n(wiz, 2)["spool_data"]["extra"]
    _set_link(wiz, "")
    assert _save_n(wiz, 3)["spool_data"]["extra"]["product_url"] == "__FCC_DELETE_EXTRA__"


def test_a_link_checked_while_a_save_was_out_waits_for_the_next_save(wiz):
    """R3W8 (older than 66.9): the answer of a Save that didn't carry the link never marks
    it saved, and the form stays changed."""
    _wiz_edit(wiz)
    wiz.evaluate("() => { window.__saveMode = 'hold'; window.wizardSubmit(); }")
    wiz.wait_for_function("() => window.__posts.filter((p) => p.url === '/api/edit_spool_wizard').length === 1")
    link = "https://prusament.com/spool/17705/5b1a183b26/"
    _set_link(wiz, link)
    wiz.evaluate("""(l) => { Object.assign(wizardState.spoolRows[0], { status: 'linked-new', linkValue: l, linkFills: [],
        errorMsg: 'Links at Save' }); wizardState.isDirty = true; }""", link)
    wiz.evaluate("() => window.__releaseSave({ success: true, spool_id: 57 })")
    wiz.wait_for_function("() => wizardState.saving == null")
    out = wiz.evaluate("() => ({ status: wizardState.spoolRows[0].status, dirty: wizardState.isDirty })")
    assert out == {"status": "linked-new", "dirty": True}
    assert _save_n(wiz, 2)["spool_data"]["extra"]["product_url"] == link


def test_a_landed_rename_is_the_label_checks_baseline(wiz):
    """R3W7 (older than 66.9): the second Save of a renamed filament flags no label again."""
    _wiz_edit(wiz)
    wiz.evaluate("""() => { const n = document.getElementById('wiz-fil-color_name'); n.value = 'Purple Renamed';
        n.dispatchEvent(new Event('input', { bubbles: true })); }""")
    _save_n(wiz, 1)
    _save_n(wiz, 2)
    calls = wiz.evaluate("window.__labelCalls")
    assert calls[0]["cn"].get("name") == "Purple Renamed"
    assert calls[1]["cn"] == {} and calls[1]["ce"] == {}


@pytest.mark.parametrize("merged", ["the baseline's", "the one sent"])
def test_a_merge_while_a_save_is_out_leaves_the_kept_one_as_the_baseline(wiz, merged):
    """R3W6 / R3T9 (3): either way the baseline names the kept one, never a deleted id, and
    the next unchanged Save sends no manufacturer and flags no label."""
    from test_wizard_vendor_66_1 import _brand
    _wiz_edit(wiz)
    if merged == "the one sent":
        _pick_vendor(wiz, 4, "Other")
        detail = {"from": "4", "into": "2", "vendor": _brand(2), "moved": [7]}
    else:
        detail = {"from": "2", "into": "4", "vendor": _brand(4, "Other"), "moved": [7]}
    wiz.evaluate("() => { window.__saveMode = 'hold'; window.wizardSubmit(); }")
    wiz.wait_for_function("() => window.__posts.filter((p) => p.url === '/api/edit_spool_wizard').length === 1")
    wiz.evaluate("(d) => document.dispatchEvent(new CustomEvent('vendor:merged', { detail: d }))", detail)
    wiz.wait_for_timeout(100)
    wiz.evaluate("() => window.__releaseSave({ success: true, spool_id: 57 })")
    wiz.wait_for_function("() => wizardState.saving == null")
    kept = detail["into"]
    assert wiz.evaluate("() => wizardState.editFilamentOriginal.vendor_id") == kept
    assert wiz.locator(HIDDEN_VENDOR).input_value() == kept
    assert _save_n(wiz, 2)["filament_data"].get("vendor_id") is None
    assert "vendor_id" not in wiz.evaluate("window.__labelCalls")[-1]["cn"]
