# -*- coding: utf-8 -*-
# pragma pylint: disable=unused-argument, no-self-use

# This function will retrieve a file or directory from an endpoint in a zipped file.
# File: cb_retrieve_file_or_directory.py
# Date: 04/04/2019 - Modified: 04/04/2019
# Author: Jared F

"""Function implementation"""
#   @function -> cb_retrieve_file_or_directory
#   @params -> integer: incident_id, string: hostname, string: path_or_file, int: max_file_size (optional)
#   @return -> boolean: results['was_successful'], string: results['hostname']


import os
import time
import tempfile
import zipfile
import logging
import datetime
from resilient_circuits import ResilientComponent, function, handler, StatusMessage, FunctionResult, FunctionError
from cbapi.response import CbEnterpriseResponseAPI, Sensor
from cbapi.errors import TimeoutError
import carbon_black.util.selftest as selftest

cb = CbEnterpriseResponseAPI()  # CB Response API
MAX_TIMEOUTS = 3  # The number of CB timeouts that must occur before the function aborts
DAYS_UNTIL_TIMEOUT = 3  # The number of days that must pass before the function aborts

MAX_FILE_SIZE = 100000000  # Bytes, the default maximum file size to transfer (per file)
TRANSFER_RATE = 225000  # Bytes per second, the expected minimum file transfer rate via Carbon Black


