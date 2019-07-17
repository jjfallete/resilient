# -*- coding: utf-8 -*-
# pragma pylint: disable=unused-argument, no-self-use

# This function will convert a TXT attachment into a JSON (dictionary) structure for use in table building.
# File: utility_txt_to_json_structure.py
# Date: 07/16/2019 - Modified: 07/17/2019
# Author: Jared F

"""Function implementation"""
#   @function -> utility_txt_to_json_structure
#   @params -> integer: incident_id, integer: attachment_id, string: attachment_name, string list: split_rows_on_new_lines (optional), integer: row_limit (optional)
#   @return -> boolean: results['was_successful'], list of ordered dicts: results["json_data"]

import logging
import unicodedata
from cStringIO import StringIO
from resilient_lib import get_file_attachment
from resilient_circuits import ResilientComponent, function, handler, StatusMessage, FunctionResult, FunctionError
import utilities.util.selftest as selftest


class FunctionComponent(ResilientComponent):
    """Component that implements Resilient function 'utility_txt_to_json_structure"""

    def __init__(self, opts):
        """constructor provides access to the configuration options"""
        super(FunctionComponent, self).__init__(opts)
        self.options = opts.get("carbon_black", {})
        selftest.selftest_function(opts)

    @handler("reload")
    def _reload(self, event, opts):
        """Configuration options have changed, save new values"""
        self.options = opts.get("carbon_black", {})

    @function("utility_txt_to_json_structure")
    def _utility_txt_to_json_structure_function(self, event, *args, **kwargs):

        results = {}
        results["was_successful"] = False

        try:
            # Get the function parameters:
            incident_id = kwargs.get("incident_id")  # number
            attachment_id = kwargs.get("attachment_id")  # number
            attachment_name = kwargs.get("attachment_name")  # text (not required at this time)
            split_rows_on_new_lines = kwargs.get("split_rows_on_new_lines")  # bool
            row_limit = kwargs.get("row_limit")  # number (optional)

            log = logging.getLogger(__name__)  # Establish logging

            yield StatusMessage('Converting {} data to JSON...'.format(attachment_name))

            # Get the TXT file attachment by its incident and attachment IDs
            txt_file_data = get_file_attachment(self.rest_client(), incident_id, artifact_id=None, task_id=None, attachment_id=attachment_id)
            txt_file = StringIO(unicodedata.normalize("NFKD", txt_file_data.decode('utf-8', 'ignore')))

            txt_data = []

            if split_rows_on_new_lines is True:  # Each line will be split and added to the txt_data list
                lines = txt_file.readlines()
                row_index = 0
                for line in lines:
                    row_index += 1
                    txt_data.append({'content': line})
                    if row_limit and row_index >= int(row_limit): break

            else:  # All content will be in a single item in the txt_data list
                txt_data = {'content': txt_file.read()}

            results["json_data"] = [txt_data]

            results["was_successful"] = True

            # Produce a FunctionResult with the results
            yield FunctionResult(results)
        except Exception:
            yield FunctionError()
