PYTHON ?= python3
PYTHONPATH_VALUE := src

.PHONY: test list

test:
	PYTHONPATH=$(PYTHONPATH_VALUE) $(PYTHON) -m unittest discover -s tests/unit -v

list:
	PYTHONPATH=$(PYTHONPATH_VALUE) $(PYTHON) -m axiom.cli --repo-root . list
