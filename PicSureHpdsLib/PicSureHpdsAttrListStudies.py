# -*- coding: utf-8 -*-

"""
Base class used for the query object's  list attributes fields
"""

import PicSureHpdsLib
from json import JSONEncoder


class AttrListStudies(PicSureHpdsLib.AttrList):
    """ Class that powers the query's SELECT/REQUIRE list operations """

    def add(self, key, *args):
        """ overload the add() operator """
        # see if we are going to need to purge non-study keys after fresh retrieval of data dictionary
        do_culling = False
        if self.all_keys is None:
            do_culling = True

        # save number of entries for later display of additional information on failure
        start_entries = len(self.data)

        # process all add operations as a key-only add
        ret_ref = super().add('\\_studies\\' + key + '\\')

        if do_culling:
            # remove all data dictionary entries which are not studies
            keys = list(self.all_keys.copy().keys())
            for key in keys:
                if key != 'phenotypes':
                    del self.all_keys[key]

            keys = list(self.all_keys['phenotypes'].copy().keys())
            for key in keys:
                if not key.startswith('\\_studies\\'):
                    del self.all_keys['phenotypes'][key]

        if start_entries == len(self.data):
            print('| _Other Available Studies'.ljust(128, '_') + ' |')
            for key in self.all_keys["phenotypes"].keys():
                if key.startswith("\\_studies\\"):
                    if key not in self.data:
                        study = key.split('\\')[2]
                        print('|   ' + study.replace('\\', '\\\\').ljust(124) + ' |', flush=True)


        return ret_ref

    def delete(self, key, *args):
        """ overload the delete() operator """

        # process all delete() operations as a key-only delete
        return super().delete("\\_studies\\" + key + "\\")

    def show(self):
        print('| _Selected Studies_'.ljust(128, '_') + " |")
        if len(self.data) == 0:
            print('|   << All studies included by default >>'.ljust(128) + ' |', flush=True)

        for key, rec in self.data.items():
            try:
                study = key.split('\\')[2]
                print('|   ' + study.replace('\\','\\\\').ljust(124) + ' |', flush=True)
            except:
                pass

        print('| _Other Available Studies'.ljust(128, '_') + ' |')
        if self.all_keys is None:
            print('|   << Studies have not been loaded (try to add one first) >>'.ljust(128) + ' |', flush=True)
        else:
            keys = self.all_keys["phenotypes"].keys()
            for key in keys:
                if key.startswith("\\_studies\\"):
                    if key not in self.data:
                        study = key.split('\\')[2]
                        print('|   ' + study.replace('\\', '\\\\').ljust(124) + ' |', flush=True)
            if len(keys) == len(self.data):
                print('|   << All studies are selected >>'.ljust(128) + ' |', flush=True)


    def getQueryValues(self):
        ret = {}
        for key, rec in self.data.items():
            if rec['type'] == 'exists':
                ret[key] = [True]
        return ret

    def load(self, keys):
        for loopkey in keys:
            study = loopkey.split('\\')[2]
            self.data[study] = {"type": "exists", "HpdsDataType": "Loaded"}


    def getJSON(self):
        """ only include 'exists' entries """
        e = JSONEncoder()
        return e.encode(self.getQueryValues())

