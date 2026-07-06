#!/usr/bin/env bash
set -euo pipefail

ruff format src/ tests/
ruff check src/ tests/
mypy src/
pytest
