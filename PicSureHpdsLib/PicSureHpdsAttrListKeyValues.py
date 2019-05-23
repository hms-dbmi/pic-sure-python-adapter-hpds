# -*- coding: utf-8 -*-

"""
Base class used for the query object's  list attributes fields
"""

import PicSureHpdsLib
from json import JSONEncoder

class AttrListKeyValues(PicSureHpdsLib.AttrList):
    """ Class that powers the query's FILTER list operations """

    def add(self, key, *args, **kwargs):
        """ overload the add() operator """
        if len(args) == 0 and len(kwargs) == 0:
            # raise Exception("All Filter.add()'s must specify matching value, values, or range")
            print('ERROR: All Filter.add()\'s must specify matching value, values, or range')
            return
        # process all add operations as a key-only add
        return super().add(key, *args, **kwargs)

    def getQueryValues(self):
        ret = {"numericFilters":{}, "categoryFilters":{}}
        for key, rec in self.data.items():
            if rec['type'] == 'minmax':
                ret['numericFilters'][key] = {}
                if rec['min'] == int:
                    ret['numericFilters'][key]["min"] = rec['min']
                if rec['max'] == int:
                    ret['numericFilters'][key]["min"] = rec['max']
            elif rec['type'] == 'categorical':
                ret['categoryFilters'][key] = rec['values']
            elif rec['type'] == 'value':
                if type(rec['value']) == str:
                    ret['categoryFilters'][key] = [rec['value']]
                else:
                    ret['numericFilters'][key] = {"min":rec['value'], "max":rec['value']}
        return ret

    def getJSON(self):
        """ include all but the 'exists' entries """
        e = JSONEncoder()
        return e.encode(self.getQueryValues())
