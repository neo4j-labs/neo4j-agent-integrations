#!/bin/bash
#
# Random Query Runner
# Continuously invokes the deployed agent with random queries from queries.txt
# Runs every 10 seconds until interrupted with Ctrl+C
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
QUERIES_FILE="$SCRIPT_DIR/queries.txt"

# Check if queries file exists
if [[ ! -f "$QUERIES_FILE" ]]; then
    echo "ERROR: queries.txt not found at $QUERIES_FILE"
    exit 1
fi

# Extract queries (lines starting with a number followed by a period)
# Store in a temp file for compatibility with older bash
TEMP_QUERIES=$(mktemp)
grep -E '^[0-9]+\.' "$QUERIES_FILE" | sed 's/^[0-9]*\. //' > "$TEMP_QUERIES"

# Count queries
NUM_QUERIES=$(wc -l < "$TEMP_QUERIES" | tr -d ' ')

if [[ "$NUM_QUERIES" -eq 0 ]]; then
    echo "ERROR: No queries found in $QUERIES_FILE"
    rm -f "$TEMP_QUERIES"
    exit 1
fi

echo "============================================================"
echo "Random Query Runner"
echo "============================================================"
echo "Loaded $NUM_QUERIES queries from queries.txt"
echo "Running a random query every 10 seconds..."
echo "Press Ctrl+C to stop"
echo "============================================================"
echo

# Cleanup temp file on exit
trap "rm -f $TEMP_QUERIES" EXIT

iteration=1

while true; do
    # Select a random line number (1-based)
    random_line=$(( (RANDOM % NUM_QUERIES) + 1 ))

    # Get the query at that line
    query=$(sed -n "${random_line}p" "$TEMP_QUERIES")

    echo "============================================================"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Iteration $iteration - Query #$random_line"
    echo "============================================================"
    echo "Query: $query"
    echo "------------------------------------------------------------"
    echo

    # Invoke the agent
    cd "$SCRIPT_DIR"
    ./agent.sh invoke-cloud "$query"

    echo
    echo "------------------------------------------------------------"
    echo "Waiting 10 seconds before next query..."
    echo

    iteration=$((iteration + 1))
    sleep 10
done
