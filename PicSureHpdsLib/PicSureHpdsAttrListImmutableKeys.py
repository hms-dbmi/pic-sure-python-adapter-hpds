# -*- coding: utf-8 -*-

"""
Base class used for the query object's  list attributes fields
"""

import PicSureHpdsLib
from json import JSONEncoder


class AttrListImmutableKeys(PicSureHpdsLib.AttrList):
    """ Class that powers the query's SELECT/REQUIRE list operations """

    def add(self, *args, **kwargs):
        print("ERROR: this query is already queued or otherwise ran.  You cannot change it.")

    def delete(self, *args, **kwargs):
        print("ERROR: this query is already queued or otherwise ran.  You cannot change it.")

    def clear(self, *args, **kwargs):
        print("ERROR: this query is already queued or otherwise ran.  You cannot change it.")

    def load(self, *args, **kwargs):
        print("ERROR: this query is already queued or otherwise ran.  You cannot change it.")


    def show(self):
        print('| _key_'.ljust(128, '_'))
        for key, rec in self.data.items():
            print('| ', key.replace('\\','\\\\').ljust(128), end='', flush=True)
            print(' |')

    def getQueryValues(self):
        ret = list()
        for key, rec in self.data.items():
            if rec['type'] == 'exists':
                ret.append(key)
        return ret

    def load(self, keys):
        for loopkey in keys:
            self.data[loopkey] = {"type": "exists", "HpdsDataType": "Loaded"}


    def getJSON(self):
        """ only include 'exists' entries """
        e = JSONEncoder()
        return e.encode(self.getQueryValues())

