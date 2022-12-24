""" HTTP server for curlbus """
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
from . import __version__
from aiohttp import web
from aiohttp import client_exceptions
from gino.ext.aiohttp import Gino
from .operators import operators, operators_by_id, operator_names, operator_logos
from .render import render_station_arrivals, render_operator_index, render_route_alternatives, render_route_map, render_station_list
from .siri import SIRIClient
from .gtfs.utils import (get_stop_info, get_routes, get_route_route,
                         get_arrival_gtfs_info, translate_route_name,
                         count_routes, get_rail_stations, get_nearby_stops)
from .gtfs import model as gtfs_model
from .gtfs_rt import GtfsRtClient
from .html import html_template, relative_linkify
from aiocache import SimpleMemoryCache
from datetime import datetime
import os.path
import ansi2html
# monkey-patch ansi2html to get a more modern HTML document structure and a footer
ansi2html.converter._html_template = html_template
ansi2html.converter.linkify = relative_linkify
CACHE_TTL = 30
ANSI_RESET = "\033[0m\033[39m\033[49m"


def parse_accept_header(request):
    """ Returns `json`, `html`, or `text` according to the accept header """
    # This doesn't care for priorities, it'll take the first guess
    accept = request.headers.getall('ACCEPT', [])
    for item in accept:
        for sub_item in item.lower().split(','):
            if "text/html" in sub_item:
                return 'html'
            if "application/json" in sub_item:
                return 'json'
            if "*/*" in sub_item:
                return 'text'
    # Default to text
    return 'text'


