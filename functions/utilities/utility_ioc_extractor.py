# -*- coding: utf-8 -*-
# pragma pylint: disable=unused-argument, no-self-use

# This function will extract IPv4s, IPv6s, URLs, the domains of each URL, email addresses, the domains of each email address, MD5 hashes, and SHA256 hashes from a text string.
# File: utility_ioc_extractor.py
# Date: 07/10/2019 - Modified: 09/18/2019
# Author: Jared F

"""Function implementation"""
#   @function -> utility_ioc_extractor
#   @params -> integer: incident_id, string: text_string
#   @return -> boolean: results['was_successful'], list: results["ipv4s"], list: results["ipv6s"], list: results["urls"], list: results["url_domains"],
#               list: results["email_addresses"], list: results["email_domains"], list: results["md5_hashes"], list: results["sha256_hashes"]

import logging
import unicodedata
from bs4 import BeautifulSoup  # Need to pip install
from urlparse import urlparse
from collections import OrderedDict
from resilient_circuits import ResilientComponent, function, handler, StatusMessage, FunctionResult, FunctionError
import utilities.util.selftest as selftest
import utilities.util.ioc_extractor as iocextractor


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
            is_html = kwargs.get("is_html")  # boolean

            log = logging.getLogger(__name__)  # Establish logging

            if is_html is True: text_string = BeautifulSoup(text_string.replace('<span>', ''), "html.parser").get_text(' ')  # Convert HTML to plain text

            text_string = unicodedata.normalize("NFKD", text_string)  # Strip HTML and normalize text

            # Parse IOCs by type from text_string - OrderedDict.fromkeys() preserves order and removes duplicates.
            results["ipv4s"] = list(OrderedDict.fromkeys(list(iocextractor.extract_ipv4s(text_string, refang=True))))
            results["ipv6s"] = list(OrderedDict.fromkeys(list(iocextractor.extract_ipv6s(text_string))))

            results["urls"] = list(OrderedDict.fromkeys(list(iocextractor.extract_urls(text_string, refang=True))))  # URLs

            url_domains = []
            for parsed_url in [urlparse(url) for url in results["urls"]]:
                if parsed_url.netloc: parsed_url = parsed_url.netloc
                elif parsed_url.path: parsed_url = str(parsed_url.path).split('/')[0]
                if parsed_url.startswith('www.'): parsed_url = parsed_url.replace('www.', '', 1)
                url_domains.append(parsed_url)
            results["url_domains"] = list(OrderedDict.fromkeys(url_domains))  # URL domains

            results["email_addresses"] = list(OrderedDict.fromkeys(list(iocextractor.extract_emails(text_string, refang=True))))
            results["email_domains"] = list(OrderedDict.fromkeys([email.split('@')[1] for email in results["email_addresses"]]))  # Email domains

            results["md5_hashes"] = list(OrderedDict.fromkeys(list(iocextractor.extract_md5_hashes(text_string))))
            results["sha256_hashes"] = list(OrderedDict.fromkeys(list(iocextractor.extract_sha256_hashes(text_string))))

            results["was_successful"] = True

            # Produce a FunctionResult with the results
            yield FunctionResult(results)
        except Exception:
            yield FunctionError()
