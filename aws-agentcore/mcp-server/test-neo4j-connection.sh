#!/bin/bash
# Test Neo4j connectivity using cypher-shell
# Usage: ./scripts/test-neo4j-connection.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "Neo4j Connection Test"
echo "====================="
echo

# Check for cypher-shell
if ! command -v cypher-shell &> /dev/null; then
    echo -e "${RED}ERROR: cypher-shell not found${NC}"
    echo
    echo "Install with:"
    echo "  brew install cypher-shell"
    echo
    exit 1
fi

# Load .env from current directory
ENV_FILE=".env"

if [[ -f "$ENV_FILE" ]]; then
    echo "Loading environment from: $ENV_FILE"
    source "$ENV_FILE"
else
    echo -e "${YELLOW}WARNING: .env file not found in current directory${NC}"
    echo "Checking for environment variables..."
fi

echo

# Validate required variables
missing_vars=()

if [[ -z "$NEO4J_URI" ]]; then
    missing_vars+=("NEO4J_URI")
fi

if [[ -z "$NEO4J_USERNAME" ]]; then
    missing_vars+=("NEO4J_USERNAME")
fi

if [[ -z "$NEO4J_PASSWORD" ]]; then
    missing_vars+=("NEO4J_PASSWORD")
fi

if [[ ${#missing_vars[@]} -gt 0 ]]; then
    echo -e "${RED}ERROR: Missing required environment variables:${NC}"
    for var in "${missing_vars[@]}"; do
        echo "  - $var"
    done
    echo
    echo "Please set these in your .env file or export them."
    exit 1
fi

# Use default database if not set
NEO4J_DATABASE="${NEO4J_DATABASE:-neo4j}"

echo "Connection details:"
echo "  URI:      $NEO4J_URI"
echo "  Database: $NEO4J_DATABASE"
echo "  Username: $NEO4J_USERNAME"
echo

# Test connectivity
echo "Testing connection..."
echo

if echo "RETURN 1 AS test;" | cypher-shell \
    -a "$NEO4J_URI" \
    -u "$NEO4J_USERNAME" \
    -p "$NEO4J_PASSWORD" \
    -d "$NEO4J_DATABASE" \
    --non-interactive \
    --format plain &> /dev/null; then

    echo -e "${GREEN}SUCCESS: Connected to Neo4j!${NC}"
    echo

    # Get database info
    echo "Database info:"
    cypher-shell \
        -a "$NEO4J_URI" \
        -u "$NEO4J_USERNAME" \
        -p "$NEO4J_PASSWORD" \
        -d "$NEO4J_DATABASE" \
        --non-interactive \
        --format plain \
        "CALL dbms.components() YIELD name, versions, edition RETURN name, versions[0] AS version, edition;"
else
    echo -e "${RED}FAILED: Could not connect to Neo4j${NC}"
    echo
    echo "Please check:"
    echo "  - NEO4J_URI is correct"
    echo "  - NEO4J_USERNAME and NEO4J_PASSWORD are valid"
    echo "  - The Neo4j database is running and accessible"
    echo "  - Network connectivity (firewall, VPN, etc.)"
    exit 1
fi
