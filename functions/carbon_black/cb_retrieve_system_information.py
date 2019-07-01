# -*- coding: utf-8 -*-
# pragma pylint: disable=unused-argument, no-self-use

# This function will retrieve current system information from an endpoint in a CSV file.
# File: cb_retrieve_system_information.py
# Date: 04/14/2019 - Modified: 06/25/2019
# Author: Jared F

"""Function implementation"""
#   @function -> cb_retrieve_system_information
#   @params -> integer: incident_id, string: hostname
#   @return -> boolean: results['was_successful'], string: results['hostname']


import os
import csv
import time
import tempfile
import logging
import datetime
from six import PY3
from resilient_circuits import ResilientComponent, function, handler, StatusMessage, FunctionResult, FunctionError
from cbapi.response import CbEnterpriseResponseAPI, Sensor
from cbapi.errors import TimeoutError, ApiError
from urllib3.exceptions import ProtocolError, NewConnectionError, ConnectTimeoutError, MaxRetryError
import carbon_black.util.selftest as selftest

cb = CbEnterpriseResponseAPI()  # CB Response API


# display_time function from https://stackoverflow.com/a/24542445
def display_time(seconds):
    result = []
    intervals = (('weeks', 604800), ('days', 86400), ('hours', 3600), ('minutes', 60), ('seconds', 1))

    if seconds == 0: return '0 seconds'

    sign = ''
    if seconds < 0:
        sign = '-'
        seconds = seconds/-1

    for name, count in intervals:
        value = seconds // count
        if value:
            seconds -= value * count
            if value == 1:
                name = name.rstrip('s')
            result.append("{} {}".format(value, name))
    return sign + (', '.join(result)).strip()


# UnicodeWriter class from http://python3porting.com/problems.html
class UnicodeWriter:
    def __init__(self, filename, dialect=csv.excel, encoding="utf-8", **kw):
        self.filename = filename
        self.dialect = dialect
        self.encoding = encoding
        self.kw = kw

    def __enter__(self):
        if PY3:
            self.f = open(self.filename, 'at', encoding=self.encoding, newline='')
        else:
            self.f = open(self.filename, 'ab')
        self.writer = csv.writer(self.f, dialect=self.dialect, **self.kw)
        return self

    def __exit__(self, type, value, traceback):
        self.f.close()

    def writerow(self, row):
        if not PY3:
            row = [s or "" for s in row]
            row = [s.encode(self.encoding) for s in row]
        self.writer.writerow(row)

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)


