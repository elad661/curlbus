# curlbus 🚉🚍🚌

*It's like a catbus, but uses a different command :)*

[curlbus](https://curlbus.app) provides easy terminal based UI (or JSON) abstraction to the Israeli Mininstry of Transportation realtime public transit API.

Support for other countries / transit operators is theoretically possible to implement, if you want that feature - let me know.

Inspired by [wttr.in](https://github.com/chubin/wttr.in) and [mapscii](https://github.com/rastapasta/mapscii).

## Usage

### Terminal UI

`curl https://curlbus.app/<stop_code>`

To find the stop code, use OpenStreetMap, Google Maps, or look at the sign on the stop itself.

Other endpoints are also available:

* `/operators` - Get a list of known transit operator names
* `/<operator>/<route_number>` - Get information for a specific route from a specific operator, for example `/dan/1`.
* `/<operator>/<route_number>/<alternative>` - Get information for a specific route alternative

You can set up convinent shell aliases to quickly query a line or a stop you care about, for example put this in your `~/.bashrc`:

```bash
alias bus="curl https://curlbus.app/36601"
```

And now you just need to type `bus` to get live ETAs for your bus home :)

### HTML-based terminal-like UI

[curlbus](https://curlbus.app) is also accessible via a browser, but curl is still the recommended method of interaction.

### JSON API

curlbus also has a JSON based API. Send a request with the header `Accept: application/json` to get the output in a JSON format. All endpoints support JSON.

# Installing the Server

If you want to run it yourself, you'll need access to the Israeli MoT realtime "SIRI-SM" API.

Follow [the instructions on the Ministry of Transportation website](https://www.gov.il/he/Departments/General/real_time_information_siri) to apply for API access.

Note that having your application reviewed can take very long time, and that the API access requires your IP to be added to the whitelist, which
means you have to have a static IP. Not great for cloud deployments.

After you have API access (if you haven't given up on this stage), install the required dependencies:

`pip3 --user -f requirements.txt`

And edit config.ini.example to fill in the required values.

You'll need Postgresql for the GTFS database. Other databases are not supported.

The GTFS feed updates nightly, so you'll need to set up a cron job to call `./update_feed.sh`.

It's also a good idea to occasionally run `./update_cities.sh` to download the city name database.

## Development Server

Running `mock_siri_server.py` and pointing your config file for it will allow you to run curlbus locally without access to the SIRI API.
it still requires PostgreSQL.

`mock_siri_server.py` will make up random arrival times for random routes when queried, but all the routes would be valid ones that actually
stop on the requested stop according to the GTFS database. Make sure to run `update_feed.sh` before running the mock server.
