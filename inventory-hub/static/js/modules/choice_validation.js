/* MODULE: CHOICE VALIDATION — Group 10.9 prevention guards for filament-attributes
   and other choice-field add-new entry points.

   Spoolman makes choices permanent the moment they're POSTed to
   /api/external/fields/add_choice — removal requires a destructive
   snapshot/restore migration. The filament-attributes list grew dead entries
   like `Tran`, `F`, `Carbon-Fiber` from unchecked single-char and typo-prone
   input. These guards block the obvious garbage before it reaches Spoolman.

   API (all globals on window.*):
     window.normalizeChoice(raw)
       → string with leading/trailing whitespace removed and internal
         whitespace runs collapsed to single spaces.

     window.levenshtein(a, b)
       → integer edit distance.

     window.validateNewChoice(raw, existingChoices)
       → { ok: bool, canonical: string, error?: string, suggestion?: string }
         * ok=false + error      → reject with inline message.
         * ok=true + suggestion  → fuzzy/exact match found; caller should
                                   ask "Did you mean <suggestion>?".
         * ok=true (no suggestion) → safe to commit (caller may still wrap
                                     in a two-step confirm).
*/
console.log("🚀 Loaded Module: CHOICE VALIDATION");

(function () {
    const LEADING_TRAILING_PUNCT = /^[;,:/]|[;,:/]$/;
    const MIN_LENGTH = 3;

    function normalizeChoice(raw) {
        return String(raw == null ? '' : raw)
            .trim()
            .replace(/\s+/g, ' ');
    }

    function levenshtein(a, b) {
        a = String(a == null ? '' : a);
        b = String(b == null ? '' : b);
        if (a === b) return 0;
        if (!a.length) return b.length;
        if (!b.length) return a.length;
        const prev = new Array(b.length + 1);
        const curr = new Array(b.length + 1);
        for (let j = 0; j <= b.length; j++) prev[j] = j;
        for (let i = 1; i <= a.length; i++) {
            curr[0] = i;
            for (let j = 1; j <= b.length; j++) {
                const cost = a.charCodeAt(i - 1) === b.charCodeAt(j - 1) ? 0 : 1;
                curr[j] = Math.min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost);
            }
            for (let j = 0; j <= b.length; j++) prev[j] = curr[j];
        }
        return prev[b.length];
    }

    // Normalized-key form: lowercase + drop hyphens/underscores/spaces.
    // Catches "Carbon-Fiber" vs "Carbon Fiber" vs "carbonfiber".
    function _normKey(s) {
        return String(s == null ? '' : s).toLowerCase().replace(/[-_\s]+/g, '');
    }

    function validateNewChoice(raw, existingChoices) {
        const list = Array.isArray(existingChoices) ? existingChoices : [];
        const trimmed = String(raw == null ? '' : raw).trim();

        if (!trimmed) {
            return { ok: false, canonical: '', error: 'Cannot be empty' };
        }
        // Punctuation check runs on the trimmed-but-not-collapsed string so
        // that "Transparent; High-Speed" (separator confusion) gets caught.
        if (LEADING_TRAILING_PUNCT.test(trimmed)) {
            return {
                ok: false,
                canonical: trimmed,
                error: 'Cannot start or end with punctuation (; , : /)',
            };
        }
        const canonical = normalizeChoice(trimmed);
        if (canonical.length < MIN_LENGTH) {
            return {
                ok: false,
                canonical,
                error: `Must be at least ${MIN_LENGTH} characters`,
            };
        }

        const canonLower = canonical.toLowerCase();
        const canonNorm = _normKey(canonical);

        // Search existing choices for a suggestion. Priority order:
        //   exact case-insensitive > normalized-key equality > prefix-of > Levenshtein <= 2.
        // First match wins; we don't enumerate all matches because a single
        // suggestion is the actionable signal we want to surface.
        let best = null;
        for (const existing of list) {
            if (!existing) continue;
            const existingStr = String(existing);
            const existingLower = existingStr.toLowerCase();
            if (existingLower === canonLower) {
                best = { existing: existingStr, rank: 0 };
                break;
            }
            if (_normKey(existingStr) === canonNorm) {
                if (!best || best.rank > 1) best = { existing: existingStr, rank: 1 };
                continue;
            }
            if (existingLower.startsWith(canonLower) && existingLower !== canonLower) {
                if (!best || best.rank > 2) best = { existing: existingStr, rank: 2 };
                continue;
            }
            const d = levenshtein(canonLower, existingLower);
            if (d > 0 && d <= 2) {
                if (!best || best.rank > 3) best = { existing: existingStr, rank: 3 };
            }
        }

        if (best) {
            return { ok: true, canonical, suggestion: best.existing };
        }
        return { ok: true, canonical };
    }

    window.normalizeChoice = normalizeChoice;
    window.levenshtein = levenshtein;
    window.validateNewChoice = validateNewChoice;
})();
