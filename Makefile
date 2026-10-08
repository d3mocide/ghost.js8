# ghost.js8 developer entry points. See AGENTS.md.
SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := check

UV  := uv --directory bridge
NPM := npm --prefix web

.PHONY: setup lint typecheck test check contract contract-check acceptance decoder-image fixtures

setup:
	$(UV) sync --locked --all-extras
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

fixtures:
	python3 tools/fixtures/fetch_fixture.py

COMPOSE_TEST := EXTRA_CA=$(EXTRA_CA) docker compose -f docker-compose.test.yml

acceptance: fixtures
	$(COMPOSE_TEST) build
	$(COMPOSE_TEST) up --abort-on-container-exit --exit-code-from acceptance; \
	  rc=$$?; $(COMPOSE_TEST) down -v --remove-orphans >/dev/null 2>&1; exit $$rc

comma := ,
EXTRA_CA ?=
DOCKER_SECRET := $(if $(EXTRA_CA),--secret id=extra_ca$(comma)src=$(EXTRA_CA),)

decoder-image:
	docker build $(DOCKER_SECRET) -f decoder/Dockerfile -t ghostjs8-decoder:dev .
