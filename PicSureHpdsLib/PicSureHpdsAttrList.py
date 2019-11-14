# -*- coding: utf-8 -*-

"""
Base class used for the query object's  list attributes fields
"""

import json
import re


class AttrList:
    """ base class that powers all the query list operations """

    def __init__(self, init_list=None, help_text='', resource_uuid='', apiObj=None, allowVariantSpec=True):
        self.helpstr = """ [Help] valid commands are:
        |    add(): add a value
        |  delete(): delete a value
        |   show(): lists all current values
        |  clear(): clears all values from list
        |   help(): this command...
        """
        self.data = {}
        if type(init_list) == dict:
            self.data = init_list
        if type(help_text) == str and len(help_text) > 0:
            self.helpstr = help_text
        self._apiObj = apiObj
        self._resource_uuid = resource_uuid
        self._allow_variant_spec = allowVariantSpec

    def add(self, key, *args, **kwargs):
        func_args = list(args)
        keys = key
        if type(key) == str:
            # the key is a single string, transform into a single element list
            keys = [key]

        # remove any keys that already exist in our filter set
        new_keys = []
        for loopkey in keys:
            if loopkey in self.data:
                print('ERROR: cannot add, key already exists -> ', loopkey)
            else:
                new_keys.append(loopkey)
        keys = new_keys

        # query the resource and identify what data_class the key belongs to
        new_keys = []
        key_class_list = {}
        for loopkey in keys:
            # do not lookup if key is variant spec
            temp = self._variant_spec_str(loopkey)
            if self._is_variant_spec_str(temp):
                if self._allow_variant_spec:
                    new_keys.append(temp)
                    key_class_list[str(temp)] = "HpdsVariantSpec"
                else:
                    print('ERROR: cannot add key, it is of type HpdsVariantSpec -> ', loopkey)
            else:
                query = {"query": str(loopkey)}
                results = self._apiObj.search(self._resource_uuid, json.dumps(query))
                results = json.loads(results)['results']
                merge_results = {}
                was_found = False
                for typename in results:
                    if loopkey in results[typename]:
                        was_found = True
                        new_keys.append(loopkey)
                        key_class_list[str(loopkey)] = typename
                        break
                if not was_found:
                    print('ERROR: cannot add, key does not exist in resource -> ', str(loopkey))
                    # we do not append to the new_keys array so futher processing of this key will not occur
        keys = new_keys

        # process just a key add
        if len(func_args) == 0 and len(kwargs) == 0:
            for loopkey in keys:
                # TODO: Test keys' class criteria (info, phenotype, etc)
                self.data[loopkey] = {'type': 'exists', 'HpdsDataType': key_class_list[loopkey]}
        else:
            # process categorical add
            if len(func_args) > 0 and type(func_args[0]) == list:
                for loopkey in keys:
                    # Do not add entries with no list entries
                    if len(func_args[0]) > 0:
                        # TODO: Test keys' class criteria (info, phenotype, etc)
                        # TODO: Test that the entries for categorical values match results retreved
                        #       from data dictionary call (unless entry is a VariantSpec)
                        self.data[loopkey] = {'type': 'categorical', 'values': func_args[0], 'HpdsDataType': key_class_list[loopkey]}
                    else:
                        print("ERROR: cannot add, key does not have any categorical values set -> ", str(loopkey))
            else:
                # process min+max add (2 unnamed parameters)
                if len(func_args) > 1 and (type(func_args[0]) == int or type(func_args[1]) == int):
                    for loopkey in keys:
                        # TODO: Test keys' class criteria (info, phenotype, etc)
                        # do not add HpdsVariantSpec type with min/max values
                        if key_class_list[loopkey] != "HpdsVariantSpec":
                            self.data[loopkey] = {'type': 'minmax', 'HpdsDataType': key_class_list[loopkey]}
                            if type(func_args[0]) == int:
                                self.data[loopkey]['min'] = func_args[0]
                            if type(func_args[0]) == int:
                                self.data[loopkey]['max'] = func_args[1]
                        else:
                            print('ERROR: cannot add key, HpdsVariantSpec cannot filter as a range -> ', loopkey)
                else:
                    # process min and/or max add (1 or 2 named parameters)
                    if 'min' in kwargs or 'max' in kwargs:
                        for loopkey in keys:
                            # TODO: Test keys' class criteria (info, phenotype, etc)
                            # do not add HpdsVariantSpec type with min/max values
                            if key_class_list[loopkey] != "HpdsVariantSpec":
                                self.data[loopkey] = {'type': 'minmax', 'HpdsDataType': key_class_list[loopkey]}
                                if 'min' in kwargs:
                                    self.data[loopkey]['min'] = kwargs['min']
                                if 'max' in kwargs:
                                    self.data[loopkey]['max'] = kwargs['max']
                            else:
                                print('ERROR: cannot add key, HpdsVariantSpec cannot filter as a range -> ', loopkey)
                    else:
                        # process single value add
                        if type(func_args[0]) == int or type(func_args[0]) == str:
                            for loopkey in keys:
                                # TODO: Test keys' class criteria (info, phenotype, etc)
                                # do not add HpdsVariantSpec type with min/max values
                                if key_class_list[loopkey] != "HpdsVariantSpec":
                                    self.data[loopkey] = {'type': 'value', 'value': func_args[0], 'HpdsDataType': key_class_list[loopkey]}
                                else:
                                    print('ERROR: cannot add key, HpdsVariantSpec cannot filter on a value (use catagorical by passing single value in array) -> ', loopkey)
        return self


    def delete(self, key, *args):
        func_args = list(args)
        if type(key) != list:
            keys = [key]
        else:
            keys = key
        for t_key in keys:
            # does the key exist?
            if t_key in self.data:
                # delete the key
                self.data.pop(t_key)
            else:
                print('ERROR: the specified key does not exist')
                return
        return self


    def show(self):
        print('| _restriction_type_ |', '_key_'.ljust(110, '_'), '| _restriction_values_')
        for key, rec in self.data.items():
            print('| ', rec['type'].ljust(16), ' |', key.replace('\\','\\\\').ljust(110), '| ', end='', flush=True)
            if rec.get('type') == 'exists':
                print(rec['values'], end='', flush=True)
            elif rec.get('type') == 'categorical':
                print(rec['values'], end='', flush=True)
            elif rec.get('type') == 'minmax':
                if 'min' in rec:
                    print(rec['min'], end='')
                else:
                    print('n/a', end='')
                print(' to ', end='')
                if 'max' in rec:
                    print(rec['max'], end='', flush=True)
                else:
                    print('n/a', end='', flush=True)
            elif rec.get('type') == 'value':
                print(rec['value'], end='', flush=True)
            print(' |')

    def clear(self):
        print('cleared list')
        self.data.clear()
        return self

    def help(self):
        print(self.helpstr)

    def _variant_spec_str(self, variant_str):
        # convert to standard format
        return (',').join(re.split('[:_/]', variant_str))

    def _is_variant_spec_str(self, variant_str):
        # is if string contains variant spec format
        is_variant = False
        if re.match('rs[0-9]+$', variant_str) is not None:
            is_variant = True
        if re.match('[0-9]+,[0-9\\.]+,.*', variant_str) is not None:
            is_variant = True
        return is_variant
