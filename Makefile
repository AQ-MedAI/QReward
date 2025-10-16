# Variables
PACKAGE_NAME = qreward
WHEEL_FILE = ./dist/$(PACKAGE_NAME)-*.whl

# Targets
.PHONY: help
help:
	@echo "Please use \`make <target>\` where <target> is one of"
	@echo "  test        -- run local unit tests"
	@echo "  build       -- build the package"
	@echo "  install     -- install the package"
	@echo "  reinstall   -- uninstall and reinstall the tool"
	@echo "  uninstall   -- uninstall the package"
	@echo "  lint        -- run both flake8"
	@echo "  clean       -- clean up temporary files"

.PHONY: test
test:
	@pytest -n auto -v tests/

.PHONY: build
build:
	@python setup.py sdist bdist_wheel

.PHONY: install
install: build
	@pip install $(WHEEL_FILE) --no-cache-dir
	@$(MAKE) clean

.PHONY: reinstall
reinstall: build
	@pip uninstall -y $(PACKAGE_NAME)
	@pip install $(WHEEL_FILE) --no-cache-dir
	@$(MAKE) clean

.PHONY: uninstall
uninstall:
	@pip uninstall -y $(PACKAGE_NAME)

.PHONY: lint
lint:
	@flake8 --exclude=build,examples,.venv

.PHONY: clean
clean:
	@rm -rf htmlcov tests/htmlcov dist build $(PACKAGE_NAME).egg-info
	@rm -f .coverage coverage.xml tests/.coverage tests/coverage.xml