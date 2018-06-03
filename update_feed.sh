#!/bin/bash
set -euo pipefail
wget ftp://gtfs.mot.gov.il/israel-public-transportation.zip -O israel-public-transportation.zip
python3 create_tables.py
python3 load_translations.py israel-public-transportation.zip
TEMP_DIR="$(mktemp -d)"
unzip israel-public-transportation.zip -d "$TEMP_DIR"
pushd "$TEMP_DIR"
# Hack! use  (U+0007, bell) as a quote character, since this will probably
# will never appear in the CSV. This will avoid skipping lines when "
# is used in the original CSV
psql -d gtfs -c "\\copy agency from 'agency.txt' with csv header"
psql -d gtfs -c "\\copy stops from stops.txt with csv header quote ''"
psql -d gtfs -c "\\copy routes from routes.txt with csv header quote ''"
psql -d gtfs -c "\\copy trips from trips.txt with csv header quote ''"
psql -d gtfs -c "\\copy stoptimes from 'stop_times.txt' with csv header"
popd
rm -fr "$TEMP_DIR"
