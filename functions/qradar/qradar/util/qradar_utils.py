# -*- coding: utf-8 -*-
#
# (c) Copyright IBM Corp. 2018. All Rights Reserved.
#
#   Util classes for qradar
#
import requests
import time
import base64
import logging
import qradar.util.qradar_constants as qradar_constants
import qradar.util.function_utils as function_utils
from resilient_lib import get_workflow_status


# handle python2 and 3
try:
    from urllib import quote  # Python 2.X
except ImportError:
    from urllib.parse import quote  # Python 3+

LOG = logging.getLogger(__name__)


class RequestError(Exception):
    """ Request error"""
    def __init__(self, url, message):
        fail_msg = "Request to url [{}] throws exception. Error [{}]".format(url, message)
        super(RequestError, self).__init__(fail_msg)

class DeleteError(Exception):
    """ Request error"""
    def __init__(self, url, message):
        fail_msg = "Delete request to url [{}] throws exception. Error [{}]".format(url, message)
        super(DeleteError, self).__init__(fail_msg)

class SearchTimeout(Exception):
    """ Query failed to complete in time specified """
    def __init__(self, search_id, search_status):
        fail_msg = "Query [{}] timed out. Final Status was [{}]".format(search_id, search_status)
        super(SearchTimeout, self).__init__(fail_msg)
        self.search_status = search_status

class SearchJobFailure(Exception):
    """ Search job creation failure"""
    def __init__(self, query):
        fail_msg = "Failed to create search job for query [{}] ".format(query)
        super(SearchJobFailure, self).__init__(fail_msg)

class SearchFailure(Exception):
    """ Search failed to execute """
    def __init__(self, search_id, search_status):
        fail_msg = "Query [{}] failed with status [{}]".format(search_id, str(search_status))
        super(SearchFailure, self).__init__(fail_msg)
        self.search_status = search_status


class AuthInfo(object):
    # Singleton
    __instance = None

    def __init__(self):
        self.headers = {}
        self.qradar_auth = None
        self.qradar_token = None
        self.api_url = None
        self.cafile = True
        pass

    @staticmethod
    def get_authInfo():
        if AuthInfo.__instance is None:
            AuthInfo.__instance = AuthInfo()
        return AuthInfo.__instance

    def create(self, host, username=None, password=None, token=None, cafile=None):
        """
        Create headers used for REST Api calls
        :param host: qradar host
        :param username: qradar user login
        :param password: qradar password
        :param token: Use token or username/password to auth
        :param cafile:
        :return:
        """
        self.headers = {'Accept': 'application/json'}
        if username and password:
            self.qradar_auth = base64.b64encode((username + ':' + password).encode('ascii'))
            self.headers['Authorization'] = b"Basic " + self.qradar_auth
        elif token:
            self.qradar_token = token
            self.headers["SEC"] = self.qradar_token

        self.api_url = "https://{}/api/".format(host)
        self.cafile = cafile


