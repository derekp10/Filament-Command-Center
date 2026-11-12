"""The README's pictures, from the README demo FCC (127.0.0.1:8100 only; see README.md here).

Usage (from the repo root):  python docs/readme-demo/readme_shots.py <out_dir>
Takes: dashboard.png, quick-swap.png, slot-picker.png, spool-window.png, help.png.
Shoot into a scratch folder and copy only the pictures that should change into
docs/images/readme/; set the README caption's date when you do.

The dashboard shows two spools moved and two left in the buffer. When the demo's buffer is
empty (it empties when its FCC restarts), the script makes that state itself with six scans,
typed as a scanner types them: #16 to SHELF-2, #9 to SHELF-1, then #14 and #8 into the buffer.
The slot picker is cancelled after its picture: nothing else moves.
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8100/"
assert "8100" in BASE   # the demo only: never dev, never prod
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)


def ready(page):
    page.goto(BASE)
    page.wait_for_function(
        "() => typeof state === 'object' && Array.isArray(state.allLocations) && state.allLocations.length > 0",
        timeout=20000)
    page.wait_for_timeout(5000)   # the heartbeat paints Printer Status and the log


def settle_modal(page, mid):
    page.wait_for_selector(f"#{mid}.show", timeout=10000)
    page.wait_for_function(
        "(id) => { const m = bootstrap.Modal.getInstance(document.getElementById(id)); return !!m && !m._isTransitioning; }",
        arg=mid, timeout=10000)
    page.wait_for_timeout(1500)


def held(spool_id):
    return f"() => (state.heldSpools || []).some((s) => Number(s.id) === {spool_id})"


def stage(page):
    """Two spools moved and two left in the buffer, as the README's dashboard shows."""
    if page.evaluate("() => (state.heldSpools || []).length") > 0:
        return
    page.mouse.move(5, 5)

    def scan(text, done):
        page.keyboard.type(text, delay=8)   # a scanner's burst, then its Enter
        page.keyboard.press("Enter")
        page.wait_for_function(done, timeout=15000)
        page.wait_for_timeout(700)

    empty = "() => (state.heldSpools || []).length === 0"
    scan("ID:16", held(16))
    scan("LOC:SHELF-2", empty)
    scan("ID:9", held(9))
    scan("LOC:SHELF-1", empty)
    scan("ID:14", held(14))
    scan("ID:8", held(8))
    page.wait_for_timeout(3000)       # the log's lines come with the next heartbeat


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1600, "height": 1300})
    # The log's lines count as read (the dashboard shows them all), as after a person
    # has looked: its "N new" pill would sit over a buffer card.
    page.add_init_script("try { localStorage.setItem('fcc.logPill.lastSeenTime', '99:99:99'); } catch (e) {}")

    # 1. The dashboard.
    ready(page)
    stage(page)
    page.mouse.move(5, 5)
    page.screenshot(path=str(OUT / "dashboard.png"))

    # 2. A toolhead's window with its Quick-Swap grid.
    page.evaluate("() => window.openManage('HEAD-1')")
    settle_modal(page, "manageModal")
    # Scrolled to the loaded spool's card: with a spool in the buffer, the DEPOSIT card
    # above it would be cut in half under the header.
    page.evaluate("""() => { const body = document.querySelector('#manageModal .modal-body');
        const list = document.getElementById('manage-list-view');
        if (body && list) body.scrollTop += list.getBoundingClientRect().top - body.getBoundingClientRect().top - 12; }""")
    page.wait_for_timeout(600)
    page.locator("#manageModal .modal-content").screenshot(path=str(OUT / "quick-swap.png"))

    # 5. The help for that window (the ? in its header).
    page.locator('#manageModal [data-fcc-help="location-window"]').click()
    page.wait_for_selector("#fcc-shortcuts-overlay", state="visible")
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / "help.png"))
    page.keyboard.press("Escape")
    page.evaluate("() => window.closeManage()")
    page.wait_for_selector("#manageModal", state="hidden", timeout=10000)
    page.wait_for_timeout(800)

    # 4. A spool's window.
    page.evaluate("() => openSpoolDetails(1)")
    settle_modal(page, "spoolModal")
    page.locator("#spoolModal .modal-content").screenshot(path=str(OUT / "spool-window.png"))
    page.evaluate("() => bootstrap.Modal.getInstance(document.getElementById('spoolModal')).hide()")
    page.wait_for_selector("#spoolModal", state="hidden", timeout=10000)
    page.wait_for_timeout(800)

    # 3. The slot picker: a buffered spool, then the dryer box's label. Cancelled after.
    # Not returned: evaluate would wait on the picker's promise, which only an answer settles.
    page.evaluate("() => { window.openSlotPicker({ location: 'DRYBOX-1', spool: 8 }); }")
    page.wait_for_selector("#fcc-slot-picker .fcc-sp-tile", timeout=15000)
    page.wait_for_timeout(1200)
    page.screenshot(path=str(OUT / "slot-picker.png"))
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    browser.close()
print("done", OUT)
