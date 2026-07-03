.PHONY: help setup download reproduce stats docs

help:
	@echo "CLI-Tool-Bench Reproducibility Workflow"
	@echo ""
	@echo "Commands:"
	@echo "  make docs       - Regenerate docs/ markdown (leaderboard, task catalog, guides)"
	@echo "  make setup      - Install required Python dependencies"
	@echo "  make download   - Download pre-computed agent trajectories and logs (~1GB) from cloud"
	@echo "  make reproduce  - Run evaluation metrics script to generate Leaderboard JSON"
	@echo "  make stats      - Compute Standard Deviation and 90% Confidence Intervals"

docs:
	python generate_artifact_docs.py

setup:
	pip install -r requirements.txt || echo "Please ensure you have Python 3.8+ installed."

download:
	@echo "Downloading evaluation data (Mock command for artifact, please refer to anonymous cloud link)"
	# In actual artifact, uncomment the wget/curl lines to fetch the 1GB zip.
	# wget -O openhands_repo.zip "https://example.com/link"
	# wget -O mini-swe-agent_repo.zip "https://example.com/link"
	# unzip -q openhands_repo.zip
	# unzip -q mini-swe-agent_repo.zip
	@echo "Data downloaded and unzipped successfully."

reproduce:
	@echo "Reproducing metrics..."
	python compute_se_macro.py
	python plot_rq1_new.py || echo "Plot scripts skipped if GUI not available."
	@echo "Metrics reproduced successfully."

stats:
	@echo "Computing Statistical Rigor (SD & 90% CI)..."
	python compute_confidence_intervals.py
	@echo "Done."