class FunctionComponent(ResilientComponent):
    """Component that implements Resilient function 'cb_retrieve_system_information"""

    def __init__(self, opts):
        """constructor provides access to the configuration options"""
        super(FunctionComponent, self).__init__(opts)
        self.options = opts.get("carbon_black", {})
        selftest.selftest_function(opts)

    @handler("reload")
    def _reload(self, event, opts):
        """Configuration options have changed, save new values"""
        self.options = opts.get("carbon_black", {})

    @function("cb_retrieve_system_information")
    def _cb_retrieve_system_information_function(self, event, *args, **kwargs):
        """Function: Retrieves system information from Carbon Black and builds a data table from the data. No Live Response session occurs."""

        results = {}
        results["was_successful"] = False
        results["hostname"] = None
        results['sensor_system_information'] = None

        try:
            # Get the function parameters:
            incident_id = kwargs.get("incident_id")  # number
            hostname = kwargs.get("hostname")  # text

            log = logging.getLogger(__name__)  # Establish logging

            hostname = hostname.upper()[:15]  # CB limits hostname to 15 characters
            sensor = cb.select(Sensor).where('hostname:' + hostname)  # Query CB for the hostname's sensor

            if len(sensor) <= 0:  # Host does not have CB agent, abort
                yield StatusMessage("[FATAL ERROR] CB could not find hostname: " + str(hostname))
                yield StatusMessage('[FAILURE] Fatal error caused exit!')
                yield FunctionResult(results)
                return

            sensor = sensor[0]  # Get the sensor object from the query
            results["hostname"] = str(hostname).upper()

            try:

                with tempfile.NamedTemporaryFile(delete=False) as temp_file:  # Create temporary temp_file for the CSV file
                    try:
                        with UnicodeWriter(temp_file.name) as csv_writer:
                            csv_writer.writerow(['Sensor ID:', 'Computer Name:', 'Group ID:', 'Group Name:', 'Status:', 'Power State:', 'Uptime:', 'Sensor Uptime:', 'Last Seen:',
                                                 'Health Score (/100):', 'Health Message:', 'Memory Capacity (GB):', 'Disk Capacity (GB):', 'OS ID:', 'OS Name:', 'Interface(s):',
                                                 'Clock Delta:', 'Pending Isolation:', 'Isolated:', 'Sensor Version:', 'Sensor Registered:', 'Host CB URL:'])
                            sensor_id = str(sensor.id)
                            sensor_computer_name = sensor.computer_name
                            sensor_group_id = str(sensor.group.id)
                            sensor_group = sensor.group.name
                            sensor_status = sensor.status

                            sensor_power_state = sensor.power_state
                            if sensor_power_state == 0: sensor_power_state = 'Running'
                            elif sensor_power_state == 1: sensor_power_state = 'Suspended'
                            elif sensor_power_state == 2: sensor_power_state = 'Offline'
                            else: sensor_power_state = 'Unknown: ' + str(sensor_power_state)

                            sensor_uptime = display_time(sensor.uptime)
                            sensor_sensor_uptime = display_time(sensor.sensor_uptime)
                            sensor_last_seen = sensor.last_checkin_time.strftime('%Y-%m-%d %H:%M:%S')
                            sensor_health_score = str(sensor.sensor_health_status)
                            sensor_health = sensor.sensor_health_message
                            sensor_ram = str(int(sensor.physical_memory_size) / 1000000000)
                            sensor_disk = str(int(sensor.systemvolume_total_size) / 1000000000)
                            sensor_os_id = str(sensor.os_environment_id)
                            sensor_os = sensor.os_environment_display_string

                            interfaces = ''
                            for interface in sensor.network_interfaces:
                                interfaces += (str(interface[0]) + ' - ' + str(interface[1]) + ' | ')

                            sensor_clock_delta = display_time(sensor.clock_delta)
                            sensor_pending_isolation = str(sensor.is_isolating)
                            sensor_isolated = str(sensor.network_isolation_enabled)
                            sensor_version = sensor.build_version_string
                            sensor_registered = sensor.registration_time.strftime('%Y-%m-%d %H:%M:%S')
                            sensor_cb_url = sensor.webui_link



                            csv_writer.writerow([sensor_id, sensor_computer_name, sensor_group_id, sensor_group, sensor_status, sensor_power_state, sensor_uptime, sensor_sensor_uptime,
                                                 sensor_last_seen, sensor_health_score, sensor_health, sensor_ram, sensor_disk, sensor_os_id, sensor_os, interfaces[:-3], sensor_clock_delta,
                                                 sensor_pending_isolation, sensor_isolated, sensor_version, sensor_registered, sensor_cb_url])

                            results['sensor_system_information'] = [sensor_id, sensor_computer_name, sensor_group_id, sensor_group, sensor_status, sensor_power_state, sensor_uptime, sensor_sensor_uptime,
                                                 sensor_last_seen, sensor_health_score, sensor_health, sensor_ram, sensor_disk, sensor_os_id, sensor_os, interfaces[:-3], sensor_clock_delta,
                                                 sensor_pending_isolation, sensor_isolated, sensor_version, sensor_registered, sensor_cb_url]

                        yield StatusMessage('[SUCCESS] Retrieved Sensor data!')
                        self.rest_client().post_attachment('/incidents/{0}/attachments'.format(incident_id), temp_file.name, '{0}-sensor_system_info.csv'.format(sensor.hostname))  # Post temp_file to incident
                        yield StatusMessage('[SUCCESS] Posted a CSV data file to the incident as an attachment!')

                    finally:
                        os.unlink(temp_file.name)  # Delete temporary temp_file


            except Exception as err:  # Catch all other exceptions and abort
                yield StatusMessage('[FATAL ERROR] Encountered: ' + str(err))
                yield StatusMessage('[FAILURE] Fatal error caused exit!')

            else:
                results["was_successful"] = True

            # Produce a FunctionResult with the results
            yield FunctionResult(results)
        except Exception:
            yield FunctionError()
