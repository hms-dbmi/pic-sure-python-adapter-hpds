#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Tests for `PicSureHpdsLib` package."""


import unittest

import PicSureHpdsLib

class TestPic_sure_hpds(unittest.TestCase):
    """Tests for `PicSureHpdsLib` package."""

    def setUp(self):
        """Set up test fixtures, if any."""
        self.config = {
            "endpoint": "http://",
            "token": ""
        }


    def tearDown(self):
        """Tear down test fixtures, if any."""

    def test_AdapterInstantiate(self):
        """Test something."""

        # class MockConnection:
        #     def __init__(self):
        #         self.url = "http://test.url/"
        #     def list(self):
        #         pass

#        mockConnection = MockConnection()
#        adapter = PicSureHpdsLib.Adapter(mockConnection)

