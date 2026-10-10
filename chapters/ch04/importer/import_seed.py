import sys
# You might need to change this import if your util structure changed
from util.graphdb_base import GraphDBBase 

if __name__ == '__main__':
    # Force the database name to 'neo4j' in the arguments if necessary
    importing = GraphDBBase(argv=sys.argv[1:])
    
    print("Note: Community Edition detected. Skipping 'CREATE DATABASE' command.")
    print("To get the PPI data, you must manually load the backup using neo4j-admin.")

    # We skip the session.run() block entirely because 'ppi' won't exist 
    # and the seedUri option is Enterprise-only.
    
    print("Importer initialized. Ready for subsequent steps using 'neo4j' database.")
    importing.close()