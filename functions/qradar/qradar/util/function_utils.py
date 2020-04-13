# -*- coding: utf-8 -*-
#
# (c) Copyright IBM Corp. 2018. All Rights Reserved.
#
# Util functions
import unicodedata


def fix_dict_value(events):
    """
    When the returned data from QRadar is used to update a datatable, we need to
    convert types like dict/list into strings
    :param events: list of dicts
    :return:
    """
    for event in events:
        # event is a dict
        if isinstance(event, dict):
            for key in event:
                if not isinstance(event[key], str):
                    event[key] = str(unicodedata.normalize("NFKD", event[key].decode('utf-8', 'ignore')))

    return events
