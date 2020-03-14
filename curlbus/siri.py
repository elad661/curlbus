"siri.py: Basic implementation of a SIRI-SM client, with Israel Ministry of Transportation quirks"
# Copyright (C) 2016, 2018 Elad Alfassa <elad@fedoraproject.org>
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

from typing import Dict
import aiohttp
import dateutil.parser
import dateutil.tz
import json
import time
import xmltodict
from aiocache import SimpleMemoryCache
from aiocache.base import BaseCache
from itertools import zip_longest
from datetime import datetime
from typing import List
from textwrap import dedent
GROUP_SIZE = 25

_SIRI_REQUEST_TEMPLATE = dedent('''
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/" xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/" xmlns:acsb="http://www.ifopt.org.uk/acsb" xmlns:datex2="http://datex2.eu/schema/1_0/1_0" xmlns:ifopt="http://www.ifopt.org.uk/ifopt" xmlns:siri="http://www.siri.org.uk/siri" xmlns:siriWS="http://new.webservice.namespace" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="./siri">
    <SOAP-ENV:Header />
    <SOAP-ENV:Body>
        <siriWS:GetStopMonitoringService>
            <Request xsi:type="siri:ServiceRequestStructure">
                <siri:RequestTimestamp>{timestamp}</siri:RequestTimestamp>
                <siri:RequestorRef xsi:type="siri:ParticipantRefStructure">{user_id}</siri:RequestorRef>
                <siri:MessageIdentifier xsi:type="siri:MessageQualifierStructure">{user_id}:{numeric_timstamp}</siri:MessageIdentifier>
                {body}
            </Request>
        </siriWS:GetStopMonitoringService>
    </SOAP-ENV:Body>
</SOAP-ENV:Envelope>''').strip().replace("\n", "")

_SIRI_REQUEST_BODY = dedent('''
<siri:StopMonitoringRequest version="IL2.71" xsi:type="siri:StopMonitoringRequestStructure">
    <siri:RequestTimestamp>{timestamp}</siri:RequestTimestamp>
    <siri:MessageIdentifier xsi:type="siri:MessageQualifierStructure">{i}</siri:MessageIdentifier>
    <siri:PreviewInterval>PT30M</siri:PreviewInterval>
    <siri:MonitoringRef xsi:type="siri:MonitoringRefStructure">{stop_code}</siri:MonitoringRef>
    <siri:MaximumStopVisits>{max_visits}</siri:MaximumStopVisits>
</siri:StopMonitoringRequest>
''').strip().replace("\n", "")

URL = None


def _listify(obj):
    """ Wrap the object in a list if it's not a list """
    if isinstance(obj, list):
        return obj
    else:
        return [obj]


def _grouper(iterable, n, fillvalue=None):
    "Collect data into fixed-length chunks or blocks"
    # From itertools recipies: https://docs.python.org/3/library/itertools.html
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx"
    args = [iter(iterable)] * n
    return zip_longest(*args, fillvalue=fillvalue)


class SIRIResponse(object):
    def __init__(self, raw_response, stop_codes, verbose=False):
        xmldict = xmltodict.parse(raw_response)
        if verbose:
            print(json.dumps(xmldict, indent=2))

        self.visits: Dict[str, SIRIStopVisit] = {}
        """ Stop visits. A dictionary in the form of {stop_code: SIRIStopVisit} """
        self.errors = []
        """ Errors, if any"""

        for stop_code in stop_codes:
            self.visits[str(stop_code)] = []

        # ew.
        try:
            response = xmldict['S:Envelope']['S:Body']['ns7:GetStopMonitoringServiceResponse']
        except KeyError:
            print(json.dumps(xmldict, indent=2))
            print(self.raw_response)
            raise

        # find SIRI namespace
        siri_namespace = "ns3"  # default to something that works most of the time
        for key in response.keys():
          if key.startswith('@xmlns:') and response[key] == 'http://www.siri.org.uk/siri':
            siri_namespace = key.replace('@xmlns:', '') + ':'
        answer = response['Answer']

        self.timestamp = answer[siri_namespace + 'ResponseTimestamp']
        """ Timestamp of the response from the server """

        for delivery in _listify(answer[siri_namespace + 'StopMonitoringDelivery']):
            if delivery[siri_namespace + 'Status'] != "true":
                # TODO actually log errors!
                self.errors.append(delivery[siri_namespace + 'ErrorCondition'][siri_namespace + 'Description'])
            else:
                for visit in _listify(delivery[siri_namespace + 'MonitoredStopVisit']):
                    stop_visit = SIRIStopVisit(visit, siri_namespace)
                    self.visits[stop_visit.stop_code].append(stop_visit)

    def to_dict(self) -> dict:
        """ Serialize to a dict format which is more readable than the original source """
        visits = {k: [visit.to_dict() for visit in v] for k, v in self.visits.items()}
        return {"errors": self.errors if len(self.errors) > 0 else None,
                "timestamp": str(self.timestamp),
                "visits": visits}

    def append(self, other):
        """ Append visits and error from a different response into this response """
        if not isinstance(other, SIRIResponse):
            raise TypeError("Expected a SIRIResponse object")
        self.errors += other.errors
        for stop_code, visits in other.visits.items():
            if stop_code in self.visits:
                raise ValueError("Merging requests for the same stop is not supported")
            self.visits[stop_code] = visits


