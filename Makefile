PYTHON ?= python3
PYTHONPATH_VALUE := src

.PHONY: test list version release-manifest release-sbom

test:
	PYTHONPATH=$(PYTHONPATH_VALUE) $(PYTHON) -m unittest discover -s tests/unit -v

list:
	PYTHONPATH=$(PYTHONPATH_VALUE) $(PYTHON) -m axiom.cli --repo-root . list

version:
	PYTHONPATH=$(PYTHONPATH_VALUE) $(PYTHON) -m axiom.cli version --verbose

release-manifest:
	$(PYTHON) scripts/release_manifest.py $(FILES)

release-sbom:
	$(PYTHON) scripts/sbom.py --package-name axiom-workflow --version 0.1.0 $(FILES)
