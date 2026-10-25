#!/bin/sh
# The shared older game (evals/_fixtures/old-game), variant task-running, written into the run's empty workspace.
here=$(cd "$(dirname "$0")" && pwd)
exec sh "$here/../_fixtures/old-game/build.sh" task-running