class CachedSIRIResponse(SIRIResponse):
    """ a SIRI response that was taken entirely from the cache """
    def __init__(self, visits):
        self.errors = []
        self.visits = visits
        self.timestamp = None

        # find a timestamp in one of the visits:
        for stop, visits in visits.items():
            if len(visits) > 0:
                self.timestamp = visits[0].timestamp
                break


class SIRIClient(object):
    """ SIRI-SM client using aiohttp """
    def __init__(self, url: str, user_id: str, cache: BaseCache = None,
                 cache_ttl: int = 30, verbose: bool = False):
        self.url = url
        self.user_id = user_id
        self.verbose = verbose
        self.cache_ttl = cache_ttl
        self._cache = cache if cache is not None else SimpleMemoryCache()
        self._connector = None

    def _prepare_request_body(self, stop_codes: List[str], max_visits: int) -> str:
        body = ""
        timestamp = datetime.now(dateutil.tz.tzlocal()).isoformat()
        numeric_timstamp = time.time()
        for i, stop in enumerate(stop_codes):
            body += _SIRI_REQUEST_BODY.format(stop_code=stop, i=i,
                                              max_visits=max_visits,
                                              timestamp=timestamp)
        return _SIRI_REQUEST_TEMPLATE.format(timestamp=timestamp,
                                             user_id=self.user_id,
                                             numeric_timstamp=numeric_timstamp,
                                             body=body)

    async def request(self, stop_codes: List[str], max_visits: int = 50) -> SIRIResponse:
        """ Request real time information for stops in `stop_codes` """
        # Look for stop_codes in cache
        to_request = []
        from_cache = []
        for stop in stop_codes:
            cached = await self._cache.get(f"realtime:{stop}")
            if cached is None:
                to_request.append(stop)
            else:
                from_cache.append((stop, cached))

        headers = {'content-type': 'text/xml; charset=utf-8',
                   'accept': 'text/xml,multipart/related'}
        async with aiohttp.ClientSession() as session:
            # Maximum 10 stops per request is defined by MoT for version 2.8.
            # We're still on 2.71, but it's better to be future proof.
            ret = None
            for group in _grouper(to_request, GROUP_SIZE):
                group = list(filter(None, group))
                body = self._prepare_request_body(group, max_visits)
                async with session.post(self.url, data=body, headers=headers) as raw_response:
                    text = await raw_response.text()
                    response = SIRIResponse(text, group, self.verbose)
                    if ret:
                        # Merge SIRIResponse objects if we have more than
                        # one group
                        if response.errors:
                            print(response.errors)
                        ret.append(response)
                    else:
                        ret = response
        if ret is not None:
            # cache new visits
            for stop_code, visits in ret.visits.items():
                await self._cache.set(f"realtime:{stop_code}", visits, ttl=self.cache_ttl)
            # add cached visits to the response
            for stop_code, visits in from_cache:
                ret.visits[stop_code] = visits
        else:
            ret = CachedSIRIResponse(dict(from_cache))
        return ret


