#!/bin/bash
set -euo pipefail

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"

pushd ${DIR}
    POSTGRES_DSN="$(python3 -c 'import configparser; c = configparser.ConfigParser(); c.read("config.ini"); print(c["gino"]["dsn"])')"
    wget --no-check-certificate https://gtfs.mot.gov.il/gtfsfiles/israel-public-transportation.zip -O israel-public-transportation.zip
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
    if grep -q 'wheelchair_accessible' trips.txt
    then
        echo "yay, it's the end of days and the ministry of transport suddenly cares about wheelchair users, no modification needed"
    else
        echo "boo, ministry of transport still doesn't care about wheelchair users :( ☹ "
        sed -i 's/\r$/,\r/' trips.txt
        sed -i "1 s|\r$|wheelchair_accessible\r|" trips.txt
    fi
    echo -n "loading trips:        "
    psql $POSTGRES_DSN -c "\\copy trips from trips.txt with csv header quote ''"
    echo -n "loading stoptimes:    "
    psql $POSTGRES_DSN -c "\\copy stoptimes from 'stop_times.txt' with csv header"
    popd
    psql $POSTGRES_DSN -c "UPDATE translations SET translation='Jerusalem' WHERE trans_id='ירושלים' AND lang='EN';"
    rm -fr "$TEMP_DIR"
    echo 'loading Tel Aviv shabbat buses feed:'
    wget  https://opendata.tel-aviv.gov.il/OpenData_Ducaments/gtfs30042021.zip -O GTFS-TA.zip
    TEMP_DIR="$(mktemp -d)"
    unzip GTFS-TA.zip -d "$TEMP_DIR"
    pushd "$TEMP_DIR"
    echo -n 'loading agencies (TA):   '
    psql $POSTGRES_DSN -c "\\copy agency from 'agency.txt' with csv header"
    popd
    python3 load_telaviv_gtfs.py "$TEMP_DIR"
    rm -fr "$TEMP_DIR"
popd
