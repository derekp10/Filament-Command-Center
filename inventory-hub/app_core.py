"""Owns the Flask application object (L316 modularization, step 1).

Every extracted route module does ``from app_core import app`` and keeps its
``@app.route(...)`` decorators verbatim, so endpoint names, the URL map, and
template/static resolution are unchanged from the pre-carve monolith (this
file lives in the same directory as app.py, so Flask's root_path is
identical). app.py re-exports ``app`` so ``from app import app`` and
``app_module.app`` keep working for every existing test and caller.

Python 3.9 runtime (the container image) — keep syntax 3.9-safe.
"""
from flask import Flask  # type: ignore

app = Flask(__name__)


@app.after_request
def add_header(r):
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return r
