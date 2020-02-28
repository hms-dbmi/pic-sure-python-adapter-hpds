# -*- coding: utf-8 -*-

import PicSureHpdsLib
import json
import time


class ImmutableQuery:
    """ Main class containing functionality for an async query """

    def __init__(self, refHpdsResourceConnection, query_id):
        self._query_id = query_id
        self._refHpdsResourceConnection = refHpdsResourceConnection
        self._apiObj = refHpdsResourceConnection.connection_reference._api_obj()
        self._resourceUUID = refHpdsResourceConnection.resource_uuid
        self._query_error = False
        self._query_done = False
        self._lstSelect = PicSureHpdsLib.AttrListImmutableKeys(
            help_text="""
            select().
              show()                lists all current columns that will be returned in results
            """,
            resource_uuid=self._resourceUUID,
            apiObj=self._apiObj,
            allowVariantSpec=False
        )
        self._lstRequire = PicSureHpdsLib.AttrListImmutableKeys(
            help_text="""
            require().
              show()                lists all current columns that results records must have
            """,
            resource_uuid=self._resourceUUID,
            apiObj=self._apiObj
        )
        self._lstCrossCntFields = PicSureHpdsLib.AttrListImmutableKeys(
            help_text="""
                crosscount().
                  show()                lists all current columns that will be calculated in cross counts
                """,
            resource_uuid=self._resourceUUID,
            apiObj=self._apiObj
        )
        self._lstAnyOf = PicSureHpdsLib.AttrListImmutableKeys(
            help_text="""
                anyof().
                  show()                lists all current columns ... 
                """,
            resource_uuid=self._resourceUUID,
            apiObj=self._apiObj
        )
        self._lstFilter = PicSureHpdsLib.AttrListImmutableKeyValues(
            help_text="""
            filter().
              show()                            lists all current filters that results records must satisfy
            """,
            resource_uuid=self._resourceUUID,
            apiObj=self._apiObj
        )

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

        .getID()        Get the identifier of the query
        .getStatus()    Get the status of the query (examp. PENDING, DONE, ERROR)
        .getResults()   returns the data that was originally specified when the query was ran
        .show()         lists all current query parameters
        .save()         returns the JSON-formatted query request as string
        .clone()        returns a new query already setup with the criteria from this query
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
            print("ERROR: did you mean to do something like .select().show()")
            return None
        return self._lstSelect

    def crosscounts(self, *args, **kwargs):
        if len(args) > 0 or len(kwargs) > 0:
            print("ERROR: did you mean to do something like .crosscounts().show()")
            return None
        return self._lstCrossCntFields

    def require(self, *args, **kwargs):
        if len(args) > 0 or len(kwargs) > 0:
            print("ERROR: did you mean to do something like .require().show()")
            return None
        return self._lstRequire

    def anyof(self, *args, **kwargs):
        if len(args) > 0 or len(kwargs) > 0:
            print("ERROR: did you mean to do something like .anyof().show()")
            return None
        return self._lstAnyOf

    def filter(self, *args, **kwargs):
        if len(args) > 0 or len(kwargs) > 0:
            print("ERROR: did you mean to do something like .filter().show()")
            return None
        return self._lstFilter

    def queryStatus(self, query_id):
        pass

    def getStatus(self, query_uuid=None):
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

    def getResults(self, asAsync=False):
        if not self._query_done:
            print("Need to query the status from the server before continuing")
            # TODO: query the status if needed

        if not self._query_done:
            print("The query is not done executing, please try again later.")
            return None

        if self._query_error is not False:
            print("ERROR: msg=" + str(self._query_error))
            return None


        httpResults = self._apiObj.queryResult(self._resourceUUID, self._query_id)


            syncQuery(self._resourceUUID, json.dumps(queryJSON))
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

    def save(self, *args):
        return json.dumps(self.buildQuery(*args))

    def clone(self):
        return PicSureHpdsLib.Query().load(self.save())

    def buildQuery(self, *args):
        """ buildQuery(self, *args) """
        ret = {"query": {
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
