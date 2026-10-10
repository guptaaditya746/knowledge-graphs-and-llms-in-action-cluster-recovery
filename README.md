# Knowledge Graphs and LLMs in Action

Code listings, importers, and analysis scripts accompanying the book *Knowledge Graphs and LLMs in Action*. The examples use Neo4j, Python, Cypher, and chapter-specific datasets.

## Setup

Install Neo4j and GNU Make. Create a Python environment for the chapter you want to run, then install that chapter's dependencies using its `requirements.txt` or `requirements.lock` where provided.

Copy `config.ini.example` to `config.ini` and fill in your local Neo4j URI, username, and password. `config.ini` is ignored by Git.

Each chapter has its own README and Makefile. From the relevant chapter directory, inspect the Makefile targets and run the importer or analysis target for your Neo4j instance. Examples are chapter-specific and may require source data or Neo4j plugins documented in that chapter.

The source checkout's local credentials and data caches are excluded from this snapshot; see `BACKUP_MANIFEST.md`.
