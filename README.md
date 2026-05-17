# phone-centipede

Generates STLs for a modular phone stand.

## Prerequisites

- [uv](https://docs.astral.sh/uv/)

## Setup

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
.venv/bin/python generate.py --phone-width 80 --phone-height 150 --phone-thickness 12 --output custom_filename.stl
```

## Development

```sh
uv pip install -r requirements-dev.txt
```

Format the code

```sh
.venv/bin/black *.py
```
