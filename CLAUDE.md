# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Keeping this file current

This document describes a moving target. The repo will grow source code, a package manifest, a test suite, and a git remote over time. **When you make a change that invalidates anything here, update this file in the same turn** — do not leave future Claude instances reading stale guidance. In particular, revise the sections below as soon as the relevant condition flips:

- **Repository status** — when the first real source file lands, update the layout description and add the actual run/test invocations (`python -m geometry`, `pytest`, `ruff check`).
- **Domain model** — when the spec in `spec/MVP.md` changes, reconcile the eight-point list here (especially ID prefixes, angle conventions, and the vector endpoint formula).
- **UI architecture** — once real widgets exist, replace the "when implementation begins" framing with pointers to the actual modules.
- Add a **Common commands** section the first time there are commands worth listing.

If you're unsure whether a change warrants a CLAUDE.md edit, err toward updating: a small stale line is worse than a small redundant one.

## License

This project is licensed under the **Apache License 2.0**. The full text is in `LICENSE` at the repo root.

**Every new Python source file must begin with this header** (adjust the filename comment as needed):

```python
# Copyright 2026 David Wies
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
```

Apply this header to:
- All files under `geometry/` (including `__init__.py` stubs)
- `main.py`
- `spec/design/_generate_drawio.py`
- Any new `.py` file added to the project, including test files under `tests/`

Do **not** add headers to `.md`, `.toml`, `.drawio`, `.json`, or other non-code files.

When adding a third-party dependency, verify it carries a license compatible with Apache 2.0 (permissive licenses — MIT, BSD, Apache 2.0 — are fine; GPL is not). Note any compatibility checks here if a non-obvious dependency is added.

## Repository status

The project has a scaffolded package structure. Most source files are empty stubs, but the entry point is wired and runnable (`geometry/__main__.py` prints a placeholder). Do not treat any module beyond `__main__.py` as functional until code is actually written inside it.

Key layout:
```
geometry/           ← main package
  __main__.py       ← real entry point (geometry.__main__:main per pyproject.toml)
  project.py        ← Document/Project: object store, selection, dirty state, undo history
  models/           ← pure data classes: Point, Line, Polygon, Ray, Vector, Circle, Tangent
  services/         ← all business logic (geometry, validation, commands/undo, render instructions, dep_graph)
  canvas/           ← matplotlib canvas integration (canvas_view, interaction state machine)
  ui/               ← tkinter widgets (main_window, dialogs, properties_panel, cards)
  persistence/      ← JSON save/load (serializer, schema/version checking)
  utils/            ← constants (EPS_*), angle conversions, id_factory, event bus
tests/              ← pytest suite (empty)
main.py             ← thin shim: `from geometry.__main__ import main; main()`
pyproject.toml      ← packaging config
spec/               ← product spec and UI/UX design (source of truth)
  MVP.md
  design/
    geometry-app-ui-ux.md      ← authoritative text design
    geometry-app-ui-ux.drawio  ← 14-page wireframe (generated, never hand-edit)
    _generate_drawio.py        ← regenerate the drawio; run after any change
    diagrams/                  ← earlier wireframe sketches (reference only)
docs/
  geo-sketch-design.md         ← architecture and design document
```

The real entry point is `geometry/__main__.py` (declared in `pyproject.toml`). `main.py` at the repo root is a convenience shim for `python main.py` during development; keep all startup logic in `geometry/__main__.py`.

**Remote**: https://github.com/david-wies/geosketch (public, Apache 2.0).

The entry point is functional: `python -m geometry` (or `python main.py`) prints the placeholder banner. All other modules remain stubs.

## Environment + common commands

The project has a Python 3.14 virtualenv at `.venv/` (gitignored). Dependencies are pinned in `requirements.txt` (runtime) and `requirements-dev.txt` (adds `ruff`, `pytest`). Activate it before running anything:

```bash
source .venv/bin/activate          # or: .venv/bin/python <cmd>
```

