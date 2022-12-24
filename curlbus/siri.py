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

from typing import Dict, List
import aiohttp
import dateutil.parser
import dateutil.tz
import json
import time
from aiocache import SimpleMemoryCache
from aiocache.base import BaseCache
from itertools import zip_longest
GROUP_SIZE = 120

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
    def __init__(self, json_response: Dict, stop_codes: List[str], verbose=False):
        if verbose:
            print(json.dumps(json_response, indent=2))

        self.visits: Dict[str, List[SIRIStopVisit]] = {}
        """ Stop visits. A dictionary in the form of {stop_code: SIRIStopVisit} """
        self.errors: List[str] = []
        """ Errors, if any"""

        for stop_code in stop_codes:
            self.visits[str(stop_code)] = []

        # ew.
        try:
            response = json_response['Siri']['ServiceDelivery']
        except KeyError:
            print(json.dumps(json_response, indent=2))
            raise

        self.timestamp = response['ResponseTimestamp']
        """ Timestamp of the response from the server """

        if 'StopMonitoringDelivery' in response:
            for delivery in _listify(response['StopMonitoringDelivery']):
                if delivery['Status'] != "true":
                    # TODO actually log errors!
                    self.errors.append(delivery['ErrorCondition']['Description'])
                elif 'MonitoredStopVisit' in delivery:
                    for visit in _listify(delivery['MonitoredStopVisit']):
                        stop_visit = SIRIStopVisit(visit)
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
                for visit in visits:
                    if not any(my_visit == visit for my_visit in self.visits[stop_code]):
                        # a new visit! let's apped it
                        self.visits[stop_code].append(visit)
            else:
                self.visits[stop_code] = visits


class CachedSIRIResponse(SIRIResponse):
    """ a SIRI response that was taken entirely from the cache """
    def __init__(self, visits):
        self.errors = []
        self.visits: Dict[str, List[SIRIStopVisit]] = visits
        self.timestamp = None

        # find a timestamp in one of the stops in this cache entry:
        for stop_visits in visits.values():
            if len(stop_visits) > 0:
                self.timestamp = stop_visits[0].timestamp
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

        headers = {'Accept': 'application/json',
                   'Accpet-Encoding': 'gzip,deflate'}
        async with aiohttp.ClientSession() as session:
            ret = None
            for group in _grouper(to_request, GROUP_SIZE):
                group = list(filter(None, group))
                params = {
                    "Key": self.user_id,
                    "MonitoringRef": ','.join(group),
                }
                async with session.get(self.url, params=params, headers=headers) as raw_response:
                    try:
                        json_response = await raw_response.json(encoding="utf-8")
                    except UnicodeDecodeError:
                        json_response = await raw_response.json()
                    except aiohttp.ContentTypeError as e:
                        print('Content type error', e)
                        print(await raw_response.text())
                        raise e

                    response = SIRIResponse(json_response, group, self.verbose)
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
    def __init__(self, src):
        self._src = src
        self.producer = 'SIRI'

        self.timestamp = dateutil.parser.parse(src['RecordedAtTime'])
        """  RecordedAtTime from the SIRI response, ie. the timestamp in which the prediction was made """

        self.stop_code = src['MonitoringRef']
        """ The stop code for this stop visit """

        journey = src['MonitoredVehicleJourney']
        self.line_id = journey['LineRef']
        """ Matches the route_id from the GTFS file """

        self.route_id = self.line_id
        """ line ref or line id is SIRI terminology, route_id is GTFS terminology. We support both. route_id is identical to line_id """

        self.direction_id = journey['DirectionRef']
        """ Direction code for this trip """

        self.line_name = journey['PublishedLineName']
        """ PublishedLineName. The meaning of this number is unclear for Israel Railways data """

        self.operator_id = journey['OperatorRef']
        """ oprator / agency ID of this route. """

        self.destination_id = journey['DestinationRef']
        """ The stop code of this trip's destination """

        try:
            vehicle_ref = journey['VehicleRef']
        except KeyError:
            vehicle_ref = None
        self.vehicle_ref = vehicle_ref
        """ In case of Israel Railways, this is the train number and is guranteed to be unique per day
        For buses, this is either the license plate number, or the internal vehicle number """

        # Assuming singular MonitoredCall object.
        # need to change that assumption if the "onward calls" feature of version 2.8 will ever be used
        call = journey['MonitoredCall']
        self.eta = dateutil.parser.parse(call['ExpectedArrivalTime'])
        """ Estimated time for arrival """

        # Convert SIRI - style trip ID to GTFS style, to make it useful

        if 'FramedVehicleJourneyRef' in journey:
            journey_ref = journey['FramedVehicleJourneyRef']

            tripdate = dateutil.parser.parse(journey_ref['DataFrameRef'])
            tripdate = tripdate.strftime('%d%m%y')

            trip_id_part = journey_ref['DatedVehicleJourneyRef']

            trip_id = f"{trip_id_part}_{tripdate}"
        else:
            trip_id = None
        self.trip_id = trip_id
        """ Trip ID, unique identifier of this trip per day """

        try:
            status = call['ArrivalStatus']
        except KeyError:
            status = None
        self.status = status
        """ Can be None, or a string: OnTime, early, delayed, cancelled, arrived, noReport. Only relevant for Israel Railways? """

        self.departed = None
        """ The aimed departure time from the origin station. In some edge case, this is slightly different then the GTFS schedule """

        if 'AimedDepartureTime' in call:
            self.departed = dateutil.parser.parse(call['AimedDepartureTime'])
        elif 'OriginAimedDepartureTime' in journey:
            self.departed = dateutil.parser.parse(journey['OriginAimedDepartureTime'])
        else:
            self.departed = None

        if "VehicleLocation" in journey:
            self.location = {'lat': journey["VehicleLocation"]["Latitude"],
                             'lon': journey["VehicleLocation"]["Longitude"]}
        else:
            self.location = None

        self.static_info = None
        """ Placeholder for plugging static GTFS schedule info """

    def __repr__(self):
        return "SIRIStopVisit <line: {0}, eta: {1}>".format(self.line_id, self.eta)

    def __eq__(self, other):
        return (self.producer == other.producer
                and self.stop_code == other.stop_code
                and self.timestamp == other.timestamp
                and self.eta == other.eta
                and self.route_id == other.route_id
                and self.vehicle_ref == other.vehicle_ref
                and self.direction_id == other.direction_id)

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
