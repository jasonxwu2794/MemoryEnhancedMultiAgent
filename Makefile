.PHONY: install test test-e2e clean

install:
	pip install -r requirements.txt

test:
	python -m pytest tests/ -v

test-e2e:
	python tests/e2e_simulation.py

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -f *.db data/*.db
	rm -rf dist/ build/ *.egg-info/
