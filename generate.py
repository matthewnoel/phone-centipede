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
import math
from pathlib import Path

from build123d import (
    Axis,
    Box,
    Polyline,
    export_stl,
    extrude,
    make_face,
)

from phones import lookup as lookup_phone

# === Slab (base of one segment) =============================================
SEGMENT_LENGTH_MM = 101.6  # X: length along desk-edge direction
SLAB_THICKNESS_MM = 18.8  # Z: vertical thickness
# Slab depth (Y) is no longer fixed — it is derived from --phone-height by
# `_depth_and_slot_y` so the phone's center of gravity lands at the segment
# midpoint.

# === Phone slot =============================================================
# The slot is a through-hole: a phone seated in it rests on whatever surface
# the stand sits on (the desk), not on a floor inside the slab.
PHONE_WIDTH_MM = 78.0  # phone's face long-edge dimension (along X)
PHONE_THICKNESS_MM = 10.0  # phone's thickness (perpendicular to face)
PHONE_HEIGHT_MM = 150.0  # phone dimension along the tilted slot axis (drives depth)
SLOT_ANGLE_DEG = 10.0  # slot tilt off vertical, leaning toward +Y
SLOT_TOLERANCE_MM = 1.0  # uniform inflation of slot vs phone dims
SLOT_X_MM = SEGMENT_LENGTH_MM / 2  # slot center X from -X end
# Distance from slab front face (-D/2) to slot center. Held constant as D
# varies with --phone-height so the front wall between mortise cavities and
# the slot stays a consistent thickness.
SLOT_FRONT_OFFSET_MM = 19.5
_SLOT_TOP_OVERSHOOT_MM = 6.0  # cutter extends above slab top for clean cut
_SLOT_BOTTOM_OVERSHOOT_MM = 5.0  # cutter extends below slab bottom for clean cut
# Minimum allowed wall between slot back edge (at z=T) and slab back face.
# `_depth_and_slot_y` raises ValueError if --phone-height is too small to
# leave at least this much; below ~3 mm the back wall is fragile in FDM and
# starts overlapping the dovetail-tail root overlap zone.
_MIN_BACK_WALL_MM = 3.0

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
DOVETAIL_WIDE_MM = 12.0  # wider end (outward), along X
DOVETAIL_NARROW_MM = 8.0  # narrower end (at slab face), along X
DOVETAIL_PROTRUSION_MM = 6.0  # how far the tail sticks out (along Y)
DOVETAIL_HEIGHT_MM = 10.0  # vertical (Z) extent, bottom-flush with slab
DOVETAIL_X_INSET_MM = 15.0  # from each X-end to nearest dovetail center
DOVETAIL_CLEARANCE_MM = 0.3  # uniform mortise inflation vs tail

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
            (w_narrow / 2, -base_overlap),
            (w_narrow / 2, 0.0),
            (w_wide / 2, depth),
            (-w_wide / 2, depth),
            (-w_narrow / 2, 0.0),
        ]
    else:
        pts = [
            (-w_narrow / 2, 0.0),
            (w_narrow / 2, 0.0),
            (w_wide / 2, depth),
            (-w_wide / 2, depth),
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
        DOVETAIL_WIDE_MM + 2 * c,
        DOVETAIL_PROTRUSION_MM + 2 * c,
        base_overlap=_FACE_OVERLAP_MM,
    )
    return extrude(face, amount=DOVETAIL_HEIGHT_MM + 2 * c)


def _build_slot_cutter(slot_w: float, slot_t: float, angle_deg: float):
    """Phone-slot cutter, oriented so the slot's opening center is at the
    origin (z=0) and its local +Z (= "up out of the slot") tips toward +Y
    by `angle_deg`. Sized to cut entirely through the slab.

    Reach below the opening along the tilted axis must be at least
    (SLAB_THICKNESS + slot_t/2 * sin(angle)) / cos(angle): the tilt magnifies
    the through-thickness reach, and the slot's bottom face is also tilted so
    its highest corner lags the tip by another slot_t/2 * sin(angle) in world
    Z. Anything less leaves a sliver of floor near the +Y edge of the bottom.
    """
    cos_a = math.cos(math.radians(angle_deg))
    sin_a = math.sin(math.radians(angle_deg))
    bot_extent = (
        SLAB_THICKNESS_MM + slot_t / 2 * sin_a
    ) / cos_a + _SLOT_BOTTOM_OVERSHOOT_MM
    top_extent = _SLOT_TOP_OVERSHOOT_MM
    total_len = bot_extent + top_extent
    cutter = Box(slot_w, slot_t, total_len)
    # Default Box is centered. Shift so the local opening (z=0) sits at the
    # boundary between the top overshoot and the bottom through-cut portion.
    cutter = cutter.translate((0, 0, (top_extent - bot_extent) / 2))
    # Negative rotation about +X (right-hand rule) tips local +Z toward +Y,
    # which is the direction the phone leans.
    return cutter.rotate(Axis.X, -angle_deg)


