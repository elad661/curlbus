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
DATASET = "https://data.gov.il/dataset/3fc54b81-25b3-4ac7-87db-248c3e1602de/resource/d4901968-dad3-4845-a9b0-a57d027f11ab/download/yeshuvim20180501.csv"

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
        response = await session.get(DATASET)
        f = io.StringIO(await response.text())
        print(f"Loading cities...")
        f.readline()  # skip the first line
        reader = csv.DictReader(f)
        cities = []
        for row in reader:
            hebrew_name = flip_brackets(row['שם_ישוב'].strip())
            english_name = row['שם_ישוב_לועזי'].strip().title()
            if english_name:
                cities.append({'name': hebrew_name, 'english_name': english_name})
        total = len(cities)
        print(f"Total: {total}")
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