- `python3 -m venv .venv && .venv/bin/python -m pip install -r requirements-dev.txt` — recreate the venv from scratch (e.g. on a fresh clone).
- `.venv/bin/python spec/design/_generate_drawio.py` — regenerate `spec/design/geometry-app-ui-ux.drawio` from the Python source. Run this whenever you change the generator; never hand-edit the drawio XML.
- `.venv/lib/python3.14/site-packages/bin/ruff check .` — lint. (`ruff` was installed with `--target` so its binary lands here, not in `.venv/bin/`).
- `.venv/bin/pytest` — test (no tests yet).

The target stack:

- Python desktop app, **tkinter** for UI, **matplotlib** for the canvas
- **NumPy float64** as the reference precision for all geometry results
- **shapely ≥ 2.0** for polygon validity, intersection, and distance (GEOS-backed)
- **scipy ≥ 1.13** for convex hull (`scipy.spatial.ConvexHull` via QHull, returns vertex indices)
- **JSON** for project persistence

## Spec-driven workflow (how the user expects work to be done)

The user follows the **Spec-Driven Workflow v1** documented in `.github/instructions/spec-driven-workflow-v1.instructions.md`. Three artifacts are treated as the source of truth and should be kept in sync when work happens:

- `requirements.md` — user stories + acceptance criteria in **EARS notation** (`WHEN … THE SYSTEM SHALL …`)
- `design.md` — architecture, data flow, interfaces, data models
- `tasks.md` — trackable implementation plan

The expected phase loop is **Analyze → Design → Implement → Validate → Reflect → Handoff**. When the user asks for "the spec", "the design", or "tasks", they mean these documents — create them if missing rather than improvising prose answers.

The `spec/MVP.md` document is the authoritative product spec. When something in conversation conflicts with it, surface the conflict before changing the spec.

## Domain model that recurs across every feature

Eight things below appear in nearly every form, calculation, and persistence concern — keep them straight before editing anything geometry-related:

1. **Coordinate system is UTM in meters**, expressed as `(easting, northing)`. Easting comes first in tuples; northing comes first in the *point-import text format* (regex `(\w+)\s+([\d.-]+)\s+([\d.-]+)` captures name, then northing, then easting). Do not flip these silently.
2. **Two angle conventions coexist.** Azimuth is clockwise from North in `[0, 2π)`. Angle is standard-math counter-clockwise from East. Every direction-bearing object (Line, Ray, Vector, Tangent) carries `direction_mode` (`azimuth`|`angle`) and `direction_units` (`radians`|`degrees`) but stores `direction` internally in **radians**. Conversions are bidirectional. In-memory enums are uppercase (`DirectionMode.AZIMUTH`); the JSON wire format uses lowercase strings (`"azimuth"`). Deserialization is case-insensitive but always re-saves canonical lowercase.
3. **Polygons are stored CCW.** Any polygon creation path (click, form, file import, relative-offset import) ends up CCW. Default mechanism is **signed-area reverse** on the user-supplied boundary order (works for convex *and* concave). Polygon **file import** additionally exposes an opt-in `Sort (centroid + polar angle)` mode for unordered point sets — this is the *only* place centroid+angle sort is allowed, and it is documented as convex-only. Polygons with `|signed_area| < EPS_AREA` are degenerate and rejected. Simplicity (no self-intersections) is always validated. `is_convex` is cached on creation/modification using the cross-product method.
4. **Object identity is a string ID** of the form `"<type>_NNN"` (e.g. `pt_001`, `ln_001`, `pg_001`, `ry_001`, `vc_001`, `ci_001`, `tg_001`). References between objects (line→points, polygon→points, tangent→circle+point, etc.) are **ID strings, not memory pointers**, and must survive save/load.
5. **Cascading delete.** Deleting a point removes every line/ray/vector/circle/tangent/polygon that references it. Modifying a point's coordinates triggers recomputation of all dependents (directions, distances, intersections).
6. **Seven object types share a common visual envelope** of `name`, `id`, `type`, `alpha` (0.0–1.0), `visibility`. **Point** additionally carries a single `color` (marker color). All other types — **Line, Polygon, Ray, Vector, Circle, Tangent** — carry `line_color` (stroke/outline) and `fill_color` (interior fill). Both are always stored; `fill_color` is only rendered for objects with a closed interior (Circle, Polygon) — for 1D objects (Line, Ray, Vector, Tangent) it is present in the schema but ignored at render time. The JSON persistence schema in `spec/MVP.md` puts these at the top level and nests type-specific fields under `properties` — match that shape exactly when serializing.
7. **Vector endpoint formula** uses the azimuth convention: `endpoint = (origin_e + length·sin(az), origin_n + length·cos(az))`. The `sin`/`cos` swap relative to standard math angle is intentional; do not "fix" it.
8. **Distance semantics differ by argument type.** Point↔polygon = 0 if inside, else min edge distance. Ray↔polygon = distance to nearest intersection or **Infinity**. Polygon↔polygon = 0 if they touch/intersect, else min edge-to-edge.

