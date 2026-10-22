.PHONY: test lint format dev server-test server-lint client-test client-lint dev-server dev-client

CLIENT_DEPS := client/node_modules/.package-lock.json
SIMILE_VOICE ?= 0

test: server-test client-test

lint: server-lint client-lint

format: $(CLIENT_DEPS)
	cd server && uv run ruff check --fix . && uv run ruff format .
	cd client && npx eslint --fix .

dev: $(CLIENT_DEPS)
	$(MAKE) -j2 dev-server dev-client

server-test:
	cd server && uv run pytest

server-lint:
	cd server && uv run ruff check . && uv run ruff format --check .

client-test: $(CLIENT_DEPS)
	cd client && npm test

client-lint: $(CLIENT_DEPS)
	cd client && npm run lint

dev-server:
	cd server && SIMILE_VOICE=$(SIMILE_VOICE) uv run simile serve --reload

dev-client: $(CLIENT_DEPS)
	cd client && npm run dev

$(CLIENT_DEPS): client/package.json client/package-lock.json
	cd client && npm ci
