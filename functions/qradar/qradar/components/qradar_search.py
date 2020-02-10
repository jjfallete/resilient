# -*- coding: utf-8 -*-
#
# (c) Copyright IBM Corp. 2018. All Rights Reserved.
#
# pragma pylint: disable=unused-argument, no-self-use
"""Function implementation"""

import os
import csv
import shutil
import zipfile
import tempfile
import logging
from resilient_circuits import ResilientComponent, function, handler, StatusMessage, FunctionResult, FunctionError
from qradar.util.qradar_utils import QRadarClient
from qradar.util import function_utils

MAX_UPLOAD_SIZE = 50*1000000  # Maximum number of bytes of files to upload as an attachment before reverting to a network share drop, default = 50MB
NET_SHARE_PATH = r'/mnt/cyber-sec-forensics/Resilient'  # Network share path accessible to Resilient Circuits


class FunctionComponent(ResilientComponent):
    """Component that implements Resilient function 'qradar_search"""

    def __init__(self, opts):
        """constructor provides access to the configuration options"""
        super(FunctionComponent, self).__init__(opts)
        self.options = opts.get("qradar", {})

    @handler("reload")
    def _reload(self, event, opts):
        """Configuration options have changed, save new values"""
        self.options = opts.get("qradar", {})

    @function("qradar_search")
    def _qradar_search_function(self, event, *args, **kwargs):

        results = {}

        try:
            # Get the function parameters:
            incident_id = kwargs.get("incident_id")  # number
            qradar_query = self.get_textarea_param(kwargs.get("qradar_query"))  # textarea
            qradar_query_range_start = kwargs.get("qradar_query_range_start")  # number
            qradar_query_range_end = kwargs.get("qradar_query_range_end")  # number
            qradar_query_timeout_mins = kwargs.get("qradar_query_timeout_mins")  # number

            # Get app.config vars
            qradar_config = self.opts.get("qradar")
            host = qradar_config.get("host")
            qradartoken = qradar_config.get("qradartoken")

            log = logging.getLogger(__name__)

            qradar_verify_cert = False

            if qradar_query_timeout_mins is None: qradar_query_timeout = float(86400)  # Default: 1 day
            else: qradar_query_timeout = float(qradar_query_timeout_mins*60)

            #try:
            log.debug('[INFO] Connecting to QRadar API...')
            qradar_client = QRadarClient(host=host, username=None, password=None, token=qradartoken, cafile=qradar_verify_cert)

            yield StatusMessage('[INFO] Running QRadar search query...')
            log.info('[INFO] QRadar search query: ' + qradar_query)
            query_result = qradar_client.ariel_search(qradar_query, range_start=qradar_query_range_start, range_end=qradar_query_range_end, timeout=qradar_query_timeout)

            yield StatusMessage('[INFO] Search query completed!')

            with tempfile.NamedTemporaryFile(delete=False) as temp_zip:  # Create temporary temp_zip for creating zip_file
                try:
                    with zipfile.ZipFile(temp_zip, 'w') as zip_file:  # Establish zip_file from temporary temp_zip for packaging CSV into
                        with tempfile.NamedTemporaryFile(delete=False) as temp_file:  # Create temp_file for CSV
                            try:
                                if len(query_result['events']) == 0:
                                    yield StatusMessage('[INFO] No matching events found.')
                                    temp_file.write('No matching events.')
                                else:
                                    yield StatusMessage('[INFO] ' + str(len(query_result['events'])) + ' matching events found.')
                                    csv_writer = csv.writer(temp_file)
                                    csv_writer.writerow(query_result['events'][0].keys())  # header row
                                    for row in query_result['events']:
                                        csv_writer.writerow(row.values())  # values row
                                temp_file.close()
                                zip_file.write(temp_file.name, 'QRadar_Search_Query_Results.csv', compress_type=zipfile.ZIP_DEFLATED)  # Write temp_file into zip_file

                            finally:
                                os.unlink(temp_file.name)  # Delete temporary temp_file

                    if os.stat(temp_zip.name).st_size <= MAX_UPLOAD_SIZE:
                        self.rest_client().post_attachment('/incidents/{0}/attachments'.format(incident_id), temp_zip.name, 'QRadar_Search_Query_Results{0}.zip'.format(''))  # Post temp_zip to incident
                        yield StatusMessage('[SUCCESS] Posted ZIP file of QRadar Search Query to the incident as an attachment!')
                    else:
                        if not os.path.exists(os.path.normpath(NET_SHARE_PATH + '/{0}'.format(incident_id))): os.makedirs('/{0}'.format(incident_id))
                        shutil.copyfile(temp_zip.name, NET_SHARE_PATH + '/{0}/QRadar_Search_Query_Results{1}.zip'.format(incident_id, ''))  # Post temp_zip to network share
                        yield StatusMessage('[SUCCESS] Posted ZIP file of QRadar Search Query to the forensics network share!')

                finally:
                    os.unlink(temp_zip.name)  # Delete temporary temp_file

            #else:
            results["was_successful"] = True
            results["events"] = query_result['events']

            # Produce a FunctionResult with the results
            yield FunctionResult(results)
        except Exception:
            yield FunctionError()
