#!/bin/bash
# Run tests with proper environment variables to prevent FAISS segmentation fault on macOS

# Set thread count to 1 to prevent FAISS threading issues on macOS
export MKL_NUM_THREADS=1
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1

# Run pytest with the provided arguments (or default arguments if none provided)
if [ $# -eq 0 ]; then
    # Default: run all tests with short tracebacks and quiet output
    uv run pytest backend/tests/ -x --tb=short -q --no-header
else
    # Use custom arguments
    uv run pytest "$@"
fi
