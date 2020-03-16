# -*- coding: utf-8 -*-

import PicSureHpdsLib
import json
import time


class Query:
    """ Main class of library """
    def __init__(self, refHpdsResourceConnection, load_query=None):
        self._performance = {
            "running": False,
            "tmr_start": 0,
            "tmr_query": 0,
            "tmr_recv": 0,
            "tmr_proc": 0
        }
        self._refHpdsResourceConnection = refHpdsResourceConnection
        self._apiObj = refHpdsResourceConnection.connection_reference._api_obj()
        self._resourceUUID = refHpdsResourceConnection.resource_uuid
        self._lstSelect = PicSureHpdsLib.AttrListKeys(
            help_text="""
            select().
              add("key")            add a single column to be returned in results
              add(["key1", "key2"]) add several columns to be returned in results
              delete("key")         delete a single column from the list of columns to return
              show()                lists all current columns that will be returned in results
              clear()               clears all values from the select list
            """,
            resource_uuid = self._resourceUUID,
            apiObj = self._apiObj,
            allowVariantSpec = False
        )
        self._lstRequire = PicSureHpdsLib.AttrListKeys(
            help_text="""
            require().
              add("key")            add a single column that must exist within each results record
              add(["key1", "key2"]) add several columns that must exist within each results record
              delete("key")         delete a single column from the list of columns to that results records must have
              show()                lists all current columns that results records must have
              clear()               clears all values from the require list
            """,
            resource_uuid = self._resourceUUID,
            apiObj = self._apiObj
        )
        self._lstCrossCntFields = PicSureHpdsLib.AttrListKeys(
            help_text="""
                crosscount().
                  add("key")            add a single column to the cross count results
                  add(["key1", "key2"]) add several columns to the cross count results
                  delete("key")         delete a single column from the list of cross count results
                  show()                lists all current columns that will be calculated in cross counts
                  clear()               clears all values from the cross counts list
                """,
            resource_uuid=self._resourceUUID,
            apiObj=self._apiObj
        )
        self._lstAnyOf = PicSureHpdsLib.AttrListKeys(
            help_text="""
                anyof().
                  add("key")            add a single column to ...
                  add(["key1", "key2"]) add several columns to ...
                  delete("key")         delete a single column ... from the list of results
                  show()                lists all current columns ... 
                  clear()               clears all values from the "any-of" list
                """,
            resource_uuid=self._resourceUUID,
            apiObj=self._apiObj
        )
        self._lstFilter = PicSureHpdsLib.AttrListKeyValues(
            help_text="""
            filter().
              add("key", value)                  - or -
              add("key", "value")               filter to records with KEY column that equals VALUE
              add("key", ["value1", "value2"])  filter to records with KEY column equalling one value within the given list
              add("key", start, end)            filter to records with KEY column value between START and END (inclusive)
                                                    start -or- end may be set to None to filter by a max or min value
              delete("key")                     delete a filter from the list of filters
              show()                            lists all current filters that results records must satisfy
              clear()                           clears all values from the filters list
            """,
            resource_uuid = self._resourceUUID,
            apiObj = self._apiObj
        )
        if load_query is not None:
            if type(load_query) is not str:
                raise ValueError
            self.load(load_query, merge=True)


    def help(self):
        print("""
        .select()       list of data fields to return from resource for each record
        .crosscounts()  list of data fields that cross counts will be calculated for
        .require()      list of data fields that must be present in all returned records
        .anyof()        list of data fields that records must be a member of at least one entry
        .filter()       list of data fields and conditions that returned records satisfy
                  [ Filter keys exert an AND relationship on returned records      ]
                  [ Categorical values have an OR relationship on their key        ]
                  [ Numerical Ranges are inclusive of their start and end points   ]

        .getCount()             single count indicating the number of matching records
        .getCrossCount()        array indicating number of matching records per cross-count keys
        .getResults()           CSV-like string containing the matching records
        .getResultsDataFrame()  pandas DataFrame containing the matching records...
                                  Params "asAsynch" and "timeout" are used by function, any 
                                  additional named parameters are passed to pandas.read_csv()
        .getRunDetails()        details about the last run of the query
        .show()                 lists all current query parameters
        .save()                 returns the JSON-formatted query request as string
        .load(query)            set query's current criteria to those in given JSON string
        
            * getCount(), getResults(), and getResultsDataFrame() functions can also 
              accept options that run queries differently which might help with 
              connection timeouts. Example: .getResults(async=True, timeout=60)
        """)
    def show(self):
        if len(self._lstSelect.getQueryValues()) == 0:
            print('.__________[ Query.select()  has NO SELECTIONS ]'.ljust(156, '_'))
        else:
            print('.__________[ Query.select()  Settings ]'.ljust(156, '_'))
            self._lstSelect.show()
        if len(self._lstCrossCntFields.getQueryValues()) == 0:
            print('.__________[ Query.crosscounts()  has NO SELECTIONS ]'.ljust(156, '_'))
        else:
            print('.__________[ Query.crosscounts()  Settings ]'.ljust(156, '_'))
            self._lstCrossCntFields.show()
        if len(self._lstRequire.getQueryValues()) == 0:
            print('.__________[ Query.require() has NO SELECTIONS ]'.ljust(156, '_'))
        else:
            print('.__________[ Query.require() Settings ]'.ljust(128, '_'))
            self._lstRequire.show()
        if len(self._lstAnyOf.getQueryValues()) == 0:
            print('.__________[ Query.anyof()  has NO SELECTIONS ]'.ljust(156, '_'))
        else:
            print('.__________[ Query.anyof()  Settings ]'.ljust(156, '_'))
            self._lstAnyOf.show()
        temp = self._lstFilter.getQueryValues()
        if len(temp["numericFilters"]) == 0 and len(temp['categoryFilters']) == 0:
            print('.__________[ Query.filter()  has NO SELECTIONS ]'.ljust(156, '_'))
        else:
            print('.__________[ Query.filter()  Settings ]'.ljust(156, '_'))
            self._lstFilter.show()

    def select(self, *args, **kwargs):
        if len(args) > 0 or len(kwargs) > 0:
            print("ERROR: did you mean to do something like .select().add(<something here>)")
            return None
        return self._lstSelect

    def crosscounts(self, *args, **kwargs):
        if len(args) > 0 or len(kwargs) > 0:
            print("ERROR: did you mean to do something like .crosscounts().add(<something here>)")
            return None
        return self._lstCrossCntFields

    def require(self, *args, **kwargs):
        if len(args) > 0 or len(kwargs) > 0:
            print("ERROR: did you mean to do something like .require().add(<something here>)")
            return None
        return self._lstRequire

    def anyof(self, *args, **kwargs):
        if len(args) > 0 or len(kwargs) > 0:
            print("ERROR: did you mean to do something like .anyof().add(<something here>)")
            return None
        return self._lstAnyOf

    def filter(self, *args, **kwargs):
        if len(args) > 0 or len(kwargs) > 0:
            print("ERROR: did you mean to do something like .filter().add(<something here>)")
            return None
        return self._lstFilter

    def getCount(self, asAsync=False, timeout=30):
        self._performance['running'] = True
        self._performance['tmr_start'] = time.time()
        queryJSON = self.buildQuery('COUNT')
        self._performance['tmr_query'] = time.time()
        httpResults = self._apiObj.syncQuery(self._resourceUUID, json.dumps(queryJSON))
        self._performance['tmr_recv'] = time.time()
        self._performance['running'] = False
        # make sure we are able to convert to a valid number
        try:
            if str(int(httpResults)) == httpResults:
                self._performance['tmr_proc'] = time.time()
                return int(httpResults)
            else:
                pass
        except:
            pass
        print('[ERROR] could not convert results of RequestCount to integer')
        self._performance['tmr_proc'] = time.time()
        return httpResults

    def getAsyncResults(self, query_uuid=None):
        print("NOTHING DONE: This function is not yet fully implemented!")
        return False
        # if query_uuid is not None:
        #     self._performance['running'] = True
        #     self._performance['tmr_start'] = time.time()
        #     queryJSON = self.buildQuery('COUNT')
        #     self._performance['tmr_query'] = time.time()
        #     httpResults = self._apiObj.queryResult(self._resourceUUID, query_uuid)
        #     self._performance['tmr_recv'] = time.time()
        #     self._performance['running'] = False
        #     return httpResults
        # else:
        #     print("ERROR-209: No query_uuid was given")
        #     return None

    def getAsyncStatus(self, query_uuid=None):
        print("NOTHING DONE: This function is not yet fully implemented!")
        return False
        # if query_uuid is not None:
        #     self._performance['running'] = True
        #     self._performance['tmr_start'] = time.time()
        #     queryJSON = self.buildQuery('COUNT')
        #     self._performance['tmr_query'] = time.time()
        #     httpResults = self._apiObj.queryStatus(self._resourceUUID, json.dumps(queryJSON))
        #     self._performance['tmr_recv'] = time.time()
        #     self._performance['running'] = False
        #     return httpResults
        # else:
        #     print("ERROR-222: No query_uuid was given")
        #     return None


    def getCrossCounts(self, asAsync=False):
        self._performance['running'] = True
        self._performance['tmr_start'] = time.time()
        queryJSON = self.buildQuery('CROSS_COUNT')
        self._performance['tmr_query'] = time.time()
        httpResults = self._apiObj.syncQuery(self._resourceUUID, json.dumps(queryJSON))
        self._performance['tmr_recv'] = time.time()
        self._performance['running'] = False
        self._performance['tmr_proc'] = time.time()
        # Return as dict mapping variant spec to count
        return json.loads(httpResults)

    def getResults(self, asAsync=False, timeout=30):
        self._performance['running'] = True
        self._performance['tmr_start'] = time.time()
        queryJSON = self.buildQuery('DATAFRAME')
        self._performance['tmr_query'] = time.time()
        httpResults = self._apiObj.syncQuery(self._resourceUUID, json.dumps(queryJSON))
        self._performance['tmr_recv'] = time.time()
        self._performance['running'] = False
        try:
            from json.decoder import JSONDecodeError
            result = json.loads(httpResults)
            if result.error == True:
                print("[ERROR]")
                print(httpResults)
                self._performance['tmr_proc'] = time.time()
                raise Exception('An error has occured with the server')
        except JSONDecodeError:
            pass
        self._performance['tmr_proc'] = time.time()
        return httpResults

    def getResultsDataFrame(self, asAsync=False, timeout=30, **kwargs):
        self._performance['running'] = True
        self._performance['tmr_start'] = time.time()
        queryJSON = self.buildQuery('DATAFRAME')
        self._performance['tmr_query'] = time.time()
        httpResults = self._apiObj.syncQuery(self._resourceUUID, json.dumps(queryJSON))
        self._performance['tmr_recv'] = time.time()
        self._performance['running'] = False
        try:
            from json.decoder import JSONDecodeError
            result = json.loads(httpResults)
            if result.error == True:
                print("[ERROR]")
                print(httpResults)
                self._performance['tmr_proc'] = time.time()
                raise Exception('An error has occured with the server')
        except JSONDecodeError:
            pass
        self._performance['tmr_proc'] = time.time()
        from io import StringIO
        import pandas
        ret = pandas.read_csv(StringIO(httpResults), **kwargs)
        self._performance['tmr_proc'] = time.time()
        return ret

    def getRunDetails(self):
        print('This function returns None or details about the last run of the query')
        if self._performance['tmr_start'] > 0:
            if self._performance['running'] == True:
                print("Query is RUNNING...")
            else:
                print("Query is FINISHED...")
            if self._performance['tmr_query'] < self._performance['tmr_start']:
                print("   Query Build: --- ms")
                print(" Query Execute: --- ms")
                print("Process Result: --- ms")
            else:
                print("   Query Build: " + str((self._performance['tmr_query'] - self._performance['tmr_start'])*1000) + " ms")
                if self._performance['tmr_recv'] < self._performance['tmr_query']:
                    print(" Query Execute: --- ms")
                    print("Process Result: --- ms")
                else:
                    print(" Query Execute: " + str((self._performance['tmr_recv'] - self._performance['tmr_query'])*1000) + " ms")
                    if self._performance['tmr_proc'] < self._performance['tmr_recv']:
                        print("Process Result: --- ms")
                    else:
                        print("Process Result: " + str((self._performance['tmr_proc'] - self._performance['tmr_recv'])*1000) + " ms")
                        print("____Total Time: " + str((self._performance['tmr_proc'] - self._performance['tmr_start'])*1000) + " ms")


    def save(self, *args):
        """ save() """
        return json.dumps(self.buildQuery(*args))

    def load(self, query, merge = False):
        """ load(query=str, merge=bool) """
        if type(query) == str:
            query = json.loads(query)

        # clear the current criteria if we are not merging
        if not merge:
            self._lstSelect.clear()
            self._lstCrossCntFields.clear()
            self._lstRequire.clear()
            self._lstAnyOf.clear()
            self._lstFilter.clear()

        # ___ handle key-only fields ____
        if "query" in query:
            query_root = query["query"]
        else:
            query_root = query

        if "fields" in query_root:
            self._lstSelect.load(query_root["fields"])
        if "crossCountFields" in query_root:
            self._lstCrossCntFields.load(query_root["crossCountFields"])
        if "requiredFields" in query_root:
            self._lstRequire.load(query_root["requiredFields"])
        if "anyRecordOf" in query_root:
            self._lstAnyOf.load(query_root["anyRecordOf"])

        # ___ handle various filters ___
        filter_num = {}
        filter_cat = {}
        filter_info = []
        if "numericFilters" in query_root:
            filter_num = query_root["numericFilters"]
        if "categoryFilters" in query_root:
            filter_cat = query_root["categoryFilters"]
        if "variantInfoFilters" in query_root:
            filter_info = query_root["variantInfoFilters"]

        self._lstFilter.load(
            filter_num,
            filter_cat,
            filter_info
        )
        return self


    def buildQuery(self, *args):
        """ buildQuery(self, *args) """
        ret = {"query":{
            "fields": [],
            "crossCountFields": [],
            "requiredFields": [],
            "anyRecordOf": [],
            "numericFilters": {},
            "categoryFilters": {},
            "variantInfoFilters": []
        }}
        ret['query']['fields'] = self._lstSelect.getQueryValues()
        ret['query']['crossCountFields'] = self._lstCrossCntFields.getQueryValues()
        ret['query']['anyRecordOf'] = self._lstAnyOf.getQueryValues()
        ret['query']['requiredFields'] = self._lstRequire.getQueryValues()
        temp = self._lstFilter.getQueryValues()
        ret['query']['numericFilters'] = temp['numericFilters']
        ret['query']['categoryFilters'] = temp['categoryFilters']
        ret['query']['variantInfoFilters'] = temp['variantInfoFilters']

        if hasattr(self._refHpdsResourceConnection, 'resource_uuid'):
            if self._refHpdsResourceConnection.resource_uuid != None:
                ret['resourceUUID'] = self._refHpdsResourceConnection.resource_uuid
        if len(args) > 0:
            ret['query']['expectedResultType'] = list(args)[0]
        return ret