class SIRIStopVisit(object):
    def __init__(self, src, siri_namespace):
        self._src = src
        self.timestamp = dateutil.parser.parse(src[siri_namespace + 'RecordedAtTime'])
        """  RecordedAtTime from the SIRI response, ie. the timestamp in which the prediction was made """

        self.stop_code = src[siri_namespace + 'MonitoringRef']
        """ The stop code for this stop visit """

        journey = src[siri_namespace + 'MonitoredVehicleJourney']
        self.line_id = journey[siri_namespace + 'LineRef']
        """ Matches the route_id from the GTFS file """

        self.route_id = self.line_id
        """ line ref or line id is SIRI terminology, route_id is GTFS terminology. We support both. route_id is identical to line_id """

        self.direction_id = journey[siri_namespace + 'DirectionRef']
        """ Direction code for this trip """

        self.line_name = journey[siri_namespace + 'PublishedLineName']
        """ PublishedLineName. The meaning of this number is unclear for Israel Railways data """

        self.operator_id = journey[siri_namespace + 'OperatorRef']
        """ oprator / agency ID of this route. """

        self.destination_id = journey[siri_namespace + 'DestinationRef']
        """ The stop code of this trip's destination """

        try:
            vehicle_ref = journey[siri_namespace + 'VehicleRef']
        except KeyError:
            vehicle_ref = None
        self.vehicle_ref = vehicle_ref
        """ In case of Israel Railways, this is the train number and is guranteed to be unique per day
        For buses, this is either the license plate number, or the internal vehicle number """

        # Assuming singular MonitoredCall object.
        # we need to change that assumption if we use the "onward calls" feature of version 2.8, which was not released yet
        call = journey[siri_namespace + 'MonitoredCall']
        self.eta = dateutil.parser.parse(call[siri_namespace + 'ExpectedArrivalTime'])
        """ Estimated time for arrival """

        # Convert SIRI - style trip ID to GTFS style, to make it useful

        if siri_namespace + 'FramedVehicleJourneyRef' in journey:
            journey_ref = journey[siri_namespace + 'FramedVehicleJourneyRef']

            tripdate = dateutil.parser.parse(journey_ref[siri_namespace + 'DataFrameRef'])
            tripdate = tripdate.strftime('%d%m%y')

            trip_id_part = journey_ref[siri_namespace + 'DatedVehicleJourneyRef']

            trip_id = f"{trip_id_part}_{tripdate}"
        else:
            trip_id = None
        self.trip_id = trip_id
        """ Trip ID, unique identifier of this trip per day """

        try:
            status = call[siri_namespace + 'ArrivalStatus']
        except KeyError:
            status = None
        self.status = status
        """ Can be None, or a string: OnTime, early, delayed, cancelled, arrived, noReport. Only relevant for Israel Railways? """

        self.departed = None
        """ The aimed departure time from the origin station. In some edge case, this is slightly different then the GTFS schedule """

        if siri_namespace + 'AimedDepartureTime' in call:
            self.departed = dateutil.parser.parse(call[siri_namespace + 'AimedDepartureTime'])
        elif siri_namespace + 'OriginAimedDepartureTime' in journey:
            self.departed = dateutil.parser.parse(journey[siri_namespace + 'OriginAimedDepartureTime'])
        else:
            self.departed = None

        if siri_namespace + "VehicleLocation" in journey:
            self.location = {'lat': journey[siri_namespace + "VehicleLocation"][siri_namespace + "Latitude"],
                             'lon': journey[siri_namespace + "VehicleLocation"][siri_namespace + "Longitude"]}
        else:
            self.location = None

        self.static_info = None
        """ Placeholder for plugging static GTFS schedule info """

    def __repr__(self):
        return "SIRIStopVisit <line: {0}, eta: {1}>".format(self.line_id, self.eta)

    def to_dict(self) -> dict:
        ret = {}
        for key, value in self.__dict__.items():
            if key.startswith("_"):
                continue
            if isinstance(value, (int, str, type(None), dict)):
                ret[key] = value
            elif callable(getattr(value, "to_dict", None)):
                ret[key] = value.to_dict()
            else:
                ret[key] = str(value)
        return ret
