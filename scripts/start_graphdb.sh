#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GRAPHDB_URL="${GRAPHDB_URL:-http://localhost:7200}"
REPOSITORY_ID="${REPOSITORY_ID:-baseball}"
RDF_FILE="${RDF_FILE:-$ROOT_DIR/rdf/baseball.nt}"
GRAPHDB_DESKTOP_BIN="${GRAPHDB_DESKTOP_BIN:-/opt/graphdb-desktop/bin/graphdb-desktop}"
WAIT_SECONDS="${WAIT_SECONDS:-120}"
LOG_FILE="${LOG_FILE:-$ROOT_DIR/.graphdb-desktop.log}"

print_step() {
  printf '\n[%s] %s\n' "$(date +%H:%M:%S)" "$1"
}

fail() {
  printf 'Error: %s\n' "$1" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

graphdb_ready() {
  curl -fsS "$GRAPHDB_URL/rest/repositories" >/dev/null 2>&1
}

repo_exists() {
  curl -fsS "$GRAPHDB_URL/rest/repositories" | grep -q "\"id\":\"$REPOSITORY_ID\""
}

start_graphdb_desktop() {
  [[ -x "$GRAPHDB_DESKTOP_BIN" ]] || fail "GraphDB Desktop binary not found at $GRAPHDB_DESKTOP_BIN"

  print_step "Starting GraphDB Desktop"
  nohup "$GRAPHDB_DESKTOP_BIN" >"$LOG_FILE" 2>&1 </dev/null &

  cat <<EOF
GraphDB Desktop was launched.
If this is your first time opening it, create/start a local GraphDB location in the GUI.
The script will keep waiting for GraphDB at $GRAPHDB_URL for up to $WAIT_SECONDS seconds.
EOF
}

wait_for_graphdb() {
  local elapsed=0

  while (( elapsed < WAIT_SECONDS )); do
    if graphdb_ready; then
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done

  cat <<EOF
GraphDB is still not reachable at $GRAPHDB_URL.
Open GraphDB Desktop and make sure the local service is started, then rerun this script.
Desktop log: $LOG_FILE
EOF
  exit 1
}

create_repo_config() {
  local config_file="$1"

  cat >"$config_file" <<EOF
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#>.
@prefix rep: <http://www.openrdf.org/config/repository#>.
@prefix sr: <http://www.openrdf.org/config/repository/sail#>.
@prefix sail: <http://www.openrdf.org/config/sail#>.
@prefix graphdb: <http://www.ontotext.com/config/graphdb#>.

[] a rep:Repository ;
   rep:repositoryID "$REPOSITORY_ID" ;
   rdfs:label "Baseball repository" ;
   rep:repositoryImpl [
      rep:repositoryType "graphdb:SailRepository" ;
      sr:sailImpl [
         sail:sailType "graphdb:Sail" ;
         graphdb:ruleset "rdfsplus-optimized" ;
         graphdb:disable-sameAs "true" ;
         graphdb:check-for-inconsistencies "false" ;
         graphdb:query-timeout "0" ;
         graphdb:query-limit-results "0" ;
         graphdb:enable-context-index "false" ;
         graphdb:enablePredicateList "true" ;
         graphdb:enable-fts-index "false" ;
         graphdb:repository-type "file-repository" ;
         graphdb:base-URL "http://baseball.ws.pt/" ;
      ]
   ] .
EOF
}

create_repository() {
  local config_file
  config_file="$(mktemp)"

  create_repo_config "$config_file"

  print_step "Creating repository '$REPOSITORY_ID'"
  curl -fsS -X POST \
    "$GRAPHDB_URL/rest/repositories" \
    -H 'Content-Type: multipart/form-data' \
    -F "config=@$config_file" >/dev/null

  rm -f "$config_file"
}

import_rdf() {
  [[ -f "$RDF_FILE" ]] || fail "RDF file not found at $RDF_FILE"

  print_step "Importing $(basename "$RDF_FILE") into '$REPOSITORY_ID'"
  
  curl -X POST "$GRAPHDB_URL/repositories/$REPOSITORY_ID/statements" \
       -H "Content-Type:application/n-triples" \
       -T "$RDF_FILE"
}

main() {
  require_cmd curl

  if graphdb_ready; then
    print_step "GraphDB is already running at $GRAPHDB_URL"
  else
    start_graphdb_desktop
    wait_for_graphdb
    print_step "GraphDB is reachable"
  fi

  if repo_exists; then
    print_step "Repository '$REPOSITORY_ID' already exists. Skipping creation/import."
  else
    create_repository
    import_rdf
    print_step "Repository '$REPOSITORY_ID' is ready"
  fi

  cat <<EOF

Next step:
  cd "$ROOT_DIR/webapp"
  source "$ROOT_DIR/venv/bin/activate"
  python manage.py runserver 8001
EOF
}

main "$@"
