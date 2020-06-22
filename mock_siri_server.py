#!/usr/bin/env python3
# mock_siri_server.py - a fake SIRI-SM server for testing curlbus
#
# Copyright 2018,2020 Elad Alfassa <elad@fedoraproject.org>
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
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Usage: mock_siri_server.py [-c <file>] [-p <port>]

A mock siri api server that lies to you about when your next bus is coming.
use for testing curlbus without MoT API access.

Options:
  -c <file>, --config <file>  Use the specified configuration file.
  -p <port>, --port <port>  Port to listen on. Defaults to 8081
"""
import dateutil.tz
import configparser
from docopt import docopt
from aiohttp import web
from gino.ext.aiohttp import Gino
from curlbus.gtfs import model as gtfs_model
from random import randint
from datetime import datetime, timedelta
from dateutil.parser import parse

RANDOM_TRIPS_QUERY = """SELECT t.trip_id
                        FROM stoptimes as st
                        JOIN trips as t ON t.trip_id=st.trip_id
                        JOIN stops as s ON s.stop_id=st.stop_id
                        WHERE s.stop_code='{code}'
                        GROUP BY t.trip_id
                        ORDER BY random() LIMIT 5;"""


async def random_trips(db, stop_code: int):
    """ Get random trips for a stop """
    # Query random trips that actually happen in this stop
    result = await db.all(RANDOM_TRIPS_QUERY.format(code=stop_code))
    trips = [r[0] for r in result]  # remove the noise
    # get ORM trip objects
    query = gtfs_model.Trip.query.where(gtfs_model.Trip.trip_id.in_(trips))
    return await db.all(query)


async def get_route_for_trip(db, trip: gtfs_model.Trip) -> gtfs_model.Route:
    query = gtfs_model.Route.query.where(gtfs_model.Route.route_id == trip.route_id)
    return (await db.all(query))[0]


def now():
    return datetime.now(dateutil.tz.tzlocal())


class MockSIRIServer(object):
    def __init__(self, config):
        db = Gino(model_classes=tuple(gtfs_model.tables))
        app = web.Application(middlewares=[db])
        app["config"] = config

        db.init_app(app)
        app.add_routes([web.get('/{tail:.*}', self.handle_request)])
        self._app = app

    def run(self, port):
        web.run_app(self._app, port=port)

    async def handle_request(self, request):
        response = {
            "Siri": {
                "ServiceDelivery": {
                    "ResponseTimestamp": str(now()),
                    "ProducerRef": "Mock Siri Server",
                    "ResponseMessageIdentifier": 7603,
                    "RequestMessageRef": "[REDACTED]",
                    "Status": "true",
                    "StopMonitoringDelivery": {
                        "-version": "2.8",
                        "Status": "true",
                        "ResponseTimestamp": str(now()),
                        "MonitoredStopVisit": [
                            # To be filled
                        ]
                    }
                }
            }
        }
        db = request.app['db']

        visits = response['Siri']['ServiceDelivery']['StopMonitoringDelivery']['MonitoredStopVisit']
        print(request.query['MonitoringRef'])
        for stop in request.query['MonitoringRef'].split(','):
            for i, trip in enumerate(await random_trips(db, stop)):
                # Collect variables
                route = await get_route_for_trip(db, trip)
                destination_code = await trip.get_last_stop_code(db)
                timestamp = now()

                # Make up random times
                eta = now() + timedelta(minutes=randint(0, 30))
                departed = now() - timedelta(minutes=randint(0, 180))
                trip_id = trip.trip_id.split('_')[0]
                trip_date = parse(trip.trip_id.split('_')[1])

                visits.append({
                    "RecordedAtTime": str(timestamp),
                    "ItemIdentifier": i,
                    "MonitoringRef": stop,
                    "MonitoredVehicleJourney": {
                        "LineRef": trip.route_id,
                        "DirectionRef": trip.direction_id,
                        "FramedVehicleJourneyRef": {
                            "DataFrameRef": str(trip_date),
                            "DatedVehicleJourneyRef": trip_id
                        },
                        "PublishedLineName": route.route_short_name,
                        "OperatorRef": route.agency_id,
                        "DestinationRef": destination_code,
                        "OriginAimedDepartureTime": str(departed),
                        "VehicleLocation": {
                            "Longitude": 34.746543884277344,
                            "Latitude": 32.012107849121094
                        },
                        "VehicleRef": "###",
                        "MonitoredCall": {
                            "StopPointRef": stop,
                            "ExpectedArrivalTime": str(eta)
                        }
                    }
                })
        return web.json_response(response)


def main():
    arguments = docopt(__doc__)
    configfile = arguments['--config'] or "config.ini"
    port_str = arguments['--port']
    port = int(port_str) if port_str else 8081
    config = configparser.ConfigParser()
    config.read(configfile)
    config_dict = {s: dict(config.items(s)) for s in config.sections()}
    server = MockSIRIServer(config_dict)
    server.run(port)


if __name__ == "__main__":
    main()
