#!/usr/bin/env bash
# Writes deploy/requirements-hub.txt from your venv, leaving out the heavy face recognition and test packages.
cd "$(dirname "$0")/.."
./venv/bin/pip freeze \
  | grep -v -i -E "^(dlib|dlib-bin|face[-_]recognition|face[-_]recognition[-_]models|opencv|numpy|pytest|pluggy|iniconfig|setuptools)" \
  > deploy/requirements-hub.txt
grep -q -i "^psycopg2" deploy/requirements-hub.txt || echo "psycopg2-binary" >> deploy/requirements-hub.txt
echo "deploy/requirements-hub.txt written with $(wc -l < deploy/requirements-hub.txt) packages:"
cat deploy/requirements-hub.txt
