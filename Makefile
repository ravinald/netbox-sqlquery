## Compose resolves containers by project name, so a fixed one makes every checkout of this
## repository on one host the same stack, and `docker compose exec` from one tree reaches
## whichever tree brought the stack up last. Derived from this directory, two checkouts are two
## stacks. COMPOSE_PROJECT_NAME outranks the `name:` in dev/docker-compose.yml, which still
## applies to a bare `docker compose` run from dev/. `cksum` because macOS ships no `sha1sum`.
PROJECT := netbox-sqlquery-dev-$(shell printf '%s' '$(CURDIR)' | cksum | cut -d' ' -f1)
export COMPOSE_PROJECT_NAME := $(PROJECT)

## Two stacks still share one host port. Overriding this runs a second checkout beside the first.
NETBOX_PORT ?= 8000
export NETBOX_PORT

COMPOSE := docker compose -f dev/docker-compose.yml
NB      := $(COMPOSE) exec -T netbox /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py
## The dev stack runs DEBUG=true, which installs the Django Debug Toolbar. Django forces
## DEBUG=False under tests and the toolbar's own check (debug_toolbar.E001) then fails the run
## before a test executes, so the tests get DEBUG=false rather than suppressed checks.
NB_TEST := $(COMPOSE) exec -T -e DEBUG=false netbox /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py
PKG     := netbox_sqlquery

.PHONY: gate lint check migrate-check test up down reset wait logs shell help

## The one gate every item is held to: the lint and test legs of CI, against the dev stack.
gate: lint check migrate-check test

lint:
	ruff check .
	ruff format --check .

check:
	$(NB) check

migrate-check:
	$(NB) makemigrations --check --dry-run $(PKG)

test:
	$(NB_TEST) test $(PKG) --no-input

## The precondition replaces "Bind for 0.0.0.0:8000 failed: port is already allocated", which
## says the port is taken and not that another checkout of this repository took it.
up:
	@held="$$(docker ps --filter publish=$(NETBOX_PORT) --format '{{.Names}}' 2>/dev/null \
	  | grep -v '^$(PROJECT)-' || true)"; \
	if [ -n "$$held" ]; then \
	  echo "port $(NETBOX_PORT) is held by $$held, which this checkout did not start." >&2; \
	  echo "Stop it, or bring this tree up beside it: NETBOX_PORT=8001 make up" >&2; \
	  exit 1; \
	fi
	$(COMPOSE) up -d --build
	$(MAKE) wait

## `compose up -d` returns once containers start, not once the entrypoint's migrations finish,
## so anything that execs into NetBox races that boot. `showmigrations` answers once Django
## reaches the database, which gates the manage.py targets; the login page answering is what
## makes the stack usable in a browser. The port comes from `compose port` so a stack this
## tree did not start cannot satisfy the wait.
wait:
	@port="$$($(COMPOSE) port netbox 8080 2>/dev/null | sed 's/.*://')"; \
	if [ -z "$$port" ]; then \
	  echo "no netbox container in compose project $(PROJECT). Run 'make up'." >&2; \
	  exit 1; \
	fi; \
	url="http://localhost:$$port"; \
	for i in $$(seq 1 90); do \
	  $(NB) showmigrations --plan >/dev/null 2>&1 && break; \
	  sleep 5; \
	  if [ $$i -eq 90 ]; then \
	    echo "netbox never reached its database" >&2; \
	    $(COMPOSE) logs netbox | tail -40; \
	    exit 1; \
	  fi; \
	done; \
	for i in $$(seq 1 90); do \
	  curl -sf -o /dev/null "$$url/login/" && { echo "netbox is serving $$url/"; exit 0; }; \
	  sleep 5; \
	done; \
	echo "netbox reached its database but never served $$url/" >&2; \
	$(COMPOSE) logs netbox | tail -40; \
	exit 1

down:
	$(COMPOSE) down

reset:
	$(COMPOSE) down -v

logs:
	$(COMPOSE) logs -f netbox

shell:
	$(NB) nbshell

help:
	@grep -E '^[a-z][a-z-]*:' Makefile | cut -d: -f1 | sort -u | tr '\n' ' '; echo
