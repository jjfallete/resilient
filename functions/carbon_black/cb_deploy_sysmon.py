# -*- coding: utf-8 -*-
# pragma pylint: disable=unused-argument, no-self-use

# This function will deploy Sysmon (System Monitor) to an endpoint.
# File: cb_deploy_sysmon.py
# Date: 07/02/2019 - Modified: 07/02/2019
# Author: Jared F

"""Function implementation"""
#   @function -> cb_deploy_sysmon
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

PATH_TO_SYSMON = '/home/integrations/ir-tools/Sysmon.exe'  # The integration server's absolute file path to Sysmon.exe
PATH_TO_SYSMON_x64 = '/home/integrations/ir-tools/Sysmon64.exe'  # The integration server's absolute file path to Sysmon64.exe
PATH_TO_SYSMON_CONFIG = '/home/integrations/ir-tools/sysmonconfig-export.xml'  # The integration server's absolute file path to the sysmonconfig-export.xml


class FunctionComponent(ResilientComponent):
    """Component that implements Resilient function 'cb_function_base_starter"""

    def __init__(self, opts):
        """constructor provides access to the configuration options"""
        super(FunctionComponent, self).__init__(opts)
        self.options = opts.get("carbon_black", {})
        selftest.selftest_function(opts)

    @handler("reload")
    def _reload(self, event, opts):
        """Configuration options have changed, save new values"""
        self.options = opts.get("carbon_black", {})

    @function("cb_deploy_sysmon")
    def _cb_deploy_sysmon_function(self, event, *args, **kwargs):

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
                yield StatusMessage('[FAILURE] Fatal error caused exit!')
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
                        yield StatusMessage('[FAILURE] Fatal error caused exit!')
                        break

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
                        break

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

                    try: session.create_directory(r'C:\Windows\CarbonBlack\Tools')
                    except TimeoutError: raise
                    except Exception: pass  # Existed already

                    if '64-bit' in sensor.os_environment_display_string:
                        path_to_sysmon_utility = PATH_TO_SYSMON_x64
                        sysmon_exe_path = r'C:\Windows\Sysmon64.exe'

                    else:
                        path_to_sysmon_utility = PATH_TO_SYSMON
                        sysmon_exe_path = r'C:\Windows\Sysmon.exe'

                    try: session.delete_file(sysmon_exe_path)
                    except TimeoutError: raise
                    except Exception: pass  # Didn't exist already or Sysmon is running

                    try: session.delete_file(r'C:\Windows\CarbonBlack\Tools\sysmonconfig-export.xml')
                    except TimeoutError: raise
                    except Exception: pass  # Didn't exist already

                    try: session.put_file(open(path_to_sysmon_utility, 'rb'), sysmon_exe_path)  # Place Sysmon on the endpoint
                    except TimeoutError: raise
                    except Exception: pass  # Sysmon is already running

                    session.put_file(open(PATH_TO_SYSMON_CONFIG, "rb"), r'C:\Windows\CarbonBlack\Tools\sysmonconfig-export.xml')

                    output = session.create_process(r'{0} -accepteula -i C:\Windows\CarbonBlack\Tools\sysmonconfig-export.xml'.format(sysmon_exe_path), True)  # Install Sysmon

                    if ('sysmon installed.' in output.lower() and 'sysmon started.' in output.lower()) or ('sysmon64 installed.' in output.lower() and 'sysmon64 started.' in output.lower()):
                        yield StatusMessage('[SUCCESS] Sysmon installed successfully!')

                    elif 'is already registered.' in output or 'unsupported schema version' in output:
                        sysmon_uninstalled = False
                        yield StatusMessage('[WARNING] Sysmon is already installed!')
                        yield StatusMessage('[WARNING] Performing Sysmon re-install...')
                        yield StatusMessage('[WARNING] Removing Sysmon from endpoint...')

                        try:  # Try to uninstall Sysmon
                            session.create_process(r'net stop Sysmon & sc delete Sysmon', True, None, None, 60, True)  # Stop and delete Sysmon service
                            session.create_process(r'net stop Sysmon64 & sc delete Sysmon64', True, None, None, 60, True)  # Stop and delete Sysmon x64 service
                            session.create_process(r'net stop SysmonDrv & sc delete SysmonDrv', True, None, None, 60, True)  # Stop and delete Sysmon driver service

                            try: output = session.create_process(r'C:\Windows\Sysmon.exe -u', True, None, None, 300, True)  # Uninstall Sysmon
                            except TimeoutError: raise
                            except Exception: pass

                            try: output = session.create_process(r'C:\Windows\Sysmon64.exe -u', True, None, None, 300, True)  # Uninstall Sysmon x64
                            except TimeoutError: raise
                            except Exception: pass

                            if "Use '-u force' to force an uninstall" in output:
                                try: output = session.create_process(r'C:\Windows\Sysmon.exe -u force', True, None, None, 300, True)  # Uninstall Sysmon with force if requested (Sysmon 2019+)
                                except TimeoutError: raise
                                except Exception: pass

                                try: output = session.create_process(r'C:\Windows\Sysmon64.exe -u force', True, None, None, 300, True)  # Uninstall Sysmon x64 with force if requested (Sysmon 2019+)
                                except TimeoutError: raise
                                except Exception: pass

                            try:  # Kill any running Sysmon process
                                process_list = session.list_processes()
                                for process in (process for process in process_list if r'c:\windows\sysmon' in process['path'].lower()): session.kill_process(process['pid'])
                            except TimeoutError: raise
                            except Exception: pass  # No Sysmon processes were running

                            try: session.delete_file(r'C:\Windows\Sysmon.exe')  # Delete Sysmon
                            except TimeoutError: raise
                            except Exception: pass  # Didn't exist already

                            try: session.delete_file(r'C:\Windows\Sysmon64.exe')  # Delete Sysmon x64
                            except TimeoutError: raise
                            except Exception: pass  # Didn't exist already

                            try: session.delete_file(r'C:\Windows\SysmonDrv.sys')  # Delete sysmonDrv.sys
                            except TimeoutError: raise
                            except Exception: pass  # Didn't exist already

                            sysmon_uninstalled = True
                            yield StatusMessage('[SUCCESS] Removed Sysmon!')
                            log.info('[DEBUG] Removal output was: \n' + output)

                        except TimeoutError: raise

                        except Exception as err:
                            if sysmon_uninstalled is True: pass  # Sysmon was uninstalled
                            else: yield StatusMessage('[ERROR] Sysmon uninstall failed. Returned output during uninstall attempt was:\n\n' + str(output))

                        try:
                            session.put_file(open(path_to_sysmon_utility, 'rb'), sysmon_exe_path)  # Place sysmon on the endpoint in CB tools
                            output = session.create_process(r'{0} -accepteula -i C:\Windows\CarbonBlack\Tools\sysmonconfig-export.xml'.format(sysmon_exe_path), True)  # Install Sysmon
                            if ('sysmon installed.' in output.lower() and 'sysmon started.' in output.lower()) or ('sysmon64 installed.' in output.lower() and 'sysmon64 started.' in output.lower()):
                                yield StatusMessage('[SUCCESS] Sysmon installed successfully!')
                            else:
                                raise
                        except TimeoutError: raise
                        except Exception:
                            session.delete_file(r'C:\Windows\CarbonBlack\Tools\sysmonconfig-export.xml')
                            raise Exception('[ERROR] Sysmon re-install failed. Returned output during re-install was:\n\n' + str(output))

                    elif 'Error copying sysmon in systemroot' in output or 'it is being used by another process' in output:
                        sysmon_uninstalled = False
                        yield StatusMessage('[WARNING] Sysmon is already installed!')
                        yield StatusMessage('[WARNING] Performing Sysmon re-install...')
                        yield StatusMessage('[WARNING] Removing Sysmon from endpoint...')

                        try:  # Try to uninstall Sysmon
                            session.create_process(r'net stop Sysmon & sc delete Sysmon', True, None, None, 60, True)  # Stop and delete Sysmon service
                            session.create_process(r'net stop Sysmon64 & sc delete Sysmon64', True, None, None, 60, True)  # Stop and delete Sysmon x64 service
                            session.create_process(r'net stop SysmonDrv & sc delete SysmonDrv', True, None, None, 60, True)  # Stop and delete Sysmon driver service

                            try: output = session.create_process(r'C:\Windows\Sysmon.exe -u', True, None, None, 300, True)  # Uninstall Sysmon
                            except TimeoutError: raise
                            except Exception: pass

                            try: output = session.create_process(r'C:\Windows\Sysmon64.exe -u', True, None, None, 300, True)  # Uninstall Sysmon x64
                            except TimeoutError: raise
                            except Exception: pass

                            if "Use '-u force' to force an uninstall" in output:
                                try: output = session.create_process(r'C:\Windows\Sysmon.exe -u force', True, None, None, 300, True)  # Uninstall Sysmon with force if requested (Sysmon 2019+)
                                except TimeoutError: raise
                                except Exception: pass

                                try: output = session.create_process(r'C:\Windows\Sysmon64.exe -u force', True, None, None, 300, True)  # Uninstall Sysmon x64 with force if requested (Sysmon 2019+)
                                except TimeoutError: raise
                                except Exception: pass

                            try:  # Kill any running Sysmon process
                                process_list = session.list_processes()
                                for process in (process for process in process_list if r'c:\windows\sysmon' in process['path'].lower()): session.kill_process(process['pid'])
                            except TimeoutError: raise
                            except Exception: pass  # No Sysmon processes were running

                            try: session.delete_file(r'C:\Windows\Sysmon.exe')  # Delete Sysmon
                            except TimeoutError: raise
                            except Exception: pass  # Didn't exist already

                            try: session.delete_file(r'C:\Windows\Sysmon64.exe')  # Delete Sysmon x64
                            except TimeoutError: raise
                            except Exception: pass  # Didn't exist already

                            try: session.delete_file(r'C:\Windows\SysmonDrv.sys')  # Delete sysmonDrv.sys
                            except TimeoutError: raise
                            except Exception: pass  # Didn't exist already

                            sysmon_uninstalled = True
                            yield StatusMessage('[SUCCESS] Removed Sysmon!')
                            log.info('[DEBUG] Removal output was: \n' + output)

                        except TimeoutError: raise

                        except Exception:
                            if sysmon_uninstalled is True: pass  # Sysmon was uninstalled
                            else: yield StatusMessage('[ERROR] Sysmon uninstall failed. Returned output during uninstall attempt was:\n\n' + str(output))

                        try:
                            session.put_file(open(path_to_sysmon_utility, 'rb'), sysmon_exe_path.replace(r'C:\Windows', r'C:\Windows\CarbonBlack\Tools'))  # Place sysmon on the endpoint in CB tools
                            output = session.create_process(r'{0} -accepteula -i C:\Windows\CarbonBlack\Tools\sysmonconfig-export.xml'.format(sysmon_exe_path.replace(r'C:\Windows', r'C:\Windows\CarbonBlack\Tools')), True)  # Install Sysmon
                            if ('sysmon installed.' in output.lower() and 'sysmon started.' in output.lower()) or ('sysmon64 installed.' in output.lower() and 'sysmon64 started.' in output.lower()):
                                yield StatusMessage('[SUCCESS] Sysmon installed successfully!')
                            else:
                                raise
                        except TimeoutError: raise
                        except Exception:
                            session.delete_file(r'C:\Windows\CarbonBlack\Tools\sysmonconfig-export.xml')
                            raise Exception('[ERROR] Sysmon re-install failed. Returned output during re-install was:\n\n' + str(output))

                    else:
                        session.delete_file(r'C:\Windows\CarbonBlack\Tools\sysmonconfig-export.xml')
                        raise Exception('[ERROR] Sysmon install failed. Returned output during install was:\n\n' + str(output))

                    session.delete_file(r'C:\Windows\CarbonBlack\Tools\sysmonconfig-export.xml')

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
