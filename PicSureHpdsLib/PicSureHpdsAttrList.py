# -*- coding: utf-8 -*-

"""
Base class used for the query object's  list attributes fields
"""

from json import JSONEncoder

class AttrList:
    """ base class that powers all the query list operations """

    def __init__(self, init_list=None, help_text=""):
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

    def add(self, key, *other):
        func_args = list(other)
        keys = key
        if type(key) == str:
            # the key is a single string, transform into a single element list
            keys = [key]
        # process just a key add
        if len(func_args) == 0:
            for loopkey in keys:
                if loopkey in self.data:
                    print("ERROR: cannot add, key already exists -> ", loopkey)
                    return
                else:
                    self.data[loopkey] = {'type': 'exists'}
        else:
            # process catagorical add
            if type(func_args[0]) == list:
                for loopkey in keys:
                    if loopkey in self.data:
                        print("ERROR: cannot add, key already exists -> ", loopkey)
                        return
                    else:
                        self.data[loopkey] = {'type': 'catagorical', 'values': func_args[0]}
            else:
                # process min/max add
                if len(func_args) > 1 and type(func_args[0]) == int and type(func_args[1]) == int:
                    for loopkey in keys:
                        if loopkey in self.data:
                            print("ERROR: cannot add, key already exists -> ", loopkey)
                            return
                        else:
                            self.data[loopkey] = {'type': 'minmax', 'min': func_args[0], 'max': func_args[1]}
                else:
                    # process single value add
                    if type(func_args[0]) == int or type(func_args[0]) == str:
                        for loopkey in keys:
                            if loopkey in self.data:
                                print("ERROR: cannot add, key already exists -> ", loopkey)
                                return
                            else:
                                self.data[loopkey] = {'type': 'value', 'value': func_args[0]}
        return self

    def delete(self, key, *other):
        func_args = list(other)
        # does the key exist?
        if key in self.data:
            # are we deleting the whole key or just some values?
            if len(func_args) == 0:
                # just deleting the key
                self.data.pop(key)
            else:
                # trying to remove a value, confirm catagorical type
                if self.data[key].get('type') == 'catagorical':
                    if func_args[0] in self.data[key].get('values'):
                        # delete the matching value from the targeted values list
                        self.data[key].get('values').remove(func_args[0])
                    else:
                        print("ERROR: value was not found in the key's catagorical value list")
                        return
                else:
                    print("ERROR: a value was specified but the key is not catagorical")
                    return
        else:
            print("ERROR: the specified key does not exist")
            return
        return self

    def show(self):
        print("| _restriction_type_ |", "_key_".ljust(110, "_"), "| _restriction_values_")
        for key, rec in self.data.items():
            print("| ", rec['type'].ljust(16), " |", key.ljust(110), "| ", end='', flush=True)
            if rec.get('type') == 'exists':
                print(rec['values'], end='', flush=True)
            elif rec.get('type') == 'catagorical':
                print(rec['values'], end='', flush=True)
            elif rec.get('type') == 'minmax':
                print(rec['min'], " to ", rec['max'], end='', flush=True)
            elif rec.get('type') == 'value':
                print(rec['value'], end='', flush=True)
            print(" |")

    def clear(self):
        print("cleared list")
        self.data.clear()
        return self

    def help(self):
        print(self.helpstr)

