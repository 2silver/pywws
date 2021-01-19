# pywws - Python software for USB Wireless Weather Stations
# http://github.com/jim-easterbrook/pywws
# Copyright (C) 2018  pywws contributors

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""Upload weather data to InfluxDB OpenSource Time Series Database.

InfluxDB is an open-source time series database (TSDB) developed by InfluxData.
It is written in Go and optimized for fast, high-availability storage and
retrieval of time series data in fields such as operations monitoring,
application metrics, Internet of Things sensor data, and real-time analytics.
See :ref:`Dependencies - InfluxDB <dependencies-influxdb>` for details.

* InfluxDB (a lightweight broker): https://github.com/influxdata/influxdb
* Example ``weather.ini`` configuration::

    [influxdb]
    hostname = 192.168.0.1
    port = 8086
    user = weather
    password = weather
    database = weatherstation
    tls_cert =
    ssl = 0
    template_txt = ('\\n'
            '#idx          \\'"idx"         : "%Y-%m-%d %H:%M:%S",\\'#\\n'
            '#wind_dir     \\'"wind_dir"    : "%.0f",\\' \\'\\' \\'winddir_degrees(x)\\'#\\n'
            '#wind_ave     \\'"wind_ave"    : "%.2f",\\' \\'\\' \\'wind_mph(x)\\'#\\n'
            '#wind_gust    \\'"wind_gust"   : "%.2f",\\' \\'\\' \\'wind_mph(x)\\'#\\n'
            '#hum_out      \\'"hum_out"     : "%.d",\\'#\\n'
            '#hum_in       \\'"hum_in"      : "%.d",\\'#\\n'
            '#temp_in      \\'"temp_in_c"   : "%.1f",\\'#\\n'
            '#temp_in      \\'"temp_in_f"   : "%.1f",\\' \\'\\' \\'temp_f(x)\\'#\\n'
            '#temp_out     \\'"temp_out_c"  : "%.1f",\\'#\\n'
            '#temp_out     \\'"temp_out_f"  : "%.1f",\\' \\'\\' \\'temp_f(x)\\'#\\n'
            '#rel_pressure \\'"rel_pressure": "%.4f",\\' \\'\\' \\'pressure_inhg(x)\\'#\\n'
            '#calc \\'rain_inch(rain_hour(data))\\' \\'"rainin": "%g",\\'#\\n'
            '#calc \\'rain_inch(rain_day(data))\\' \\'"dailyrainin": "%g",\\'#\\n'
            '#calc \\'rain_hour(data)\\' \\'"rain": "%g",\\'#\\n'
            '#calc \\'rain_day(data)\\' \\'"dailyrain": "%g",\\'#\\n'
            '\\n')

    [logged]
    services = ['influxdb', 'underground']

pywws will publish weather data. This data will be
pushed to the database running on ``hostname``, with the port number
specified. (An IP address can be used instead of a host name.)

``user`` and ``password`` can be used for Database authentication.

``tls_cert`` is used for Database TLS authentication. Set
tls_cert as the path to a CA certificate (e.g. tls_cert =
/home/pi/pywws/ca_cert/tls_ca.crt). See
Note that secure SSL usually uses
port 8086, so you will need to also change the port number.
See (https://docs.influxdata.com/influxdb/v1.7/administration/https_setup/) for
HTTPS Setup

``template_txt`` is the template used to generate the data to be
published. You can edit it to suit your own requirements, e.g. not using
antiquated units of measurement. Be very careful about the backslash
escaped quotation marks though.

.. _InfluxDB: https://www.influxdata.com/

"""

from __future__ import absolute_import, unicode_literals

from ast import literal_eval
from contextlib import contextmanager
from datetime import datetime
import logging
import os
import pprint
import sys

from influxdb import InfluxDBClient

import pywws.service

__docformat__ = "restructuredtext en"
service_name = os.path.splitext(os.path.basename(__file__))[0]
logger = logging.getLogger(__name__)


class ToService(pywws.service.LiveDataService):
    config = {
        'hostname'   : ('localhost',      True,  None),
        'port'       : ('1883',           True,  None),
        'user'       : ('',               False, None),
        'password'   : ('',               False, None),
        'database'   : ('',               False, None),
        'tls_cert'   : ('',               False, None),
        'ssl'        : ('1',              True,  None),
        }
    logger = logger
    service_name = service_name
    template = """
#wind_dir     '"wind_dir"    : "%.0f",' '' 'winddir_degrees(x)'#
#wind_ave     '"wind_ave"    : "%.2f",' '' 'wind_mph(x)'#
#wind_gust    '"wind_gust"   : "%.2f",' '' 'wind_mph(x)'#
#hum_out      '"hum_out"     : "%.d",'#
#hum_in       '"hum_in"      : "%.d",'#
#temp_in      '"temp_in_c"   : "%.1f",'#
#temp_in      '"temp_in_f"   : "%.1f",' '' 'temp_f(x)'#
#temp_out     '"temp_out_c"  : "%.1f",'#
#temp_out     '"temp_out_f"  : "%.1f",' '' 'temp_f(x)'#
#rel_pressure '"rel_pressure": "%.4f",' '' 'pressure_inhg(x)'#
#calc 'rain_inch(rain_hour(data))' '"rainin": "%g",'#
#calc 'rain_inch(rain_day(data))' '"dailyrainin": "%g",'#
#calc 'rain_hour(data)' '"rain": "%g",'#
#calc 'rain_day(data)' '"dailyrain": "%g",'#
"""

    def __init__(self, context, check_params=True):
        super(ToService, self).__init__(context, check_params)
        # get template text
        template = literal_eval(context.params.get(
            service_name, 'template_txt', pprint.pformat(self.template)))
        logger.log(logging.DEBUG - 1, 'template:\n' + template)
        self.template = "#live#" + template
        # convert some params from string
        for key in ('port', 'tls_ver'):
            self.params[key] = literal_eval(self.params[key])

    @contextmanager
    def session(self):
        client = InfluxDBClient(
            self.params['hostname'],
            self.params['port'],
            self.params['user'],
            self.params['password'],
            self.params['database'],
            self.params['ssl'],
            self.params['cert'],
        )
        logger.debug(('connecting to host {hostname:s}:{port:d}').format(**self.params))
        logger.debug("client {}".format(client))
        try:
            yield client
        finally:
            client.close()


    def upload_data(self, session, prepared_data={}):
        series = []

        for p in prepared_data.keys():
            # for consistency, we leave all data in template_text in strings
            # but for upload we will convert them in floats
            # idx/time is not needed, because InfluxDB create it self-reliant
            value = p
            try:
                value = float(prepared_data.get(p))
            except Exception as e:
                logger.debug("float {e}")
            data = dict({
                "measurement": p,
                "fields": {
                    'value': value
                },
                "tags": {
                    "sensor": "WH-3080",
                    "location": "garden"
                },
            })
            series.append(data)

        try:
            logger.debug("session {}".format(session))
            logger.debug("series {}".format(series))
            session.write_points(series)
            return True, 'OK'
        except Exception as ex:
            logger.debug("ex: {}".format(ex))
            return False, repr(ex)
        logger.debug("ok")
        return True, 'OK'


if __name__ == "__main__":
    sys.exit(pywws.service.main(ToService))
