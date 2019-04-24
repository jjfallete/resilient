# -*- coding: utf-8 -*-
# pragma pylint: disable=unused-argument, no-self-use

# This function will retrieve user account data from an endpoint as an HTML data file.
# File: cb_retrieve_user_accounts_data.py
# Date: 04/15/2019 - Modified: 04/15/2019
# Author: Jared F

"""Function implementation"""
#   @function -> cb_retrieve_user_accounts_data
#   @params -> integer: incident_id, string: hostname
#   @return -> boolean: results['was_successful'], string: results['hostname']


import os
import time
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
PATH_TO_UTILITY = '/home/integrations/ir-tools/UserProfilesView.exe'  # The integration server's absolute file path to the BrowsingHistoryView.exe utility


class FunctionComponent(ResilientComponent):
    """Component that implements Resilient function 'cb_retrieve_user_accounts_data"""

    def __init__(self, opts):
        """constructor provides access to the configuration options"""
        super(FunctionComponent, self).__init__(opts)
        self.options = opts.get("carbon_black", {})
        selftest.selftest_function(opts)

    @handler("reload")
    def _reload(self, event, opts):
        """Configuration options have changed, save new values"""
        self.options = opts.get("carbon_black", {})

    @function("cb_retrieve_user_accounts_data")
    def _cb_retrieve_user_accounts_data_function(self, event, *args, **kwargs):

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

                    try: session.create_directory('C:\Windows\CarbonBlack\Reports')
                    except TimeoutError: raise TimeoutError(message=err)
                    except Exception: pass  # Existed already

                    try: session.create_directory(r'C:\Windows\CarbonBlack\Tools')
                    except TimeoutError: raise TimeoutError(message=err)
                    except Exception: pass  # Existed already

                    try: session.delete_file(r'C:\Windows\CarbonBlack\Tools\UPV.exe')
                    except TimeoutError: raise TimeoutError(message=err)
                    except Exception: pass  # Didn't exist already

                    session.put_file(open(PATH_TO_UTILITY, 'rb'), r'C:\Windows\CarbonBlack\Tools\UPV.exe')  # Place the utility on the endpoint

                    session.create_process(r'C:\Windows\CarbonBlack\Tools\UPV.exe /shtml "C:\Windows\CarbonBlack\Reports\ua-dump.html" /sort "User Name"', True)  # Execute the utility
                    yield StatusMessage('[SUCCESS] Executed UPV.exe on Sensor!')

                    with tempfile.NamedTemporaryFile(delete=False) as temp_file:  # Create temporary temp_file for HTML file
                        try:
                            temp_file.write(session.get_file(r'C:\Windows\CarbonBlack\Reports\ua-dump.html'))  # Write the HTML file from the endpoint to temp_file
                            temp_file.close()
                            yield StatusMessage('[SUCCESS] Retrieved HTML data file from Sensor!')
                            self.rest_client().post_attachment('/incidents/{0}/attachments'.format(incident_id), temp_file.name, '{0}-user_accounts.html'.format(sensor.hostname))  # Post temp_file to incident
                            yield StatusMessage('[SUCCESS] Posted HTML data file to the incident as an attachment!')

                        finally:
                            os.unlink(temp_file.name)  # Delete temporary temp_file

                    session.delete_file(r'C:\Windows\CarbonBlack\Tools\UPV.exe')
                    session.delete_file(r'C:\Windows\CarbonBlack\Reports\ua-dump.html')

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