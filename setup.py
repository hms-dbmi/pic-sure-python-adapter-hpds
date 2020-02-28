#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""The setup script."""

from setuptools import setup, find_packages

with open('README.rst') as readme_file:
    readme = readme_file.read()

with open('HISTORY.rst') as history_file:
    history = history_file.read()

requirements = ['httplib2' ]

setup_requirements = [ ]

test_requirements = [ ]

setup(
    author="Nick Benik",
    author_email='nick_benik@hms.harvard.edu',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
    description="Client library to run queries against a PIC-SURE High Performance Data Store (HPDS) resource.",
    install_requires=requirements,
    license="Apache Software License 2.0",
    long_description=readme + '\n\n' + history,
    include_package_data=True,
    keywords='PicSureHpdsLib',
    name='PicSureHpdsLib',
    packages=find_packages(include=['PicSureHpdsLib']),
    setup_requires=setup_requirements,
    test_suite='tests',
    tests_require=test_requirements,
    url='https://github.com/hms-dbmi/pic-sure-hpds-python-client',
    version='0.9.0',
    zip_safe=False,
)
