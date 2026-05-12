COMPOSE=docker compose

.PHONY: up down logs test lint build backup monitoring

up:
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f backend web_server prometheus grafana

build:
	$(COMPOSE) build

test:
	cd app_server && PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m pytest

lint:
	cd app_server && PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m ruff check .

backup:
	./scripts/backup-db.sh

monitoring:
	@echo "App UI: http://localhost:8080"
	@echo "Prometheus: http://localhost:9090"
	@echo "Grafana: http://localhost:3000"
