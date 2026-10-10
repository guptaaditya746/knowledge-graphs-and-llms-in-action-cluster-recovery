import sys
import logging

from neo4j.exceptions import ClientError as Neo4jClientError
from util.base_importer import BaseImporter

# ------------------------------------------------------------------------------
# Logging configuration
# ------------------------------------------------------------------------------
# Logs are printed with timestamps and severity levels to make long-running
# imports traceable and debuggable.
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)


class HPOImporter(BaseImporter):
    """
    HPOImporter is responsible for building a Neo4j knowledge graph from the
    Human Phenotype Ontology (HPO) and its disease annotations.

    The import process consists of:
    1. Creating constraints and indexes
    2. Initializing Neosemantics (n10s)
    3. Importing the HPO ontology (OWL/RDF)
    4. Creating disease nodes from HPO annotations
    5. Creating and enriching disease–phenotype relationships
    6. Cleaning up unused nodes
    """

    def __init__(self, argv):
        """
        Initialize the importer and connect to the Neo4j database.

        Parameters
        ----------
        argv : list
            Command-line arguments forwarded to BaseImporter.
        """
        super().__init__(command=__file__, argv=argv)

        # Neo4j database name (default database in Neo4j 5.x)
        self._database = "neo4j"

        # Open a test session to ensure connectivity
        with self._driver.session() as session:
            logging.info(f"Using default database: {self._database}")

    def set_constraints(self):
        """
        Create constraints and indexes to ensure data integrity and
        improve query performance.

        - Enforces uniqueness of RDF resources by URI
        - Enforces uniqueness of HPO IDs
        - Adds indexes for faster disease and phenotype lookups
        """
        queries = [
            # Unique RDF resource URI (required by Neosemantics)
            "CREATE CONSTRAINT n10s_unique_uri IF NOT EXISTS "
            "FOR (r:Resource) REQUIRE r.uri IS UNIQUE;",

            # Unique resource identifier
            "CREATE CONSTRAINT IF NOT EXISTS "
            "FOR (n:Resource) REQUIRE (n.id) IS UNIQUE;",

            # Indexes for frequent lookup fields
            "CREATE INDEX disease_id IF NOT EXISTS FOR (n:HpoDisease) ON (n.id);",
            "CREATE INDEX phenotype_id IF NOT EXISTS FOR (n:HpoPhenotype) ON (n.id);"
        ]

        with self._driver.session(database=self._database) as session:
            for q in queries:
                try:
                    session.run(q)
                except Neo4jClientError as e:
                    # Ignore errors if the constraint or index already exists
                    if e.code != "Neo.ClientError.Schema.EquivalentSchemaRuleAlreadyExists":
                        raise e

    def check_neo_semantics(self):
        """
        Verify that the Neosemantics (n10s) plugin is installed.

        The import relies heavily on n10s procedures for RDF ingestion.
        If n10s is missing, the import cannot proceed.
        """
        query = (
            'SHOW PROCEDURES YIELD name '
            'WHERE name = "n10s.graphconfig.init"'
        )

        with self._driver.session(database=self._database) as session:
            r = session.run(query)
            if len(r.data()) == 0:
                raise RuntimeError(
                    "Cannot find `n10s.graphconfig.init`. "
                    "Please make sure Neosemantics is installed.\n"
                    "https://neo4j.com/labs/neosemantics/installation/"
                )

    def initialize_neo_semantics(self):
        """
        Initialize the Neosemantics graph configuration if the graph
        is currently empty.

        Configuration choices:
        - handleVocabUris = 'IGNORE':
          Shortens RDF URIs by ignoring vocabulary prefixes.
        - applyNeo4jNaming = True:
          Converts RDF names into Neo4j-friendly labels and properties.
        """
        test_query = "MATCH (n:Resource) RETURN n"

        with self._driver.session(database=self._database) as session:
            r = session.run(test_query)

            # Only initialize if the graph is empty
            if len(r.data()) == 0:
                queries = [
                    "CALL n10s.graphconfig.init();",
                    "CALL n10s.graphconfig.set({ handleVocabUris: 'IGNORE' });",
                    "CALL n10s.graphconfig.set({ applyNeo4jNaming: True });"
                ]

                for q in queries:
                    session.run(q)

    def load_HPO_ontology(self):
        """
        Import the Human Phenotype Ontology (HPO) from its OWL file.

        The ontology is fetched directly from the OBO repository and
        loaded using Neosemantics' RDF import functionality.
        """
        query = """
        CALL n10s.rdf.import.fetch(
            "http://purl.obolibrary.org/obo/hp.owl",
            "RDF/XML"
        );
        """

        with self._driver.session(database=self._database) as session:
            session.run(query)

    def label_HPO_entities(self):
        """
        Label HPO phenotype nodes and extract human-readable IDs.

        - Assigns the label `HpoPhenotype` to phenotype resources
        - Extracts the HPO ID (e.g., HP:0000118) from the URI
        """
        query = """
        MATCH (n:Resource)
        WHERE n.uri STARTS WITH "http://purl.obolibrary.org/obo/HP"
        SET n:HpoPhenotype,
            n.id = coalesce(
                n.id,
                replace(
                    apoc.text.replace(n.uri, '(.*)obo/', ''),
                    '_',
                    ':'
                )
            );
        """

        with self._driver.session(database=self._database) as session:
            session.run(query)

    def create_disease_entities(self):
        """
        Create disease nodes from the HPO annotation file.

        Diseases are represented as `HpoDisease` nodes and are linked
        to phenotypes in later steps.
        """
        query = """
        LOAD CSV FROM
        'https://github.com/obophenotype/human-phenotype-ontology/releases/latest/download/phenotype.hpoa'
        AS row
        FIELDTERMINATOR '\\t'
        WITH row
        SKIP 5
        MERGE (dis:Resource:HpoDisease {id: row[0]})
        ON CREATE SET dis.label = row[1];
        """

        with self._driver.session(database=self._database) as session:
            session.run(query)

    def create_rels_features_diseases(self):
        """
        Create HAS_PHENOTYPIC_FEATURE relationships between diseases
        and phenotypes using the HPO annotation file.
        """
        query = """
        LOAD CSV FROM
        'https://github.com/obophenotype/human-phenotype-ontology/releases/latest/download/phenotype.hpoa'
        AS row
        FIELDTERMINATOR '\\t'
        WITH row
        SKIP 5
        MATCH (dis:HpoDisease {id: row[0]})
        MATCH (phe:HpoPhenotype {id: row[3]})
        MERGE (dis)-[:HAS_PHENOTYPIC_FEATURE]->(phe);
        """

        with self._driver.session(database=self._database) as session:
            session.run(query)

    def add_base_properties_to_rels(self):
        """
        Add base annotation properties to HAS_PHENOTYPIC_FEATURE relationships.

        Properties include:
        - source
        - evidence
        - onset
        - frequency
        - sex
        - modifier
        - aspect
        - biocuration
        """
        query = """
        LOAD CSV FROM
        'https://github.com/obophenotype/human-phenotype-ontology/releases/latest/download/phenotype.hpoa'
        AS row
        FIELDTERMINATOR '\\t'
        WITH row
        SKIP 5
        MATCH (dis:HpoDisease {id: row[0]})-[rel:HAS_PHENOTYPIC_FEATURE]->(phe:HpoPhenotype {id: row[3]})
        FOREACH(_ IN CASE WHEN row[4]  IS NOT NULL THEN [1] ELSE [] END | SET rel.source = row[4])
        FOREACH(_ IN CASE WHEN row[5]  IS NOT NULL THEN [1] ELSE [] END | SET rel.evidence = row[5])
        FOREACH(_ IN CASE WHEN row[6]  IS NOT NULL THEN [1] ELSE [] END | SET rel.onset = row[6])
        FOREACH(_ IN CASE WHEN row[7]  IS NOT NULL THEN [1] ELSE [] END | SET rel.frequency = row[7])
        FOREACH(_ IN CASE WHEN row[8]  IS NOT NULL THEN [1] ELSE [] END | SET rel.sex = row[8])
        FOREACH(_ IN CASE WHEN row[9]  IS NOT NULL THEN [1] ELSE [] END | SET rel.modifier = row[9])
        FOREACH(_ IN CASE WHEN row[10] IS NOT NULL THEN [1] ELSE [] END | SET rel.aspect = row[10])
        FOREACH(_ IN CASE WHEN row[11] IS NOT NULL THEN [1] ELSE [] END | SET rel.biocuration = row[11]);
        """

        with self._driver.session(database=self._database) as session:
            session.run(query)

    def enrich_with_descriptive_properties(self):
        """
        Enrich relationships with human-readable descriptions.

        Uses APOC to:
        - Extract curator and date information
        - Map evidence and aspect codes to descriptive text
        - Generate URLs to external biomedical resources
        """
        query = """
        CALL apoc.periodic.iterate(
            "MATCH ()-[rel:HAS_PHENOTYPIC_FEATURE]->() RETURN rel",
            "SET
                rel.createdBy = apoc.text.regexGroups(rel.biocuration, 'HPO:(\\\\w+)\\\\[')[0][1],
                rel.creationDate = apoc.text.regexGroups(rel.biocuration, '\\\\[(\\\\d{4}-\\\\d{2}-\\\\d{2})\\\\]')[0][1],
                rel.aspectName =
                    CASE rel.aspect
                        WHEN 'P' THEN 'Phenotypic abnormality'
                        WHEN 'I' THEN 'Inheritance'
                    END,
                rel.aspectDescription =
                    CASE rel.aspect
                        WHEN 'P' THEN 'Phenotypic abnormality subontology'
                        WHEN 'I' THEN 'Inheritance subontology'
                    END,
                rel.evidenceName =
                    CASE rel.evidence
                        WHEN 'IEA' THEN 'Inferred from electronic annotation'
                        WHEN 'PCS' THEN 'Published clinical study'
                        WHEN 'TAS' THEN 'Traceable author statement'
                    END,
                rel.url =
                    CASE
                        WHEN rel.source STARTS WITH 'PMID:' THEN
                            'https://pubmed.ncbi.nlm.nih.gov/' + apoc.text.replace(rel.source, '(.*)PMID:', '')
                        WHEN rel.source STARTS WITH 'OMIM:' THEN
                            'https://omim.org/entry/' + apoc.text.replace(rel.source, '(.*)OMIM:', '')
                    END",
            {batchSize: 1000}
        );
        """

        with self._driver.session(database=self._database) as session:
            session.run(query)

    def remove_unused_node(self):
        """
        Remove unused Resource nodes that are neither phenotypes nor diseases.

        This step cleans up intermediate RDF nodes that are not relevant
        to the final knowledge graph.
        """
        query = """
        CALL apoc.periodic.iterate(
            "MATCH (n:Resource) RETURN id(n) AS node_id",
            "MATCH (n)
             WHERE id(n) = node_id
               AND NOT 'HpoPhenotype' IN labels(n)
               AND NOT 'HpoDisease' IN labels(n)
             DETACH DELETE n",
            {batchSize: 10000}
        );
        """

        with self._driver.session(database=self._database) as session:
            session.run(query)


# ------------------------------------------------------------------------------
# Main execution pipeline
# ------------------------------------------------------------------------------
if __name__ == '__main__':
    importing = HPOImporter(argv=sys.argv[1:])

    logging.info('Setting Constraints')
    importing.set_constraints()

    logging.info('Initializing Neosemantics')
    importing.check_neo_semantics()
    importing.initialize_neo_semantics()

    logging.info('Loading HPO Ontology')
    importing.load_HPO_ontology()

    logging.info('Loading HPO Entities')
    importing.label_HPO_entities()

    logging.info('Creating Disease Entities')
    importing.create_disease_entities()

    logging.info('Creating Phenotype Relationships')
    importing.create_rels_features_diseases()

    logging.info('Base Relationship Enriching')
    importing.add_base_properties_to_rels()

    logging.info('Descriptive Relationship Enriching')
    importing.enrich_with_descriptive_properties()

    logging.info('Cleaning the Knowledge Graph...')
    importing.remove_unused_node()