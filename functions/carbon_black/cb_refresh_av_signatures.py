# -*- coding: utf-8 -*-
# pragma pylint: disable=unused-argument, no-self-use

# This function will remove AV signatures from Windows Defender / Microsoft Security Client and then updates them.
# File: cb_refresh_av_signatures.py
# Date: 03/26/2019 - Modified: 03/26/2019
# Author: Jared F

"""Function implementation"""
#   @function -> cb_refresh_av_signatures
#   @params -> integer: incident_id, string: hostname
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
MAX_TIMEOUTS = 3  # The number of CB timeouts that must occur before the function aborts
DAYS_UNTIL_TIMEOUT = 3  # The number of days that must pass before the function aborts


class FunctionComponent(ResilientComponent):
    """Component that implements Resilient function 'cb_refresh_av_signatures"""

    def __init__(self, opts):
        """constructor provides access to the configuration options"""
        super(FunctionComponent, self).__init__(opts)
        self.options = opts.get("carbon_black", {})
        selftest.selftest_function(opts)

    @handler("reload")
    def _reload(self, event, opts):
        """Configuration options have changed, save new values"""
        self.options = opts.get("carbon_black", {})

    @function("cb_refresh_av_signatures")
    def _cb_refresh_av_signatures(self, event, *args, **kwargs):

        results = {}
        results["was_successful"] = False
        results["hostname"] = None

        try:
            # Get the function parameters:
            incident_id = kwargs.get("incident_id")  # number
            hostname = kwargs.get("hostname")  # text

            log = logging.getLogger(__name__)  # Establish logging

            days_later_timeout_length = datetime.datetime.now() + datetime.timedelta(days=DAYS_UNTIL_TIMEOUT)  # Max duration length before aborting
            hostname = hostname.upper()[:15]  # CB limits hostname to 15 characters
            sensor = cb.select(Sensor).where('hostname:' + hostname)  # Query CB for the hostname's sensor
            timeouts = 0  # Number of timeouts that have occurred

            if len(sensor) <= 0:  # Host does not have CB agent, abort
                yield StatusMessage("[FATAL ERROR] CB could not find hostname: " + str(hostname))
                yield FunctionResult(results)
                return

            sensor = sensor[0]  # Get the sensor object from the query
            results["hostname"] = str(hostname).upper()

            while timeouts <= MAX_TIMEOUTS:  # Max timeouts before aborting

                try:

                    now = datetime.datetime.now()

                    # Check if the sensor is queued to restart, wait up to 90 seconds before checking online status
                    three_minutes_passed = datetime.datetime.now() + datetime.timedelta(minutes=3)
                    while (sensor.restart_queued is True) and (three_minutes_passed >= now):
                        time.sleep(3)  # Give the CPU a break, it works hard!
                        now = datetime.datetime.now()
                        sensor = (cb.select(Sensor).where('hostname:' + hostname))[0]  # Retrieve the latest sensor vitals

                    # Check online status
                    if sensor.status != "Online":
                        yield StatusMessage('[WARNING] Hostname: ' + str(hostname) + ' is offline. Will attempt for ' + str(DAYS_UNTIL_TIMEOUT) + ' days...')
                    while (sensor.status != "Online") and (days_later_timeout_length >= now):  # Continuously check if the sensor comes online for 3 days
                        time.sleep(3)  # Give the CPU a break, it works hard!
                        now = datetime.datetime.now()
                        sensor = (cb.select(Sensor).where('hostname:' + hostname))[0]  # Retrieve the latest sensor vitals

                    # Abort after DAYS_UNTIL_TIMEOUT
                    if sensor.status != "Online":
                        yield StatusMessage('[FATAL ERROR] Hostname: ' + str(hostname) + ' is still offline!')
                        yield FunctionResult(results)
                        return

                    # Check if the sensor is queued to restart, wait up to 90 seconds before continuing
                    three_minutes_passed = datetime.datetime.now() + datetime.timedelta(minutes=3)
                    while (sensor.restart_queued is True) and (three_minutes_passed >= now):  # If the sensor is queued to restart, wait up to 90 seconds
                        time.sleep(3)  # Give the CPU a break, it works hard!
                        now = datetime.datetime.now()
                        sensor = (cb.select(Sensor).where('hostname:' + hostname))[0]  # Retrieve the latest sensor vitals

                    # Verify the incident still exists and is reachable, if not abort
                    try: incident = self.rest_client().get('/incidents/{0}?text_content_output_format=always_text&handle_format=names'.format(str(incident_id)))
                    except Exception as err:
                        if err.message and "not found" in err.message.lower():
                            log.info('[FATAL ERROR] Incident ID ' + str(incident_id) + ' no longer exists.')
                            log.info('[FAILURE] Fatal error caused exit!')
                        else:
                            log.info('[FATAL ERROR] Incident ID ' + str(incident_id) + ' could not be reached, Resilient instance may be down.')
                            log.info('[FAILURE] Fatal error caused exit!')
                        return

                    # Establish a session to the host sensor
                    yield StatusMessage('[INFO] Establishing session to CB Sensor #' + str(sensor.id) + ' (' + sensor.hostname + ')')
                    session = cb.live_response.request_session(sensor.id)
                    yield StatusMessage('[SUCCESS] Connected on Session #' + str(session.session_id) + ' to CB Sensor #' + str(sensor.id) + ' (' + sensor.hostname + ')')

                    av_paths = []

                    try:
                        session.list_directory(r'C:\Program Files\Microsoft Security Client\mpcmdrun.exe')
                        av_paths.append(r'C:\Program Files\Microsoft Security Client\mpcmdrun.exe')
                    except TimeoutError: raise
                    except Exception: pass

                    try:
                        session.list_directory(r'C:\Program Files\Windows Defender\mpcmdrun.exe')
                        av_paths.append(r'C:\Program Files\Windows Defender\mpcmdrun.exe')
                    except TimeoutError: raise
                    except Exception: pass

                    if len(av_paths) > 1:  # If both Defender and Microsoft Security Client were found
                        for process in session.list_processes():  # Use whichever version is running on the endpoint
                            if ('c:\program files\microsoft security client' in process['path'].lower()):
                                av_paths.remove('C:\Program Files\Windows Defender\mpcmdrun.exe')
                                break

                            elif ('c:\program files\windows defender' in process['path'].lower()):
                                av_paths.remove('C:\Program Files\Microsoft Security Client\mpcmdrun.exe')
                                break

                    for detected_av_path in av_paths:
                        o = session.create_process(detected_av_path + ' -RemoveDefinitions -All', True, None, None, 300)
                        yield StatusMessage('[SUCCESS] Signature removal command sent to ' + detected_av_path)
                        log.info('[INFO] Output was: \n' + str(o))
                        results["remove_definitions_output"] = str(o)

                        o = session.create_process(detected_av_path + ' -SignatureUpdate', True, None, None, 300)
                        log.info('[SUCCESS] Signature update command sent to ' + detected_av_path)
                        yield StatusMessage('[SUCCESS] Signature update command sent to ' + detected_av_path)
                        log.info('[INFO] Output was: \n' + str(o))
                        results["signature_update_output"] = str(o)

                    if len(av_paths) == 0:
                        yield StatusMessage('[ERROR] Neither Windows Defender nor Microsoft Security Client were detected.')
                        yield StatusMessage('[FAILURE] Signatures were neither cleaned nor updated!')
                        results["was_successful"] = False
                        try: session.close()
                        except: pass
                        yield FunctionResult(results)
                        return

                except TimeoutError:  # Catch TimeoutError and handle
                    timeouts = timeouts + 1
                    if timeouts <= MAX_TIMEOUTS:
                        yield StatusMessage('[ERROR] TimeoutError was encountered. Reattempting... (' + str(timeouts) + '/3)')
                        try: session.close()
                        except: pass
                        sensor = (cb.select(Sensor).where('hostname:' + hostname))[0]  # Retrieve the latest sensor vitals
                        sensor.restart_sensor()  # Restarting the sensor may avoid a timeout from occurring again
                        time.sleep(30)  # Sleep to apply sensor restart
                        sensor = (cb.select(Sensor).where('hostname:' + hostname))[0]  # Retrieve the latest sensor vitals
                    else:
                        yield StatusMessage('[FATAL ERROR] TimeoutError was encountered. The maximum number of retries was reached. Aborting!')
                        yield StatusMessage('[FAILURE] Fatal error caused exit!')
                    continue

                except(ApiError, ProtocolError, NewConnectionError, ConnectTimeoutError, MaxRetryError) as err:  # Catch urllib3 connection exceptions and handle
                    if 'ApiError' in str(type(err).__name__) and 'network connection error' not in str(err): raise  # Only handle ApiError involving network connection error
                    timeouts = timeouts + 1
                    if timeouts <= MAX_TIMEOUTS:
                        yield StatusMessage('[ERROR] Carbon Black was unreachable. Reattempting in 30 minutes... (' + str(timeouts) + '/3)')
                        time.sleep(1800)  # Sleep for 30 minutes, backup service may have been running.
                    else:
                        yield StatusMessage('[FATAL ERROR] ' + str(type(err).__name__) + ' was encountered. The maximum number of retries was reached. Aborting!')
                        yield StatusMessage('[FAILURE] Fatal error caused exit!')
                    continue

                except Exception as err:  # Catch all other exceptions and abort
                    yield StatusMessage('[FATAL ERROR] Encountered: ' + str(err))
                    yield StatusMessage('[FAILURE] Fatal error caused exit!')

                else:
                    results["was_successful"] = True

                try: session.close()
                except: pass
                yield StatusMessage('[INFO] Session has been closed to CB Sensor #' + str(sensor.id) + '(' + sensor.hostname + ')')
                break

            # Produce a FunctionResult with the results
            yield FunctionResult(results)
        except Exception:
            yield FunctionError()
