#!/bin/sh
# Copies the fixture game repo (a CLAUDE.md with the refs rule, the index, a tiny refs/ tree) into the run's folder.
here=$(cd "$(dirname "$0")" && pwd)
cp -R "$here/workspace/." .
