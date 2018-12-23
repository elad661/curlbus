#!/bin/bash
set -euo pipefail

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"

pushd ${DIR}
    POSTGRES_DSN="$(python3 -c 'import configparser; c = configparser.ConfigParser(); c.read("config.ini"); print(c["gino"]["dsn"])')"
    wget ftp://gtfs.mot.gov.il/israel-public-transportation.zip -O israel-public-transportation.zip
    python3 create_tables.py
    TEMP_DIR="$(mktemp -d)"
    unzip israel-public-transportation.zip -d "$TEMP_DIR"
    pushd "$TEMP_DIR"
    # Hack! use  (U+0007, bell) as a quote character, since this will probably
    # will never appear in the CSV. This will avoid skipping lines when "
    # is used in the original CSV
    echo -n "loading translations: "
    psql $POSTGRES_DSN -c "\\copy translations from 'translations.txt' with csv header quote ''"
    echo -n "loading agencies:     "
    psql $POSTGRES_DSN -c "\\copy agency from 'agency.txt' with csv header"
    echo -n "loading stops:        "
    psql $POSTGRES_DSN -c "\\copy stops from stops.txt with csv header quote ''"
    echo -n "loading routes:       "
    psql $POSTGRES_DSN -c "\\copy routes from routes.txt with csv header quote ''"
    echo -n "loading trips:        "
    psql $POSTGRES_DSN -c "\\copy trips from trips.txt with csv header quote ''"
    echo -n "loading stoptimes:    "
    psql $POSTGRES_DSN -c "\\copy stoptimes from 'stop_times.txt' with csv header"
    popd
    psql $POSTGRES_DSN -c "UPDATE translations SET translation='Jerusalem' WHERE trans_id='ירושלים' AND lang='EN';"
    rm -fr "$TEMP_DIR"
popd
