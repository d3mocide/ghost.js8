# ghost.js8 developer entry points. See AGENTS.md.
SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := check

UV  := uv --directory bridge
NPM := npm --prefix web

.PHONY: setup lint typecheck test check contract contract-check acceptance

setup:
	$(UV) sync --locked
	$(NPM) ci

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(NPM) run lint

typecheck:
	$(UV) run mypy
	$(NPM) run check

test:
	$(UV) run pytest
	$(NPM) test

check: lint typecheck test

contract:
	@echo "contract generation lands in milestone 6" >&2; exit 1

contract-check:
	@echo "contract drift check lands in milestone 6" >&2; exit 1

acceptance:
	@echo "acceptance test lands in milestone 5" >&2; exit 1
