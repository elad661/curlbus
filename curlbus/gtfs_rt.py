"gtfs_rt.py: GTFS-RT Client for Tel Aviv's municipal weekend buses"
# Copyright (C) 2020 Elad Alfassa <elad@fedoraproject.org>
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

import asyncio
from datetime import datetime
from typing import List, Dict

import aiohttp
from aiocache import SimpleMemoryCache
from dateutil import tz
from google.transit.gtfs_realtime_pb2 import FeedMessage
import google.transit.gtfs_realtime_pb2 as rt

from .siri import SIRIResponse, SIRIStopVisit
from .gtfs.utils import get_routes_for_trips
from .gtfs.model import TAShabbatStop

TELAVIV_FEED_URL = 'https://api.busnear.by/external/gtfsrt/export'
TELAVIV_AUTH_KEY = 'tlv_848e1b42-c0c2'
TELAVIV_GTFS_ID_PREFIX = 'ta'
ISRAEL_TZ = tz.gettz('Asia/Jerusalem')

MINUTES = 60*60


class GtfsRtVisit(SIRIStopVisit):
    """ A `SIRIStopVisit` compatible object for represnting stop visits from GTFS-RT """
    def __init__(self, feed, stop_time_update, stop_code: str, trip_info: Dict[str, str], vehicle: dict):
        self.producer = 'GTFS-RT'

        self.timestamp = datetime.fromtimestamp(feed.header.timestamp, tz=ISRAEL_TZ)
        """  GTFS-RT feed timestamp """

        self.stop_code = stop_code
        """ The stop code for this stop visit """

        self.line_id = trip_info['route_id']
        """ Matches the route_id from the GTFS file """

        self.route_id = self.line_id
        """ line ref or line id is SIRI terminology, route_id is GTFS terminology. We support both. route_id is identical to line_id """

        self.direction_id = trip_info['direction_id']
        """ Direction code for this trip """

        self.line_name = trip_info['route_short_name']
        """ Line number/name """

        self.operator_id = trip_info['agency_id']
        """ oprator / agency ID of this route. """

        self.destination_id = trip_info['destination_code']
        """ The stop code of this trip's destination """

        self.vehicle_ref = vehicle['id']
        """ Vehicle ID from the GTFS-RT feed """

        self.eta = datetime.fromtimestamp(stop_time_update.arrival.time, tz=ISRAEL_TZ)
        """ Estimated time for arrival """

        # Convert SIRI - style trip ID to GTFS style, to make it useful

        self.trip_id = trip_info['trip_id']
        """ Trip ID, unique identifier of this trip per day """

        self.status = None
        """ not supported """

        self.departed = None
        """ The aimed departure time from the origin station. In some edge case, this is slightly different then the GTFS schedule """

        self.location = vehicle['position']

        self.static_info = None
        """ Placeholder for plugging static GTFS schedule info """

    def __repr__(self):
        return "GtfsRtVisit <line: {0}, eta: {1}>".format(self.line_id, self.eta)


class GtfsRtResponse(SIRIResponse):
    """ A `SIRIResponse` compatible object for represnting stop visits from GTFS-RT """
    def __init__(self, feed: FeedMessage, requested_stop_codes: List[str], trips_data: Dict[str, Dict[str, str]], stops_mapping: Dict[str, str], timestamp):
        self.errors = []
        self.visits: Dict[str, List[SIRIStopVisit]] = {code: [] for code in requested_stop_codes}
        self.timestamp = timestamp
        vehicle_positions: Dict[str, Dict[str, str]] = {}

        for entity in feed.entity:
            if entity.HasField('vehicle'):
                vehicle_positions[entity.vehicle.vehicle.id] = {
                    "lat": entity.vehicle.position.latitude,
                    "lon": entity.vehicle.position.longitude
                }

        for entity in feed.entity:
            if not entity.HasField('trip_update'):
                continue  # useless entity
            trip_update = entity.trip_update
            trip_id = f'{TELAVIV_GTFS_ID_PREFIX}{trip_update.trip.trip_id}'
            for stop_time_update in trip_update.stop_time_update:
                if stop_time_update.stop_id not in stops_mapping:
                    continue
                stop_code = stops_mapping[stop_time_update.stop_id]
                if stop_code in requested_stop_codes:
                    trip_info = None
                    if trip_id in trips_data:
                        trip_info = trips_data[trip_id]
                        trip_info['trip_id'] = trip_id
                    else:
                        print('missing info for trip', trip_id)
                    vehicle = { 'id': trip_update.vehicle.id,
                                'position': vehicle_positions[trip_update.vehicle.id]}
                    self.visits[stop_code].append(GtfsRtVisit(feed, stop_time_update, stop_code, trip_info, vehicle))



class GtfsRtClient(object):
    """ A GTFS-RT client for Tel Aviv's municipal weekend buses """
    def __init__(self, db, feed_url: str = TELAVIV_FEED_URL):
        self.feed_url: str = feed_url
        self.db = db
        self.cache = SimpleMemoryCache()

    async def get_feed(self):
        feed = await self.cache.get('feed')
        if feed is None:
            async with aiohttp.ClientSession() as session: # type: aiohttp.ClientSession
                async with session.get(self.feed_url, headers={'Authorization': TELAVIV_AUTH_KEY}) as response: # type: aiohttp.ClientResponse
                    contents = await response.read()
                    feed: FeedMessage = FeedMessage()
                    feed.ParseFromString(contents)
                    await self.cache.set('feed', feed, ttl=30)
        return feed

    async def request(self, stop_codes: List[str])  -> GtfsRtResponse:
        """ Get arrivals filtered for specific stops in a SIRI compatible format """
        # this is in a SIRI format because curlbus was built for it,
        # it's easier to reuse existing class + structure than to refactor all of curlbus
        feed = await self.get_feed()

        # collect trip IDs and stop IDs for the DB query
        trips_for_query = set()
        stops_for_query = set()
        trips_data: Dict[str, Dict[str, str]] = {}
        stops_mapping: Dict[str, str] = {}
        timestamp = feed.header.timestamp

        for entity in feed.entity:
            if not entity.HasField('trip_update'):
                continue  # useless entity
            trip_id = f'{TELAVIV_GTFS_ID_PREFIX}{entity.trip_update.trip.trip_id}'
            trip_info = await self.cache.get(f'trip:{trip_id}')
            if trip_info is None:
                trips_for_query.add(trip_id)
            else:
                trips_data[trip_id] = trip_info

            for stop_time_update in entity.trip_update.stop_time_update:
                stop_code = await self.cache.get(f'stop:{stop_time_update.stop_id}')
                if stop_code is None:
                    stops_for_query.add(stop_time_update.stop_id)
                else:
                    stops_mapping[stop_time_update.stop_id] = stop_code

        routes_for_trips = await get_routes_for_trips(self.db, list(trips_for_query))
        for trip_id, trip in routes_for_trips.items():
            trips_data[trip_id] = trip
            await self.cache.set(f'trip:{trip_id}', trip, ttl = 30 * MINUTES)

        stops_mapping_query = await TAShabbatStop.get_mapped_stop_codes(self.db, stops_for_query)
        for stop_id, stop_code in stops_mapping_query.items():
            stops_mapping[stop_id] = stop_code
            await self.cache.set(f'stop:{stop_id}', stop_code, ttl = 30 * MINUTES)

        # cool, we know about the routes/stops. Now to create "visits" and assign them to stops
        return GtfsRtResponse(feed, stop_codes, trips_data, stops_mapping, timestamp)
