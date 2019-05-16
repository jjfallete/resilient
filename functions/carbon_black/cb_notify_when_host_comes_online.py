# -*- coding: utf-8 -*-
# pragma pylint: disable=unused-argument, no-self-use

# This function will return when a host comes online (or a max_days value is reached).
# File: cb_notify_when_host_comes_online.py
# Date: 04/18/2019 - Modified: 04/18/2019
# Author: Jared F

"""Function implementation"""
#   @function -> cb_notify_when_host_comes_online
#   @params -> integer: incident_id, string: hostname, int: max_days
#   @return -> boolean: results['was_successful'], string: results['hostname']


import os
import time
import logging
import datetime
from resilient_circuits import ResilientComponent, function, handler, StatusMessage, FunctionResult, FunctionError
from cbapi.response import CbEnterpriseResponseAPI, Sensor
from cbapi.errors import TimeoutError, ApiError
from urllib3.exceptions import ProtocolError, NewConnectionError, ConnectTimeoutError, MaxRetryError
import carbon_black.util.selftest as selftest

cb = CbEnterpriseResponseAPI()  # CB Response API

class FunctionComponent(ResilientComponent):
    """Component that implements Resilient function 'cb_notify_when_host_comes_online"""

    def __init__(self, opts):
        """constructor provides access to the configuration options"""
        super(FunctionComponent, self).__init__(opts)
        self.options = opts.get("carbon_black", {})
        selftest.selftest_function(opts)

    @handler("reload")
    def _reload(self, event, opts):
        """Configuration options have changed, save new values"""
        self.options = opts.get("carbon_black", {})

    @function("cb_notify_when_host_comes_online")
    def _cb_notify_when_host_comes_online_function(self, event, *args, **kwargs):
        """Function: Notifies the incident owner when a host comes back online."""
        results = {}
        results["was_successful"] = False
        results["hostname"] = None
        results["Online"] = False

        try:
            # Get the function parameters:
            incident_id = kwargs.get("incident_id")  # number
            hostname = kwargs.get("hostname")  # text
            max_days = kwargs.get("max_days")  # number

            log = logging.getLogger(__name__)  # Establish logging

            try:

                days_later_timeout_length = datetime.datetime.now() + datetime.timedelta(days=max_days)  # Max duration length before aborting
                hostname = hostname.upper().replace('@MNPOWER.COM', '').replace('.MNPOWER.COM', '')[:15]  # CB limits hostname to 15 characters
                sensor = cb.select(Sensor).where('hostname:' + hostname)  # Query CB for the hostname's sensor

                if len(sensor) <= 0:  # Host does not have CB agent, abort
                    yield StatusMessage("[FATAL ERROR] CB could not find hostname: " + str(hostname))
                    yield FunctionResult(results)
                    return

                sensor = sensor[0]  # Get the sensor object from the query
                results["hostname"] = str(hostname).upper()

                now = datetime.datetime.now()

                # Check online status
                if sensor.status != "Online":
                    yield StatusMessage('[INFO] Hostname: ' + str(hostname) + ' is offline. Will notify when online for ' + str(max_days) + ' days...')
                while (sensor.status != "Online") and (days_later_timeout_length >= now):  # Continuously check if the sensor comes online for max_days
                    time.sleep(3)  # Give the CPU a break, it works hard!
                    now = datetime.datetime.now()
                    sensor = (cb.select(Sensor).where('hostname:' + hostname))[0]  # Retrieve the latest sensor vitals

                # Abort after max_days
                if sensor.status != "Online":
                    yield StatusMessage('[FATAL ERROR] Hostname: ' + str(hostname) + ' is still offline!')
                    yield FunctionResult(results)
                    return

            except Exception as err:  # Catch all other exceptions and abort
                yield StatusMessage('[FATAL ERROR] Encountered: ' + str(err))
                yield StatusMessage('[FAILURE] Fatal error caused exit!')

            else:
                yield StatusMessage('[SUCCESS] Hostname: ' + str(hostname) + ' is online!')
                results["was_successful"] = True
                results["Online"] = True

            # Produce a FunctionResult with the results
            yield FunctionResult(results)
        except Exception:
            yield FunctionError()
