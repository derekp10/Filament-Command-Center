# 📋 Epic Planning Sprint — Scope Remaining Epics, then Group by Commonality

> **Status:** IN PROGRESS (started 2026-07-07). **Self-contained handoff — a fresh chat needs no prior context.**
> **Kicked off by Derek:** *"I'd like to build out more plans and see if they all don't have a commonality so I could see if they can't be grouped together so that they can be done together."*
> **Prod state:** the cleanup sweep + empty-weight combine + Bulk Moves scoping were **RELEASED to `main` (`b49158b`, 2026-07-07)** — ⚠️ **PROD PULL PENDING Derek's TrueNAS play** (`update.sh` → `git reset --hard origin/main`). `dev` == `main`.

## The goal
Scope each remaining FCC epic into a **phased plan doc** (the model is [L298-bulk-moves-plan.md](L298-bulk-moves-plan.md)), THEN do a **cross-plan commonality pass** to find shared surfaces, so related epics can be batched into a **working group and built together** — a shared component built once and reused N×, instead of each epic re-inventing it.

## Method (per epic — no code during scoping)
1. Research fan-out (grounded, file:line) over the epic's subsystem — reuse the `Workflow` tool with ~4–6 parallel readers (see how the Bulk Moves scope was built: primitives / model / scan-flow / edge-cases / UX-undo).
2. Synthesize a plan doc under `docs/agent_docs/tasks/` with: **reuse map** (what to build ON, not reinvent), **design decisions** (surface the real forks for Derek via `AskUserQuestion`, like the Bulk Moves 4 decisions), **phased build order**, **edge-case/safety checklist**.
3. Lock the decisions with Derek, then the doc is build-ready.

## Epic inventory + status
| Epic | Status | Plan doc / groundwork |
|---|---|---|
| **Bulk Moves (L298)** | ✅ **SCOPED, 4 decisions locked** | [L298-bulk-moves-plan.md](L298-bulk-moves-plan.md) |
| **Sub-location add redesign** | ⬜ NEEDS SCOPING | (buglist "Adding new locations… messy") |
| **L271 Phase-5 prefix-retirement** | ⬜ NEEDS SCOPING | groundwork in [L271-location-manager-phase-plan.md](L271-location-manager-phase-plan.md) |
| **Per-printer Config (L18 Phase 5)** | ⬜ NEEDS SCOPING | groundwork in [L18-config-system-design.md](L18-config-system-design.md) |
| Make everything user-configurable | folds into the Config cluster | — |
| Rename inventory hub → FCC | ⬜ NEEDS SCOPING (mechanical branding sweep) | — |
| Mobile (L315) | ⬜ NEEDS SCOPING (large, self-contained) | — |
| Project Color Loadout (L391) | separate SQLite add-on; blocked on a real ColorMix `.3mf` | `docs/Project-Color-Loadout/` |
| Amazon multi-pack / external parsers | small, **INPUT-GATED** (needs Derek decisions first) | — |

## Commonality groupings (preliminary — confirm during the pass)

### 🌳 Location-tree cluster — STRONGEST grouping candidate
- **Bulk Moves (L298)** — needs source/dest **location-tree pickers**
- **Sub-location add redesign** — needs a **parent picker** in the add/edit flow
- **L271 Phase-5 prefix-retirement** — retires prefix-parsing on the same `parent_id` model
- → **Shared surface: a reusable location-tree picker + the L271 `parent_id` model.** Build the picker once, use it 3×. Bundle into ONE working group.

### ⚙️ Config cluster
- **Per-printer Config (L18 Phase 5)** — a per-printer *map* field type + UI renderer
- **Make-everything-configurable** — same `config_schema.py` + Config modal
- → **Shared surface: `config_schema.py` + the Config UI renderer.**

### Standalone (no strong grouping)
Rename→FCC, Mobile (L315), Project Color Loadout (L391), Amazon multi-pack + external parsers.

## ▶ NEXT-CHAT KICKOFF — start here
Recommended order:
1. **Scope the two unscoped Location-tree epics** into plan docs (Bulk Moves is already scoped):
   - Sub-location add redesign
   - L271 Phase-5 prefix-retirement
2. **Run the commonality pass** across all three → confirm the shared location-tree picker → propose ONE **"Location-tree cluster" working group** that builds the picker + all three epics together.
3. Then optionally scope the **Config cluster** (Per-printer Config, L18 Phase 5).
4. Surface each plan's design forks to Derek (like the Bulk Moves 4 decisions) before finalizing.

**Paste this into a fresh chat to resume:**
> Continue the epic planning sprint — see `docs/agent_docs/tasks/planning-sprint-epic-grouping.md`. Scope the Location-tree cluster (sub-location add redesign + L271 Phase-5 prefix-retirement) into phased plan docs like the Bulk Moves one, then do the commonality pass and propose the working group. No code yet — surface the design decisions for me.
