#!/usr/bin/env bash
# Source this before running anything: `source env.sh`
export PROJECT_ROOT="/home/tsuki/BIgData"
export JAVA_HOME="$HOME/.local/jdk"
export PATH="$JAVA_HOME/bin:$HOME/.local/bin:$PATH"
# Driver and workers MUST agree on the Python minor version, else Spark
# raises PYTHON_VERSION_MISMATCH (system python here is 3.14, venv is 3.11).
export PYSPARK_PYTHON="$PROJECT_ROOT/.venv/bin/python"
export PYSPARK_DRIVER_PYTHON="$PROJECT_ROOT/.venv/bin/python"
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"
