FROM ubuntu:18.04
MAINTAINER Guy Sheffer <guysoft at gmail dot com>

EXPOSE 80

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    tzdata \
    apt-utils \
    python3 \
    python3-distutils \
    python3-dev \
    python3-ujson \
    wget \
    sudo \
    unzip \
    postgresql-client-common \
    postgresql-client-10 \
  && rm -rf /var/lib/apt/lists/* \
  && apt -qyy clean

#===================
# Timezone settings
#===================
# Full list at https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
#  e.g. "US/Pacific" for Los Angeles, California, USA
# e.g. ENV TZ "US/Pacific"
ENV TZ="Asia/Jerusalem"
# Apply TimeZone
# Layer size: tiny: 1.339 MB
RUN echo "Setting time zone to '${TZ}'" \
  && echo "${TZ}" > /etc/timezone \
  && dpkg-reconfigure --frontend noninteractive tzdata

RUN wget https://bootstrap.pypa.io/get-pip.py -O - | python3
#WORKDIR /
COPY ./requirements.txt /requirements.txt
RUN pip3 install -r requirements.txt
RUN pip3 install msgpack

COPY . /curlbus
CMD ["/curlbus/main.py","-c","/curlbus/config.ini"]

