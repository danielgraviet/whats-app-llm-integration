.PHONY: format check-format install help

help:
	@echo "Available commands:"
	@echo "  make format        - Format all Python files"
	@echo "  make check-format  - Check if files need formatting"
	@echo "  make install       - Install formatting tools"

install:
	pip install black isort

# Format code
format:
	black .
	isort .

# Check formatting
check-format:
	black --check .
	isort --check .

# Format specific directory
format-src:
	black src/
	isort src/