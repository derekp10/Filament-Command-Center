# Spoolman API & Serialization Rules 🚨

> [!WARNING]  
> Before spending hours debugging `500 Internal Server Errors` or serialization issues when patching or creating Spools/Filaments natively against the Spoolman API, **consult this document first**. Checked against Spoolman 0.27 (what dev and prod run, 2026-11). CLAUDE.md's "Spool / Filament write surfaces" section has the full rules for writing to Spoolman: the read-merge, clearing an extra, and surfacing a refusal.

## 1. Boolean String Coercion inside `extra`
Spoolman uses Pydantic to strictly interpret payload models. For any custom fields saved in the `extra` dictionary, Pydantic type-checks against `dict[str, str]`. 

* **❌ INVALID (NATIVE BOOL):** `{"is_refill": False}` -> **Fails with 422 Unprocessable Entity** 
* **✅ VALID (LITERAL STRING):** `{"is_refill": "false"}` -> **Succeeds**.

You must map standard Python Native Booleans into purely lowercase string literals `"true"` and `"false"`. The wrapper function `sanitize_outbound_data()` in `spoolman_api.py` automatically does this. 

## 2. Every `extra` value is JSON, encoded exactly once
Spoolman reads each value in `extra` as JSON. A text or choice value therefore goes out with its quote marks, encoded once, and a choice field (e.g. `spool_type`) then checks the decoded text against its choices exactly. The examples below are request bodies as they go over the wire:

* **✅ VALID (encoded once):** `{"extra": {"spool_type": "\"NFC Plastic\""}}` -> the value's text is `"NFC Plastic"`, quote marks included, which reads as NFC Plastic -> **Succeeds** when NFC Plastic is one of the field's choices.
* **❌ INVALID (bare):** `{"extra": {"spool_type": "NFC Plastic"}}` -> the value's text `NFC Plastic` isn't JSON -> **Fails with 400 "Value is not valid JSON."**
* **❌ INVALID (encoded twice):** `{"extra": {"spool_type": "\"\\\"NFC Plastic\\\"\""}}` -> it reads as `"NFC Plastic"` with the quote marks still on -> **Fails with 400 "Value is not a valid choice."**

`sanitize_outbound_data()` in `spoolman_api.py` encodes each value once and leaves a value that is already encoded alone. (Until 2026-11 this rule said the bare value was the valid one, which neither the code nor Spoolman agrees with; `tests/spoolman_extra_fake.py` checks values the way Spoolman 0.27 does.)

## 3. The `500 Internal Server Error` Fake-out (TrueNAS permissions)
If every single test confirms your payload structure is perfectly legal according to Rules 1 and 2, but a `PATCH` or `POST` still returns a stark `500 Internal Server Error` uniformly, **the Database file on TrueNAS is likely locked to ReadOnly!**
- **Symptom Phase 1:** A `PATCH` containing identical data to the DB natively returns `200 OK` (because SQLAlchemy detects no change and skips the write cycle).
- **Symptom Phase 2:** A `PATCH` attempting to modify literally any field individually returns `500 Internal Server Error`.
- **Diagnosis:** Run a docker log dump on TrueNAS. You will see: `sqlite3.OperationalError) attempt to write a readonly database`. This is a SysAdmin File Permission mismatch (usually on Dev containers), NOT a code bug!

## 4. Spool Extrusion Math Integrity Constraint
Spoolman schemas internally dictate that you cannot mathematically extract more filament than natively defined. 

* **Math Limit:** `used_weight` <= `initial_weight`
* **Consequence:** Pushing a `used_weight` that exceeds `initial_weight` (or pushing `scale_weight` updates that result in the same mathematical outcome) crashes Spoolman via native SQLAlchemy constraint violation.
* **Solution:** Data sent to Spoolman must be strictly clamped `min(used_weight, initial_weight)`. The `create_spool` and `update_spool` backend callers natively intercept and clamp this before dispatching. `update_spool` caps only against a spool's own `initial_weight`; for a spool with none, the print deduct clamps against the filament's net weight itself (`spoolman_api.effective_initial_weight`).

*These guidelines are permanently baked-in via unit tests located at `inventory-hub/tests/`*
