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
        ret = {
            "numericFilters":{},
            "categoryFilters":{},
            "variantInfoFilters": []
        }
        ret_variant_category = {}
        ret_variant_numeric = {}
        for key, rec in self.data.items():
            if rec['type'] == 'minmax':
                save_rec = {}
                if 'min' in rec:
                    save_rec["min"] = rec["min"]
                if 'max' in rec:
                    save_rec["max"] = rec["max"]
                if rec['HpdsDataType'] == 'info':
                    ret_variant_numeric[key] = save_rec
                else:
                    ret['numericFilters'][key] = save_rec
            elif rec['type'] == 'categorical':
                save_rec = rec['values']
                if rec['HpdsDataType'] == 'info':
                    ret_variant_category[key] = save_rec
                else:
                    ret['categoryFilters'][key] = save_rec
            elif rec['type'] == 'value':
                if type(rec['value']) == str:
                    save_rec = [rec['value']]
                    if rec['HpdsDataType'] == 'info':
                        ret_variant_category[key] = save_rec
                    else:
                        ret['categoryFilters'][key] = save_rec
                else:
                    save_rec = {"min":rec['value'], "max":rec['value']}
                    if rec['HpdsDataType'] == 'info':
                        ret_variant_numeric[key] = save_rec
                    else:
                        ret['numericFilters'][key] = save_rec
        # add variant filters
        ret['variantInfoFilters'].append({"categoryVariantInfoFilters": ret_variant_category, "numericVariantInfoFilters": ret_variant_numeric})
        return ret

    def load(self, numeric, catagorical, variants):
        for key, rec in numeric.items():
            to_save = {"type":"minmax", "HpdsDataType": ""}
            if "min" in rec:
                to_save['min'] = rec['min']
            if "max" in rec:
                to_save['max'] = rec['max']
            self.data[key] = to_save

        for key, rec in catagorical.items():
            to_save = {"type":"categorical", "HpdsDataType": ""}
            to_save['values'] = rec
            self.data[key] = to_save

        if len(variants) > 0:
            for key, rec in variants[0]['categoryVariantInfoFilters'].items():
                to_save = {"type": "categorical", "HpdsDataType": "info"}
                to_save['values'] = rec
                self.data[key] = to_save

            for key, rec in variants[0]["numericVariantInfoFilters"].items():
                to_save = {"type":"minmax", "HpdsDataType": "info"}
                if "min" in rec:
                    to_save['min'] = rec['min']
                if "max" in rec:
                    to_save['max'] = rec['max']
                self.data[key] = to_save
        return self

    def getJSON(self):
        """ include all but the 'exists' entries """
        e = JSONEncoder()
        return e.encode(self.getQueryValues())
