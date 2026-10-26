#!/usr/bin/env bash
#***********************************************************************
# Record MuSoHu evaluation topics through the native bag recorder services.
# Description: Uses the web app's session client and metadata/finalization checks.
# Usage: ./record-evaluation.sh [--topics FILE] [--output DIR] [--label NAME]
# Options: --duration SECONDS; -h/--help displays complete help without changes.
# Examples: ./record-evaluation.sh --label route_a --duration 30
# Prerequisites: Built workspace and helmet/standalone recorder already launched.
# Author: MuSoHu Team
# Date: 2026-10-22
#***********************************************************************
set -euo pipefail

#***********************************************************************
# Delegate validation, service ownership and graceful stopping to the client.
#***********************************************************************
record_script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec /usr/bin/python3 "$record_script_dir/record-session.py" "$@"
