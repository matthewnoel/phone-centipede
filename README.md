# phone-centipede

Generates STLs for a modular phone stand.

## Setup

Uses [uv](https://docs.astral.sh/uv/) to manage the Python environment. Install it first (`brew install uv` on macOS), then:

```sh
uv venv .venv --python 3.12
uv pip install -r requirements.txt
```

## Usage

```sh
.venv/bin/python generate.py
```

With a few overrides:

```sh
.venv/bin/python generate.py --phone-width 80 --phone-thickness 12 --slot-angle 12 \
    --output thicker_phone.stl
```
