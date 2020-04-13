#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages
import glob
import ntpath

def get_module_name(module_path):
    """
    Return the module name of the module path
    """
    return ntpath.split(module_path)[1].split(".")[0]

def snake_to_camel(word):
    """
    Convert a word from snake_case to CamelCase
    """
    return ''.join(x.capitalize() or '_' for x in word.split('_'))

setup(
    name='qradar',
    version='3.0.0',
    license='MIT License',
    author='IBM Resilient and Jared Fagel',
    author_email='support@resilientsystems.com',
    description="Resilient Circuits Components for 'qradar'",
    long_description="qradar supports performing ariel search to retrieve data from QRadar. It also provide functions to find/add/delete reference set items.",
    install_requires=[
        'resilient_circuits>=30.0.0',
        'resilient_lib>30.0.0',
        'requests>0.0.0'
    ],
    packages=find_packages(),
    include_package_data=True,
    platforms='any',
    classifiers=[
        'Programming Language :: Python',
    ],
    entry_points={
        "resilient.circuits.components": [
            # When setup.py is executed, loop through the .py files in the components directory and create the entry points.
            "{}FunctionComponent = qradar.components.{}:FunctionComponent".format(snake_to_camel(get_module_name(filename)), get_module_name(filename)) for filename in glob.glob("./qradar/components/[a-zA-Z]*.py")
        ],
        "resilient.circuits.configsection": ["gen_config = qradar.util.config:config_section_data"],
        "resilient.circuits.customize": ["customize = qradar.util.customize:customization_data"]
    }
)
