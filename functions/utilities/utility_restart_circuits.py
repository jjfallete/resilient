# -*- coding: utf-8 -*-
# pragma pylint: disable=unused-argument, no-self-use

# This function will restart Resilient Circuits.
# File: utility_restart_circuits.py
# Date: 04/26/2019 - Modified: 07/10/2019
# Author: Jared F

"""Function implementation"""
#   @function -> utility_restart_resilient_circuits
#   @params -> None
#   @return -> boolean: results['was_successful']


import os
import time
import shutil
import logging
import datetime
from resilient_circuits import ResilientComponent, function, handler, StatusMessage, FunctionResult, FunctionError
import utilities.util.selftest as selftest


class FunctionComponent(ResilientComponent):
    """Component that implements Resilient function 'utility_restart_resilient_circuits"""

    def __init__(self, opts):
        """constructor provides access to the configuration options"""
        super(FunctionComponent, self).__init__(opts)
        self.options = opts.get("carbon_black", {})
        selftest.selftest_function(opts)

    @handler("reload")
    def _reload(self, event, opts):
        """Configuration options have changed, save new values"""
        self.options = opts.get("carbon_black", {})

    @function("utility_restart_resilient_circuits")
    def _utility_restart_resilient_circuits_function(self, event, *args, **kwargs):

        results = {}
        results["was_successful"] = False

        try:
            # Get the function parameters:
            reboot_server = kwargs.get("reboot_server")  # boolean

            if os.path.exists('/home/integrations/.resilient/rc_restarted.lock') is False:
                open('/home/integrations/.resilient/rc_restarted.lock', 'w+').close()
                if os.path.exists('/home/integrations/.resilient/rc_restarted.lock') is False: raise IOError
                if reboot_server is True:
                    yield StatusMessage('[INFO] Rebooting the Resilient integrations server...')
                    os.system('reboot')
                else:
                    yield StatusMessage('[INFO] Restarting the Resilient Circuits service...')
                    os.system("sudo systemctl restart resilient_circuits.service")

            else:
                os.remove('/home/integrations/.resilient/rc_restarted.lock')
                if reboot_server is True: yield StatusMessage('[SUCCESS] Reboot completed!')
                else: yield StatusMessage('[SUCCESS] Restart completed!')

        except Exception as err:  # Catch all exceptions and abort
            try: os.remove('/home/integrations/.resilient/rc_restarted.lock')
            except: pass
            yield StatusMessage('[FATAL ERROR] Encountered: ' + str(err))
            yield StatusMessage('[FAILURE] Fatal error caused exit!')

            # Produce a FunctionResult with the results
            yield FunctionResult(results)
        except Exception:
            yield FunctionError()
