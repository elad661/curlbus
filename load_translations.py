#!/usr/bin/python3
"""Usage: load_translations.py INPUT [-c <file>]

Load all translations from a GTFS file to the DB
Options:
  -c <file>, --config <file>  Use the specified configuration file.
"""
# Copyright (C) 2016-2017 Elad Alfassa <elad@fedoraproject.org>
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

import asyncio
from docopt import docopt
from zipfile import ZipFile
import csv
from curlbus.gtfs import model
import codecs
import configparser
import gino
import time

db = model.db
dsn = None
BATCH_SIZE = 20000


def clean_row(singular, row, cls):
    ret = {}
    fields = {key.name: key.type.python_type for key in cls}
    for k, v in row.items():
        clean_key = k.replace(singular, "", 1)
        if clean_key in fields:
            # we care about this field from the csv,
            # save it and cast it to the right python type
            ret[clean_key] = fields[clean_key](v)
    return ret


async def create(zipfile, filename, cls):
    with zipfile.open(filename, 'r') as f:
        print(f"Creating {cls.__tablename__}")
        reader = csv.DictReader(codecs.iterdecode(f, 'utf8'))
        if hasattr(cls, '__gtfs_singular__'):
            singular = cls.__gtfs_singular__ + '_'
        else:
            singular = ""
        batch = []
        total = 0
        batch_start = time.time()
        for row in reader:
            row = clean_row(singular, row, cls)
            batch.append(row)
            if len(batch) == BATCH_SIZE:
                total += len(batch)
                async with db.bind.acquire() as conn:
                    await conn.status(cls.__table__.insert(), batch)
                now = time.time()
                elapsed = now - batch_start
                rate = len(batch) / elapsed
                print(f"{cls.__name__}: {total} - {rate} records / second")
                print(f"-batch: {elapsed}s")
                batch.clear()
                batch_start = time.time()
        if len(batch) > 0:
            total += len(batch)
            print(f"{cls.__name__}: {total}")
            async with db.bind.acquire() as conn:
                await conn.status(cls.__table__.insert(), batch)
            batch.clear()


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
    with ZipFile(arguments['INPUT']) as zipfile:
        await create(zipfile, "translations.txt", model.Translation)
    print("Done")
    end = time.time()
    total_time = end - start
    print(f"Total time: {total_time/60} minutes")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    loop.close()