# ----------------------------------------------------------------------------
# Assembly
# ----------------------------------------------------------------------------


def _depth_and_slot_y(
    phone_height: float, phone_thickness: float
) -> tuple[float, float]:
    """Solve for slab depth D and slot center Y from phone height.

    Keeps SLOT_FRONT_OFFSET_MM constant (front wall between mortise cavities
    and slot is invariant), and lands the phone's CoG at the full
    segment-footprint midpoint — i.e. world Y = +DOVETAIL_PROTRUSION_MM/2,
    where the footprint runs from slab front face -D/2 to tail tip
    D/2 + DOVETAIL_PROTRUSION_MM.

    Derivation: slot_y = -D/2 + SLOT_FRONT_OFFSET_MM is the slot center at
    z=T. At z=0 the slot center is slot_y - T*tan(θ) (the slot tilts toward
    +Y, so its bottom is more -Y than its top). The phone bottom rests on
    the desk at z=0; its CoG is H/2 up the tilted axis, giving
    y_cog = slot_y - T*tan(θ) + (H/2)*sin(θ). Setting y_cog =
    DOVETAIL_PROTRUSION_MM/2 yields
        D = 2*SLOT_FRONT_OFFSET_MM - 2*T*tan(θ) + H*sin(θ) - DOVETAIL_PROTRUSION_MM.

    The phone's bottom contact edge actually sits (slot_t/2)*sin²(θ)/cos(θ)
    on the +Y side of the slot centerline (~0.17 mm at default tilt), which
    would shift the CoG by the same amount; below FDM precision and ignored.
    """
    theta = math.radians(SLOT_ANGLE_DEG)
    D = (
        2 * SLOT_FRONT_OFFSET_MM
        - 2 * SLAB_THICKNESS_MM * math.tan(theta)
        + phone_height * math.sin(theta)
        - DOVETAIL_PROTRUSION_MM
    )
    slot_y = -D / 2 + SLOT_FRONT_OFFSET_MM
    slot_t = phone_thickness + SLOT_TOLERANCE_MM
    back_wall = D / 2 - slot_y - slot_t / (2 * math.cos(theta))
    if back_wall < _MIN_BACK_WALL_MM:
        raise ValueError(
            f"phone_height={phone_height} mm gives back wall {back_wall:.2f} mm "
            f"(< {_MIN_BACK_WALL_MM} mm minimum). Increase --phone-height."
        )
    return D, slot_y


