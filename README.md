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

`pip3 install --user -r requirements.txt`

And edit config.ini.example to fill in the required values. Remeber to point it to the MoT server if you have API access.

You'll need Postgresql for the GTFS database. Other databases are not supported.

You need to use `./update_feed.sh` to load the GTFS database, and `./load_cities.py` to download the city name database.

The GTFS feed updates nightly, but `update_feed.sh` currently can only load it into an empty database. For now, the way to do updates is manual (once a week or so):

Change the configuration file to point to a different postgres database (I've been using two databases, "gtfs" and "gtfs2". when "gtfs2" is active I switch to "gtfs" and vise-versa), connect to it and make sure to drop all tables, then run `./update_feed.sh` and `./load_cities.py`. Afte they're done, restart the service. Doing it this way ensures the update is atomic and there are no inconsistencies while the update is running, and allows you to roll back in case of a problematic update (by just changing the config file back to the previous database).

I don't particularly like this process being manual, but I didn't have time to automate it.

Note that the GTFS feed can be quite big (more than 2GB of csv files), and loading it into your database can take a while, so be patient and make sure to have plenty of free disk space.

## Development Server

Running `mock_siri_server.py` and pointing your config file for it will allow you to run curlbus locally without access to the SIRI API.
it still requires PostgreSQL.

`mock_siri_server.py` will make up random arrival times for random routes when queried, but all the routes would be valid ones that actually
stop on the requested stop according to the GTFS database. Make sure to run `update_feed.sh` before running the mock server.


## Deploy with Docker
1. Create a file ``docker-compose.yml``:

```
version: '3.1'
  
services:
  curlbus:
    container_name: curlbus
    build:
      guysoft/curlbus
    volumes:
      - ./config.ini:/curlbus/config.ini:ro
    tty: true
    links:
      - "db:postgres"
    ports:
      - 8080:80

  db:
    image: postgres
    restart: always
    container_name: curlbus-db
    environment:
      POSTGRES_PASSWORD: example
      POSTGRES_DB: curlbus
```
2. 
```
wget https://raw.githubusercontent.com/guysoft/curlbus/master/config.ini.docker -O config.ini
```
3. Edit config.ini to include your SERI username.

4. 
```
sudo docker-compose up -d
sudo docker exec -it curlbus /curlbus/update_feed.sh
sudo docker exec -it curlbus /curlbus/load_cities.py -c /curlbus/config.ini
```

5. 

```
sudo docker exec -it curlbus /curlbus/main.py -c /curlbus/config.ini
```

6. Your curlbus server is avilable at port 8080
