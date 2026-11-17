"""The buffer cards' refresh answers are kept in order (Group 57 review), node.

Runs the REAL buffer-refresh block of static/js/modules/inv_cmd.js (from
`let _liveRefreshInflight` through `window.liveRefreshBuffer =
liveRefreshBuffer;`) under node's `vm` with a fake clock and fetches released
by hand, so it runs under --offline (skipped without node, as
test_core1_return_ejectall_js.py is).

Since 57.5 a heartbeat answers spools_refresh from the spool list it read
before its printer probes, seconds before it lands, so an answer can be older
than what the cards already show. Pinned:
  - a heartbeat sent before the page's own change (a weigh-out's
    liveRefreshBuffer) never paints over it (round 1: 40 g back to 120 g);
  - a refresh asked for while another is in flight sends one more once that
    one is back, and the one in flight (read before the change) doesn't paint
    (round 2: it painted 120 g, and the heartbeat that would have mended it
    was dropped); two changes meanwhile send one more, not two;
  - an older answer never paints over a newer one, whichever kind each is;
  - a payload with no send time (an older caller) paints as it comes.
Each case was run against inv_cmd.js at 6314386 and the coalesced and
newer-over-older cases failed there.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from test_core1_return_ejectall_js import MODULES, NODE, pytestmark  # noqa: F401  (skip without node)

DRIVER = r"""
const fs = require('fs');
const vm = require('vm');
const src = fs.readFileSync(__INV_CMD__, 'utf8');
const startTag = 'let _liveRefreshInflight';
const endTag = 'window.liveRefreshBuffer = liveRefreshBuffer;';
const a = src.indexOf(startTag);
const b = src.indexOf(endTag);
if (a < 0 || b < 0) { console.log('RESULT:' + JSON.stringify({ error: 'block not found' })); process.exit(0); }
const block = src.slice(a, b + endTag.length);

async function run(steps) {
    let now = 0;
    const pending = [];
    const ctx = {
        state: { heldSpools: [
            { id: 1, display: 'A', remaining_weight: 500, details: {}, archived: false, location: 'X' },
            { id: 2, display: 'B', remaining_weight: 120, details: {}, archived: false, location: 'X' },
        ] },
        window: {}, console, Number, JSON,
        Date: { now: () => now },
        performance: { now: () => now },
        fetch: (url, opts) => new Promise((resolve) => pending.push({ url, resolve })),
    };
    ctx.window.renderBuffer = () => {};
    vm.createContext(ctx);
    vm.runInContext(block + '\nthis.__paint = _renderSpoolsRefreshPayload; this.__refresh = liveRefreshBuffer;', ctx);
    const B = () => ctx.state.heldSpools.find((s) => s.id === 2).remaining_weight;
    const payload = (bw) => ({ 1: { display: 'A', remaining_weight: 500, details: {}, archived: false, location: 'X' },
                               2: { display: 'B', remaining_weight: bw, details: {}, archived: false, location: 'X' } });
    const flush = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); };
    const seen = [];
    const api = {
        at: (t) => { now = t; },
        change: (w) => { if (w !== undefined) ctx.state.heldSpools.find((s) => s.id === 2).remaining_weight = w; ctx.__refresh(); },
        land: async (bw) => {
            const p = pending.shift();
            if (!p) { seen.push(['(no refresh was out to land)', B(), 0]); return; }
            p.resolve({ json: () => Promise.resolve(payload(bw)) });
            await flush();
        },
        tick: (sentAt, bw) => { ctx.__paint(payload(bw), sentAt === null ? undefined : { sentAt }); },
        // A tick whose spools_refresh is `body` as it is ({} after an outage
        // stop, {error} from a section that raised, or only some spools).
        tickRaw: (sentAt, body) => { ctx.__paint(body, { sentAt }); },
        only: (id, w) => ({ [id]: Object.assign({}, payload(w)[id], id === 1 ? { remaining_weight: w } : {}) }),
        inflight: () => pending.length,
        note: (what) => seen.push([what, B(), pending.length]),
        noteA: (what) => seen.push([what, ctx.state.heldSpools.find((s) => s.id === 1).remaining_weight]),
    };
    await steps(api);
    return seen;
}

