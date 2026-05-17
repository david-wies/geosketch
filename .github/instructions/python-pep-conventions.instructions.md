---
description: 'Python PEP coding conventions for the Geometry app. Enforced by ruff. Applies to all .py files.'
applyTo: '**/*.py'
---

# Python PEP Conventions

## Linting and Formatting

All Python code is linted and formatted with **ruff** (configured in `pyproject.toml`).

```bash
.venv/bin/ruff check --fix .   # lint + auto-fix
.venv/bin/ruff format .        # format (Black-compatible)
```

Always run both before committing. Do not suppress ruff rules without a documented reason.

---

## PEP 8 — Style Guide

### Naming

| Kind | Convention | Example |
|---|---|---|
| Module / package | `snake_case` | `geometry/models/point.py` |
| Class | `PascalCase` | `class GeometryObject` |
| Function / method | `snake_case` | `def compute_distance()` |
| Variable | `snake_case` | `origin_point` |
| Constant | `UPPER_SNAKE_CASE` | `EPS_DISTANCE = 1e-6` |
| Private | leading underscore | `_internal_state` |
| Type alias | `PascalCase` | `PointId = str` |
| Enum member | `UPPER_SNAKE_CASE` | `DirectionMode.AZIMUTH` |

### Indentation and Line Length

- **4 spaces** per level — no tabs.
- Max line length: **100 characters** (set in `pyproject.toml`).
- Break long expressions at operators or with parentheses — never with backslash continuation.

### Imports

Follow this order, separated by blank lines:

```python
# 1. Standard library
import math
from enum import Enum

# 2. Third-party
import numpy as np
import matplotlib.pyplot as plt

# 3. First-party (this package)
from geometry.models import Point
from geometry.utils import EPS_DISTANCE
```

Rules:
- One import per line (no `import os, sys`).
- Prefer `from module import name` over aliased star imports.
- Use `from __future__ import annotations` at the top of any file that needs forward references in type hints.

### Blank Lines

- **2** blank lines between top-level definitions (classes, functions).
- **1** blank line between methods inside a class.
- **1** blank line to separate logical sections inside a function (use sparingly).

### Whitespace

```python
# ✅ Good
x = point.easting + offset
result = compute(a, b, c=default)
items = [1, 2, 3]

# ❌ Bad
x=point.easting+offset
result = compute(a, b ,c = default )
items = [ 1, 2, 3 ]
```

---

## PEP 257 — Docstrings

Use triple double-quotes. Follow the one-liner / multi-line split:

```python
# One-liner: fits on one line, period at end
def signed_area(vertices: list[tuple[float, float]]) -> float:
    """Return the signed area of the polygon (positive = CCW)."""

# Multi-line: summary line, blank line, then body
def reorder_ccw(vertices: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Reorder polygon vertices to counter-clockwise orientation.

    Uses the signed-area method, which works for both convex and concave
    polygons. Raises ValueError if the polygon is degenerate.
    """
```

Rules:
- Public modules, classes, and functions **must** have a docstring.
- Private helpers and simple `__init__` methods may omit docstrings.
- The closing `"""` of a multi-line docstring goes on its own line.
- Do not restate the signature in the docstring — describe behaviour and edge cases.

---

## PEP 484 — Type Hints

Annotate every public function signature (parameters and return type).

```python
def distance(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    ...

def find_by_id(object_id: str) -> "GeometryObject | None":
    ...
```

Rules:
- Use built-in generics (`list[str]`, `dict[str, int]`, `tuple[float, float]`) — no `List`, `Dict` from `typing`.
- Use `X | Y` union syntax (Python 3.10+), not `Optional[X]` or `Union[X, Y]`.
- Use `from __future__ import annotations` when a class references itself or a type defined later in the file.
- `TYPE_CHECKING` guard for imports that are only needed at type-check time:

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from geometry.models import GeometryObject
```

---

## Project-specific conventions

- **Tolerances** (`EPS_DISTANCE`, `EPS_ANGLE`, `EPS_AREA`, `EPS_PARAM`) live in `geometry/utils/`. Never use bare float literals for comparisons — always reference the named constant.
- **Enums** (`DirectionMode`, `DirectionUnits`) are defined in `geometry/models/`. JSON serialization always lowercases the name; deserialization is case-insensitive.
- **Coordinate order**: tuples are `(easting, northing)`. The point-import text format is `name northing easting` — conversions live in `geometry/utils/`, not scattered across UI code.
