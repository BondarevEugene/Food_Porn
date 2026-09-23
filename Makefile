.PHONY: install migrate run test lint docker-up

install:
	python -m pip install -r requirements-dev.txt

migrate:
	alembic upgrade head

run:
	python run.py

test:
	pytest -q

lint:
	ruff check .

docker-up:
	docker compose up --build

