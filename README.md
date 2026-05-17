# phone-centipede

Generates STLs for a modular phone stand.

## Setup

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```sh
python generate.py
```

With a few overrides:

```sh
python generate.py --phone-width 80 --phone-thickness 12 --slot-angle 12
--output thicker_phone.stl
```
