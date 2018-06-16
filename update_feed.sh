#!/bin/bash
set -euo pipefail
POSTGRES_DSN="$(python3 -c 'import configparser; c = configparser.ConfigParser(); c.read("config.ini"); print(c["gino"]["dsn"])')"
wget ftp://gtfs.mot.gov.il/israel-public-transportation.zip -O israel-public-transportation.zip
python3 create_tables.py
python3 load_translations.py israel-public-transportation.zip
TEMP_DIR="$(mktemp -d)"
unzip israel-public-transportation.zip -d "$TEMP_DIR"
pushd "$TEMP_DIR"
# Hack! use  (U+0007, bell) as a quote character, since this will probably
# will never appear in the CSV. This will avoid skipping lines when "
# is used in the original CSV
psql $POSTGRES_DSN -c "\\copy agency from 'agency.txt' with csv header"
psql $POSTGRES_DSN -c "\\copy stops from stops.txt with csv header quote ''"
psql $POSTGRES_DSN -c "\\copy routes from routes.txt with csv header quote ''"
psql $POSTGRES_DSN -c "\\copy trips from trips.txt with csv header quote ''"
psql $POSTGRES_DSN -c "\\copy stoptimes from 'stop_times.txt' with csv header"
popd
rm -fr "$TEMP_DIR"
