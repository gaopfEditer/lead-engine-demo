.PHONY: demo demo-local test screenshots fetch-cslb install

install:
	python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

demo:
	docker compose up -d --build
	@echo "Waiting for services..."
	@sleep 5
	docker compose exec -T app python -m app.cli demo
	@echo "Dashboard: http://localhost:8000"

demo-local:
	@test -d .venv || $(MAKE) install
	$(MAKE) mocksites-local &
	@sleep 2
	MOCK_SITES_BASE_URL=http://127.0.0.1:8081 .venv/bin/python -m app.cli demo
	@echo "Dashboard: http://127.0.0.1:8000 (run: .venv/bin/uvicorn app.main:app --reload)"

mocksites-local:
	python3 -m http.server 8081 --directory mocksites

test:
	python3 -m pytest -q

screenshots:
	python3 scripts/screenshot_pages.py

fetch-cslb:
	python3 scripts/fetch_cslb_data.py

demo-snapshot:
	PUBLIC_DEMO=1 DATABASE_URL=sqlite:///$(CURDIR)/demo_snapshot/lead_engine.db \
		MOCK_SITES_BASE_URL=http://127.0.0.1:8081 \
		python3 -m app.cli demo
