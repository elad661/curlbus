#!/usr/bin/python3
"""Usage: load_cities.py [-c <file>]

Load
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

from curlbus.gtfs import model
from docopt import docopt
import aiohttp
import asyncio
import configparser
import csv
import gino
import io
import time
# https://data.gov.il/dataset/citiesandsettelments/resource/d4901968-dad3-4845-a9b0-a57d027f11ab
DATASET_BASE_URL = "https://data.gov.il"
DATASET = "/api/action/datastore_search?resource_id=d4901968-dad3-4845-a9b0-a57d027f11ab&include_total=true"
headers = { 'User-Agent': 'Mozilla/5.0 (X11; Fedora; Linux x86_64; rv:72.0) Gecko/20100101 Firefox/72.0' }

db = model.db


def flip_brackets(source: str) -> str:
    """ I can't believe this is needed, but it is - the brackets in the source are flipped! """
    ret = ""
    for char in source:
        if char == '(':
            ret += ')'
        elif char == ')':
            ret += '('
        else:
            ret += char
    return ret


async def main():
    start = time.time()
    arguments = docopt(__doc__)
    configfile = arguments['--config'] or "config.ini"
    config = configparser.ConfigParser()
    config.read(configfile)
    dsn = config['gino']['dsn']
    engine = await gino.create_engine(dsn)
    db.bind = engine
    await db.gino.create_all()
    async with aiohttp.ClientSession() as session:
        print("Downloading city name dataset...")
        response = await session.get(DATASET_BASE_URL + DATASET, headers=headers)
        data = await response.json()
        print(f"Loading cities...")
        total = data['result']['total']
        processed = 0
        missing = []
        print(f"Total expected: {total}")
        cities = []
        while processed < total:
            for row in data['result']['records']:
                hebrew_name = flip_brackets(row['שם_ישוב'].strip())
                english_name = row['שם_ישוב_לועזי'].strip().title()
                if english_name:
                    cities.append({'name': hebrew_name, 'english_name': english_name})
                else:
                    missing.append(hebrew_name)
                processed += 1
            next = data['result']['_links']['next']
            if processed < total:
                print(f'Have so far: {len(cities)} / {total}')
                response = await session.get(DATASET_BASE_URL + next, headers=headers)
                data = await response.json()

        total_saved = len(cities)
        print(f"Total saved: {total_saved} out of {processed}")
        print(f"Missing translations: {len(missing)} records, {missing}")
        async with db.bind.acquire() as conn:
            await conn.status(model.City.insert(), cities)

    print("Done")
    end = time.time()
    total_time = end - start
    print(f"Total time: {total_time} seconds")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    loop.close()
