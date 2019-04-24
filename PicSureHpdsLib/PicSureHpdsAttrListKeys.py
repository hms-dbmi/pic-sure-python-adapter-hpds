# -*- coding: utf-8 -*-

"""
Base class used for the query object's  list attributes fields
"""

import PicSureHpdsLib
from json import JSONEncoder


class AttrListKeys(PicSureHpdsLib.AttrList):
    """ Class that powers the query's SELECT/REQUIRE list operations """

    def add(self, key, *args):
        """ overload the add() operator """
        # process all add operations as a key-only add
        return super().add(key)

    def delete(self, key, *args):
        """ overload the delete() operator """

        # process all delete() operations as a key-only delete
        return super().delete(key)

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

    def getJSON(self):
        """ only include 'exists' entries """
        e = JSONEncoder()
        return e.encode(self.getQueryValues())

