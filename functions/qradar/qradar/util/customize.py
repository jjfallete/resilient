# -*- coding: utf-8 -*-

# TODO: This needs to be reconstructed to align with this app - qradar_search function is much different than in v2 from Resilient.

"""Generate the Resilient customizations required for qradar"""

from __future__ import print_function
from resilient_circuits.util import *

def codegen_reload_data():
    """Parameters to codegen used to generate the qradar package"""
    reload_params = {"package": u"qradar",
                    "incident_fields": [u"qradar_id"], 
                    "action_fields": [], 
                    #"function_params": [u"qradar_query", u"qradar_query_param1", u"qradar_query_param2", u"qradar_query_param3", u"qradar_query_param4", u"qradar_query_param5", u"qradar_query_range_end", u"qradar_query_range_start", u"qradar_reference_set_item_value", u"qradar_reference_set_name"], 
                    #"datatables": [u"qradar_offense_event", u"qradar_reference_set"], 
                    #"message_destinations": [u"qradar"], 
                    #"functions": [u"qradar_add_reference_set_item", u"qradar_delete_reference_set_item", u"qradar_find_reference_set_item", u"qradar_find_reference_sets", u"qradar_search"], 
                    #"phases": [], 
                    #"automatic_tasks": [], 
                    #"scripts": [], 
                    #"workflows": [u"qradar_add_reference_set_item", u"qradar_delete_reference_set_item", u"qradar_find_reference_set_item", u"qradar_find_reference_sets_artifact", u"qradar_move_item_to_different_ref_set", u"qradar_search_event_offense"], 
                    #"actions": [u"Delete from QRadar Reference Set", u"Find All QRadar Reference Sets", u"Find in QRadar Reference Set", u"QRadar Add to Reference Set", u"QRadar Move from suspect to blocked", u"Search QRadar for offense id"] 
                    }
    return reload_params


def customization_data(client=None):
    """Produce any customization definitions (types, fields, message destinations, etc)
       that should be installed by `resilient-circuits customize`
    """

    # This import data contains:
    #   Incident fields:
    #     qradar_id
    #   Function inputs:
    #     incident_id
    #     qradar_query
    #     qradar_query_range_start
    #     qradar_query_range_end
    #     qradar_query_timeout_mins
    #     qradar_reference_set_item_value
    #     qradar_reference_set_name
    #   DataTables:
    #     qradar_reference_set
    #   Message Destinations:
    #     qradar
    #   Functions:
    #     qradar_add_reference_set_item
    #     qradar_delete_reference_set_item
    #     qradar_find_reference_set_item
    #     qradar_find_reference_sets
    #     qradar_search
    #   Workflows:
    #
    #   Rules:
    #

    yield ImportDefinition(u"""
"""
    )
