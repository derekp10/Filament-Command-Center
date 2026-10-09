"""Bounded retry for outbound `requests` calls, on TRANSPORT errors only.

Why this exists (Group 36): the filament-attributes schema migration PATCHes
~150 records back one at a time after deleting the field. Under load the dev
Spoolman on the NAS blows a multi-second read timeout — hub.log shows
ConnectTimeout/ReadTimeout lines minutes before each observed loss, and every
restore failure costs almost exactly the loop's `timeout` in wall clock, which
is the signature of a transport stall rather than an HTTP rejection (a 4xx
comes back in milliseconds). Because the DELETE has already happened by then,
one blip was permanent data loss.

There was no HTTP retry primitive anywhere in the backend — zero `urllib3`
Retry, zero `HTTPAdapter`, zero retry loop. The only one in the repo lived in
`tests/test_filament_attributes_bulk_api.py` (Group 32.2, written for the very
same flake against the very same endpoint). This promotes that helper into
production essentially verbatim.

Deliberate design points:

* **Transport errors only.** An HTTP status is a real answer from a healthy
  server and must never be retried away — a 400 "Unknown extra field" would
  just fail four times more slowly. Only ReadTimeout / ConnectTimeout /
  ConnectionError are ridden out.
* **A 15 s floor per attempt.** Callers that hand us a tight timeout get
  headroom under load; a fast response still returns immediately. This is the
  same floor `cac02f4` settled on when it raised `update_spool` 5s -> 15s, and
  it cites this same helper as the precedent.
* **The last error is re-raised** after the final attempt, so a genuinely
  wedged server still surfaces instead of silently dropping the write.
* **Verb dispatch via `getattr(requests, verb)`, not `requests.request`.** The
  test suite monkeypatches `requests.get/post/patch/delete` on the shared
  module object to intercept wire calls (see `_install_wire` in
  tests/test_l316_charact_filament_attributes_unit.py). Routing through
  `requests.request` would bypass every one of those seams and silently
  un-test the destructive paths. Keep the getattr form.

Python 3.9 runtime (the container image) — keep syntax 3.9-safe.
"""
import time

import requests  # type: ignore

# Per-attempt timeout floor, in seconds. See the module docstring.
TIMEOUT_FLOOR = 15
# Total attempts (so: 1 initial try + 3 retries).
ATTEMPTS = 4
# Linear backoff base, in seconds; scaled by attempt index (0.75 / 1.5 / 2.25).
BACKOFF = 0.75

# Transport-level failures a bounded retry can ride out. NOT HTTP status
# errors — those are real responses and must never be retried away.
TRANSPORT_ERRORS = (
    requests.exceptions.ReadTimeout,
    requests.exceptions.ConnectTimeout,
    requests.exceptions.ConnectionError,
)


def request_with_retry(method, url, *, attempts=None, backoff=None,
                       timeout_floor=None, **kwargs):
    """`requests.<method>(url, **kwargs)` with a bounded transport retry.

    Returns the `Response` from the first attempt that produced one — including
    an error response, which is returned rather than retried. Raises the last
    transport exception if every attempt failed that way.

    `timeout_floor` raises a caller-supplied timeout to at least that many
    seconds; pass `timeout_floor=0` to honor the caller's value verbatim.

    The three knobs default to the module globals and are resolved HERE rather
    than as parameter defaults, which would bind them at import time and make
    them unpatchable. Tests need to zero the backoff — a full 4-attempt failure
    otherwise sleeps 4.5 s — and that is the same reason `atomic_store` keeps
    its pacing module-level.
    """
    attempts = ATTEMPTS if attempts is None else attempts
    backoff = BACKOFF if backoff is None else backoff
    timeout_floor = TIMEOUT_FLOOR if timeout_floor is None else timeout_floor
    verb = str(method).lower()
    if timeout_floor and kwargs.get("timeout") is not None:
        try:
            kwargs["timeout"] = max(kwargs["timeout"], timeout_floor)
        except TypeError:
            # A tuple timeout (connect, read) — leave it exactly as given.
            pass

    attempts = max(1, attempts)
    last = None
    for i in range(attempts):
        try:
            return getattr(requests, verb)(url, **kwargs)
        except TRANSPORT_ERRORS as e:
            last = e
            if i < attempts - 1:
                time.sleep(backoff * (i + 1))
    # The loop always makes at least one real attempt, so `last` is set here —
    # but assert it rather than letting a future edit turn "no attempts ran"
    # into a confusing `raise None`.
    if last is None:  # pragma: no cover - unreachable while attempts >= 1
        raise RuntimeError(f"request_with_retry made no attempt for {verb} {url}")
    raise last
