# -*- coding: utf-8 -*-
# pragma pylint: disable=unused-argument, no-self-use

# This function will convert a CSV attachment into a JSON (dictionary) structure for use in table building.
# File: utility_csv_to_json_structure.py
# Date: 07/10/2019 - Modified: 08/17/2019
# Author: Jared F

"""Function implementation"""
#   @function -> utility_csv_to_json_structure
#   @params -> integer: incident_id, integer: attachment_id, string: attachment_name, string list: csv_fields (optional),
#               table_fields (optional), integer: row_limit (optional), integer: column_limit (optional)
#   @return -> boolean: results['was_successful'], list of ordered dicts: results["json_data"], tuple: results["fieldnames"]

import csv
import logging
import unicodedata
from cStringIO import StringIO
from collections import OrderedDict
from resilient_lib import get_file_attachment
from resilient_circuits import ResilientComponent, function, handler, StatusMessage, FunctionResult, FunctionError
import utilities.util.selftest as selftest


class FunctionComponent(ResilientComponent):
    """Component that implements Resilient function 'utility_csv_to_json_structure"""

    def __init__(self, opts):
        """constructor provides access to the configuration options"""
        super(FunctionComponent, self).__init__(opts)
        self.options = opts.get("carbon_black", {})
        selftest.selftest_function(opts)

    @handler("reload")
    def _reload(self, event, opts):
        """Configuration options have changed, save new values"""
        self.options = opts.get("carbon_black", {})

    @function("utility_csv_to_json_structure")
    def _utility_csv_to_json_structure_function(self, event, *args, **kwargs):

        results = {}
        results["was_successful"] = False

        try:
            # Get the function parameters:
            incident_id = kwargs.get("incident_id")  # number
            attachment_id = kwargs.get("attachment_id")  # number
            csv_filename = kwargs.get("attachment_name")  # text (not required at this time)
            csv_fields = kwargs.get("csv_fields")  # text list (optional) (ie: inputs.csv_fields = "Name", "LastAccessTime", "Field To Skip" "CreationTime")
            table_fields = kwargs.get("table_fields")  # text list (optional) (ie: inputs.table_fields = "Name", "LastAccessTime", "CreationTime")
            row_limit = kwargs.get("row_limit")  # number (optional)
            column_limit = kwargs.get("column_limit")  # number (optional)

            log = logging.getLogger(__name__)  # Establish logging

            # Get the CSV file attachment by its incident and attachment IDs
            csv_file_data = get_file_attachment(self.rest_client(), incident_id, artifact_id=None, task_id=None, attachment_id=attachment_id)
            csv_file = StringIO(unicodedata.normalize("NFKD", csv_file_data.decode('utf-8', 'ignore')))
            try:
                csv_dialect = csv.Sniffer().sniff(csv_file.readline())
                csv_delimiter = csv_dialect.delimiter
            except:
                csv_dialect = None
                csv_delimiter = ','
            csv_file.seek(0)

            # Clean the pre-processor provided csv_fields to ensure a clean tuple
            if csv_fields:
                if ',' in csv_fields and '[' not in csv_fields:
                    if '(' not in csv_fields: csv_fields = str('(' + csv_fields + ')')
                    csv_fields = tuple(item.strip() for item in csv_fields.replace('(', '').replace(')', '').replace("'", ',').split(','))
                elif '[' in csv_fields: csv_fields = tuple([row.strip(' ') for row in csv_fields.strip('][').split(',')])
                else: csv_fields = tuple(csv_fields)

            # Clean the pre-processor provided table_fields to ensure a clean tuple
            if table_fields:
                if ',' in table_fields and '[' not in table_fields:
                    if '(' not in table_fields: table_fields = str('(' + table_fields + ')')
                    table_fields = tuple(item.strip() for item in table_fields.replace('(', '').replace(')', '').replace("'", ',').split(','))
                elif '[' in table_fields: table_fields = tuple([row.strip(' ') for row in table_fields.strip('][').split(',')])
                else: table_fields = tuple(table_fields)

            # If csv_fields is not provided
            if not csv_fields:
                csv_fields = None  # Use first row as keys

            # If csv_fields is the same as the first row of the data
            if csv_fields == (csv_file_data.partition('\n')[0]):
                next(csv_file)  # Pass over first row

            yield StatusMessage('Converting {} data to JSON...'.format(csv_filename))

            csv_data = csv.DictReader((line.replace('\0', '') for line in csv_file), fieldnames=csv_fields, dialect='excel', delimiter=csv_delimiter)

            if not table_fields:
                table_fields = csv_data.fieldnames

            # Python 2 returns an unordered dictionary from csv.DictReader(), but using the order of fieldnames, we can reorder using OrderedDict and lambda
            order_maintained_rows = []
            row_index = 0
            for row in csv_data:
                if not any([str(value).strip() for value in row.values()]): continue  # Skip empty rows
                row_index += 1
                row_dict = dict(filter(lambda i: i[0] in table_fields, row.items()))  # Remove row items not included in table_fields
                fieldnames_tuple = tuple(filter(lambda i: i in row_dict.keys(), table_fields))  # Remove table_fields not found in row items
                if column_limit and int(column_limit) < row.items():
                    order_maintained_rows.append(OrderedDict(sorted(row_dict.items(), key=lambda item: fieldnames_tuple.index(item[0]))[:int(column_limit)]))
                else:
                    order_maintained_rows.append(OrderedDict(sorted(row_dict.items(), key=lambda item: fieldnames_tuple.index(item[0]))))
                if row_limit and row_index >= int(row_limit): break

            results["json_data"] = order_maintained_rows
            results["fieldnames"] = table_fields
            results["was_successful"] = True

            # Produce a FunctionResult with the results
            yield FunctionResult(results)
        except Exception:
            yield FunctionError()
