# Testing Guide

## Running Tests

### Quick Start

To run all tests with the required environment configuration:

```bash
./run_tests.sh
```

Or with custom pytest arguments:

```bash
./run_tests.sh backend/tests/unit -v
./run_tests.sh backend/tests/ -k "test_embed" --tb=long
```

### Manual Command

If you prefer to run pytest directly, ensure you set these environment variables to prevent FAISS segmentation faults on macOS:

```bash
export MKL_NUM_THREADS=1
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1

uv run pytest backend/tests/ -x --tb=short -q --no-header
```

## Test Structure

- **Unit tests** (`backend/tests/unit/`): Fast, isolated tests of individual components
- **Migration tests** (`backend/tests/migration/`): Database schema migration tests
- **Integration tests** (`backend/tests/integration/`):
  - Database integration tests
  - Embedding adapter tests
  - FAISS vector store tests (marked with `@pytest.mark.faiss`)

## Test Results

### Full Test Suite

- **Total tests**: 390
  - Unit: 218 tests
  - Migration: 101 tests
  - Database integration: 43 tests
  - Embedding adapter integration: 13 tests
  - FAISS store integration: 15 tests

### Running Specific Test Groups

```bash
# Unit tests only
./run_tests.sh backend/tests/unit -q

# Integration tests (excluding FAISS)
./run_tests.sh backend/tests/integration -m "not faiss" -q

# FAISS tests only
./run_tests.sh backend/tests/integration/infrastructure/test_faiss_store.py -v

# Database tests
./run_tests.sh backend/tests/integration/db -q
```

## macOS FAISS Issue

**Issue**: FAISS 1.9.0 on macOS has a known threading bug that causes segmentation faults when running multiple tests in a single process.

**Solution**: Set thread count environment variables to 1:

- `MKL_NUM_THREADS=1` - Intel MKL threading
- `OMP_NUM_THREADS=1` - OpenMP threading
- `OPENBLAS_NUM_THREADS=1` - OpenBLAS threading
- `VECLIB_MAXIMUM_THREADS=1` - vecLib threading

These settings prevent FAISS from using multiple threads, which avoids the threading bug while having minimal performance impact during testing.

## Code Quality

### Linting

```bash
uv run ruff check backend/src/
```

### Type Checking

```bash
uv run mypy backend/src/sentinel/ --config-file=pyproject.toml
```

### All Checks

```bash
uv run ruff check backend/src/ && \
  uv run mypy backend/src/sentinel/ --config-file=pyproject.toml && \
  ./run_tests.sh
```
