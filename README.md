# GeoSketch

A Python desktop application for creating, visualizing, and analyzing 2D geometric objects in UTM coordinates.

## What it does

GeoSketch lets you build geometric scenes from seven object types — **Points, Lines, Rays, Vectors, Circles, Polygons, and Tangents** — and then compute spatial relationships between them: directions, distances, intersections, convexity, and more. Objects are created by clicking on the canvas, filling in a form, or importing from a file. Projects are saved as JSON.

## Status

Pre-implementation. The package structure, spec, and design documents are in place; no business logic has been written yet.

## Requirements

- Python 3.14+
- See `requirements.txt` for runtime dependencies (NumPy, matplotlib, shapely, scipy)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

## Running

```bash
python main.py
# or
python -m geometry
```

## Development

```bash
# Lint
.venv/bin/ruff check .

# Test
.venv/bin/pytest

# Regenerate the UI wireframe (after editing spec/design/_generate_drawio.py)
.venv/bin/python spec/design/_generate_drawio.py
```

## Project layout

```
geometry/       main package (models, services, canvas, ui, persistence, utils)
spec/           product spec (MVP.md) and UI/UX wireframes
docs/           architecture and design notes
tests/          pytest suite
main.py         convenience shim for python main.py during development
```

## License

Apache License 2.0 — see [LICENSE](LICENSE).
