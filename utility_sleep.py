# -*- coding: utf-8 -*-
# pragma pylint: disable=unused-argument, no-self-use
"""Function implementation"""

import time
import logging
from resilient_circuits import ResilientComponent, function, handler, StatusMessage, FunctionResult, FunctionError
import utilities.util.selftest as selftest


class FunctionComponent(ResilientComponent):
    """Component that implements Resilient function 'utility_sleep"""

    def __init__(self, opts):
        """constructor provides access to the configuration options"""
        super(FunctionComponent, self).__init__(opts)
        self.options = opts.get("utilities", {})
        selftest.selftest_function(opts)

    @handler("reload")
    def _reload(self, event, opts):
        """Configuration options have changed, save new values"""
        self.options = opts.get("utilities", {})

    @function("utility_sleep")
    def _utility_sleep_function(self, event, *args, **kwargs):
        """Function: A basic timer (sleep)."""
        try:
            # Get the function parameters:
            time_in_seconds = kwargs.get("time_in_seconds")  # number

            log = logging.getLogger(__name__)
            log.info("time_in_seconds: %s", time_in_seconds)

            # PUT YOUR FUNCTION IMPLEMENTATION CODE HERE
            yield StatusMessage('Sleeping for ' + str(time_in_seconds) + ' seconds...')
			
	    time.sleep(int(time_in_seconds))

            results = {
                "sleep": "done"
            }

            # Produce a FunctionResult with the results
            yield FunctionResult(results)
        except Exception:
            yield FunctionError()
