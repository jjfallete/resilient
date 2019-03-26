# -*- coding: utf-8 -*-
# pragma pylint: disable=unused-argument, no-self-use

# This function will delete an absolute-path file or directory from an endpoint, found processes will be killed prior to deletion.
# File: cb_delete_file_kill_if_necessary.py
# Date: 03/18/2019 - Modified: 03/26/2019
# Author: Jared F

"""Function implementation"""
#   @function -> cb_delete_file_kill_if_necessary
#   @params -> integer: incident_id, string: hostname, string: path_or_file
#   @return -> boolean: results['was_successful'], string: results['hostname'], list of strings: results['deleted']

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
    """Component that implements Resilient function 'cb_delete_file_kill_if_necessary"""

    def __init__(self, opts):
        """constructor provides access to the configuration options"""
        super(FunctionComponent, self).__init__(opts)
        self.options = opts.get("carbon_black", {})
        selftest.selftest_function(opts)

    @handler("reload")
    def _reload(self, event, opts):
        """Configuration options have changed, save new values"""
        self.options = opts.get("carbon_black", {})

    @function("cb_delete_file_kill_if_necessary")
    def _cb_delete_file_kill_if_necessary_function(self, event, *args, **kwargs):
        """Function: Deletes an absolute-path file or directory."""

        results = {}
        results["was_successful"] = False
        results["hostname"] = None
        results["deleted"] = []

        try:
            # Get the function parameters:
            incident_id = kwargs.get("incident_id")  # number
            hostname = kwargs.get("hostname")  # text
            path_or_file = kwargs.get("path_or_file")  # text

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
            deleted = []

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
                        results["deleted"] = deleted
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

                    path = session.walk(path_or_file, False)  # Walk everything. False = performs a bottom->up walk, not top->down
                    exe_files = []  # List of executable files, used for killing if necessary prior to deletion
                    other_files = []  # List of all other files
                    count = 0  # Will remain at 0 if path_or_file is a file and not a path

                    for item in path:  # For each subdirectory in the path
                        count = count + 1
                        directory = os.path.normpath((str(item[0]))).replace(r'//', '\\')
                        file_list = item[2]  # List of files in the subdirectory
                        if str(file_list) != '[]':  # If the subdirectory is not empty
                            for f in file_list:  # For each file in the subdirectory
                                file_path = os.path.normpath(directory + '\\' + f).replace(r'//', '\\')
                                if f.endswith('.exe'): exe_files.append(file_path)
                                else: other_files.append(file_path)
                        other_files.append(directory)

                    for e in exe_files:  # For each executable file
                        process_list = session.list_processes()
                        for pr in process_list:
                            if (e.lower()) in str((pr['path']).lower()):  # If the executable is running as a process
                                yield StatusMessage('[SUCCESS] Found running process: ' + e + ' (killing it now...)')
                                try: session.kill_process((pr['pid']))  # Kill the process
                                except TimeoutError: raise
                                except Exception as err: yield StatusMessage('[ERROR] Failed to kill process! Encountered: ' + str(err))
                        try:
                            session.delete_file(e)  # Delete the executable file
                            deleted.append(e)
                            yield StatusMessage('[INFO] Deleted: ' + e)
                        except TimeoutError: raise TimeoutError(message=err)
                        except: yield StatusMessage('[ERROR] Deletion failed for: ' + e)

                    for o in other_files:  # For each non-executable file
                        try:
                            session.delete_file(o)  # Delete the file
                            deleted.append(o)
                            yield StatusMessage('[INFO] Deleted: ' + o)
                        except TimeoutError: raise TimeoutError(message=err)
                        except: yield StatusMessage('[ERROR] Deletion failed for: ' + o)

                    if count == 0:  # path_or_file was a file
                        try:
                            session.delete_file(path_or_file)  # Delete the file
                            deleted.append(path_or_file)
                            yield StatusMessage('[INFO] Deleted: ' + path_or_file)
                        except TimeoutError: raise TimeoutError(message=err)
                        except: yield StatusMessage('[ERROR] Deletion failed for: ' + path_or_file)

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
                    results["deleted"] = deleted

                else:
                    results["was_successful"] = True
                    results["deleted"] = deleted

                try: session.close()
                except: pass
                yield StatusMessage('[INFO] Session has been closed to CB Sensor #' + str(sensor.id) + '(' + sensor.hostname + ')')
                break

            # Produce a FunctionResult with the results
            yield FunctionResult(results)
        except Exception:
            yield FunctionError()
