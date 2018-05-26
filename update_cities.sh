#!/bin/bash
set -euo pipefail
# https://data.gov.il/dataset/citiesandsettelments/resource/d4901968-dad3-4845-a9b0-a57d027f11ab
wget https://data.gov.il/dataset/3fc54b81-25b3-4ac7-87db-248c3e1602de/resource/d4901968-dad3-4845-a9b0-a57d027f11ab/download/yeshuvim20180501.csv -O yeshuvim20180501.csv
python3 load_cities.py yeshuvim20180501.csv