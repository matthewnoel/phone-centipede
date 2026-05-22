# phone-centipede

Generates STLs for a modular phone stand.

## Prerequisites

- [uv](https://docs.astral.sh/uv/)

## Environment Setup

```sh
uv venv .venv --python 3.12
uv pip install -r requirements.txt
# optional requirements for code contributors
uv pip install -r requirements-dev.txt
```

## Usage

With default sizes:

```sh
.venv/bin/python generate.py
```

Use dimensions for a known phone model (see `phones.py` for the list):

```sh
.venv/bin/python generate.py --phone iPhone17Pro
```

Using custom phone measurements:

```sh
.venv/bin/python generate.py --phone-width 80 --phone-height 150 --phone-thickness 12 --output custom_filename.stl
```

Individual `--phone-width` / `--phone-thickness` / `--phone-height` flags override
values from `--phone` when both are given.

Phone measurements default to millimeters. Pass `--units inches` to give them in
inches instead — they are converted to mm before printing:

```sh
.venv/bin/python generate.py --units inches --phone-width 3.07 --phone-thickness 0.39 --phone-height 5.9
```

`--units` affects only the `--phone-*` flags you type. Values from `--phone` and
the built-in defaults are always millimeters.

Build a nameplate — a 45° wedge that slides into the two front dovetails of any
segment, for writing on, stickers, etc.:

```sh
.venv/bin/python generate.py --component nameplate
```

## Development

Format the code

```sh
.venv/bin/black *.py
```
