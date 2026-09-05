.PHONY: all deb rpm installers run test clean help

all: help

help:
	@echo "Comic Scroll Reader - Build & Development Targets"
	@echo ""
	@echo "  make deb        - Compile and build standalone .deb installer"
	@echo "  make rpm        - Compile and build Red Hat/Fedora .rpm installer"
	@echo "  make installers - Compile all available host installers"
	@echo "  make run        - Run reader from source in current environment"
	@echo "  make test       - Run unit test suite"
	@echo "  make clean      - Clean build, dist, and temporary artifacts"
	@echo ""

deb:
	./build_installers.sh --deb

rpm:
	./build_installers.sh --rpm

installers:
	./build_installers.sh --all

run:
	./comic-scroll-reader.sh

test:
	PYTHONPATH=. .venv/bin/pytest tests

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache
	find . -type d -name "__pycache__" -exec rm -rf {} +