## UI architecture (when implementation begins)

The UI design is fixed by `spec/design/geometry-app-ui-ux.md` (text spec) and `spec/design/geometry-app-ui-ux.drawio` (14-page wireframe set) — treat these as binding, not advisory. The drawio file is regenerated by `spec/design/_generate_drawio.py`; edit the generator and re-run, do not hand-edit the XML.

- **Three-column main window**: left = creation + tools + import/export + measurements (collapsible cards), center = matplotlib canvas, right = properties of current selection.
- **Shared form layout for every object dialog**: top row is `Name` (full width), second row is color picker + alpha. Mode choices are **radio buttons, not dropdowns** (`Click`/`Form`, `Azimuth`/`Angle`, `Radians`/`Degrees`).
- **Vector form is two tabs**: `Origin + Endpoint` and `Length + Direction`. **Polygon form is two tabs**: `Select Points` and `Enter Vertices` (with a `Number of vertices` spinbox driving a scrollable row table).
- **Reference-point subcomponent** (checkbox + point combobox) is a single reusable widget; it appears in point text import, polygon file import, and polygon `Enter Vertices` tab.
- **Polygon file import dialog** also exposes `Vertex ordering` radios (`Boundary order` / `Sort (centroid + polar angle)`); see `MVP.md`.
- **Edit reuses the create dialog** with fields prefilled — do not build a separate edit form.
- **Render-on-demand canvas**: the canvas only redraws when explicitly requested, not on every model change. The trigger list lives in `MVP.md` §Canvas Display.

## PR review and issue implementation workflow

### PR reviews
After completing a PR review, **always post the findings as a comment on the PR** using `gh pr comment <number> --body "..."`. Do not just report findings in the conversation — they must be recorded on the PR itself.

When a PR includes a **Test Plan** section (a checklist of test steps), **execute every step** as part of the review — even if the checklist items are already marked done. After running each step, update the comment to mark passing items with `[x]` and failing items with a note. Do this on every review pass, including re-reviews before merge, so the test plan reflects the current state of the code.

### Issue implementation
When implementing an issue that contains **Acceptance Criteria**, treat each criterion as a gate:
1. After finishing implementation, go through every criterion one by one and verify it is satisfied.
2. Post a comment on the issue (or PR that closes it) marking each criterion `[x]` (done) or `[ ]` (not done) with a brief note.
3. Do not consider the implementation complete until all criteria are checked off.

## Git workflow

**Never commit directly to `main`.** All changes — including documentation, spec edits, and code — must go through a feature branch and a pull request.

1. Create a branch before making any changes: `git checkout -b <type>/<short-description>` (e.g. `feat/point-model`, `fix/polygon-winding`, `docs/update-readme`).
2. Commit your work on the branch.
3. Open a PR against `main` on GitHub (`gh pr create`).
4. Do not push directly to `main` or use `git push origin main`.

Branch naming convention: `<type>/<kebab-description>` where type is one of `feat`, `fix`, `refactor`, `docs`, `chore`, `test`.

## `.github/` directory — what's actually loaded

`.github/agents/`, `.github/instructions/`, and `.github/skills/` are **the user's curated library of GitHub Copilot-style agent personas, instruction docs, and skill packs**. They are *not* automatically loaded by Claude Code and they are not Claude Code subagents. Treat them as reference material the user may point you at ("follow the principal-software-engineer agent", "use the spec-driven workflow instructions"). Read the specific file when invoked; do not pre-load them.

The top-level `.agent.md` defines a "UX Design Documenter" persona — same category, same caveat.