class CurlbusServer(object):
    def __init__(self, config):
        db = Gino(model_classes=tuple(gtfs_model.tables))
        app = web.Application(middlewares=[db])
        # I don't quite get why aiohttp says I shouldn't just use self.config
        # for this, but whatever
        app["config"] = config
        app["aiocache"] = SimpleMemoryCache()
        app["ansiconv"] = ansi2html.converter.Ansi2HTMLConverter(linkify=True,
                                                                 title="curlbus",
                                                                 font_size='16px')
        app['siriclient'] = SIRIClient(config["mot"]["url"],
                                       config["mot"]["user_id"])

        app['gtfs-rt-client'] = GtfsRtClient(db)

        db.init_app(app)
        app.router.add_static("/static/", os.path.join(os.path.dirname(__file__), '..', "static"))
        app.add_routes([web.get('/{prefix:0*}{stop_code:\d+(\+\d+)*}{tail:/*}', self.handle_station),
                        web.get('/operators{tail:/*}', self.handle_operator_index),
                        web.get('/nearby', self.handle_nearby),
                        web.get('/{operator:\w+}{tail:/*}', self.handle_operator),
                        web.get('/rail/stations{tail:/*}', self.handle_rail_stations),
                        web.get('/rail/map{tail:/*}', self.handle_rail_map),
                        web.get('/operators/{operator}/{route_number}{tail:/*}', self.handle_route),
                        web.get('/operators/{operator}/{route_number}/{alternative}{tail:/*}', self.handle_route),
                        web.get('/operators/{operator}{tail:/*}', self.handle_operator),
                        web.get('/{operator}/{route_number}{tail:/*}', self.handle_route),
                        web.get('/{operator}/{route_number}/{alternative}{tail:/*}', self.handle_route),
                        web.get('/{tail:/*}', self.handle_index)])
        self._app = app

    def run(self, appconfig):
        web.run_app(self._app, port=appconfig['port'], host=appconfig['host'])

    def ansi_or_html(self, accept, request, text):
        if accept == 'html':
            text = request.app['ansiconv'].convert(text)
            return web.Response(text=text, content_type="text/html")
        return web.Response(text=text)

    async def realtime_request(self, request, stop_codes):
        client: SIRIClient = request.app['siriclient']
        gtfs_rt_client: GtfsRtClient = request.app['gtfs-rt-client']
        today = datetime.now().isoweekday()
        response = None
        try:
            response = await client.request(stop_codes)
        except Exception as e:
            if today not in [5, 6]:
                raise e
            else:
                print('MOT SIRI Error')
                print(e)

        if today in [5, 6]:
            # municipal buses are weekend only, so only query them on the weekend
            gtfs_rt_response = await gtfs_rt_client.request(stop_codes)
            if response:
                response.append(gtfs_rt_response)
            else:
                return gtfs_rt_response

        return response


    async def handle_station(self, request):
        """ Get real-time arrivals for a specific station """
        db = request['connection']
        stop_codes = request.match_info["stop_code"].split('+')
        # TODO bunching to limit request rate?
        # TODO IP-based rate limit?
        # all these are because this is the interface of the user to the MoT
        # API and I do not want to get banned from the MoT API
        accept = parse_accept_header(request)

        if len(stop_codes) > 30:
            if accept == 'json':
                return web.json_response({"errors": ['Maximum 30 stops per request, please']}, status=400)
            else:
                return web.Response(text='Maximum 30 stops per request, please',
                                    status=400)

        stops = {}
        errors = []
        for stop_code in stop_codes:
            if stop_code in stops:
                errors.append(f"Duplicate stop code {stop_code}\n")
            else:
                # collect info for the stops not in cache
                stop_info = await get_stop_info(db, stop_code)
                if stop_info is None:
                    # errors are batched, instead of returning the first one
                    errors.append(f"Invalid stop code {stop_code}\n")
                stops[stop_code] = stop_info

        if errors:
            if accept == 'json':
                return web.json_response({"errors": errors})
            else:
                return web.Response(text='\n'.join(errors),
                                    status=404)

        try:
            realtime = await self.realtime_request(request, stop_codes)
        except client_exceptions.ClientConnectorError as e:
            return web.Response(text=f'Error connecting to MoT server, {type(e).__name__}: [Errno {e.os_error.errno}]\n', status=500)

        # filtering, if needed
        if 'filter' in request.query:
            line_names = set(request.query['filter'].split(','))
            for stop_code, visits in realtime.visits.items():
                filtered_visits = [visit for visit in visits if visit.line_name in line_names]
                realtime.visits[stop_code] = filtered_visits

        # add static GTFS info for each route
        for _, visits in realtime.visits.items():
            for arrival in visits:
                gtfsinfo = await get_arrival_gtfs_info(arrival, db)
                arrival.static_info = {"route": gtfsinfo}

        if accept == 'json':
            out = realtime.to_dict()
            if len(stop_codes) == 1:
                # backwards compatibility: stop_info as a single item
                out['stop_info'] = stop_info
            else:
                out['stops_info'] = {stop_code: stops[stop_code] for stop_code in stop_codes}
            return web.json_response(out)
        else:
            text = ""
            for stop_code in stop_codes:
                text += render_station_arrivals(stop_code, stops[stop_code], realtime)
            return self.ansi_or_html(accept, request, text)

    async def handle_operator_index(self, request):
        """ Get the index of all transit operators in the database """
        response = []
        db = request['connection']
        accept = parse_accept_header(request)
        for operator in await db.all(gtfs_model.Agency.query):
            if int(operator.agency_id) in operators_by_id:
                operator_json = {'id': operator.agency_id,
                                'website': operator.agency_url,
                                'name': { 'HE': operator.agency_name },
                                'url': f'/{operators_by_id[int(operator.agency_id)]}'}
                if int(operator.agency_id) in operator_names:
                    operator_json['name']['EN'] = operator_names[int(operator.agency_id)]
                else:
                    # no English translation, fall back to Hebrew name
                    operator_json['name']['EN'] = operator_json['name']['HE']
                response.append(operator_json)
        if accept == 'json':
            return web.json_response(response)
        else:
            text = render_operator_index(response)
            return self.ansi_or_html(accept, request, text)

    async def handle_route(self, request):
        """ Get a schematic map for a specific route """
        operator = request.match_info['operator'].lower().strip("/")
        db = request['connection']
        if operator not in operators:
            # Fail fast for invalid data
            return web.Response(text="Unknown operator, check /operators\n",
                                status=404)
        operator_id = operators[operator]
        route_number = request.match_info['route_number'].strip("/")
        try:
            alternative = request.match_info['alternative'].strip("/")
        except KeyError:
            alternative = None

        accept = parse_accept_header(request)

        routes = await get_routes(db, operator_id, route_number)
        if len(routes) == 1 or (alternative is not None and int(alternative) < len(routes)):
            # Render route map
            index = 0 if len(routes) == 1 else int(alternative)

            route, direction_id = routes[index]

            routemap = await get_route_route(db, route.route_id, direction_id)
            if routemap is None:
                text = "This route has no map! Strange..."
                return self.ansi_or_html(accept, request, text)

            # get realtime ETAs for each stop in this route
            stop_codes = [stop.stop_code for stop in routemap]
            realtime = await self.realtime_request(request, stop_codes)
            etas = {}
            for stop_code, visits in realtime.visits.items():
                for visit in visits:
                    if visit.route_id == route.route_id:
                        if stop_code in etas:
                            etas[stop_code].append(visit.eta)
                        else:
                            etas[stop_code] = [visit.eta]

            # Merge route map with etas:
            mergedmap = []
            for stop in routemap:
                mergedmap.append({"stop_code": stop.stop_code,
                                  "etas": etas.get(stop.stop_code, []),
                                  "address": stop.address,
                                  "name": stop.translated_name})

            route_name = await translate_route_name(db, route)
            route_info = {"operator_name": operator_names[operator_id],
                          "short_name": route.route_short_name,
                          "long_name": route_name}
            if accept == 'json':
                return web.json_response({"route_info": route_info,
                                          "map": mergedmap})
            else:
                text = render_route_map(route_info, mergedmap)
                return self.ansi_or_html(accept, request, text)
        elif len(routes) > 1 and not alternative:
            # Render route alternative selection screen
            alternatives = []
            for route, direction_id in routes:
                alternatives.append({"long_name": await translate_route_name(db, route),
                                     "short_name": route.route_short_name})
            if accept == 'json':
                return web.json_response({"route_alternatives": alternatives})
            else:
                text = render_route_alternatives(operator_id, alternatives)
                return self.ansi_or_html(accept, request, text)
        else:
            return web.Response(text="Unknown route!\n",
                                status=404)

    async def handle_operator(self, request):
        """ Get a specific operator's page """
        operator = request.match_info['operator'].lower().strip("/")
        if operator not in operators:
            return web.Response(text="Unknown operator!\n try /operators\n",
                                status=404)
        operator_id = operators[operator]
        operator_name = operator_names[operator_id]
        ret = ["\n"]

        db = request['connection']
        accept = parse_accept_header(request)
        route_count = await count_routes(db, operator_id)

        if operator_id in operator_logos:
            # Cool, there's a logo for this operator, draw it
            with open(operator_logos[operator_id], "r") as f:
                logo = f.read()
            for line in logo.splitlines():
                ret.append(line + ANSI_RESET)
            ret.append("\n")
        if route_count > 0:
            if operator != "rail":
                ret.append(f"{operator_name} has {route_count} routes - try /{operator}/<route_number>")
            else:
                ret.append(f"{operator_name}: - try /rail/stations or /rail/map")
        else:
            # Special casing for unfortunate operators, such as the Carmelit
            ret.append(f"{operator_name} has no routes :(")
        text = "\n".join(ret)+"\n"
        return self.ansi_or_html(accept, request, text)

    async def handle_nearby(self, request):
        """ Get nearby stops """
        db = request['connection']
        try:
            # Rounding lat and lon to 5 decimal digits to avoid cache bloat
            lat = round(float(request.query['lat']), 5)
            lon = round(float(request.query['lon']), 5)
        except KeyError:
            return web.Response(text="missing lat and lon", status=400)
        except ValueError:
            return web.Response(text="lat or lon are in the wrong format", status=400)
        try:
            try:
                radius = int(request.query['radius'])
            except ValueError:
                return web.Response(text=f"Radius must be a number",
                                    status=400)
            # 5 meters, 10 meters, 50 meters, up to 1000 in 50m increments
            allowed_radii = [5, 10, *range(50, 1050, 50)]
            if radius not in allowed_radii:
                return web.Response(text=f"Radius not allowed, try one of {allowed_radii}",
                                    status=400)
        except KeyError:
            radius = 300

        return web.json_response(await get_nearby_stops(db, lat, lon, radius))

    async def handle_rail_stations(self, request):
        db = request['connection']
        accept = parse_accept_header(request)
        stations = await get_rail_stations(db)
        if accept == "json":
            return web.json_response(stations)
        else:
            rendered = render_station_list(stations)
            return self.ansi_or_html(accept, request, rendered)

    async def handle_rail_map(self, request):
        accept = parse_accept_header(request)
        if accept == "json":
            return web.json_response("not available for this endpoint")
        else:
            railmap = os.path.join(os.path.dirname(__file__), "railwaymap.txt")
            with open(railmap, "r") as f:
                railmap = f.read()
            return self.ansi_or_html(accept, request, railmap)

    async def handle_index(self, request):
        ret = []
        logo = os.path.join(os.path.dirname(__file__), "curlbus.txt")
        with open(logo, "r", encoding="utf-8") as f:
            logo = f.read()
        for line in logo.splitlines():
            ret.append(line + ANSI_RESET)
        ret.append("\n")
        ret.append(f"curlbus v{__version__}".center(70))
        ret.append("by Elad Alfassa".rjust(43))
        ret.append("")
        ret.append("Try /<stop_code> or /operators")
        ret.append("")
        ret.append("Source code: https://github.com/elad661/curlbus")
        text = "\n".join(ret)+"\n"
        accept = parse_accept_header(request)
        return self.ansi_or_html(accept, request, text)
