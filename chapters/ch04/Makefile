UV=uv

init:
	cd ../../ && $(UV) pip sync chapters/ch04/requirements.lock --python 3.9
import:
	cd ../../ && PYTHONPATH=. $(UV) run python chapters/ch04/importer/import_seed.py

analysis:
	cd ../../ && PYTHONPATH=. $(UV) run python chapters/ch04/analysis/louvain_cluster_analysis.py
	cd ../../ && PYTHONPATH=. $(UV) run python chapters/ch04/analysis/pharma_analysis.py

