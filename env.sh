#!/usr/bin/env bash
# Source this before running anything: `source env.sh`

# Derive the project root from this file's own location, so a clone works
# anywhere. (Hardcoding it broke every checkout outside /home/tsuki.)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PROJECT_ROOT

export JAVA_HOME="${JAVA_HOME:-$HOME/.local/jdk}"
export PATH="$JAVA_HOME/bin:$HOME/.local/bin:$PATH"

# Driver and workers MUST agree on the Python minor version, else Spark
# raises PYTHON_VERSION_MISMATCH at task time (not at import).
export PYSPARK_PYTHON="$PROJECT_ROOT/.venv/bin/python"
export PYSPARK_DRIVER_PYTHON="$PROJECT_ROOT/.venv/bin/python"
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"
