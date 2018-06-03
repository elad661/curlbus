""" gtfs database model """
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

# Specs:
# https://developers.google.com/transit/gtfs/reference/
# https://developers.google.com/transit/gtfs/reference/gtfs-extensions
# https://www.gov.il/blobFolder/generalpage/gtfs_general_transit_feed_specifications/he/%D7%A1%D7%98%20%D7%A7%D7%91%D7%A6%D7%99%D7%9D%20-%20GTFS%20-%20%D7%94%D7%A1%D7%91%D7%A8%20%D7%9C%D7%9E%D7%A4%D7%AA%D7%97%D7%99%D7%9D.pdf

# This file intentionally only supports a small subset of GTFS needed for curlbus
import re
from gino import Gino
STOP_DESC_REGEX = re.compile("(?:רחוב:)(?P<street>.*)(?:עיר:)(?P<city>.*)(?:רציף:)(?P<platform>.*)(?:קומה:)(?P<floor>.*)")

db = Gino()


class Agency(db.Model):
    """  https://developers.google.com/transit/gtfs/reference/#agencytxt """
    __tablename__ = 'agency'
    __gtfs_singular__ = 'agency'

    agency_id = db.Column(db.Unicode, primary_key=True)
    agency_name = db.Column(db.Unicode)
    agency_url = db.Column(db.Unicode)
    agency_timezone = db.Column(db.Unicode)
    agency_lang = db.Column(db.Unicode)
    agency_phone = db.Column(db.Unicode)
    agency_fare_url = db.Column(db.Unicode)


class Stop(db.Model):
    """  https://developers.google.com/transit/gtfs/reference/#stopstxt """
    __tablename__ = 'stops'
    __gtfs_singular__ = 'stop'

    stop_id = db.Column(db.Unicode, primary_key=True)
    stop_code = db.Column(db.Unicode, index=True)
    stop_name = db.Column(db.Unicode)
    stop_desc = db.Column(db.Unicode)
    stop_lat = db.Column(db.Unicode)
    stop_lon = db.Column(db.Unicode)
    location_type = db.Column(db.Boolean)
    parent_station = db.Column(db.Unicode)
    zone_id = db.Column(db.Unicode)

    def __init__(self, *args, **kwargs):
        self._address = None
        self.translated_name = None
        super().__init__(*args, **kwargs)

    @property
    def address(self):
        """ MoT uses the 'stop_desc' in GTFS to encode the stop address.
        returns a dictionary of strings in the following form:
        {"street": "street name and house number if exists",
         "city": "city name in the original Hebrew, if exists",
         "platform": "platform number, if exists",
         "floor": "floor number, if exists"}
         or an empty dictionary if there's no data available. """
        # Cache the parsing and allow users of the class to modify the address
        if self._address is not None:
            return self._address

        match = STOP_DESC_REGEX.match(self.stop_desc.strip())
        if match is not None:
            self._address = {k: v.strip() for k, v in match.groupdict().items()}
        else:
            self._address = {}
        return self._address

    @address.setter
    def address(self, value):
        self._address = value


class Route(db.Model):
    """  https://developers.google.com/transit/gtfs/reference/#routestxt """
    __tablename__ = 'routes'
    __gtfs_singular__ = 'route'

    route_id = db.Column(db.Unicode, primary_key=True)
    agency_id = db.Column(db.Unicode)
    route_short_name = db.Column(db.Unicode, index=True)
    route_long_name = db.Column(db.Unicode)
    route_desc = db.Column(db.Unicode)
    route_type = db.Column(db.Integer)
    route_color = db.Column(db.Unicode)


class Trip(db.Model):
    """  https://developers.google.com/transit/gtfs/reference/#tripsstxt """
    __tablename__ = 'trips'
    __gtfs_singular__ = 'trip'

    route_id = db.Column(db.Unicode, index=True)
    service_id = db.Column(db.Unicode)
    trip_id = db.Column(db.Unicode, primary_key=True)
    trip_headsign = db.Column(db.Unicode)
    direction_id = db.Column(db.Integer)
    shape_id = db.Column(db.Unicode)

    async def get_stop_times(self, connection):
        """ Get all StopTime objects associated with this trip """
        stoptimes = await connection.all(StopTime.query.where(StopTime.trip_id == self.trip_id))
        return sorted(stoptimes, key=lambda s: s.stop_sequence)

    async def get_last_stop_code(self, connection):
        """ Return the destination stop_code for this trip """
        return await connection.scalar(f"""SELECT stop_code FROM stoptimes AS st
                                           JOIN stops AS s ON s.stop_id=st.stop_id
                                           WHERE trip_id='{self.trip_id}'
                                           ORDER BY st.stop_sequence DESC LIMIT 1;""")


class StopTime(db.Model):
    """  https://developers.google.com/transit/gtfs/reference/#tripsstxt """
    __tablename__ = 'stoptimes'

    trip_id = db.Column(db.Unicode, primary_key=True)
    arrival_time = db.Column(db.Unicode, primary_key=True)
    departure_time = db.Column(db.Unicode)
    stop_id = db.Column(db.Unicode, primary_key=True)
    stop_sequence = db.Column(db.Integer, primary_key=True)
    pickup_type = db.Column(db.Boolean)
    drop_off_type = db.Column(db.Boolean)
    shape_dist_traveled = db.Column(db.Unicode)


class Translation(db.Model):
    """ GTFS Translations - a Google extension to the GTFS spec

    https://developers.google.com/transit/gtfs/reference/gtfs-extensions#translations
    """
    __tablename__ = 'translations'

    trans_id = db.Column(db.Unicode, primary_key=True, index=True)
    """ Translation ID - the source string """
    lang = db.Column(db.Unicode, primary_key=True)
    """ Translation language code """
    translation = db.Column(db.Unicode)
    """ Translated string """

    def __str__(self):
        return self.translation

    @staticmethod
    async def get(connection, source, lang=None) -> dict:
        """ Get a translation for `source` (to `lang`). Returns the orignal string when no translation is present """
        # Strings in the GTFS feed *somtetimes* use '' instead of ",
        # translations correctly use ", so use .replace
        source2 = source.replace("''", '"')
        try:
            query = Translation.query.where(Translation.trans_id.in_([source,  source2]))
            if lang is not None:
                return await connection.first(query.where(Translation.lang == lang))
            else:
                ret = {t.lang: t.translation for t in await connection.all(query)}
                if len(ret) == 0:
                    return {"HE": source2}
                return ret
        except AttributeError:
            return {"HE": source2}

    def __repr__(self):
        return '<Translation of %s (to %s): %s>' % (self.trans_id, self.lang,
                                                    self.translation)


class City(db.Model):
    """ mapping between city/settelment/village name in Hebrew to its official English name.
    This is not a GTFS type, but it's related"""
    __tablename__ = 'cities'

    name = db.Column(db.Unicode, primary_key=True)
    """ Original city/town/village name in Hebrew """

    english_name = db.Column(db.Unicode)
    """ The official transliterated name """


tables = (Agency, Route, Trip, Stop, StopTime, Translation, City)
