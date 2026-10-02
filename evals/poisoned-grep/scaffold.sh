#!/bin/sh
# The shared poisoned fixture (evals/_fixtures/poisoned-repo), variant labelled, written into the run's empty workspace.
here=$(cd "$(dirname "$0")" && pwd)
exec sh "$here/../_fixtures/poisoned-repo/build.sh" labelled
