# Environment notes (reproducibility)

This project was built on Ubuntu 26.04 with **no root access**, so both the JDK
and Python were installed into the user's home directory.

| Component | Version | Why this one |
|---|---|---|
| OpenJDK | Temurin 17.0.21 (`~/.local/jdk`) | Spark 3.5 supports Java 8/11/17. Installed from the Adoptium API as a tarball because `apt` needs sudo. |
| Python | 3.11.18 (via `uv`) | **Not** the system 3.14, and **not** 3.12 — see below. |
| PySpark | 3.5.3 | |

## Two version traps we hit, and the fixes

**1. `PYSPARK_PYTHON` must be pinned.** The system Python here is 3.14. If the
driver runs in the venv but workers resolve bare `python3`, Spark fails *at task
execution time* (not at import) with:

```
[PYTHON_VERSION_MISMATCH] Python in worker has different version (3, 14)
than that in driver 3.11, PySpark cannot run with different minor versions.
```

`env.sh` exports `PYSPARK_PYTHON` and `PYSPARK_DRIVER_PYTHON` to the venv
interpreter to prevent this.

**2. PySpark 3.5 cannot run on Python 3.12.** Python 3.12 removed `distutils`,
which `pyspark/ml/image.py` still imports:

```
ModuleNotFoundError: No module named 'distutils'
```

Python 3.12 support landed in Spark 4.0. We use Python 3.11, the newest version
officially supported by PySpark 3.5.x, rather than relying on a `setuptools`
shim.

## Recreating the environment

```bash
# JDK (no root)
mkdir -p ~/.local/jdk && cd /tmp
URL=$(curl -s "https://api.adoptium.net/v3/assets/latest/17/hotspot?architecture=x64&image_type=jdk&os=linux&vendor=eclipse" \
      | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['binary']['package']['link'])")
curl -L "$URL" -o jdk17.tar.gz && tar xzf jdk17.tar.gz -C ~/.local/jdk --strip-components=1

# Python + deps
cd /home/tsuki/BIgData
uv python install 3.11
uv venv --python 3.11 .venv
VIRTUAL_ENV=$PWD/.venv uv pip install -r requirements.txt

source env.sh && python -c "import pyspark; print(pyspark.__version__)"
```

## Hardware this was tuned for

12 cores / 15 GB RAM, single machine, `master=local[*]`. Relevant settings in
`src/config.py`: `spark.driver.memory=6g`,
`spark.sql.shuffle.partitions=48` (~4× cores), AQE and skew-join handling on.

If you move to a real cluster, raise `shuffle.partitions` to roughly
2–4× total executor cores and drop `spark.driver.memory` back to a modest value,
since the executors will no longer live inside the driver JVM.
