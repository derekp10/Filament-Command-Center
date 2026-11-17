"""The low-stock warning names the grams its Low row shows (Group 57 review,
round 3), node.

stock_report.grams_text (the "running low: 249.9 g left" warning) against the
REAL _stockText of static/js/modules/inv_stock.js (the Low row the page draws
from the server's row grams, stock_report._row_grams), run under node's `vm`
so it RUNS under --offline (skipped without node, as
test_core1_return_ejectall_js.py is).

Round 2 built the warning's text from the total on its own: between the line
and half a gram under it the two printed different tenths ("249.5 g left" in
the Activity Log, "249.6 g" in the list, for 249.57 g), and lower down the two
roundings disagreed by a gram (248.5 g: Python's half-to-even "248", the page's
Math.round "249"). Pinned on every total from 100.00 to 260.00 g in 0.01 g
steps that is Low, under a whole-gram line and two lines with decimals (the
setting takes them), plus sums with binary noise. RED on 2749590.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys

from test_core1_return_ejectall_js import MODULES, NODE, pytestmark  # noqa: F401  (skip without node)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import stock_report  # noqa: E402

DRIVER = r"""
const fs = require('fs');
const vm = require('vm');
const src = fs.readFileSync(__INV_STOCK__, 'utf8').replace(/\r\n/g, '\n');
// The two functions the row's text needs, exactly as the page has them.
const cut = (start, end) => {
    const a = src.indexOf(start);
    const b = src.indexOf(end, a);
    if (a < 0 || b < 0) throw new Error('not found: ' + start);
    return src.slice(a, b + end.length);
};
const code = [
    cut('const _plural = ', ';'),
    cut('const _finite = ', ');'),
    cut('function _stockText(row, threshold) {', '\n    }\n'),
].join('\n');
const ctx = { Number, Math, String };
vm.createContext(ctx);
vm.runInContext(code + '\nthis.__text = _stockText;', ctx);
const cases = JSON.parse(fs.readFileSync(__CASES__, 'utf8'));
const out = cases.map(([grams, line]) => ctx.__text({ grams, spools: 3, spools_total: 3 }, line));
console.log('RESULT:' + JSON.stringify(out));
"""


def _totals():
    totals = [round(100 + i / 100, 2) for i in range(16001)]          # 100.00 .. 260.00 g
    # Sums with binary noise, as stock_of adds real spools.
    totals += [math.fsum(p) for p in ([130.1, 61.3, 58.17], [100, 99, 50.47], [150, 98.5], [200, 49.55],
                                      [136.2, 7.9, 69.6, 36.2], [0.1, 0.2, 249.6])]
    totals += [1000 - 750.2, 1000 - 750.45, 1000 - 750.05]
    return totals


def test_the_warning_names_the_grams_its_low_row_shows(tmp_path):
    cases, want = [], []
    for line in (250.0, 250.4, 249.65):
        for total in _totals():
            if not stock_report.under_line(total, line):
                continue                         # only a Low filament is warned about
            cases.append([stock_report._row_grams(total, line), line])
            want.append((total, line, f"{stock_report.grams_text(total, line)} g · 3 spools"))
    (tmp_path / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
    script = tmp_path / "driver.js"
    script.write_text(DRIVER.replace("__INV_STOCK__", json.dumps(str(MODULES / "inv_stock.js")))
                      .replace("__CASES__", json.dumps(str(tmp_path / "cases.json"))), encoding="utf-8")
    proc = subprocess.run([NODE, str(script)], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=120)
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT:")]
    assert proc.returncode == 0 and lines, f"node failed (rc={proc.returncode})\n{proc.stdout}\n{proc.stderr}"
    shown = json.loads(lines[-1][len("RESULT:"):])
    assert len(shown) == len(want) > 30000
    differ = [(total, line, w, s) for (total, line, w), s in zip(want, shown) if w != s]
    assert not differ, f"{len(differ)} totals differ (total, line, warning, row): {differ[:8]}"


def test_a_tenth_below_survives_binary_noise():
    """A 1000 g spool with 750.2 g used has 249.79999999999995 g left in
    binary: 249.8 to the tenth below, not 249.7 (the docstring's own example
    was wrong, round 3)."""
    assert stock_report._floor_tenth(1000 - 750.2) == 249.8
    assert stock_report._floor_tenth(249.96) == 249.9
    assert stock_report.grams_text(1000 - 750.2, 250.0) == "249.8"
