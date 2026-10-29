.PHONY: all build deps install clean run help

PYTHON ?= python

ifeq ($(OS),Windows_NT)
    BINARY_EXT := .exe
else
    BINARY_EXT :=
endif

BINARY_NAME := anime-downloader$(BINARY_EXT)
ENTRY_POINT := run.py

NUITKA_FLAGS := --standalone \
                --onefile \
                --lto=auto \
                --python-flag=-O \
                --python-flag=no_docstrings \
                --include-package=src \
                --enable-plugin=anti-bloat \
                --assume-yes-for-downloads \
                --output-filename=$(BINARY_NAME)

all: deps build

help:
	@echo "Available commands:"
	@echo "  make deps     Install Python dependencies (requirements.txt + Nuitka)"
	@echo "  make build    Compile standalone binary using Nuitka with optimizations"
	@echo "  make all      Install deps and compile (default)"
	@echo "  make run      Run the program directly with Python"
	@echo "  make clean    Remove build artifacts and compiled binaries"

deps:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m pip install nuitka zstandard

build:
	$(PYTHON) -m nuitka $(NUITKA_FLAGS) $(ENTRY_POINT)

run:
	$(PYTHON) $(ENTRY_POINT)

clean:
	$(PYTHON) -c "import glob, shutil, os; [shutil.rmtree(p, ignore_errors=True) for p in glob.glob('*.build') + glob.glob('*.dist') + glob.glob('*.onefile-build') + glob.glob('__pycache__') + glob.glob('src/__pycache__')]; [os.remove(f) for f in glob.glob('anime-downloader*') + glob.glob('*.exe') if os.path.isfile(f)]"
	@echo "Cleaned build artifacts."