def build_segment(
    *,
    phone_width: float,
    phone_thickness: float,
    phone_height: float,
):
    L = SEGMENT_LENGTH_MM
    T = SLAB_THICKNESS_MM
    D, slot_y = _depth_and_slot_y(phone_height, phone_thickness)

    # Slab centered in X and Y; bottom on z=0 (the desk surface).
    slab = Box(L, D, T).translate((0, 0, T / 2))

    # --- Phone slot ---------------------------------------------------------
    slot_w = phone_width + SLOT_TOLERANCE_MM
    slot_t = phone_thickness + SLOT_TOLERANCE_MM
    slot = _build_slot_cutter(slot_w, slot_t, SLOT_ANGLE_DEG)
    # SLOT_X_MM is measured from the -X end of the slab; world center is x=0.
    slot = slot.translate((SLOT_X_MM - L / 2, slot_y, T))
    slab = slab - slot

    # --- Dovetail tails on +Y face (back) -----------------------------------
    tail = _build_tail()
    slab = slab + tail.translate((-L / 2 + DOVETAIL_X_INSET_MM, D / 2, 0))
    slab = slab + tail.translate((L / 2 - DOVETAIL_X_INSET_MM, D / 2, 0))

    # --- Dovetail mortises on -Y face (front) -------------------------------
    # The mortise face is authored narrow-at-y=0, wide-at-y=+depth, with the
    # overlap tab on the negative side. Translating to (x_inset, -D/2, 0) puts
    # the narrow edge flush with the slab's front face, the wide end buried
    # inside the slab, and (since the mortise sits on z=0) opens the cavity
    # at the slab's bottom face so the tail can slide in vertically.
    mortise = _build_mortise()
    slab = slab - mortise.translate((-L / 2 + DOVETAIL_X_INSET_MM, -D / 2, 0))
    slab = slab - mortise.translate((L / 2 - DOVETAIL_X_INSET_MM, -D / 2, 0))

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
        "--phone",
        type=str,
        default=None,
        metavar="MODEL",
        help=(
            "Load phone dimensions from the named model in phones.py "
            "(e.g. iPhone17Pro). Individual --phone-width/--phone-thickness/"
            "--phone-height flags override values from the model."
        ),
    )
    p.add_argument(
        "--phone-width",
        type=float,
        default=None,
        metavar="MM",
        help=(
            "Long dimension of the phone slot (parallel to X — the long edge "
            f"of the phone's face). Default: {PHONE_WIDTH_MM} mm."
        ),
    )
    p.add_argument(
        "--phone-thickness",
        type=float,
        default=None,
        metavar="MM",
        help=(
            "Short dimension of the phone slot (the phone's thickness, "
            f"perpendicular to its face). Default: {PHONE_THICKNESS_MM} mm."
        ),
    )
    p.add_argument(
        "--phone-height",
        type=float,
        default=None,
        metavar="MM",
        help=(
            "Phone dimension along the tilted slot axis. Drives slab depth "
            "so the phone's center of gravity lands at the segment midpoint. "
            f"Default: {PHONE_HEIGHT_MM} mm."
        ),
    )
    p.add_argument(
        "--output",
        type=Path,
        default=Path(DEFAULT_OUTPUT),
        metavar="PATH",
        help=f"STL output path. Default: {DEFAULT_OUTPUT}",
    )
    return p.parse_args()


def main():
    args = _parse_args()

    if args.phone is not None:
        try:
            config = lookup_phone(args.phone)
        except ValueError as e:
            raise SystemExit(str(e))
    else:
        config = {}

    def _resolve(cli_value, key, fallback):
        if cli_value is not None:
            return cli_value
        return config.get(key, fallback)

    phone_width = _resolve(args.phone_width, "phone_width", PHONE_WIDTH_MM)
    phone_thickness = _resolve(
        args.phone_thickness, "phone_thickness", PHONE_THICKNESS_MM
    )
    phone_height = _resolve(args.phone_height, "phone_height", PHONE_HEIGHT_MM)

    D, slot_y = _depth_and_slot_y(phone_height, phone_thickness)

    print("Phone holder segment — resolved parameters:")
    print(
        f"  Slab (L x D x T)     : {SEGMENT_LENGTH_MM} x {D:.2f} x {SLAB_THICKNESS_MM} mm"
    )
    if args.phone is not None:
        print(f"  Phone model          : {args.phone}")
    print(f"  Phone width  (X)     : {phone_width} mm")
    print(f"  Phone thickness      : {phone_thickness} mm")
    print(f"  Phone height         : {phone_height} mm")
    print(f"  Slot tolerance       : {SLOT_TOLERANCE_MM} mm (slot cuts fully through)")
    print(f"  Slot angle           : {SLOT_ANGLE_DEG} deg (toward +Y)")
    print(f"  Slot X (from -X end) : {SLOT_X_MM} mm")
    print(f"  Slot Y offset        : {slot_y:.2f} mm")
    print(f"  Dovetail wide/narrow : {DOVETAIL_WIDE_MM} / {DOVETAIL_NARROW_MM} mm")
    print(f"  Dovetail protrusion  : {DOVETAIL_PROTRUSION_MM} mm")
    print(f"  Dovetail height  (Z) : {DOVETAIL_HEIGHT_MM} mm")
    print(f"  Dovetail X-inset     : {DOVETAIL_X_INSET_MM} mm")
    print(f"  Dovetail clearance   : {DOVETAIL_CLEARANCE_MM} mm")
    print(f"  Output               : {args.output}")
    print()

    segment = build_segment(
        phone_width=phone_width,
        phone_thickness=phone_thickness,
        phone_height=phone_height,
    )

    out_path = args.output
    if out_path.parent and str(out_path.parent) not in ("", "."):
        out_path.parent.mkdir(parents=True, exist_ok=True)
    export_stl(segment, str(out_path))
    print(f"Wrote STL: {out_path}")


if __name__ == "__main__":
    main()
