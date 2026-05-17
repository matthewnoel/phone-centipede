"""Known outer dimensions of common phones, used by --phone in generate.py.

Keys match the kwarg names accepted by build_segment(): phone_width is the
phone's face dimension along X (short side when the phone sits portrait in
the stand), phone_height is along the tilted slot axis (long side), and
phone_thickness is perpendicular to the face. All values in millimeters.
"""

PHONES = {
    "iPhone17Pro": {
        "phone_width": 73.0,
        "phone_height": 150.8,
        "phone_thickness": 7.9,
    },
}


def lookup(name: str) -> dict:
    """Return the measurement dict for `name`, or raise ValueError listing the valid options."""
    if name not in PHONES:
        valid = ", ".join(sorted(PHONES))
        raise ValueError(f"Unknown phone {name!r}. Known phones: {valid}.")
    return PHONES[name]
