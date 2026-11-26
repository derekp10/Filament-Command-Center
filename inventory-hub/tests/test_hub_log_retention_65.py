"""Group 65.4 (Derek, 2026-11-03): "I didn't realize how handy those logs are, and I'm
beginning to wonder if we shouldn't keep them longer."

FCC's own log (every Activity Log line, plus errors) keeps 20 files of 5 MB, 100 MB,
where it kept 6 of 1 MB: from 2026-02-16 to 02-19 one repeated line filled four of the
six and pushed out everything logged before. At today's rate (~66 KB a month) 100 MB
never fills, and a burst like February's would take about 38 days. Group 45.9's
delay=True stays (also pinned in test_host_data_dir_45_9.py), and nothing that reads the
file changes (conftest's count_spoolman_timeouts still reads hub.log.1 after a rollover).

Red on 26daffc2 (maxBytes 1000000, backupCount 5).
"""
from __future__ import annotations

import logging.handlers
import os

import state


def test_hub_log_keeps_100_mb_in_20_files_of_5_mb():
    h = state.f_handler
    assert isinstance(h, logging.handlers.RotatingFileHandler), type(h)
    assert os.path.basename(h.baseFilename) == "hub.log", h.baseFilename
    assert (h.maxBytes, h.backupCount) == (5_000_000, 19), (h.maxBytes, h.backupCount)
    assert h.maxBytes * (h.backupCount + 1) == 100_000_000
    assert h.delay is True
