#!/usr/bin/env python3
"""Generate an STL of a single phone-holder segment.

Multiple segments are printed and connected front-to-back via dovetail joints
to form a row of phone holders on a desk. This script outputs one segment.

Coordinate system (right-handed):
    +X : segment length, along the desk's front edge (long edge of phone face)
    +Y : segment depth, away from the user; the phone leans toward +Y
    +Z : vertical, up off the desk

All geometry constants are at the top of this file; a subset is exposed on the
CLI. See --help.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from build123d import (
    Axis,
    Box,
    Polyline,
    export_stl,
    extrude,
    make_face,
)

# === Slab (base of one segment) =============================================
SEGMENT_LENGTH_MM      = 101.6   # X: length along desk-edge direction
SEGMENT_DEPTH_MM       = 55.0    # Y: front-to-back depth
SLAB_THICKNESS_MM      = 18.8    # Z: vertical thickness

# === Phone slot =============================================================
PHONE_WIDTH_MM         = 78.0    # phone's face long-edge dimension (along X)
PHONE_THICKNESS_MM     = 10.0    # phone's thickness (perpendicular to face)
SLOT_DEPTH_MM          = 12.0    # cut depth into slab along the slot's axis
SLOT_ANGLE_DEG         = 10.0    # slot tilt off vertical, leaning toward +Y
SLOT_TOLERANCE_MM      = 1.0     # uniform inflation of slot vs phone dims
SLOT_X_DEFAULT_MM      = SEGMENT_LENGTH_MM / 2  # slot center X from -X end
SLOT_Y_OFFSET_MM       = 0.0     # slot center Y (0 = mid-depth of slab)
_SLOT_TOP_OVERSHOOT_MM = 6.0     # cutter extends above slab for clean cut

# === Dovetail joints ========================================================
# Tails (male) on +Y face; mortises (female) on -Y face. When a segment is
# lowered from above behind the current one, its -Y mortises receive the
# current segment's +Y tails — locking the joint against the phone's backward
# tipping moment. Two dovetails per face (not one centered) prevent racking.
#
# Bottom-aligned (z = 0 to z = DOVETAIL_HEIGHT_MM), not centered:
#   - the tail rests on the build plate during FDM printing (centering it left
#     its underside cantilevered into air, which printed as spaghetti); and
#   - the mortise opens at the slab's bottom face, giving the tail an actual
#     entry path when sliding the joint together (a centered mortise is a
#     closed internal cavity with no way to mate).
DOVETAIL_WIDE_MM       = 12.0    # wider end (outward), along X
DOVETAIL_NARROW_MM     = 8.0     # narrower end (at slab face), along X
DOVETAIL_PROTRUSION_MM = 6.0     # how far the tail sticks out (along Y)
DOVETAIL_HEIGHT_MM     = 10.0    # vertical (Z) extent, bottom-flush with slab
DOVETAIL_X_INSET_MM    = 15.0    # from each X-end to nearest dovetail center
DOVETAIL_CLEARANCE_MM  = 0.3     # uniform mortise inflation vs tail

# Tiny in-slab overlap used when adding tails / cutting mortises, so the
# Boolean ops never touch a coincident slab face.
_FACE_OVERLAP_MM = 1.0

DEFAULT_OUTPUT = "phone-centipede.stl"


# ----------------------------------------------------------------------------
# Geometry helpers
# ----------------------------------------------------------------------------

def _trapezoid_face(w_narrow: float, w_wide: float, depth: float, base_overlap: float):
    """Trapezoidal face in the XY plane, used for both tails and mortises.

    Narrow edge (width w_narrow) sits on y=0, wide edge (width w_wide) at
    y=+depth. The face is symmetric about the Y axis. When base_overlap > 0,
    a rectangular tab of width w_narrow extends from y=-base_overlap to y=0;
    this tab gets buried inside the parent slab so the Boolean op never has
    to resolve a coincident face.
    """
    if base_overlap > 0:
        pts = [
            (-w_narrow / 2, -base_overlap),
            ( w_narrow / 2, -base_overlap),
            ( w_narrow / 2, 0.0),
            ( w_wide   / 2, depth),
            (-w_wide   / 2, depth),
            (-w_narrow / 2, 0.0),
        ]
    else:
        pts = [
            (-w_narrow / 2, 0.0),
            ( w_narrow / 2, 0.0),
            ( w_wide   / 2, depth),
            (-w_wide   / 2, depth),
        ]
    return make_face(Polyline(*pts, close=True))


def _build_tail():
    """One dovetail tail at origin, sitting on z=0 (build plate). Narrow edge
    on the y=0 plane, wide end at y=+protrusion. See the dovetail-block
    comment above for why this is bottom-aligned rather than centered."""
    face = _trapezoid_face(
        DOVETAIL_NARROW_MM,
        DOVETAIL_WIDE_MM,
        DOVETAIL_PROTRUSION_MM,
        base_overlap=_FACE_OVERLAP_MM,
    )
    return extrude(face, amount=DOVETAIL_HEIGHT_MM)


def _build_mortise():
    """One mortise cutter at origin, sitting on z=0. Matches _build_tail but
    inflated by DOVETAIL_CLEARANCE_MM on every face for a sliding fit; the
    base_overlap tab extends *outside* the slab's -Y face so the cut breaks
    cleanly through the front."""
    c = DOVETAIL_CLEARANCE_MM
    face = _trapezoid_face(
        DOVETAIL_NARROW_MM + 2 * c,
        DOVETAIL_WIDE_MM   + 2 * c,
        DOVETAIL_PROTRUSION_MM + 2 * c,
        base_overlap=_FACE_OVERLAP_MM,
    )
    return extrude(face, amount=DOVETAIL_HEIGHT_MM + 2 * c)


def _build_slot_cutter(slot_w: float, slot_t: float, angle_deg: float):
    """Phone-slot cutter, oriented so the slot's opening center is at the
    origin (z=0) and its local +Z (= "up out of the slot") tips toward +Y
    by `angle_deg`.

    The cutter extends SLOT_DEPTH_MM below the opening along its tilted axis
    and _SLOT_TOP_OVERSHOOT_MM above, so even the high corner of the tilted
    top face clears the slab.
    """
    total_len = SLOT_DEPTH_MM + _SLOT_TOP_OVERSHOOT_MM
    cutter = Box(slot_w, slot_t, total_len)
    # Default Box is centered. Shift so the local opening (transition from
    # outside to inside the slab) sits at z=0.
    cutter = cutter.translate((0, 0, (_SLOT_TOP_OVERSHOOT_MM - SLOT_DEPTH_MM) / 2))
    # Negative rotation about +X (right-hand rule) tips local +Z toward +Y,
    # which is the direction the phone leans.
    return cutter.rotate(Axis.X, -angle_deg)


# ----------------------------------------------------------------------------
# Assembly
# ----------------------------------------------------------------------------

def build_segment(
    *,
    phone_width: float,
    phone_thickness: float,
    slot_x_from_neg_end: float,
    slot_angle_deg: float,
):
    L = SEGMENT_LENGTH_MM
    D = SEGMENT_DEPTH_MM
    T = SLAB_THICKNESS_MM

    # Slab centered in X and Y; bottom on z=0 (the desk surface).
    slab = Box(L, D, T).translate((0, 0, T / 2))

    # --- Phone slot ---------------------------------------------------------
    slot_w = phone_width + SLOT_TOLERANCE_MM
    slot_t = phone_thickness + SLOT_TOLERANCE_MM
    slot = _build_slot_cutter(slot_w, slot_t, slot_angle_deg)
    # slot_x is measured from the -X end of the slab; world center is at x=0.
    slot = slot.translate((slot_x_from_neg_end - L / 2, SLOT_Y_OFFSET_MM, T))
    slab = slab - slot

    # --- Dovetail tails on +Y face (back) -----------------------------------
    tail = _build_tail()
    slab = slab + tail.translate((-L / 2 + DOVETAIL_X_INSET_MM, D / 2, 0))
    slab = slab + tail.translate(( L / 2 - DOVETAIL_X_INSET_MM, D / 2, 0))

    # --- Dovetail mortises on -Y face (front) -------------------------------
    # The mortise face is authored narrow-at-y=0, wide-at-y=+depth, with the
    # overlap tab on the negative side. Translating to (x_inset, -D/2, 0) puts
    # the narrow edge flush with the slab's front face, the wide end buried
    # inside the slab, and (since the mortise sits on z=0) opens the cavity
    # at the slab's bottom face so the tail can slide in vertically.
    mortise = _build_mortise()
    slab = slab - mortise.translate((-L / 2 + DOVETAIL_X_INSET_MM, -D / 2, 0))
    slab = slab - mortise.translate(( L / 2 - DOVETAIL_X_INSET_MM, -D / 2, 0))

    return slab


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def _parse_args():
    p = argparse.ArgumentParser(
        description=(
            "Generate an STL for one segment of a sectioned, dovetail-mating "
            "desk phone holder."
        ),
    )
    p.add_argument(
        "--phone-width", type=float, default=PHONE_WIDTH_MM, metavar="MM",
        help=("Long dimension of the phone slot (parallel to X — the long edge "
              f"of the phone's face). Default: {PHONE_WIDTH_MM} mm."),
    )
    p.add_argument(
        "--phone-thickness", type=float, default=PHONE_THICKNESS_MM, metavar="MM",
        help=("Short dimension of the phone slot (the phone's thickness, "
              f"perpendicular to its face). Default: {PHONE_THICKNESS_MM} mm."),
    )
    p.add_argument(
        "--slot-x", type=float, default=SLOT_X_DEFAULT_MM, metavar="MM",
        help=("X position of the slot's center, measured from the segment's "
              f"-X end (so 0 = left end, {SEGMENT_LENGTH_MM} = right end). "
              f"Default: {SLOT_X_DEFAULT_MM} mm (center)."),
    )
    p.add_argument(
        "--slot-angle", type=float, default=SLOT_ANGLE_DEG, metavar="DEG",
        help=("Slot tilt off vertical, leaning toward +Y (the direction the "
              f"phone leans). Default: {SLOT_ANGLE_DEG} degrees."),
    )
    p.add_argument(
        "--output", type=Path, default=Path(DEFAULT_OUTPUT), metavar="PATH",
        help=f"STL output path. Default: {DEFAULT_OUTPUT}",
    )
    return p.parse_args()


def main():
    args = _parse_args()

    print("Phone holder segment — resolved parameters:")
    print(f"  Slab (L x D x T)     : {SEGMENT_LENGTH_MM} x {SEGMENT_DEPTH_MM} x {SLAB_THICKNESS_MM} mm")
    print(f"  Phone width  (X)     : {args.phone_width} mm")
    print(f"  Phone thickness      : {args.phone_thickness} mm")
    print(f"  Slot depth           : {SLOT_DEPTH_MM} mm")
    print(f"  Slot tolerance       : {SLOT_TOLERANCE_MM} mm")
    print(f"  Slot angle           : {args.slot_angle} deg (toward +Y)")
    print(f"  Slot X (from -X end) : {args.slot_x} mm")
    print(f"  Slot Y offset        : {SLOT_Y_OFFSET_MM} mm")
    print(f"  Dovetail wide/narrow : {DOVETAIL_WIDE_MM} / {DOVETAIL_NARROW_MM} mm")
    print(f"  Dovetail protrusion  : {DOVETAIL_PROTRUSION_MM} mm")
    print(f"  Dovetail height  (Z) : {DOVETAIL_HEIGHT_MM} mm")
    print(f"  Dovetail X-inset     : {DOVETAIL_X_INSET_MM} mm")
    print(f"  Dovetail clearance   : {DOVETAIL_CLEARANCE_MM} mm")
    print(f"  Output               : {args.output}")
    print()

    segment = build_segment(
        phone_width=args.phone_width,
        phone_thickness=args.phone_thickness,
        slot_x_from_neg_end=args.slot_x,
        slot_angle_deg=args.slot_angle,
    )

    out_path = args.output
    if out_path.parent and str(out_path.parent) not in ("", "."):
        out_path.parent.mkdir(parents=True, exist_ok=True)
    export_stl(segment, str(out_path))
    print(f"Wrote STL: {out_path}")


if __name__ == "__main__":
    main()
