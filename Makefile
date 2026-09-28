.PHONY: demo run test check integrations-test
PYTHON ?= python3

demo:
	$(PYTHON) -m usoe --demo

run:
	$(PYTHON) -m usoe

test:
	$(PYTHON) -m unittest discover -s tests -v

check:
	$(PYTHON) -m compileall -q usoe tests scripts
	node --check web/app.js

integrations-test:
	.venv/bin/python -m unittest discover -s tests -v
