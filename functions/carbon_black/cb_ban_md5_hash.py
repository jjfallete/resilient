# -*- coding: utf-8 -*-
# pragma pylint: disable=unused-argument, no-self-use

# This function will ban an MD5 hash in Carbon Black, preventing execution of the file on endpoints.
# File: cb_ban_md5_hash.py
# Date: 02/27/2019 - Modified: 03/18/2019
# Author: Jared F

"""Function implementation"""
#   @function -> cb_ban_md5_hash
#   @params -> string: md5_hash, string: ban_reason, boolean string: override_failing_if_hash_seen
#   @return -> boolean: results['was_successful'], integer: results['seen_on_count']

import logging
from resilient_circuits import ResilientComponent, function, handler, StatusMessage, FunctionResult, FunctionError
from cbapi.response import CbEnterpriseResponseAPI, Binary, BannedHash
from cbapi.errors import ObjectNotFoundError, InvalidHashError
import carbon_black.util.selftest as selftest

c = CbEnterpriseResponseAPI()


class FunctionComponent(ResilientComponent):
    """Component that implements Resilient function 'cb_ban_md5_hash"""

    def __init__(self, opts):
        """constructor provides access to the configuration options"""
        super(FunctionComponent, self).__init__(opts)
        self.options = opts.get("carbon_black", {})
        selftest.selftest_function(opts)

    @handler("reload")
    def _reload(self, event, opts):
        """Configuration options have changed, save new values"""
        self.options = opts.get("carbon_black", {})

    @function("cb_ban_md5_hash")
    def _cb_ban_md5_hash_function(self, event, *args, **kwargs):

        results = {}

        try:
            # Get the function parameters:
            incident_id = kwargs.get("incident_id")  # number
            md5_hash = kwargs.get("md5_hash")  # text
            ban_reason = kwargs.get("ban_reason")  # text
            override_failing_if_hash_seen = kwargs.get("override_failing_if_hash_seen")  # text

            log = logging.getLogger(__name__)  # Establish logging

            try:
                results["seen_on_count"] = 0
                binary = c.select(Binary, md5_hash)  # Try to get the binary data if it has been seen in the environment

                seen_on_count = len(binary.endpoints)  # Number of endpoints with the binary
                results["seen_on_count"] = seen_on_count
                binary_file = str(binary.internal_name.encode('ascii', 'ignore').decode('ascii'))  # The binary file name (.exe or .dll)
                binary_name = str(binary.product_name.encode('ascii', 'ignore').decode('ascii'))  # The binary name

                if binary.banned is not False:  # If the hash is banned already
                    yield StatusMessage('[FAILURE] Hash ' + str(md5_hash) + ' is already banned!')
                    results["was_successful"] = False
                    yield FunctionResult(results)
                    return

                elif seen_on_count > 0:
                    yield StatusMessage('[WARNING] This hash has been seen on: ' + str(seen_on_count) + ' endpoints as ' + binary_file + ' (' + binary_name + ')')

                    if override_failing_if_hash_seen is not True:
                        yield StatusMessage('[FAILURE] Could not ban active hash ' + str(md5_hash) + '. Try again with override enabled if ban is still desired.')
                        results["was_successful"] = False
                        yield FunctionResult(results)
                        return

            except (ObjectNotFoundError, InvalidHashError): pass  # No binary has been seen in the environment with the hash
            except Exception as err: yield StatusMessage('[WARNING] Encountered (but handled): ' + str(err))

            bh = c.create(BannedHash)  # Create the hash ban object
            bh.md5hash = md5_hash
            bh.text = ban_reason
            bh.enabled = True  # Enable the hash ban

            try:
                bh.save()  # Save the ban to the Carbon Black server
            except Exception as err:
                if 'Received error code 409 from API:' in str(err): yield StatusMessage('[FATAL ERROR] ' + str(err).replace('Received error code 409 from API: ', '').replace("'", '').strip())  # Already banned, not seen
                else: yield StatusMessage('[FATAL ERROR] Encountered: ' + str(err))
                yield StatusMessage('[FAILURE] Could not ban hash ' + str(md5_hash))
                results["was_successful"] = False
            else:
                yield StatusMessage('[SUCCESS] Banned hash ' + str(md5_hash))
                results["was_successful"] = True

            # Produce a FunctionResult with the results
            yield FunctionResult(results)
        except Exception:
            yield FunctionError()
