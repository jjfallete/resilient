# -*- coding: utf-8 -*-
# pragma pylint: disable=unused-argument, no-self-use
"""Function implementation"""

import logging
import json
import urllib
from resilient_circuits import ResilientComponent, function, handler, StatusMessage, FunctionResult, FunctionError
import utilities.util.selftest as selftest

results = {}


class FunctionComponent(ResilientComponent):
    """Component that implements Resilient function 'utility_get_incident_notes"""

    def __init__(self, opts):
        """constructor provides access to the configuration options"""
        super(FunctionComponent, self).__init__(opts)
        self.options = opts.get("utilities", {})
        selftest.selftest_function(opts)

    @handler("reload")
    def _reload(self, event, opts):
        """Configuration options have changed, save new values"""
        self.options = opts.get("utilities", {})

    @function("utility_get_incident_notes")
    def _utility_get_incident_notes_function(self, event, *args, **kwargs):
        """Function: Gets an incidents notes."""
        try:
            # Get the function parameters:
            incident_id = kwargs.get("incident_id")  # number

            log = logging.getLogger(__name__)
            log.info("incident_id: %s", incident_id)

            # PUT YOUR FUNCTION IMPLEMENTATION CODE HERE
	    notes_json = self.rest_client().get("/incidents/" + str(incident_id) + "/comments?handle_format=names")
	    log.info(json.dumps(notes_json))
            for each in notes_json:
		each["text"] = (str( each["text"].encode("UTF-8", 'replace') ))

	    #  yield StatusMessage("starting...")
            #  yield StatusMessage("done...")

            results = {"notes_list" : notes_json}

            # Produce a FunctionResult with the results
            yield FunctionResult(results)
        except Exception:
            yield FunctionError()
