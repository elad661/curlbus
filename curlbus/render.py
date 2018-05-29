""" render data as terminal-comaptible unicode tables/drawings """
# render.py
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
from .siri import SIRIResponse
from .operators import operator_names, operators_by_id
from datetime import datetime
import dateutil.tz


def table(header_lines: list, rows: list) -> str:
    """ Draw a unicode box drawing characters based table """
    width = {}

    # First pass: calculate column width
    table_width = 0
    for row in rows:
        for x, cell in enumerate(row):
            if x not in width or width[x] < len(cell) + 2:
                width[x] = len(cell) + 2

    table_width = sum(width.values()) + len(width) - 1
    header_width = max(len(line) for line in header_lines)
    if table_width < header_width:
        table_width = header_width

    if len(width) == 1:
        width[0] = table_width

    ret = ["╒"+("═"*table_width)+"╕"]
    for header_line in header_lines:
        ret.append(f"│{header_line.center(table_width)}│")

    header_bottom_border = "╞"

    # Second pass: actual table content
    for y, row in enumerate(rows):
        processed = "│"
        bottom_border = "├" if y < len(rows)-1 else "╰"
        for x, cell in enumerate(row):
            cell = cell.ljust(width[x])
            processed += f"{cell}│"
            bottom_border += "─" * len(cell)
            if y == 0:
                # Build header's bottom border
                header_bottom_border += "═"*len(cell)
                if x < len(row) - 1:
                    header_bottom_border += "╤"
            if y < len(rows)-1:
                bottom_border += "┼" if x < len(row)-1 else "┤"
            else:
                bottom_border += "┴" if x < len(row)-1 else "╯"
        if y == 0:
            header_bottom_border += "╡"
            ret.append(header_bottom_border)
        ret.append(processed)
        if row[0].strip() == "" or y == len(rows) - 1:
            ret.append(bottom_border)
    ret.append("\n")

    return "\n".join(ret)


def boxify(lines, side_margins=5, padding=2):
    """ Draw a unicdoe box """
    longest_line = max(len(line) for line in lines)
    ret = []
    padded = longest_line + padding * 2
    len_with_margins = padded + (side_margins * 2)
    ret.append(("╒"+("═" * padded) + "╕").center(len_with_margins))

    for line in lines:
        line = line.ljust(longest_line).center(padded)  # padding left/right
        ret.append(f'│{line}│'.center(len_with_margins))  # margin left/right

    ret.append(("╰"+("─" * padded) + "╯").center(len_with_margins))

    return ret


def render_station_arrivals(stop_info: dict, data: SIRIResponse) -> str:
    ret = ""
    if len(data.errors) > 0:
        for error in data.errors:
            ret += error
            ret += '\n'
    # Assuming one stop per response
    try:
        stop_name = stop_info['name']['EN']
    except KeyError:
        stop_name = stop_info['name']['HE']
    for stop_code, arrivals in data.visits.items():
        header = [f"Stop #{stop_code}",
                  stop_name]
        table_rows = []
        merged_arrivals = {}
        for arrival in arrivals:
            operator_name = operator_names[int(arrival.operator_id)]
            # operator_name = arrival.static_info['route']['agency']['name']['EN']
            try:
                destination = arrival.static_info['route']['destination']['name']['EN']
            except KeyError:
                destination = arrival.static_info['route']['destination']['name']['HE']
            except TypeError:
                destination = "???"

            line_number = arrival.line_name
            if operator_name == "Israel Railways":
                # Show "train number" for Israel Railways instead of the meaningless
                # line number. A train number is unique per day and appears
                # on the real-time departure boards in train stations
                line_number = arrival.vehicle_ref

            try:
                city = arrival.static_info['route']['destination']['address']['city']
            except TypeError:
                print(arrival.static_info)
                city = None
            except KeyError:
                print(arrival.static_info)
                city = None
            # TODO special-casing for Isral railways
            eta_minutes = round((arrival.eta - datetime.now(dateutil.tz.tzlocal())).total_seconds() / 60)
            if eta_minutes <= 0:
                eta_text = "Now"
            else:
                eta_text = str(eta_minutes) + "m"
            if operator_name == "Israel Railways":
                # since the train number is unique per day, we shouldn't merge
                # arrivals - otherwise the train number column would become
                # meaningless
                key = line_number
            else:
                # for all operators except Israel Railways
                # merged_arrivals is key'd on direction_id + operator_id + route_id + destination name
                key = f"{arrival.operator_id}{arrival.route_id}{arrival.direction_id}{destination}"
            if key in merged_arrivals:
                merged_arrivals[key]["etas"].append(eta_text)
                if merged_arrivals[key]["lowest_eta"] > eta_minutes:
                    merged_arrivals[key]["lowest_eta"] = eta_minutes
            else:
                merged_arrivals[key] = {"etas": [eta_text],
                                        "lowest_eta": eta_minutes,
                                        "line_number": line_number,
                                        "operator_name": operator_name,
                                        "destination": destination,
                                        "city": city}

        for arrival in sorted(merged_arrivals.values(), key=lambda a: a["lowest_eta"]):
            etas = ', '.join(arrival["etas"])
            table_rows.append([arrival["line_number"], arrival["operator_name"], arrival["destination"], etas])
            if arrival["city"] is not None:
                table_rows.append(["", "", arrival["city"], ""])
        if len(table_rows) == 0:
            table_rows = [["No buses in the next 30 minutes"]]

    return table(header, table_rows)