(async () => {
    const out = {};
    // A weigh-out while a refresh is in flight (R1, read before it).
    out.coalesced = await run(async (s) => {
        s.at(1000); s.change();                       // R1 goes out (some earlier change)
        s.at(2000); s.change(40);                     // B weighed to 40 here: R1 still out
        s.note('after the weigh-out');
        s.at(2500); await s.land(120); s.note('after R1 (read before the weigh-out) lands');
        s.at(3000); s.tick(1500, 40); s.note('after a tick sent before the weigh-out lands');
        s.at(3500); await s.land(40); s.note('after the one more refresh lands');
        s.at(9000); s.tick(6000, 40); s.note('after a later tick lands');
    });
    // No refresh in flight: an old tick lands after the weigh-out's own refresh.
    out.own = await run(async (s) => {
        s.at(2000); s.change(40);
        s.at(2300); await s.land(40); s.note('after its refresh lands');
        s.at(3000); s.tick(1500, 120); s.note('after an old tick lands');
    });
    // Newer over older, either way round, with no change in between.
    out.order = await run(async (s) => {
        s.at(2500); s.change();                       // a refresh R goes out at 2500
        s.at(3200); s.tick(3000, 40); s.note('after a tick sent at 3000 lands');
        s.at(3400); await s.land(120); s.note('after R (sent at 2500) lands');
        s.at(3600); s.tick(2800, 120); s.note('after a tick sent at 2800 lands');
        s.at(9000); s.tick(6000, 30); s.note('after a tick sent at 6000 lands');
    });
    // Two changes while one is in flight: one more refresh, not two.
    out.burst = await run(async (s) => {
        s.at(1000); s.change();
        s.at(1100); s.change(40);
        s.at(1200); s.change(35);
        s.note('two changes while one is out');
        s.at(1500); await s.land(120); s.note('after the first lands');
        s.at(1800); await s.land(35); s.note('after the one more lands');
    });
    // A payload with no send time paints as it comes.
    out.unstamped = await run(async (s) => {
        s.at(2000); s.change(40);
        s.at(2300); await s.land(40);
        s.tick(null, 77); s.note('after an unstamped payload');
    });
    // Round 3: a tick that carries nothing for a card lands before an older
    // refresh that does: the refresh still paints that card.
    for (const [name, body] of [['empty', {}], ['error', { error: 'boom' }]]) {
        out['carries_nothing_' + name] = await run(async (s) => {
            s.at(1000); s.change();                       // refresh R goes out; B moved on the server
            s.at(1100); s.tickRaw(1100, body); s.note('after a tick that carried no card');
            s.at(1200); await s.land(40); s.note('after R (sent before it) lands');
        });
    }
    out.carries_some = await run(async (s) => {
        s.at(1000); s.change();                           // R goes out
        s.at(1100); s.tickRaw(1100, s.only(1, 490)); s.noteA('after a tick with only A (490 g)');
        s.at(1200); await s.land(40); s.note('after R lands: B from R');
        s.noteA('and A keeps the tick\'s newer 490 g');
    });
    console.log('RESULT:' + JSON.stringify(out));
})().catch((e) => { console.log('RESULT:' + JSON.stringify({ error: String(e && e.stack || e) })); });
"""


def _run(tmp_path: Path) -> dict:
    script = tmp_path / "driver.js"
    script.write_text(DRIVER.replace("__INV_CMD__", json.dumps(str(MODULES / "inv_cmd.js"))), encoding="utf-8")
    proc = subprocess.run([NODE, str(script)], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=60)
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT:")]
    assert proc.returncode == 0 and lines, f"node failed (rc={proc.returncode})\n{proc.stdout}\n{proc.stderr}"
    out = json.loads(lines[-1][len("RESULT:"):])
    assert "error" not in out, out["error"]
    return out


def test_a_refresh_in_flight_during_a_weigh_out_never_paints_its_older_read(tmp_path):
    seen = _run(tmp_path)["coalesced"]
    assert seen == [
        ["after the weigh-out", 40, 1],
        ["after R1 (read before the weigh-out) lands", 40, 1],        # dropped; one more went out
        ["after a tick sent before the weigh-out lands", 40, 1],
        ["after the one more refresh lands", 40, 0],
        ["after a later tick lands", 40, 0],
    ], seen


def test_an_old_tick_never_paints_over_the_weigh_outs_own_refresh(tmp_path):
    seen = _run(tmp_path)["own"]
    assert seen == [["after its refresh lands", 40, 0], ["after an old tick lands", 40, 0]], seen


def test_an_older_answer_never_paints_over_a_newer_one(tmp_path):
    seen = _run(tmp_path)["order"]
    assert seen == [
        ["after a tick sent at 3000 lands", 40, 1],
        ["after R (sent at 2500) lands", 40, 0],
        ["after a tick sent at 2800 lands", 40, 0],
        ["after a tick sent at 6000 lands", 30, 0],
    ], seen


def test_changes_while_one_is_out_send_one_more_not_two(tmp_path):
    seen = _run(tmp_path)["burst"]
    assert seen == [
        ["two changes while one is out", 35, 1],
        ["after the first lands", 35, 1],
        ["after the one more lands", 35, 0],
    ], seen


def test_a_payload_with_no_send_time_paints_as_it_comes(tmp_path):
    assert _run(tmp_path)["unstamped"] == [["after an unstamped payload", 77, 0]]


def test_an_answer_that_carries_no_card_blocks_no_older_one_that_does(tmp_path):
    """Round 3: the read stamp was one for the whole buffer, so an outage
    tick's {} (or a section's {error}) landing first dropped an older refresh
    that held the moved card, and it showed the old place until the next good
    tick. The stamp is each card's now, moved only by an answer that carries
    it. RED on 2749590: B stayed at 120."""
    out = _run(tmp_path)
    for name in ("empty", "error"):
        assert out["carries_nothing_" + name] == [
            ["after a tick that carried no card", 120, 1],
            ["after R (sent before it) lands", 40, 0],
        ], (name, out["carries_nothing_" + name])


def test_an_answer_with_some_cards_moves_only_their_stamps(tmp_path):
    """A tick that carried only A: R, sent before it, still paints B, and A
    keeps the tick's newer read."""
    assert _run(tmp_path)["carries_some"] == [
        ["after a tick with only A (490 g)", 490],
        ["after R lands: B from R", 40, 0],
        ["and A keeps the tick's newer 490 g", 490],
    ]
