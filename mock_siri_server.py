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

Start mock siri server
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
import xmltodict

SIRI_RESPONSE_BODY = """<?xml version="1.0" encoding="UTF-8"?>
<Siri>
<ServiceDelivery>
<ResponseTimestamp>{timestamp}</ResponseTimestamp>
<ProducerRef>Mock Siri Server</ProducerRef>
<ResponseMessageIdentifier>76203</ResponseMessageIdentifier>
<RequestMessageRef>[REDACTED]</RequestMessageRef>
<Status>true</Status>
<StopMonitoringDelivery version="2.8">
<ResponseTimestamp>{timestamp}</ResponseTimestamp>
<Status>true</Status>
{body}
</StopMonitoringDelivery>
</ServiceDelivery>
</Siri>
"""

STOPVISIT_TEMPLATE = """
<MonitoredStopVisit>
<RecordedAtTime>{timestamp}</RecordedAtTime>
<ItemIdentifier>{i}</ItemIdentifier>
<MonitoringRef>{stop_code}</MonitoringRef>
<MonitoredVehicleJourney>
<LineRef>{route_id}</LineRef>
<DirectionRef>{direction_id}</DirectionRef>
<FramedVehicleJourneyRef>
<DataFrameRef>{trip_id_date}</DataFrameRef>
<DatedVehicleJourneyRef>{trip_id}</DatedVehicleJourneyRef>
</FramedVehicleJourneyRef>
<PublishedLineName>{route_short_name}</PublishedLineName>
<OperatorRef>{operator_id}</OperatorRef>
<DestinationRef>{destination_code}</DestinationRef>
<OriginAimedDepartureTime>{departed}</OriginAimedDepartureTime>
<VehicleLocation>
<Longitude>34.746543884277344</Longitude>
<Latitude>32.012107849121094</Latitude>
</VehicleLocation>
<VehicleRef>###</VehicleRef>
<MonitoredCall>
<StopPointRef>{stop_code}</StopPointRef>
<ExpectedArrivalTime>{eta}</ExpectedArrivalTime>
</MonitoredCall>
</MonitoredVehicleJourney>
</MonitoredStopVisit>
"""

RANDOM_TRIPS_QUERY = """SELECT t.trip_id
                        FROM stoptimes as st
                        JOIN trips as t ON t.trip_id=st.trip_id
                        JOIN stops as s ON s.stop_id=st.stop_id
                        WHERE s.stop_code='{code}'
                        GROUP BY t.trip_id
                        ORDER BY random() LIMIT 5;"""


def parse_request(data: dict) -> list:
    """ quick and dirty parser for SIRI requests. Returns a list of stop codes, nothing else """
    ret = []
    requests = data['SOAP-ENV:Envelope']['SOAP-ENV:Body']['siriWS:GetStopMonitoringService']['Request']['siri:StopMonitoringRequest']
    if not isinstance(requests, list):
        requests = [requests]
    for request in requests:
        ret.append(int(request['siri:MonitoringRef']['#text']))
    return ret


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
        db = request.app['db']
        body = ""
        stops = request.query['MonitoringRef'].split(',')
        for stop in stops:
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

                # Create xml object in the most hackish way possible
                body += STOPVISIT_TEMPLATE.format(i=i,
                                                  trip_id=trip_id,
                                                  trip_id_date=trip_date,
                                                  departed=str(departed),
                                                  eta=str(eta),
                                                  route_id=trip.route_id,
                                                  timestamp=timestamp,
                                                  route_short_name=route.route_short_name,
                                                  stop_code=stop,
                                                  operator_id=route.agency_id,
                                                  direction_id=trip.direction_id,
                                                  destination_code=destination_code)

        resp = SIRI_RESPONSE_BODY.format(timestamp=now(), body=body)
        return web.Response(text=resp)


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