def render_operator_index(data: list):
    ret = []
    for operator in sorted(data, key=lambda o: o["name"]["EN"]):
        name = operator["name"]["EN"]
        url = operator["url"]
        ret.append([name, url])
    return table(["Transit Operators"], ret)


def render_route_alternatives(operator_id: str, routes: list) -> str:
    padding = 2
    routename = routes[0]['short_name']
    operator_name = operator_names[int(operator_id)]
    operator_slug = operators_by_id[int(operator_id)]
    ret = [f'There are multiple {operator_name} routes named {routename}.',
           "Which one do you want?", ""]

    # Find width for boxes
    width = padding
    for route in routes:
        name_parts = route['long_name'].split('<->')
        this_width = max(len(part) for part in name_parts) + 2
        if this_width > width:
            width = this_width

    # Draw a box for every route
    for index, route in enumerate(routes):
        name_parts = route['long_name'].split('<->')
        ret.append("╭"+("─"*width)+"╮")
        ret.append("│" + name_parts[0].center(width) + "│")
        ret.append("│" + "▼".center(width) + "│")
        ret.append("│" + name_parts[1].center(width) + "│")
        ret.append("│" + (" "*width) + "│")
        ret.append("├" + ("─"*width) + "┤")
        ret.append("│" + f"/{operator_slug}/{route['short_name']}/{index}".center(width) + "│")
        ret.append("╰"+("─"*width)+"╯")
        ret.append("")

    return "\n".join(ret)+"\n"


def render_route_map(route_info: dict, stops: list) -> str:
    padding_left = 4
    # start with the header
    ret = [f"{route_info['operator_name']} route {route_info['short_name']}",
           f"{route_info['long_name']}",
           ""]
    # now draw the map, which will look like this:
    # ---
    #     City name ┰ origin station
    #               ┋
    #               ┣ Stop name - (eta?)
    #    other city ┋
    #               ┣ Stop name - (eta?)
    #               ┋
    #               ┸ end station
    # ----
    routemap = []
    last_city = ""
    city_len = 0
    for index, stop in enumerate(stops):
        connector = "┣"
        if index == 0:
            connector = "┰"
        elif index == len(stops) - 1:
            connector = "┸"

        city = ""
        if 'city' in stop['address'] and stop['address']['city'] != last_city:
            city = stop['address']['city']
            last_city = city

        if len(city) > city_len:
            city_len = len(city)  # to align the map later

        # Now add the dotted connector in the middle
        if index > 0 and index < len(stops) - 1:
            routemap.append([city, "┋", ""])
        elif index == len(stops) - 1:
            routemap.append(["", "┋", ""])

        fragment = []
        if index == 0 or index == len(stops) - 1:
            # city name is on the same line with the stop name on the edges
            fragment.append(city)
        else:
            fragment.append("")
        fragment.append(connector)
        if 'EN' in stop['name']:
            stop_name = stop['name']['EN']
        else:
            stop_name = stop['name']['HE']
        stop_name += f" ({stop['stop_code']})"
        fragment.append(stop_name)

        if len(stop['etas']) > 0:
            eta = sorted(stop['etas'])[0]
            eta_minutes = round((eta - datetime.now(dateutil.tz.tzlocal())).total_seconds() / 60)
            if eta_minutes <= 0:
                eta_text = "Now"
            else:
                eta_text = str(eta_minutes) + "m"

            fragment.append(f"- {eta_text}")

        # Add the line with the stop name
        routemap.append(fragment)

    for line in routemap:
        line[0] = line[0].rjust(city_len + padding_left)
        ret.append(" ".join(line))

    return '\n'.join(ret)+'\n'


def render_station_list(stations: list):
    ret = []
    for station in sorted(stations, key=lambda s: s["name"]["EN"] if "EN" in s["name"] else s["name"]["HE"]):
        code = station["code"]
        if 'EN' in station["name"]:
            name = station["name"]["EN"]
        else:
            name = station["name"]["HE"]
        ret.append([code, name])
    ret_table = table(["Israel Railways Station Codes"], ret)
    ret_table += 'Use https://curlbus.app/<station_code> to get arrivals.\n'
    return ret_table
