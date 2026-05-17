# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-file Python CLI (`generate.py`) that uses `build123d` to produce an STL for one segment of a sectioned, dovetail-mating desk phone holder. Multiple printed segments connect front-to-back via the dovetails. All geometry is parameterized via named constants at the top of `generate.py`; a small subset is exposed via argparse — see `--help`. Default output is `phone-centipede.stl` in CWD.

There are no tests. The artifact is verified by re-slicing in Bambu Studio; for quick sanity checks, inspect the STL's bounding box (default args: X = ±50.8, Y ≈ -26.21..+32.21 — slab depth ≈ 52.42 mm + 6 mm tail protrusion on +Y, Z = 0..18.8). Slab depth is now derived from `--phone-height` by `_depth_and_slot_y` (so the phone CoG lands at the segment-footprint midpoint); the front-of-slab → slot-center distance is held constant at `SLOT_FRONT_OFFSET_MM = 19.5`.

## Coordinate system

Right-handed:
- **+X** — segment length, along the desk's front edge (parallel to the phone face's long edge)
- **+Y** — depth, away from the user; the phone leans toward +Y
- **+Z** — up; the slab sits on the build plate at z = 0..`SLAB_THICKNESS_MM`

The slab is centered in X and Y. Most geometry decisions in `generate.py` only make sense with this convention in mind (e.g., "the mortise opens at the bottom face" means z = 0).

## Python environment caveat

The README uses `uv` because the local Homebrew `python@3.11/3.13/3.14` installs on this machine have a broken `pyexpat` — the .so is linked to `/usr/lib/libexpat.1.dylib` which lacks `_XML_SetAllocTrackerActivationThreshold`, so `python -m venv` fails at `ensurepip`. `brew reinstall python@*` does not fix the formula defect (it's in the formula's linkage). The code itself is fine — don't restructure `generate.py` to "work around" this; the formula will be patched upstream eventually.

## Two non-obvious geometry decisions

Both of these deviate from what a literal read of the original spec would produce. They were each fixed once after a spec-following implementation broke at print or assembly time. Don't revert them without re-thinking the original failure modes:

**1. Dovetails are bottom-aligned (z = 0 to `DOVETAIL_HEIGHT_MM`), not centered in the slab.** Centered tails cantilever ~4.4 mm off the +Y face into open air — Bambu has nothing to support the underside, and the print becomes spaghetti. Centered mortises are also a sealed internal pocket with no opening on any Z face, which means no entry path along the dovetail's length axis (Z) — even a successful print wouldn't assemble. Bottom-alignment fixes both: tail sits on the build plate, mortise opens at the slab's bottom face, and segments mate by lowering one over another's tail.

**2. The phone slot is a through-cut sized for the tilt.** Reach below the opening along the slot's *tilted* axis must be at least `(SLAB_THICKNESS + slot_t/2 · sin θ) / cos θ`. The `slot_t/2 · sin θ` term matters because the slot's bottom face is itself tilted — its high corner on the +Y side lags the cutter tip by that amount in world-Z. A naive `SLAB_THICKNESS / cos θ` leaves a sliver of floor near the +Y bottom edge. See `_build_slot_cutter` for the derivation in comments.

## Code style

Python is formatted with [black](https://black.readthedocs.io/) (pinned in `requirements-dev.txt`). Run `.venv/bin/black generate.py` after edits — black is the source of truth, so don't hand-align constants or wrap lines manually.

## Boolean-robustness conventions

Both the tail and the mortise factories use a `_FACE_OVERLAP_MM` tab on the narrow side of their trapezoid so the Boolean op never has to resolve a face coincident with the slab's ±Y face. The slot cutter does the same via `_SLOT_TOP_OVERSHOOT_MM` / `_SLOT_BOTTOM_OVERSHOOT_MM`. If you add a new feature that cuts or fuses to a slab face, follow the same pattern — coincident-face booleans in OCCT are flaky and the artifacts only show up after STL export.
