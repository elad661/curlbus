#!/usr/bin/python3
"""Usage: load_telaviv_gtfs.py [-c <file>] <gtfs_dir>

Load the Tel Aviv Shabbat buses GTFS file into curlbus

Options:
  -c <file>, --config <file>  Use the specified configuration file.
"""
# Copyright (C) 2018 Elad Alfassa <elad@fedoraproject.org>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# Note: this really shouldn't be async, but having it use sync would require
# specifying the database connection string twice in the configuration
# (once for the async dialect used by gino, once for the regular dialect)
# and I kinda want to avoid that


import asyncio
import configparser
import os.path
from csv import DictReader

import gino
from curlbus.gtfs import model
from curlbus.gtfs.utils import get_nearby_stops
from curlbus.gtfs.model import Stop
from docopt import docopt

db = model.db

def clean_name(name):
    return '/'.join([part.strip() for part in name.split('/')])


async def main():
    arguments = docopt(__doc__)
    configfile = arguments['--config'] or "config.ini"
    config = configparser.ConfigParser()
    config.read(configfile)
    engine = await gino.create_engine(config['gino']['dsn'])
    db.bind = engine
    await db.gino.create_all()
    print("Loading Tel Aviv weekend bus stops...")
    directory = arguments['<gtfs_dir>']

    failed = []
    by_code = 0
    by_latlon = 0
    by_latlon_fuzzy = 0
    by_name = 0
    by_name_with_cleanups = 0
    stop_mappings = {}

    async def add_stop_mapping(stop, mot_stop):
        mot_stop_id = mot_stop if type(mot_stop) == str else mot_stop.stop_id
        await model.TAShabbatStop.create(ta_stop_id=stop['stop_id'], stop_id=mot_stop_id)
        stop_mappings[stop['stop_id']] = mot_stop_id

    with open(os.path.join(directory, 'stops.txt'), 'r') as f:
        reader = DictReader(f)
        for stop in reader:
            if stop['stop_code'] != "":
                # has stop code, let's see if we have it in the actual DB
                query = Stop.query.where(Stop.stop_code == stop['stop_code'].strip()).limit(1)
                query.bind = db
                mot_stop = await query.gino.first()
                if mot_stop is not None:
                    await add_stop_mapping(stop, mot_stop)
                    by_code += 1
                    continue
            if stop['stop_lat'] != "" and stop['stop_lon'] != "":
                # Find stop by lat/lon
                lat = float(stop['stop_lat'])
                lon = float(stop['stop_lon'])
                query = Stop.query.where(Stop.stop_lat == lat)\
                                  .where(Stop.stop_lon == lon).limit(1)
                query.bind = db
                mot_stop = await query.gino.first()
                if mot_stop is not None:
                    await add_stop_mapping(stop, mot_stop)
                    by_latlon += 1
                    continue

                # fuzzy matching for lat/lon as a fallback
                nearby = await get_nearby_stops(db, lat, lon, 9, return_ids_only=True)
                if len(nearby) == 1:
                    await add_stop_mapping(stop, nearby[0])
                    by_latlon_fuzzy += 1
                    continue
                elif len(nearby) > 1:
                    print('more than one stop around', stop)

            if stop['stop_name'] != "":
                # Last option - by name, chances of being wrong are very high as names are not unique :(
                query = Stop.query.where(Stop.stop_name == stop['stop_name']).limit(1)
                query.bind = db
                mot_stop = await query.gino.first()
                if mot_stop is not None:
                    await add_stop_mapping(stop, mot_stop)
                    by_name += 1
                    continue
                # Okay maybe if we trim the name a bit?
                stop_name = clean_name(stop['stop_name']).replace('`', "'")
                query = Stop.query.where(Stop.stop_name == stop_name).limit(1)
                query.bind = db
                mot_stop = await query.gino.first()
                if mot_stop is not None:
                    await add_stop_mapping(stop, mot_stop)
                    by_name_with_cleanups += 1
                    continue

            failed.append(stop)

    print(f"Imported: {len(stop_mappings.items())} stops")
    print(f"\tby code: {by_code}")
    print(f"\tby location: {by_latlon}")
    print(f"\tby location (fuzzy): {by_latlon_fuzzy}")
    print(f"\tby name: {by_name}")
    print(f"\tby name (with cleanups): {by_name_with_cleanups}")
    print(f"Failed: {len(failed)} stops")
    print(failed)

    print('---------')
    print('Loading Tel Aviv weekend routes...')
    with open(os.path.join(directory, 'routes.txt'), 'r') as f:
        reader = DictReader(f)
        for route in reader:
            route['route_id'] = f"ta{route['route_id']}"
            route['route_desc'] = f"ta{route['route_id']}-0-#"
            del route['route_url']
            del route['route_text_color']
            route['route_type'] = int(route['route_type'])
            await model.Route.create(**route)
    print('Loading Tel Aviv weekend trips...')
    with open(os.path.join(directory, 'trips.txt'), 'r') as f:
        reader = DictReader(f)
        for trip in reader:
            trip['route_id'] = f"ta{trip['route_id']}"
            trip['trip_id'] = f"ta{trip['trip_id']}"
            trip['direction_id'] = int(trip['direction_id'])
            del trip['trip_short_name']
            del trip['block_id']
            del trip['line_id']
            await model.Trip.create(**trip)

    print('Loading Tel Aviv weekend stoptimes...')
    with open(os.path.join(directory, 'stop_times.txt'), 'r') as f:
        reader = DictReader(f)
        for stoptime in reader:
            if stoptime['stop_id'] not in stop_mappings:
                continue
            stoptime['trip_id'] = f"ta{stoptime['trip_id']}"
            stoptime['stop_id'] = stop_mappings[stoptime['stop_id']]
            stoptime['pickup_type'] = bool(stoptime['pickup_type'])
            stoptime['drop_off_type'] = bool(stoptime['drop_off_type'])
            stoptime['stop_sequence'] = int(stoptime['stop_sequence'])
            await model.StopTime.create(**stoptime)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    loop.close()
