# Group 60: 📱 Phone & Tags (epic)

**Branch name (when started):** one branch per milestone, e.g. `feature/group-60-phone-view-mockup`, `feature/group-60-openprinttag-read`.
**Estimated effort:** LARGE / multi-session (an epic). The step 3 plan sized its phone milestone at 3–5 sessions after the shared core (another 3–4); tags, the scale and colours add their own. Past estimates ran about 30% low.
**Risk:** **MEDIUM–HIGH, mostly design risk.** A second view must not drift from Classic's move rules; tags and the scale write weights; the HTTPS setup touches Derek's network (on-network, no open ports).

> **Status: `EPIC — design-first` — filed 2026-10-25 (`/refresh-groups`; Derek approved the grouping the same day: "Ok apply the grouping").** Nothing is built before Derek approves a mockup or a written decision (the standing order). Whenever Derek wants to look; it blocks nothing.
> FCC in Derek's pocket: a phone view (Android, a Pixel 11 Pro XL, Chrome, a web page, no app for now), spool tags (Prusa's OpenPrintTag first, read-only first), his SpoolmanScale project talking to FCC, and filament colours that match the printed colour. FCC itself stays plain http and platform-agnostic (Docker, TrueNAS or anything else).
> Research is done and on Derek's machine (git-ignored): `review-samples/2026-10-21-phone-tags/`, `2026-10-21-tags/`, `2026-10-21-scale/`, `2026-10-21-colour/`, `2026-10-21-views/`; read each folder's `corrections.md` (where there is one) before its brief.

## Items covered (quoted from `Feature-Buglist.md`)

| # | Buglist item | Direction |
|---|---|---|
| **60.1** | 📐 *"Plan docs: named sizes and colors as the base for themes; alternative views (phone, wall tablet, printer pictures, the Location Manager) (Derek, 2026-10-21; written)… To go through with him one decision at a time, not to read cold."* *"**Phone first** (decided 2026-10-21…): step 3's milestone order is rewritten after the readability merge."* | **First: Claude rewrites step 3's order to put the phone first** (the readability merge is done, 2026-10-24); then Derek's decisions one at a time (step 3's ten, step 2's six). |
| **60.2** | 📱 *"Phone view first, with spool tags (Derek, 2026-10-21). The phone ("pocket") view comes before the tablet one: Android (a Pixel 11 Pro XL), Chrome, a web page (no app for now). Testing over plain http uses Chrome's "Insecure origins treated as secure" flag on the phone; real HTTPS comes later from a reverse-proxy container with a DNS-challenge certificate, on his network with no open ports."* Plus the older **MOBILE** item: *"Make the entire app mobile friendly so NFC/Scanning works on phones… a mobile mode of mostly touch interface and scanning barcodes/QR codes and NFC tags… won't relye on all the inlaid barcode/qr codes."* | A phone-view mockup, then the shared core, then the build (step 3's milestones, re-ordered). |
| **60.3** | Same item, tags: *"Prusa's OpenPrintTag first (Chrome on his Pixel read a factory Prusament tag); read-only first, then "tap a tag, FCC sees its weight is newer than the tag's and offers to rewrite it"; tag links in Spoolman 0.27's own tag table; an unknown Prusament spool opens the Add wizard filled from its tag (as the QR scan does); FCC's values stay and the tag fills blanks; Bambu next; OpenPrintTag for untagged spools too (he has ~40 blank tags)."* Plus the import item's gap: *"Open Print Tags (Initialize, Read, and Write)"*. | Read-only first, then the write-back offer. Firmware 8.0's tag rule applies to any write ([Group 56](56-deduct-accuracy.md) 56.7): add deltas, never overwrite, once a printer writes tags. |
| **60.4** | ⏸️ PENDING DEREK: *"tap a tagged Bambu spool with Chrome's NFC test page (2026-10-21)… A "Serial Number" line means the phone can link Bambu spools by their tag ID; "Cannot read data" every time means Bambu reading comes from the scale."* (A Prusament OpenPrintTag spool passed the same test on 2026-10-21.) | Derek's hands-on test; it decides whether Bambu tags come from the phone or the scale. |
| **60.5** | ⚖️ *"SpoolmanScale that reads every tag and talks to FCC (Derek, 2026-10-21)… "set a spool on a scale, have it read out, and then put it away". Its PN532 can't read OpenPrintTag (ISO 15693), so Derek ordered a PN5180… Plan: our own copy of the scale's firmware with the new reader (its update check off), a hand test before printing the case, and an FCC "stand-in" for the scale's published server spec, so weigh-ins go through FCC's rules."* (The PN5180 arrived 2026-10-22.) | Decisions first (`corrections.md`), then a hand test, then FCC's stand-in for the scale's server spec. |
| **60.6** | 🎨 *"Filament colours aren't the most accurate available (Derek, 2026-10-21). The hex FCC stores feeds PrusaSlicer, on-screen colour picking and the printed swatch labels, so it should match the printed colour, and FCC should record where each colour came from. For one real Galaxy Red spool three sources disagree: its tag #bf1d2d, Prusament's spool page (what FCC's QR import takes) #8d2129, SpoolmanDB #d94a5a."* (Research `wf_43831b5c-daf`.) | A colour walk with Derek (which source is closest, recording the source), then the import changes. |

## Decisions

- **All design-first, Derek's, one at a time** (pictures where it's a look; the format in his memory: what / where / a real example / options / recommendation / default). The step 3 plan already lists ten (devices and scanning, HTTPS, one scan buffer or one per device, how a device picks its view, the order of work, …) and step 2 six; 60.1 rewrites step 3's order first so the phone leads.
- **Already decided (Derek, 2026-10-21):** phone before tablet; Android + Chrome, a web page; plain http with the Chrome flag for testing, real HTTPS later from an on-network reverse proxy (no open ports); FCC stays platform-agnostic; OpenPrintTag first, read-only first; FCC's values win and a tag fills blanks.
- **Open, shared with other groups:** one scan buffer for every device or one per device (step 3, decision 3) also settles [Group 58](58-audit-label-truth.md)'s "audit mode takes every device's scans"; a richer Printer Status hover card with a tap on touch ([Group 50](50-printer-status-polish.md) 50.5) is designed with the phone view.

