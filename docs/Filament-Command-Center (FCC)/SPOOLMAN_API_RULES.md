# Spoolman API & Serialization Rules 🚨

> [!WARNING]  
> Before spending hours debugging `500 Internal Server Errors` or serialization issues when patching or creating Spools/Filaments natively against the Spoolman API, **consult this document first**. The following rules act as the absolute source of truth for Spoolman 0.23+ API behavior.

## 1. Boolean String Coercion inside `extra`
Spoolman uses Pydantic to strictly interpret payload models. For any custom fields saved in the `extra` dictionary, Pydantic type-checks against `dict[str, str]`. 

* **❌ INVALID (NATIVE BOOL):** `{"is_refill": False}` -> **Fails with 422 Unprocessable Entity** 
* **✅ VALID (LITERAL STRING):** `{"is_refill": "false"}` -> **Succeeds**.

You must map standard Python Native Booleans into purely lowercase string literals `"true"` and `"false"`. The wrapper function `sanitize_outbound_data()` in `spoolman_api.py` automatically does this. 

## 2. Choice Constraints inside `extra`
Spoolman has a custom field table (`field`) that enforces data structures natively at the SQLite level. For fields typed as `choice` (e.g. `spool_type`), the input string string MUST match the exact text of the choice without recursive JSON quoting or extra wrapping.

* **❌ INVALID (JSONified String):** `{"spool_type": "\"NFC Plastic\""}` -> **Fails with 400 Value is not a valid choice**
* **✅ VALID (Naked Match):** `{"spool_type": "NFC Plastic"}` -> **Succeeds** (Provided the String matches a valid Spoolman Config Choice).

## 3. The `500 Internal Server Error` Fake-out (TrueNAS permissions)
If every single test confirms your payload structure is perfectly legal according to Rules 1 and 2, but a `PATCH` or `POST` still returns a stark `500 Internal Server Error` uniformly, **the Database file on TrueNAS is likely locked to ReadOnly!**
- **Symptom Phase 1:** A `PATCH` containing identical data to the DB natively returns `200 OK` (because SQLAlchemy detects no change and skips the write cycle).
- **Symptom Phase 2:** A `PATCH` attempting to modify literally any field individually returns `500 Internal Server Error`.
- **Diagnosis:** Run a docker log dump on TrueNAS. You will see: `sqlite3.OperationalError) attempt to write a readonly database`. This is a SysAdmin File Permission mismatch (usually on Dev containers), NOT a code bug!

## 4. Spool Extrusion Math Integrity Constraint
Spoolman schemas internally dictate that you cannot mathematically extract more filament than natively defined. 

* **Math Limit:** `used_weight` <= `initial_weight`
* **Consequence:** Pushing a `used_weight` that exceeds `initial_weight` (or pushing `scale_weight` updates that result in the same mathematical outcome) crashes Spoolman via native SQLAlchemy constraint violation.
* **Solution:** Data sent to Spoolman must be strictly clamped `min(used_weight, initial_weight)`. The `create_spool` and `update_spool` backend callers natively intercept and clamp this before dispatching.

*These guidelines are permanently baked-in via unit tests located at `inventory-hub/tests/`*
