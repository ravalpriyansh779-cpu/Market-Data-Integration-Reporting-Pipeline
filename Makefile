.PHONY: up install run test bench down
up:       ; docker compose up -d --wait
install:  ; pip install -r requirements.txt
run:      ; python -m marketdata run --mock-api
test:     ; python -m pytest -q
bench:    ; python scripts/benchmark.py
down:     ; docker compose down
