#!/usr/bin/env bash

set -euo pipefail

GRAPHDB_URL="${GRAPHDB_URL:-http://localhost:7200}"
REPOSITORY_ID="${REPOSITORY_ID:-baseball}"
ASSUME_YES="${ASSUME_YES:-false}"

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

usage() {
  cat <<EOF
Usage: $(basename "$0") [--yes] [repository_id]

Deletes a GraphDB repository using the REST API.

Options:
  --yes     Skip the confirmation prompt
  -h        Show this help message

Environment:
  GRAPHDB_URL     GraphDB base URL (default: $GRAPHDB_URL)
  REPOSITORY_ID   Repository id (default: $REPOSITORY_ID)
  ASSUME_YES      Set to true to skip confirmation

Examples:
  $(basename "$0")
  $(basename "$0") --yes
  $(basename "$0") --yes baseball
EOF
}

confirm_delete() {
  local reply
  printf "Delete GraphDB repository '%s' at %s? [y/N] " "$REPOSITORY_ID" "$GRAPHDB_URL"
  read -r reply
  case "$reply" in
    y|Y|yes|YES)
      return 0
      ;;
    *)
      print_step "Aborted"
      exit 0
      ;;
  esac
}

parse_args() {
  while (($# > 0)); do
    case "$1" in
      --yes)
        ASSUME_YES=true
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        REPOSITORY_ID="$1"
        ;;
    esac
    shift
  done
}

delete_repo() {
  print_step "Deleting repository '$REPOSITORY_ID'"
  curl -fsS -X DELETE "$GRAPHDB_URL/rest/repositories/$REPOSITORY_ID" >/dev/null
}

main() {
  require_cmd curl
  parse_args "$@"

  graphdb_ready || fail "GraphDB is not reachable at $GRAPHDB_URL"

  if ! repo_exists; then
    fail "Repository '$REPOSITORY_ID' does not exist"
  fi

  if [[ "$ASSUME_YES" != "true" ]]; then
    confirm_delete
  fi

  delete_repo
  print_step "Repository '$REPOSITORY_ID' was deleted"
}

main "$@"