class FunctionComponent(ResilientComponent):
    """Component that implements Resilient function 'cb_retrieve_file_or_directory"""

    def __init__(self, opts):
        """constructor provides access to the configuration options"""
        super(FunctionComponent, self).__init__(opts)
        self.options = opts.get("carbon_black", {})
        selftest.selftest_function(opts)

    @handler("reload")
    def _reload(self, event, opts):
        """Configuration options have changed, save new values"""
        self.options = opts.get("carbon_black", {})

    @function("cb_retrieve_file_or_directory")
    def _cb_retrieve_file_or_directory_function(self, event, *args, **kwargs):

        results = {}

        try:
            # Get the function parameters:
            incident_id = kwargs.get("incident_id")  # number
            hostname = kwargs.get("hostname")  # text
            path_or_file = kwargs.get("path_or_file")  # text
            max_file_size = kwargs.get("max_file_size")  # number

            log = logging.getLogger(__name__)  # Establish logging

            days_later_timeout_length = datetime.datetime.now() + datetime.timedelta(days=DAYS_UNTIL_TIMEOUT)  # Max duration length before aborting
            hostname = hostname.upper()[:15]  # CB limits hostname to 15 characters
            sensor = cb.select(Sensor).where('hostname:' + hostname)  # Query CB for the hostname's sensor
            timeouts = 0  # Number of timeouts that have occurred

            if len(sensor) <= 0:  # Host does not have CB agent, abort
                yield StatusMessage("[FATAL ERROR] CB could not find hostname: " + str(hostname))
                results["was_successful"] = False
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
                        sensor = (cb.select(Sensor).where('hostname:' + hostname))[0]  # Retrieve the latest CB sensor vitals

                    # Check online status
                    if sensor.status != "Online":
                        yield StatusMessage('[WARNING] Hostname: {} is offline. Will attempt for {} days...').format(str(hostname), str(DAYS_UNTIL_TIMEOUT))
                    while (sensor.status != "Online") and (days_later_timeout_length >= now):  # Continuously check if the sensor comes online for 3 days
                        time.sleep(3)  # Give the CPU a break, it works hard!
                        now = datetime.datetime.now()
                        sensor = (cb.select(Sensor).where('hostname:' + hostname))[0]  # Retrieve the latest CB sensor vitals

                    # Abort after DAYS_UNTIL_TIMEOUT
                    if sensor.status != "Online":
                        yield StatusMessage('[FATAL ERROR] Hostname: ' + str(hostname) + ' is still offline!')
                        results["was_successful"] = False
                        yield FunctionResult(results)
                        return

                    # Check if the sensor is queued to restart, wait up to 90 seconds before continuing
                    three_minutes_passed = datetime.datetime.now() + datetime.timedelta(minutes=3)
                    while (sensor.restart_queued is True) and (three_minutes_passed >= now):  # If the sensor is queued to restart, wait up to 90 seconds
                        time.sleep(3)  # Give the CPU a break, it works hard!
                        now = datetime.datetime.now()
                        sensor = (cb.select(Sensor).where('hostname:' + hostname))[0]  # Retrieve the latest CB sensor vitals

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

                    files_to_retrieve = []  # Stores log file path located for retrieval

                    if max_file_size is None:  # If max_file_size is not provided
                        max_file_size = MAX_FILE_SIZE  # Set max_file_size to the default value

                    if os.path.isfile(path_or_file):  # If path_or_file is a file
                        file_path = os.path.normpath(path_or_file)
                        file_size = session.list_directory(file_path)[0]['size']  # File size in bytes
                        custom_timeout = int((file_size / TRANSFER_RATE) + 120)  # The expected timeout duration + 120 seconds for good measure
                        if 0 < file_size < int(max_file_size):  # If the file has data and does not exceed max_file_size
                            log.info('[INFO] Located: ' + file_path)
                            files_to_retrieve.append([file_path, custom_timeout])  # Store the file path and custom timeout into files_to_retrieve

                    else:  # path_or_file is a path
                        path = session.walk(path_or_file, False)  # Walk everything. False performs a bottom->up walk, not top->down
                        for item in path:  # For each subdirectory in the path
                            directory = os.path.normpath((str(item[0])))  # The subdirectory in OS path syntax
                            file_list = item[2]  # List of files in the subdirectory
                            if str(file_list) != '[]':  # If the subdirectory is not empty
                                for f in file_list:  # For each file in the subdirectory
                                    file_path = os.path.normpath(directory + '\\' + f)
                                    file_size = session.list_directory(file_path)[0]['size']  # File size in bytes
                                    custom_timeout = int((file_size / TRANSFER_RATE) + 120)  # The expected timeout duration + 120 seconds for good measure
                                    if 0 < file_size < int(max_file_size):  # If the file has data and does not exceed max_file_size
                                        log.info('[INFO] Located: ' + file_path)
                                        files_to_retrieve.append([file_path, custom_timeout])  # Store the file path into files_to_retrieve

                    with tempfile.NamedTemporaryFile(delete=False) as temp_zip:  # Create temporary temp_zip for creating zip_file
                        try:
                            with zipfile.ZipFile(temp_zip, 'w') as zip_file:  # Establish zip_file from temporary temp_zip for packaging logs into
                                for each_file, custom_timeout in files_to_retrieve:  # For each located log file
                                    with tempfile.NamedTemporaryFile(delete=False) as temp_file:  # Create temp_file for log
                                        try:
                                            base_directory = os.path.dirname(path_or_file.replace('\\', os.sep))
                                            file_directory = os.path.dirname(each_file.replace('\\', os.sep).replace(base_directory, ''))
                                            file_path = file_directory + os.sep + os.path.basename(each_file.replace('\\', os.sep))
                                            temp_file.write(session.get_file(each_file, timeout=custom_timeout))  # Write the log to temp_file
                                            temp_file.close()
                                            zip_file.write(temp_file.name, file_path, compress_type=zipfile.ZIP_DEFLATED)  # Write temp_file into zip_file

                                        finally:
                                            os.unlink(temp_file.name)  # Delete temporary temp_file

                            self.rest_client().post_attachment('/incidents/{0}/attachments'.format(incident_id), temp_zip.name, '{0}-CB_logs.zip'.format(sensor.hostname))  # Post zip_file to incident
                            yield StatusMessage('[SUCCESS] Posted ZIP file to the incident as an attachment!')

                        finally:
                            os.unlink(temp_zip.name)  # Delete temporary temp_file

                except TimeoutError:  # Catch TimeoutError and handle
                    timeouts = timeouts + 1
                    if timeouts <= MAX_TIMEOUTS: yield StatusMessage('[ERROR] TimeoutError was encountered. Reattempting... (' + str(timeouts) + '/3)')
                    else:
                        yield StatusMessage('[FATAL ERROR] TimeoutError was encountered. The maximum number of retries was reached. Aborting!')
                        yield StatusMessage('[FAILURE] Fatal error caused exit!')
                        results["was_successful"] = False
                    try: session.close()
                    except: pass
                    sensor = (cb.select(Sensor).where('hostname:' + hostname))[0]  # Retrieve the latest CB sensor vitals
                    sensor.restart_sensor()  # Restarting the sensor may avoid a timeout from occurring again
                    time.sleep(30)  # Sleep to apply sensor restart
                    sensor = (cb.select(Sensor).where('hostname:' + hostname))[0]  # Retrieve the latest CB sensor vitals
                    continue

                except Exception as err:  # Catch all other exceptions and abort
                    yield StatusMessage('[FATAL ERROR] Encountered: ' + str(err))
                    yield StatusMessage('[FAILURE] Fatal error caused exit!')
                    results["was_successful"] = False

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
