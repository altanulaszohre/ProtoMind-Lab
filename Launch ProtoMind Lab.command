#!/bin/sh
set -eu
APP_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
exec "$APP_ROOT/scripts/observatory.sh" --open
