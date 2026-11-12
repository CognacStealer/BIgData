# Convenience wrapper. Everything needs `source env.sh` first; these targets
# do it for you.
SHELL := /bin/bash
PY := .venv/bin/python

.PHONY: help all ingest prepare features classify cluster report smoke stream clean-derived

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n",$$1,$$2}'

all: ## run every phase in order
	source env.sh && $(PY) -u src/run_all.py

ingest: ## Phase 0: bz2 TSV -> Parquet
	source env.sh && $(PY) -u src/run_all.py --only p00_ingest
prepare: ## Phase 3: cleaning and labels
	source env.sh && $(PY) -u src/run_all.py --only p03_prepare
features: ## Phase 4: feature engineering + SVD
	source env.sh && $(PY) -u src/run_all.py --only p04_features
classify: ## Phase 5a: classification
	source env.sh && $(PY) -u src/run_all.py --only p05_classification
cluster: ## Phase 5b: clustering
	source env.sh && $(PY) -u src/run_all.py --only p05_clustering
figures: ## Phase 6: figures and tables
	source env.sh && $(PY) -u src/run_all.py --only p06_report

live-train: ## train + save the live-servable bot classifier (~6 min)
	source env.sh && $(PY) -u src/pf_live_train.py

live-calibrate: ## pick the F1-optimal decision threshold (needs live-train)
	source env.sh && $(PY) -u src/pf_live_calibrate.py

live-demo: ## LIVE DEMO: classify real Wikimedia edits as they arrive
	source env.sh && $(PY) -u src/pf_live_demo.py --minutes 3

rdd: ## RDD-based processing over the raw dump
	source env.sh && $(PY) -u src/pb_rdd.py
sql: ## DataFrame + Spark SQL analytics
	source env.sh && $(PY) -u src/pc_sql.py
streaming: ## Structured Streaming replay (20 bursts x 10k)
	source env.sh && $(PY) -u src/pe_streaming.py --batches 20 --rows 10000

report-a2: ## build the Assignment 2 technical report (.docx + .pdf)
	node src/make_report_a2.js
	@zip -d reports/Assignment2_Spark_Report.docx '*/' >/dev/null 2>&1 || true
	@/opt/libreoffice26.8/program/soffice --headless --convert-to pdf \
	   --outdir reports reports/Assignment2_Spark_Report.docx >/dev/null 2>&1 || true

report: ## build the final report (.docx + .pdf) from reports/metrics
	node src/make_report.js
	@zip -d reports/MMDS_EndSem_Report.docx '*/' >/dev/null 2>&1 || true
	@command -v /opt/libreoffice26.8/program/soffice >/dev/null && \
	  /opt/libreoffice26.8/program/soffice --headless --convert-to pdf \
	    --outdir reports reports/MMDS_EndSem_Report.docx >/dev/null 2>&1 || \
	  echo "(install LibreOffice to also emit the PDF)"

ppt-a2: ## build the Assignment 2 deck (needs MMDS_TEMPLATE)
	source env.sh && $(PY) -u src/make_ppt_a2.py
	@/opt/libreoffice26.8/program/soffice --headless --convert-to pdf \
	   --outdir reports reports/Assignment2_Spark_Analytics.pptx >/dev/null 2>&1 || true

diagrams: ## render the architecture and workflow figures
	source env.sh && $(PY) -u src/make_diagrams.py

ppt: ## build the end-sem presentation (needs MMDS_TEMPLATE)
	source env.sh && $(PY) -u src/make_ppt.py

smoke: ## fast end-to-end check on a tiny real-data fixture
	source env.sh && $(PY) -u tests/smoke_test.py

stream: ## collect 2 min of live edits for the demo
	source env.sh && $(PY) -u src/stream_collector.py --minutes 2

data/raw/simplewiki.all-time.tsv.bz2: ## download the dump (951 MB)
	mkdir -p data/raw && curl -L --retry 3 -o $@ \
	  https://dumps.wikimedia.org/other/mediawiki_history/2026-10/simplewiki/2026-10.simplewiki.all-time.tsv.bz2

clean-derived: ## delete everything derived, keep the raw dump
	rm -rf data/parquet data/features data/_smoke reports/figures/* reports/metrics/*
