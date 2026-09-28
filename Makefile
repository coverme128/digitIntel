.PHONY: demo run test check

demo:
	python3 -m usoe --demo

run:
	python3 -m usoe

test:
	python3 -m unittest discover -s tests -v

check:
	python3 -m compileall -q usoe tests scripts
	node --check web/app.js
