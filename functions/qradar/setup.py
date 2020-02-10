#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

setup(
    name='qradar',
    version='3.0.3',
    license='MIT License',
    author='IBM Resilient and Jared Fagel',
    author_email='support@resilientsystems.com',
    description="Resilient Circuits Components for 'qradar'",
    long_description="qradar supports performing ariel search to retrieve data from QRadar. It also provide functions to find/add/delete reference set items.",
    install_requires=[
        'resilient_circuits>=30.0.0'
    ],
    packages=find_packages(),
    include_package_data=True,
    platforms='any',
    classifiers=[
        'Programming Language :: Python',
    ],
    entry_points={
        "resilient.circuits.components": [
            "QradarFindReferenceSetsFunctionComponent = qradar.components.qradar_find_reference_sets:FunctionComponent",
            "QradarDeleteReferenceSetItemFunctionComponent = qradar.components.qradar_delete_reference_set_item:FunctionComponent",
            "QradarAddReferenceSetItemFunctionComponent = qradar.components.qradar_add_reference_set_item:FunctionComponent",
            "QradarFindReferenceSetItemFunctionComponent = qradar.components.qradar_find_reference_set_item:FunctionComponent",
            "QradarSearchFunctionComponent = qradar.components.qradar_search:FunctionComponent"
        ],
        "resilient.circuits.configsection": ["gen_config = qradar.util.config:config_section_data"],
        "resilient.circuits.customize": ["customize = qradar.util.customize:customization_data"]
    }
)