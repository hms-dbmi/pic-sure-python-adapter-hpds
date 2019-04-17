# -*- coding: utf-8 -*-

import PicSureHpdsLib
from json import JSONEncoder


class Query:
    """ Main class of library """
    def __init__(self, refHpdsResourceConnection):
        self._lstSelect = PicSureHpdsLib.AttrListKeys(
            help_text="""
            Select().
              add("key")            add a single column to be returned in results
              add(["key1", "key2"]) add several columns to be returned in results
              delete("key")         delete a single column from the list of columns to return
              show()                lists all current columns that will be returned in results
              clear()               clears all values from the select list
            """
        )
        self._lstRequire = PicSureHpdsLib.AttrListKeys(
            help_text="""
            Require().
              add("key")            add a single column that must exist within each results record
              add(["key1", "key2"]) add several columns that must exist within each results record
              delete("key")         delete a single column from the list of columns to that results records must have
              show()                lists all current columns that results records must have
              clear()               clears all values from the require list
            """
        )
        self._lstFilter = PicSureHpdsLib.AttrListKeyValues(
            help_text="""
            Filter().
              add("key", value)                  - or -
              add("key", "value")               filter to records with KEY column that equals VALUE
              add("key", ["value1", "value2"])  filter to records with KEY column equalling one value within the given list
              add("key", start, end)            filter to records with KEY column value between START and END (inclusive)
              delete("key")                     delete a filter from the list of filters
              show()                            lists all current filters that results records must satisfy
              clear()                           clears all values from the filters list
            """
        )
        self._refResourceConnection = refHpdsResourceConnection

    def help(self):
        print("""
        .Select()   list of data fields to return from resource for each record
        .Require()  list of data fields that must be present in all returned records
        .Filter()   list of data fields and conditions that returned records satisfy
                  [ Filter keys exert an AND relationship on returned records      ]
                  [ Categorical values have an OR relationship on their key        ]
                  [ Numerical Ranges are inclusive of their start and end points   ]
                   
        .getCount()        returns a count indicating the number of matching numbers
        .getResults()      returns a dataframe containing the matching records
        .getQueryCommand() returns the JSON-formatted query request
        """)

    def Select(self):
        return self._lstSelect

    def Require(self):
        return self._lstRequire

    def Filter(self):
        return self._lstFilter

    def getCount(self):
        queryJSON = self.queryCommand("COUNT")
        httpResults = self._refHpdsResourceConnection.connection_reference.syncQuery(queryJSON)
        print("TODO: process the returned JSON into results object")
        return httpResults

    def getResults(self):
        queryJSON = self.queryCommand("RESULTS")
        if hasattr(self._refHpdsResourceConnection, "connection_reference"):
            if hasattr(self._refHpdsResourceConnection.connection_reference, "syncQuery"):
                httpResults = self._refHpdsResourceConnection.connection_reference.syncQuery(queryJSON)
                print("TODO: process the returned JSON into results object")
                return httpResults

    def getQueryCommand(self, *others):
        """ queryCommand(self, resource_g"""
        ret = {
            "fields": [],
            "requiredFields": [],
            "numericFilters": {},
            "categoryFilters": {},
        }
        ret["fields"] = self._lstSelect.getQueryValues()
        ret["requiredFields"] = self._lstRequire.getQueryValues()
        temp = self._lstFilter.getQueryValues()
        ret["numericFilters"] = temp["numericFilters"]
        ret["categoryFilters"] = temp["categoryFilters"]
        if hasattr(self._refHpdsResourceConnection, "resource_uuid"):
            ret["resourceUUID"] = self._refHpdsResourceConnection.resource_uuid
        if len(list(others)) > 0:
            ret["outputFormat"] = list(others)[0]

        e = JSONEncoder()
        return e.encode(ret)
