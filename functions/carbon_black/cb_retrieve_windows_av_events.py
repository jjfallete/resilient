# -*- coding: utf-8 -*-
# pragma pylint: disable=unused-argument, no-self-use

# This function will retrieve the Microsoft Security Client and/or Windows Defender Windows event logs from an endpoint in corresponding TXT files.
# File: cb_retrieve_windows_av_events.py
# Date: 04/15/2019 - Modified: 05/16/2019
# Author: Jared F

"""Function implementation"""
#   @function -> cb_retrieve_windows_av_events
#   @params -> integer: incident_id, string: hostname
#   @return -> boolean: results['was_successful'], string: results['hostname']


import os
import time
import shutil
import tempfile
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

MAX_UPLOAD_SIZE = 50*1000000  # Maximum number of bytes of files to upload as an attachment before reverting to a netshare drop, default = 50MB
TRANSFER_RATE = 225000  # Bytes per second, the expected minimum file transfer rate via Carbon Black


class FunctionComponent(ResilientComponent):
    """Component that implements Resilient function 'cb_retrieve_windows_av_events"""

    def __init__(self, opts):
        """constructor provides access to the configuration options"""
        super(FunctionComponent, self).__init__(opts)
        self.options = opts.get("carbon_black", {})
        selftest.selftest_function(opts)

    @handler("reload")
    def _reload(self, event, opts):
        """Configuration options have changed, save new values"""
        self.options = opts.get("carbon_black", {})

    @function("cb_retrieve_windows_av_events")
    def _cb_retrieve_windows_av_events_function(self, event, *args, **kwargs):

        results = {}
        results["was_successful"] = False
        results["hostname"] = None
        lock_acquired = False

        try:
            # Get the function parameters:
            incident_id = kwargs.get("incident_id")  # number
            hostname = kwargs.get("hostname")  # text

            log = logging.getLogger(__name__)  # Establish logging

            days_later_timeout_length = datetime.datetime.now() + datetime.timedelta(days=DAYS_UNTIL_TIMEOUT)  # Max duration length before aborting
            hostname = hostname.upper()[:15]  # CB limits hostname to 15 characters
            lock_file = '/home/integrations/.resilient/cb_host_locks/{}.lock'.format(hostname)
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

                    # Check lock status
                    if os.path.exists(lock_file) and lock_acquired is False:
                        yield StatusMessage('[WARNING] A running action has a lock on  ' + str(hostname) + '. Will attempt for ' + str(DAYS_UNTIL_TIMEOUT) + ' days...')

                    # Wait for offline and locked hosts for days_later_timeout_length
                    while (sensor.status != "Online" or (os.path.exists(lock_file) and lock_acquired is False)) and (days_later_timeout_length >= now):
                        time.sleep(3)  # Give the CPU a break, it works hard!
                        now = datetime.datetime.now()
                        sensor = (cb.select(Sensor).where('hostname:' + hostname))[0]  # Retrieve the latest sensor vitals

                    # Abort after DAYS_UNTIL_TIMEOUT
                    if sensor.status != "Online" or (os.path.exists(lock_file) and lock_acquired is False):
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

                    # Acquire host lock
                    if lock_acquired is False:
                        try:
                            f = os.fdopen(os.open(lock_file, os.O_CREAT | os.O_WRONLY | os.O_EXCL), 'w')
                            f.close()
                            lock_acquired = True
                        except OSError:
                            continue

                    # Establish a session to the host sensor
                    yield StatusMessage('[INFO] Establishing session to CB Sensor #' + str(sensor.id) + ' (' + sensor.hostname + ')')
                    session = cb.live_response.request_session(sensor.id)
                    yield StatusMessage('[SUCCESS] Connected on Session #' + str(session.session_id) + ' to CB Sensor #' + str(sensor.id) + ' (' + sensor.hostname + ')')

                    try: session.create_directory('C:\Windows\CarbonBlack\Reports')
                    except TimeoutError: raise
                    except Exception: pass  # Existed already

                    session.create_process(r'''cmd.exe /c wevtutil qe "System" /rd:True /q:"*[System[Provider[@Name='Microsoft Antimalware']]]" /f:Text > C:\Windows\CarbonBlack\Reports\Antimalware_Events.txt''', True, None, None, 300, True)  # Execute the utility
                    yield StatusMessage('[SUCCESS] Queried all Microsoft Antimalware events on Sensor!')

                    session.create_process(r'''cmd.exe /c wevtutil qe "Microsoft-Windows-Windows Defender/Operational" /rd:True /f:Text > C:\Windows\CarbonBlack\Reports\Defender_Events.txt''', True, None, None, 300, True)  # Execute the utility
                    yield StatusMessage('[SUCCESS] Queried all Windows Defender events on Sensor!')

                    with tempfile.NamedTemporaryFile(delete=False) as temp_file:  # Create temporary temp_file for TXT file
                        try:
                            file_size = session.list_directory(r'C:\Windows\CarbonBlack\Reports\Antimalware_Events.txt')[0]['size']  # File size in bytes
                            custom_timeout = int((file_size / TRANSFER_RATE) + 120)  # The expected timeout duration + 120 seconds for good measure
                            temp_file.write(session.get_file(r'C:\Windows\CarbonBlack\Reports\Antimalware_Events.txt', timeout=custom_timeout))  # Write the HTML file from the endpoint to temp_file
                            temp_file.close()
                            yield StatusMessage('[SUCCESS] Retrieved Microsoft Antimalware events data file from Sensor!')
                            if os.stat(temp_file.name).st_size == 0: yield StatusMessage('[SUCCESS] Microsoft Antimalware events data file is empty. Skipping...')  # If file is empty, don't send
                            else:
                                self.rest_client().post_attachment('/incidents/{0}/attachments'.format(incident_id), temp_file.name, '{0}-Antimalware_Events.txt'.format(sensor.hostname))  # Post temp_file to incident
                                yield StatusMessage('[SUCCESS] Posted Microsoft Antimalware events data file to the incident as an attachment!')

                        finally:
                            os.unlink(temp_file.name)  # Delete temporary temp_file

                    with tempfile.NamedTemporaryFile(delete=False) as temp_file:  # Create temporary temp_file for TXT file
                        try:
                            file_size = session.list_directory(r'C:\Windows\CarbonBlack\Reports\Defender_Events.txt')[0]['size']  # File size in bytes
                            custom_timeout = int((file_size / TRANSFER_RATE) + 120)  # The expected timeout duration + 120 seconds for good measure
                            temp_file.write(session.get_file(r'C:\Windows\CarbonBlack\Reports\Defender_Events.txt', timeout=custom_timeout))  # Write the HTML file from the endpoint to temp_file
                            temp_file.close()
                            yield StatusMessage('[SUCCESS] Retrieved Windows Defender events data file from Sensor!')

                            if os.stat(temp_file.name).st_size == 0: yield StatusMessage('[SUCCESS] Windows Defender events data file is empty. Skipping...')  # If file is empty, don't send
                            elif os.stat(temp_file.name).st_size <= MAX_UPLOAD_SIZE:
                                self.rest_client().post_attachment('/incidents/{0}/attachments'.format(incident_id), temp_file.name, '{0}-Defender_Events.txt'.format(sensor.hostname))  # Post temp_file to incident
                                yield StatusMessage('[SUCCESS] Posted Windows Defender events data file to the incident as an attachment!')
                            else:
                                if not os.path.exists(os.path.normpath('/mnt/cyber-sec-forensics/Resilient/{0}'.format(incident_id))): os.makedirs('/mnt/cyber-sec-forensics/Resilient/{0}'.format(incident_id))
                                shutil.copyfile(temp_file.name, '/mnt/cyber-sec-forensics/Resilient/{0}/{1}-Defender_Events-{2}.txt'.format(incident_id, sensor.hostname, str(int(time.time()))))  # Post temp_file to network share
                                yield StatusMessage('[SUCCESS] Posted Windows Defender events data file to the forensics network share!')

                        finally:
                            os.unlink(temp_file.name)  # Delete temporary temp_file

                    session.delete_file(r'C:\Windows\CarbonBlack\Reports\Antimalware_Events.txt')
                    session.delete_file(r'C:\Windows\CarbonBlack\Reports\Defender_Events.txt')

                except TimeoutError:  # Catch TimeoutError and handle
                    timeouts = timeouts + 1
                    if timeouts <= MAX_TIMEOUTS:
                        yield StatusMessage('[ERROR] TimeoutError was encountered. Reattempting... (' + str(timeouts) + '/' + str(MAX_TIMEOUTS) + ')')
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
                        yield StatusMessage('[ERROR] Carbon Black was unreachable. Reattempting in 30 minutes... (' + str(timeouts) + '/' + str(MAX_TIMEOUTS) + ')')
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

            # Release the host lock if acquired
            if lock_acquired is True:
                os.remove(lock_file)

            # Produce a FunctionResult with the results
            yield FunctionResult(results)
        except Exception:
            yield FunctionError()