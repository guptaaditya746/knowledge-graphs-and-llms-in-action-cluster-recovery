UV=uv

init:
	cd ../../ && $(UV) pip sync chapters/ch03/requirements.lock --python 3.9

import:
	cd ../../ && PYTHONPATH=. $(UV) run python chapters/ch03/importer/import_hpo.py
