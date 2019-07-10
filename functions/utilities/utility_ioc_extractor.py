# -*- coding: utf-8 -*-
# pragma pylint: disable=unused-argument, no-self-use

# This function will extract IPv4s, IPv6s, URLs, the domains of each URL, email addresses, the domains of each email address, MD5 hashes, and SHA256 hashes from a text string.
# File: utility_ioc_extractor.py
# Date: 07/10/2019 - Modified: 07/10/2019
# Author: Jared F

"""Function implementation"""
#   @function -> utility_ioc_extractor
#   @params -> integer: incident_id, string: text_string
#   @return -> boolean: results['was_successful'], list: results["ipv4s"], list: results["ipv6s"], list: results["urls"], list: results["domains"],
#               list: results["email_addresses"], list: results["email_domains"], list: results["md5_hashes"], list: results["sha256_hashes"]

import logging
import iocextract  # Need to pip install
import unicodedata
from bs4 import BeautifulSoup  # Need to pip install
from urlparse import urlparse
from collections import OrderedDict
from resilient_circuits import ResilientComponent, function, handler, StatusMessage, FunctionResult, FunctionError
import utilities.util.selftest as selftest


class FunctionComponent(ResilientComponent):
    """Component that implements Resilient function 'utility_ioc_extractor"""

    def __init__(self, opts):
        """constructor provides access to the configuration options"""
        super(FunctionComponent, self).__init__(opts)
        self.options = opts.get("carbon_black", {})
        selftest.selftest_function(opts)

    @handler("reload")
    def _reload(self, event, opts):
        """Configuration options have changed, save new values"""
        self.options = opts.get("carbon_black", {})

    @function("utility_ioc_extractor")
    def _utility_ioc_extractor_function(self, event, *args, **kwargs):

        results = {}
        results["was_successful"] = False

        try:
            # Get the function parameters:
            incident_id = kwargs.get("incident_id")  # number
            text_string = kwargs.get("text_string")  # text

            log = logging.getLogger(__name__)  # Establish logging

            text_string = unicodedata.normalize("NFKD", BeautifulSoup(text_string, "html.parser").get_text(' '))  # Strip HTML and normalize text

            # Parse IOCs by type from text_string - OrderedDict.fromkeys() preserves order and removes duplicates.
            results["ipv4s"] = list(OrderedDict.fromkeys(list(iocextract.extract_ipv4s(text_string, refang=True))))
            results["ipv6s"] = list(OrderedDict.fromkeys(list(iocextract.extract_ipv6s(text_string))))
            results["urls"] =  list(OrderedDict.fromkeys(list(iocextract.extract_urls(text_string, refang=True))))  # URLs and domains
            results["domains"] = list(OrderedDict.fromkeys([urlparse(url).netloc for url in results["urls"]]))  # domains only
            results["email_addresses"] = list(OrderedDict.fromkeys(list(iocextract.extract_emails(text_string, refang=True))))
            results["email_domains"] = list(OrderedDict.fromkeys([email.split('@')[1] for email in results["email_addresses"]]))  # domains only
            results["md5_hashes"] = list(OrderedDict.fromkeys(list(iocextract.extract_md5_hashes(text_string))))
            results["sha256_hashes"] = list(OrderedDict.fromkeys(list(iocextract.extract_sha256_hashes(text_string))))
            results["was_successful"] = True

            # Produce a FunctionResult with the results
            yield FunctionResult(results)
        except Exception:
            yield FunctionError()
