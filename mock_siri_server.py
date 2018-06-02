#!/usr/bin/env python3
# mock_siri_server.py - a fake SIRI-SM server for testing curlbus
#
# Copyright 2018 Elad Alfassa <elad@fedoraproject.org>
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

SIRI_RESPONSE_BODY = """<?xml version="1.0" ?>
<S:Envelope xmlns:S="http://schemas.xmlsoap.org/soap/envelope/">
<S:Body>
<ns7:GetStopMonitoringServiceResponse xmlns:ns3="http://www.siri.org.uk/siri" xmlns:ns4="http://www.ifopt.org.uk/acsb" xmlns:ns5="http://www.ifopt.org.uk/ifopt" xmlns:ns6="http://datex2.eu/schema/1_0/1_0" xmlns:ns7="http://new.webservice.namespace">
<Answer>
<ns3:ResponseTimestamp>{timestamp}</ns3:ResponseTimestamp>
<ns3:ProducerRef>Mock Siri Server</ns3:ProducerRef>
<ns3:ResponseMessageIdentifier>76203</ns3:ResponseMessageIdentifier>
<ns3:RequestMessageRef>[REDACTED]</ns3:RequestMessageRef>
<ns3:Status>true</ns3:Status>
<ns3:StopMonitoringDelivery version="IL2.71">
<ns3:ResponseTimestamp>{timestamp}</ns3:ResponseTimestamp>
<ns3:Status>true</ns3:Status>
{body}
</ns3:StopMonitoringDelivery>
</Answer>
</ns7:GetStopMonitoringServiceResponse>
</S:Body>
</S:Envelope>
"""

STOPVISIT_TEMPLATE = """
<ns3:MonitoredStopVisit>
<ns3:RecordedAtTime>{timestamp}</ns3:RecordedAtTime>
<ns3:ItemIdentifier>{i}</ns3:ItemIdentifier>
<ns3:MonitoringRef>{stop_code}</ns3:MonitoringRef>
<ns3:MonitoredVehicleJourney>
<ns3:LineRef>{route_id}</ns3:LineRef>
<ns3:DirectionRef>{direction_id}</ns3:DirectionRef>
<ns3:FramedVehicleJourneyRef>
<ns3:DataFrameRef>{trip_id_date}</ns3:DataFrameRef>
<ns3:DatedVehicleJourneyRef>{trip_id}</ns3:DatedVehicleJourneyRef>
</ns3:FramedVehicleJourneyRef>
<ns3:PublishedLineName>{route_short_name}</ns3:PublishedLineName>
<ns3:OperatorRef>{operator_id}</ns3:OperatorRef>
<ns3:DestinationRef>{destination_code}</ns3:DestinationRef>
<ns3:OriginAimedDepartureTime>{departed}</ns3:OriginAimedDepartureTime>
<ns3:VehicleLocation>
<ns3:Longitude>34.746543884277344</ns3:Longitude>
<ns3:Latitude>32.012107849121094</ns3:Latitude>
</ns3:VehicleLocation>
<ns3:VehicleRef>###</ns3:VehicleRef>
<ns3:MonitoredCall>
<ns3:StopPointRef>{stop_code}</ns3:StopPointRef>
<ns3:ExpectedArrivalTime>{eta}</ns3:ExpectedArrivalTime>
</ns3:MonitoredCall>
</ns3:MonitoredVehicleJourney>
</ns3:MonitoredStopVisit>
"""

RANDOM_TRIPS_QUERY = """select distinct t.trip_id ,random() as r
                        from stoptimes as st
                        join trips as t on t.trip_id=st.trip_id
                        join stops as s on s.stop_id=st.stop_id
                        where s.stop_code='{code}' order by r limit 5;"""


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
        app.add_routes([web.post('/{tail:.*}', self.handle_request)])
        self._app = app

    def run(self, port):
        web.run_app(self._app, port=port)

    async def handle_request(self, request):
        db = request.app['db']
        data = await request.text()
        xmldict = xmltodict.parse(data)
        body = ""
        stops = parse_request(xmldict)
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
    port = int(arguments['--port']) or 8081
    config = configparser.ConfigParser()
    config.read(configfile)
    config_dict = {s: dict(config.items(s)) for s in config.sections()}
    server = MockSIRIServer(config_dict)
    server.run(port)


if __name__ == "__main__":
    main()