## What exists today

- **The plans:** [design-step3-alternative-views.md](design-step3-alternative-views.md) (its milestones at `:169-181` still put the wall-tablet mockup first; its decisions `:183-243`) and [design-step2-named-sizes-colors-and-themes.md](design-step2-named-sizes-colors-and-themes.md) (1,222 hand-typed colours and 364 text sizes in 33 files at the time; about 8 sessions; the readability build has since added the named text sizes `--fcc-fs-small` / `-label` / `-row`).
- **Backend:** its answers are plain data any page can use (step 3, "What the backend already gives a new view"); the browser's shared parts (what a scan means, `processScan` in `inv_cmd.js`; how a move asks; the heartbeat) are wired into Classic and come out first (step 3's milestone 2).
- **Tags:** none in FCC yet. `external_parsers.py`'s gap list names *"Open Print Tags — NFC tag init/read/write, no parser yet"* (`external_parsers.py:36-38`). The Prusament QR scan already matches a spool by its unique hash and opens onboarding for an unknown one (the scan pipeline's Prusament handler), the model for "an unknown Prusament spool opens the Add wizard filled from its tag".
- **The question dialogs fit a phone** since the readability build (2026-10-24), and Printer Status lays its tiles out from 376 px wide (DESIGN.md "Printer Status tiles sit in even rows").

## Milestones (to be re-ordered with Derek in 60.1)

1. 60.1: step 3's order rewritten, phone first; Derek's decisions one at a time.
2. 60.4: his Bambu tap test (any time; it decides where Bambu tags are read).
3. A phone-view mockup (pictures, made-up data); then the shared core behind Classic (no visible change), then the phone build.
4. 60.3: OpenPrintTag read-only in the phone view; then the write-back offer, after a test on a spare tag.
5. 60.5: the scale's decisions, a hand test, FCC's stand-in for its server spec.
6. 60.6: the colour walk, then the import changes and a recorded colour source.

## Tests (per milestone)

- A new view's own pictures and checks (step 3: "each view gets its own address, its own picture checks"); every move from it goes through the same doors and questions as Classic (`askMoveConfirm`, `buildMoveReplay`), pinned by the door canaries; contrast and text-size guards; a phone viewport in the visual harness.
- Tag parsing on recorded tag dumps (offline fixtures, e.g. the decoded production tags in `review-samples/2026-10-21-phone-tags/decoded-production-tags.txt`, trimmed and committed only if they hold nothing private).
- No test writes to a real tag or to prod.

## Done when

- An epic: each milestone closes on its own. The group is done when Derek has a phone view he uses, tags read (and, if he wants, write back), and his picks on the scale and colours are built or parked.

## Risks

- Two views drifting apart (the shared core comes first for this reason).
- Tag writes: a web page rewrites the whole tag (phone-tags brief); never write a locked or foreign tag; deltas, not absolutes, once a printer writes tags.
- HTTPS on the home network is Derek's setup; FCC must keep working on plain http.
