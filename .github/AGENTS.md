# Geometry Repository Agent Guidance

## Primary rules for AI coding agents

- This is currently a **spec-only repository**. There is no source code, no package manifest, and no test suite yet.
- Do not invent or assume build/lint/test commands such as `pip install`, `pytest`, `npm`, or similar.
- The authoritative implementation targets are in `spec/MVP.md` and the UI design is in `spec/design/geometry-app-ui-ux.md`.
- Follow the Spec-Driven Workflow v1 in `.github/instructions/spec-driven-workflow-v1.instructions.md`.

## Required documents

- `requirements.md` — user stories and acceptance criteria in EARS notation.
- `design.md` — architecture, data flow, and interfaces.
- `tasks.md` — implementation plan and task tracking.

If the user asks for "the spec", "the design", or "tasks", create or update these files rather than improvising prose.

## Key domain conventions

- Coordinates are UTM in meters and represented as `(easting, northing)`.
- The point-import text format parses name, then northing, then easting.
- Direction-bearing objects store `direction` internally in radians.
- Two direction modes coexist: `azimuth` (clockwise from North) and `angle` (counter-clockwise from East).
- Polygons must be stored CCW and validated as simple (no self-intersections).
- Object IDs use the string format `<type>_NNN` (for example, `pt_001`, `ln_001`, `pg_001`).
- References between objects must be ID strings, not memory pointers, so persistence survives save/load.
- Deleting a point cascades deletes to all dependents; editing a point triggers recomputation of dependents.
- The shared visual envelope is: `name`, `id`, `type`, `color`, `alpha`, `visibility`.
- JSON persistence must match the schema shape in `spec/MVP.md` with top-level object metadata and nested `properties`.
- Vector endpoint calculation uses the azimuth convention with `sin` and `cos` swapped intentionally.
- Distance semantics are type-specific: point↔polygon = 0 if inside, ray↔polygon = nearest intersection or Infinity, polygon↔polygon = 0 if they touch/intersect.

## Notes for agents

- Respect the repo’s current state: the work is in planning and design, not production code.
- Link to existing docs instead of duplicating them.
- Preserve any `.github/agents/*` persona files and `.github/instructions/*` guidance as the user’s curated agent library.
- If asked to implement features, first confirm whether the user wants new code added or only documentation/spec work.

## Useful references

- `CLAUDE.md`
- `spec/MVP.md`
- `spec/design/geometry-app-ui-ux.md`
- `.github/instructions/spec-driven-workflow-v1.instructions.md`
