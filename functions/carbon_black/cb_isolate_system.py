# -*- coding: utf-8 -*-
# pragma pylint: disable=unused-argument, no-self-use

# This function will isolate an endpoint via Carbon Black.
# File: cb_isolate_system.py
# Date: 03/26/2019 - Modified: 03/26/2019
# Author: Jared F

"""Function implementation"""
#   @function -> cb_isolate_system
#   @params -> integer: incident_id, string: hostname
#   @return -> boolean: results['was_successful'], string: results['hostname']

import logging
from resilient_circuits import ResilientComponent, function, handler, StatusMessage, FunctionResult, FunctionError
from cbapi.response import CbEnterpriseResponseAPI, Sensor
import carbon_black.util.selftest as selftest

cb = CbEnterpriseResponseAPI()  # CB Response API
protected_sensor_group_ids = []  # List of group IDs that cannot be isolated (ie critical server groups)


class FunctionComponent(ResilientComponent):
    """Component that implements Resilient function 'cb_isolate_system"""

    def __init__(self, opts):
        """constructor provides access to the configuration options"""
        super(FunctionComponent, self).__init__(opts)
        self.options = opts.get("carbon_black", {})
        selftest.selftest_function(opts)

    @handler("reload")
    def _reload(self, event, opts):
        """Configuration options have changed, save new values"""
        self.options = opts.get("carbon_black", {})

    @function("cb_isolate_system")
    def _cb_isolate_system_function(self, event, *args, **kwargs):

        results = {}
        results["was_successful"] = False
        results["hostname"] = None

        try:
            # Get the function parameters:
            incident_id = kwargs.get("incident_id")  # number
            hostname = kwargs.get("hostname")  # text

            log = logging.getLogger(__name__)

            hostname = hostname.upper().replace('@MNPOWER.COM', '').replace('.MNPOWER.COM', '')[:15]  # CB limits hostname to 15 characters
            sensor = cb.select(Sensor).where('hostname:' + hostname)  # Query CB for the hostname's sensor

            if len(sensor) <= 0:  # Host does not have CB agent, abort
                yield StatusMessage("[FATAL ERROR] CB could not find hostname: " + str(hostname))
                yield FunctionResult(results)
                return

            sensor = sensor[0]  # Get the sensor object from the query
            results["hostname"] = str(hostname).upper()

            try:

                if sensor.group.id in protected_sensor_group_ids:
                    yield StatusMessage('[FAILURE] Hostname ' + str(hostname) + ' is in a protected group, isolation not allowed via Resilient!')
                    yield FunctionResult(results)
                    return

                elif sensor.network_isolation_enabled:
                    yield StatusMessage('[FAILURE] Hostname ' + str(hostname) + ' is already isolated!')
                    yield FunctionResult(results)
                    return

                elif sensor.is_isolating:
                    yield StatusMessage('[FAILURE] Hostname ' + str(hostname) + ' is already pending isolation!')
                    yield FunctionResult(results)
                    return

                else:
                    yield StatusMessage('[INFO] Attempting to isolate hostname ' + str(hostname) + '...')
                    is_successful = sensor.isolate()  # Isolate the sensor, wait indefinitely until the sensor acknowledges the isolation. Store the 'True' return value to is_successful

            except Exception as err:  # Catch all exceptions and abort
                yield StatusMessage('[FATAL ERROR] Encountered: ' + str(err))
                yield StatusMessage('[FAILURE] Fatal error caused exit!')

            if is_successful is True:
                results["was_successful"] = True
                yield StatusMessage('[SUCCESS] The CB agent on hostname ' + str(hostname) + ' acknowledged the isolation.')

            else:  # This can only occur if there was an exception
                yield StatusMessage('[FAILURE] Hostname ' + str(hostname) + ' was NOT isolated!')

            # Produce a FunctionResult with the results
            yield FunctionResult(results)
        except Exception:
            yield FunctionError()