class ArielSearch(object):

    def __init__(self, timeout=600, polling_period=5):
        self.range_start = 0
        self.range_end = 50
        self.search_timeout = timeout
        self.polling_period = polling_period

    def set_range_start(self, start):
        """
        Set range start for ariel search
        :param start: int for range start
        :return:
        """
        self.range_start = start

    def set_range_end(self, end):
        """
        Set range end for ariel search
        :param end: int for range end
        :return:
        """
        self.range_end = end
    def set_timeout(self, timeout):
        """
        Set timeout
        :param timeout:
        :return:
        """
        self.search_timeout = timeout

    def get_search_id(self, query):
        """
        Get the search if associated with the search using query
        :param query: input query string
        :return: search_id returned from QRadar
        :raises SearchJobFailure
        """
        auth_info = AuthInfo.get_authInfo()
        url = auth_info.api_url + qradar_constants.ARIEL_SEARCHES
        utf8 = query.encode("utf-8")
        data = {"query_expression": utf8}

        search_id = ""
        try:
            response = requests.Session().post(url=url, headers=auth_info.headers, data=data, verify=auth_info.cafile)
            json = response.json()
            if "search_id" in json:
                search_id = json["search_id"]

        except Exception as e:
            LOG.error(str(e))
            raise SearchJobFailure(query)

        return search_id

    def get_search_result(self, search_id):
        """
        Get search result associated with search_id
        :param search_id:
        :return: dict with events
        :raises SearchFailure
        """
        auth_info = AuthInfo.get_authInfo()
        url = auth_info.api_url + qradar_constants.ARIEL_SEARCHES_RESULT.format(search_id)

        headers = auth_info.headers.copy()
        # if the # of returned items is big, this call will take a long time!
        # Need to use Range to limit the #.
        headers[b"Range"] = "items={}-{}".format(str(self.range_start), str(self.range_end))

        response = None
        try:
            response = requests.Session().get(url=url, headers=headers, verify=auth_info.cafile)
        except Exception as e:
            LOG.error(str(e))
            raise SearchFailure(search_id, None)

        ret = {}
        if response.status_code == 200:
            events = response.json()["events"]
            events = function_utils.fix_dict_value(events)
            ret = {"events": events}

        return ret

    def check_status(self, search_id):
        """
        Check the search status associated with search_id
        :param search_id
        :return: qradar_constants.SEARCH_STATUS_COMPLETED, qradar_constants.SEARCH_STATUS_WAIT
        :raises SearchFailure
        """
        auth_info = AuthInfo.get_authInfo()
        url = "{}{}/{}".format(auth_info.api_url, qradar_constants.ARIEL_SEARCHES, search_id)
        status = None
        try:
            response = requests.Session().get(url=url, headers=auth_info.headers, verify=auth_info.cafile)
            json_dict = response.json()
            if "status" in json_dict:
                if json_dict["status"] == qradar_constants.SEARCH_STATUS_COMPLETED:
                    status = qradar_constants.SEARCH_STATUS_COMPLETED
                elif json_dict["status"] == qradar_constants.SEARCH_STATUS_WAIT \
                    or json_dict["status"] == qradar_constants.SEARCH_STATUS_SORTING \
                        or json_dict["status"] == qradar_constants.SEARCH_STATUS_EXECUTE:
                    status = qradar_constants.SEARCH_STATUS_WAIT  # Consider WAIT, SORTING, and EXECUTE as a WAIT status.
                else:  # CANCELED or ERROR status possible here
                    raise SearchFailure(search_id, status)

        except Exception as e:
            LOG.error(str(e))
            raise SearchFailure(search_id, status)

        return status

    def cancel_search(self, search_id):
        """
        Cancels the search associated with search_id
        :param search_id
        :raises SearchJobFailure
        """
        auth_info = AuthInfo.get_authInfo()
        url = "{}{}/{}".format(auth_info.api_url, qradar_constants.ARIEL_SEARCHES, search_id)
        data = {"status": "CANCELED"}
        try:
            response = requests.Session().post(url=url, headers=auth_info.headers, data=data, verify=auth_info.cafile)
            json_dict = response.json()

            if len(json_dict) == 0 or response.status_code != 200:
                raise SearchJobFailure("Search cancellation attempted, but failed due to an invalid response code!")

        except Exception as e:
            LOG.error(str(e))
            raise SearchJobFailure("Search cancellation attempted, but failed due to an exception!")

    def perform_search(self, query, wf_bundle):
        """
        Performs an ariel search from a provided AQL query string with workflow state in mind.
        :param query: query string to perform search
        :param wf_bundle: list containing two elements, the Resilient rest_client() and the Resilient workflow_id respectively
        :return: result: search results, None returned if workflow is stopped prior to search completion
        :raises SearchFailure or SearchJobFailure
        """
        search_id = self.get_search_id(query)

        if search_id:
            start_time = time.time()  # store the start time
            done = False

            LOG.info('Ariel search started under search_id: ' + str(search_id))

            while not done:
                status = self.check_status(search_id)
                if wf_bundle:
                    if (get_workflow_status(wf_bundle[0], wf_bundle[1])).is_terminated:
                        LOG.info('Workflow terminated. Canceling search...')
                        self.cancel_search(search_id)
                        return None

                if status == qradar_constants.SEARCH_STATUS_COMPLETED:
                    done = True
                elif status == qradar_constants.SEARCH_STATUS_WAIT:
                    done = False
                else:
                    LOG.error('Unexpected search status returned of: ' + str(status))
                    raise SearchFailure(search_id, status)

                if not done:
                    # time_out defaults to 10 minutes. If customer overrides it to 0, it will never timeout
                    if self.search_timeout != 0:
                        if time.time() - start_time > self.search_timeout:
                            self.cancel_search(search_id)  # Cancel search on timeout
                            # We could return the search results instead of raising an exception, but they would be incomplete.
                            raise SearchTimeout(search_id, status)
                    time.sleep(self.polling_period)  # polling_interval is defaulted to 5 sec
        else:
            LOG.error("search_id is None")
            raise SearchJobFailure(query)

        result = self.get_search_result(search_id)

        return result


