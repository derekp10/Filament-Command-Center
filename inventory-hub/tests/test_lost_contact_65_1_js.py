"""Group 65.1 (1a), the card: a review whose end FCC saw only after it lost sight of
the print says so, hermetic (the real cancel_review.js under node's `vm`).

  ❓ "FCC lost contact with XL at ~30% (14:02) and next saw it idle at 16:40, so the
     print may have gone further."
  🛑 "... and next saw it stopped at 16:40: it may have printed further before it was
     cancelled."
  restart: "FCC last saw this print at ~30% (14:02), before FCC restarted at 16:35."

Times are the browser's clock, from the seconds the record stores (a date before the
time when it isn't today). A card from before the release (no `lost_contact`) keeps
its look. The expected clock strings are worked out in the same node run, so the test
holds in any timezone. Red on 0fa8afd2 (no line at all).
"""
from __future__ import annotations

import time

from test_cancel_review_picker_scan_js import (  # noqa: F401  (pytestmark: skip without node)
    RESPOND_JS, SPOOLS, _base, _row, pytestmark, run)

NOW = time.time()
LOST, SEEN, BACK = NOW - 9480, NOW - 9600, NOW


def _lc(**more):
    return dict({"progress": 0.3, "seen_at": SEEN, "lost_at": LOST, "back_at": BACK,
                 "back_state": "IDLE", "why": "lost"}, **more)


CARDS = [
    _base("amb", "partial", ambiguous=True, total_grams=12.4, spools=[_row(57, "XL-1", 0, 12.4)], lost_contact=_lc()),
    _base("can", "partial", total_grams=12.4, spools=[_row(58, "XL-1", 0, 12.4)],
          lost_contact=_lc(back_state="STOPPED")),
    _base("rst", "progress_unknown", ambiguous=True, total_grams=0.0, unmeasured_reason="unsampled",
          lost_contact=_lc(lost_at=None, why="restart")),
    _base("bare", "progress_unknown", ambiguous=True, total_grams=0.0, unmeasured_reason="unsampled",
          lost_contact={"progress": 0.3, "back_state": "IDLE", "why": "lost"}),
    _base("old", "partial", ambiguous=True, total_grams=12.4, spools=[_row(59, "XL-1", 0, 12.4)]),
    _base("job", "partial", ambiguous=True, total_grams=12.4, spools=[_row(60, "XL-1", 0, 12.4)],
          lost_contact=_lc(back_state="PRINTING")),
]

LOOK_JS = r"""
const out = { cards: {}, clock: {} };
for (const c of document.querySelectorAll('.fcc-cr-card')) {
  const n = c.querySelector('.fcc-cr-lost');
  out.cards[c.dataset.job] = n ? { text: n.textContent.replace(/\s+/g, ' ').trim(),
                                   role: n.getAttribute('role') } : null;
}
const clock = (s) => {
  const d = new Date(s * 1000);
  const hm = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  return d.toDateString() === new Date().toDateString()
    ? hm : `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })} ${hm}`;
};
for (const [k, s] of Object.entries(__DATA__.times)) out.clock[k] = clock(s);
return out;
"""


def test_a_review_seen_after_lost_contact_says_where_fcc_last_saw_the_print(tmp_path):
    res = run(tmp_path, RESPOND_JS + LOOK_JS,
              {"pending": CARDS, "spools": SPOOLS, "times": {"lost": LOST, "seen": SEEN, "back": BACK}})
    c, t = res["cards"], res["clock"]
    assert c["amb"] == {"text": f"📡 FCC lost contact with TESTER at ~30% ({t['lost']}) and next saw it idle at "
                                f"{t['back']}, so the print may have gone further.", "role": "note"}, c
    assert c["can"]["text"] == (f"📡 FCC lost contact with TESTER at ~30% ({t['lost']}) and next saw it stopped at "
                                f"{t['back']}: it may have printed further before it was cancelled."), c
    assert c["rst"]["text"] == (f"📡 FCC last saw this print at ~30% ({t['seen']}), before FCC restarted at "
                                f"{t['back']}."), c
    assert c["bare"]["text"] == ("📡 FCC lost contact with TESTER at ~30% and next saw it idle, so the print may "
                                 "have gone further."), c
    assert c["job"]["text"].endswith(f"next saw it printing another job at {t['back']}, so the print may have gone "
                                     "further."), c
    assert c["old"] is None, c


def test_a_time_on_another_day_carries_its_date(tmp_path):
    long_ago = NOW - 3 * 86400
    card = _base("x", "partial", ambiguous=True, total_grams=12.4, spools=[_row(57, "XL-1", 0, 12.4)],
                 lost_contact=_lc(lost_at=long_ago))
    res = run(tmp_path, RESPOND_JS + LOOK_JS,
              {"pending": [card], "spools": SPOOLS, "times": {"lost": long_ago}})
    lost = res["clock"]["lost"]
    assert " " in lost and f"({lost})" in res["cards"]["x"]["text"], res
