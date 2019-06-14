# -*- coding: utf-8 -*-

import PicSureHpdsLib
import json
import time


class Query:
    """ Main class of library """
    def __init__(self, refHpdsResourceConnection):
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
            """
        )
        self._lstRequire = PicSureHpdsLib.AttrListKeys(
            help_text="""
            require().
              add("key")            add a single column that must exist within each results record
              add(["key1", "key2"]) add several columns that must exist within each results record
              delete("key")         delete a single column from the list of columns to that results records must have
              show()                lists all current columns that results records must have
              clear()               clears all values from the require list
            """
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
            """
        )
        self._refResourceConnection = refHpdsResourceConnection

    def help(self):
        print("""
        .select()   list of data fields to return from resource for each record
        .require()  list of data fields that must be present in all returned records
        .filter()   list of data fields and conditions that returned records satisfy
                  [ Filter keys exert an AND relationship on returned records      ]
                  [ Categorical values have an OR relationship on their key        ]
                  [ Numerical Ranges are inclusive of their start and end points   ]

        .getCount()             returns a count indicating the number of matching numbers
        .getResults()           returns a CSV-like string containing the matching records
        .getResultsDataFrame()  returns a pandas DataFrame containing the matching records
        .getRunDetails()        returns details about the last run of the query
        .getQueryCommand()      returns the JSON-formatted query request
        .show()                 lists all current query parameters
        
            * getCount(), getResults(), and getResultsDataFrame() functions can also 
              accept options that run queries differently which might help with 
              connection timeouts. Example: .getResults(async=True, timeout=60)
        """)
    def show(self):
        if len(self._lstSelect.getQueryValues()) == 0:
            print('.__________[ Query.Select()  has NO SELECTIONS ]'.ljust(156, '_'))
        else:
            print('.__________[ Query.Select()  Settings ]'.ljust(156, '_'))
            self._lstSelect.show()
        if len(self._lstRequire.getQueryValues()) == 0:
            print('.__________[ Query.Require() has NO SELECTIONS ]'.ljust(156, '_'))
        else:
            print('.__________[ Query.Require() Settings ]'.ljust(128, '_'))
            self._lstRequire.show()
        temp = self._lstFilter.getQueryValues()
        if len(temp["numericFilters"]) == 0 and len(temp['categoryFilters']) == 0:
            print('.__________[ Query.Filter()  has NO SELECTIONS ]'.ljust(156, '_'))
        else:
            print('.__________[ Query.Filter()  Settings ]'.ljust(156, '_'))
            self._lstFilter.show()

    def select(self, *args, **kwargs):
        if len(args) > 0 or len(kwargs) > 0:
            print("ERROR: did you mean to do something like .select().add(<something here>)")
            return None
        return self._lstSelect

    def require(self, *args, **kwargs):
        if len(args) > 0 or len(kwargs) > 0:
            print("ERROR: did you mean to do something like .require().add(<something here>)")
            return None
        return self._lstRequire

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
        if str(int(httpResults)) == httpResults.decode("utf-8"):
            self._performance['tmr_proc'] = time.time()
            return int(httpResults)
        else:
            print('[ERROR] could not convert results of RequestCount to integer')
            self._performance['tmr_proc'] = time.time()
            return httpResults

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
            result = json.loads(httpResults.decode("utf-8"))
            if result.error == True:
                print("[ERROR]")
                print(httpResults)
                self._performance['tmr_proc'] = time.time()
                raise Exception('An error has occured with the server')
        except JSONDecodeError:
            pass
        self._performance['tmr_proc'] = time.time()
        return httpResults

    def getResultsDataFrame(self, asAsync=False, timeout=30):
        self._performance['running'] = True
        self._performance['tmr_start'] = time.time()
        queryJSON = self.buildQuery('DATAFRAME')
        self._performance['tmr_query'] = time.time()
        httpResults = self._apiObj.syncQuery(self._resourceUUID, json.dumps(queryJSON))
        self._performance['tmr_recv'] = time.time()
        self._performance['running'] = False
        try:
            from json.decoder import JSONDecodeError
            result = json.loads(httpResults.decode("utf-8"))
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
        ret = pandas.read_csv(StringIO(httpResults))
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


    def getQueryCommand(self, *args):
        """ getQueryCommand() """
        return json.dumps(self.buildQuery(*args))


    def buildQuery(self, *args):
        """ buildQuery(self, *args) """
        ret = {"query":{
            "fields": [],
            "requiredFields": [],
            "numericFilters": {},
            "categoryFilters": {},
        }}
        ret['query']['fields'] = self._lstSelect.getQueryValues()
        ret['query']['requiredFields'] = self._lstRequire.getQueryValues()
        temp = self._lstFilter.getQueryValues()
        ret['query']['numericFilters'] = temp['numericFilters']
        ret['query']['categoryFilters'] = temp['categoryFilters']
        if hasattr(self._refHpdsResourceConnection, 'resource_uuid'):
            if self._refHpdsResourceConnection.resource_uuid != None:
                ret['resourceUUID'] = self._refHpdsResourceConnection.resource_uuid
        if len(args) > 0:
            ret['query']['expectedResultType'] = list(args)[0]
        return ret
