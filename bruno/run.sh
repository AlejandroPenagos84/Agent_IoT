#!/usr/bin/env bash
# Run the Bruno collection from its collection root.
# Usage:
#   ./bruno/run.sh --env Local
#   ./bruno/run.sh 01-auth --env Local
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$root/AgentIoT"
exec npx --yes @usebruno/cli run "$@"