class QRadarClient(object):

    def __init__(self, host, username=None, password=None, token=None, cafile=None):
        """
        Init
        :param host:  QRadar host
        :param username: QRadar user name
        :param password: QRadar password
        :param token: QRadar token
        :param cafile: verify cert or not
        """
        auth_info = AuthInfo.get_authInfo()
        auth_info.create(host, username, password, token, cafile)

    def check_openssl(self):
        """
        Do we need to verify openssl version?
        :return:
        """

    def get_versions(self):
        """
        Util function used to test connectivity to QRadar
        :return: response of API call
        """
        auth_info = AuthInfo.get_authInfo()

        url = auth_info.api_url + qradar_constants.HELP_VERSIONS
        session = requests.Session()
        response = session.get(url, headers=auth_info.headers, verify=auth_info.cafile)

        return response

    def ariel_search(self, query, range_start=None, range_end=None, timeout=None, wf_bundle=None):
        """
        Perform an Ariel search
        :param query: query string
        :param range_start: start index of event results to return
        :param range_end: ending index of event results to return
        :param timeout: timeout for search
        :param wf_bundle: list containing two elements, the Resilient rest_client() and the Resilient workflow_id respectively
        :return: dict with events
        """
        ariel_search = ArielSearch()
        if range_start is not None:
            ariel_search.set_range_start(range_start)

        if range_end is not None:
            ariel_search.set_range_end(range_end)

        if timeout is not None:
            ariel_search.set_timeout(timeout)

        response = ariel_search.perform_search(query, wf_bundle)
        return response

    def verify_connect(self):
        """
        QRadar does not support session key. check version to verify
        Sample data
        [{"id":1,"deprecated":false,"root_resource_ids":[],"removed":true,"version":"0.1"},
        {"id":2,"deprecated":false,"root_resource_ids":[],"removed":true,"version":"0.2"},
        {"id":3,"deprecated":false,"root_resource_ids":[],"removed":true,"version":"1.0"},
        {"id":4,"deprecated":false,"root_resource_ids":[],"removed":true,"version":"2.0"},
        {"id":5,"deprecated":false,"root_resource_ids":[],"removed":true,"version":"3.0"},
        {"id":6,"deprecated":false,"root_resource_ids":[],"removed":true,"version":"3.1"},
        {"id":7,"deprecated":true,"root_resource_ids":[1,7,14,16,18,28,44,51],"removed":false,"version":"4.0"},
        {"id":8,"deprecated":true,"root_resource_ids":[62,70,76,83,85,99,102,104,114,130,137,148],"removed":false,"version":"5.0"},
        {"id":9,"deprecated":true,"root_resource_ids":[157,165,171,178,180,194,199,201,211,227,234,245],"removed":false,"version":"5.1"},
        {"id":10,"deprecated":false,"root_resource_ids":[254,262,268,275,277,291,296,303,311,327,334,347],"removed":false,"version":"6.0"},
        {"id":11,"deprecated":false,"root_resource_ids":[356,390,408,417,419,471,480,491,496,503,514,526,572,579,602,607],"removed":false,"version":"7.0"}]
        """
        resp = self.get_versions()

        connected = False
        if resp.status_code == 200 and len(resp.json()) > 0:
            if "version" in resp.json()[0]:
                connected = True

        return connected

    @staticmethod
    def get_all_ref_set():
        """
        Get a list of all the reference sets.
        :return: list of reference set names
        """
        auth_info = AuthInfo.get_authInfo()
        url = "{}{}".format(auth_info.api_url, qradar_constants.REFERENCE_SET_URL)
        ret = []
        try:
            response = requests.Session().get(url=url, headers=auth_info.headers, verify=auth_info.cafile)
            #
            # Sample return:
            """
            [
                {
                    "timeout_type": "FIRST_SEEN",
                    "number_of_elements": 0,
                    "creation_time": 1516812810600,
                    "name": "Watson Advisor: File Action Blocked",
                    "element_type": "ALNIC"
                },
                ...
            ]
            """
            #
            ret = response.json()
        except Exception as e:
            LOG.error(str(e))
            raise RequestError(url, "get_all_ref_set call failed with exception {}".format(str(e)))

        return ret

    @staticmethod
    def find_all_ref_set_contains(value, type=None):
        """

        :param value:
        :param type:
        :return:
        """
        ref_sets = QRadarClient.get_all_ref_set()
        LOG.debug(u"All reference sets: {}".format(ref_sets))

        ret = []
        for r_set in ref_sets:
            LOG.info(u"Looking for {} in reference set {}".format(value, r_set["name"]))
            element = QRadarClient.search_ref_set(r_set["name"], value)
            if element["found"] == "True":
                ret.append(element["content"])

        return ret

    @staticmethod
    def search_ref_set(ref_set, filter=None):
        """
        Search a reference set using the filter
        :param ref_set: Reference set name
        :param filter:
        :return:
        """
        auth_info = AuthInfo.get_authInfo()

        try:
            #
            #   urllib.quote has trouble to handle unicode
            #
            ref_set_link = quote(ref_set, '')
        except:
            ref_set_link = ref_set

        url = u"{}{}/{}".format(auth_info.api_url, qradar_constants.REFERENCE_SET_URL, ref_set_link)

        ret = None
        try:
            if filter:
                parameter = quote('?filter=value="{}"'.format(filter))
                url = url + parameter

            response = requests.Session().get(url=url, headers=auth_info.headers, verify=auth_info.cafile)
            # Sample return
            #{"creation_time":1523020929069,"timeout_type":"FIRST_SEEN","number_of_elements":2,
            # "data":[{"last_seen":1523020984874,"first_seen":1523020984874,"source":"admin","value":"8.8.8.8"}],
            # "name":"Sample Suspect IPs","element_type":"IP"}
            found = "False"
            ret_data = response.json().get("data", [])

            if len(ret_data) > 0 and response.status_code == 200:
                found = "True"

            ret = {"status_code": response.status_code, "found": found, "content": response.json()}

        except Exception as e:
            LOG.error(str(e))
            raise RequestError(url, "search_ref_set call failed with exception {}".format(str(e)))

        return ret

    @staticmethod
    def add_ref_element(ref_set, value):
        """
        Add the value to the given ref_set
        :param ref_set: Name of reference set.
        :param value:
        :return:
        """
        auth_info = AuthInfo.get_authInfo()
        ref_set_link = quote(ref_set, '')
        url = "{}{}/{}".format(auth_info.api_url, qradar_constants.REFERENCE_SET_URL, ref_set_link)

        ret = None
        try:
            data = {"value": quote(value)}

            response = requests.Session().post(url=url, headers=auth_info.headers, data=data, verify=auth_info.cafile)

            ret = {"status_code": response.status_code, "content": response.json()}

        except Exception as e:
            LOG.error(str(e))
            raise RequestError(url, "add_ref_element call failed with exception {}".format(str(e)))

        return ret

    @staticmethod
    def delete_ref_element(ref_set, value):
        """
        Delete value from the given ref_set
        :param ref_set: Name of existing reference set
        :param value:
        :return:
        """
        auth_info = AuthInfo.get_authInfo()
        ref_set_link = quote(ref_set, '')
        value = quote(value, '')
        url = "{}{}/{}/{}".format(auth_info.api_url, qradar_constants.REFERENCE_SET_URL, ref_set_link, value)

        ret = {}
        try:
            response = requests.Session().delete(url=url, headers=auth_info.headers, verify=auth_info.cafile)

            ret = {"status_code": response.status_code, "content": response.json()}

        except Exception as e:
            LOG.error(str(e))
            raise DeleteError(url, "delete_ref_element failed with exception {}".format(str(e)))

        return ret
    
