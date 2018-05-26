# main.py - curlbus main script
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
"""Usage: main.py [-c <file>]

Start curlbus web server
Options:
  -c <file>, --config <file>  Use the specified configuration file.
"""
import configparser
from docopt import docopt
from curlbus.server import CurlbusServer


def main():
    arguments = docopt(__doc__)
    configfile = arguments['--config'] or "config.ini"
    config = configparser.ConfigParser()
    config.read(configfile)
    config_dict = {s: dict(config.items(s)) for s in config.sections()}
    server = CurlbusServer(config_dict)
    server.run(config_dict['app'])


if __name__ == "__main__":
    main()
