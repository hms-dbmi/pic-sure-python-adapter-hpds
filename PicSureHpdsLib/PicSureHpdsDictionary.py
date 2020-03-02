# -*- coding: utf-8 -*-
import PicSureHpdsLib
import json

class Dictionary:
    """ Main class of library """
    def __init__(self, refHpdsResourceConnection):
        self._refResourceConnection = refHpdsResourceConnection
        self.resourceUUID = refHpdsResourceConnection.resource_uuid
        self._apiObj = refHpdsResourceConnection.connection_reference._api_obj()
        self._profile_queryScopes = None

    def help(self):
        print("""
        [HELP] PicSureHpdsLib.Client(connection).useResource(uuid).dictionary()
            .find()                 Lists all data dictionary entries
            .find(search_string)    Lists matching data dictionary entries
        """)

    def find(self, term=None):
        if term == None:
            query = {"query":""}
        else:
            query = {"query":str(term)}
        results = json.loads(self._apiObj.search(self.resourceUUID, json.dumps(query)))

        # get the queryScopes from the user's profile if needed
        if self._profile_queryScopes is None:
            self._profile_queryScopes = []
            # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
            # TODO: Re-enable once issue with short vs. long-term tokens in PSAMA is fixed
            # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
            # profile = json.loads(self._apiObj.profile())
            # if "queryScopes" in profile:
            #     self._profile_queryScopes = profile["queryScopes"]
            # else:
            #     self._profile_queryScopes = []

        # Filter the dictionary results based on any queryScopes found in the PSAMA profile of the current user
        newResults = dict()
        for resultType in results['results']:
            for idx in results['results'][resultType]:
                valid = False
                if len(self._profile_queryScopes) > 0:
                    for filterScope in self._profile_queryScopes:
                        if idx.startswith(filterScope):
                            valid = True
                            break
                else:
                    valid = True
                if valid:
                    results['results'][resultType][idx]['HpdsDataType'] = resultType
                    newResults[idx] = results['results'][resultType][idx]
        results['results'] = newResults

        return PicSureHpdsLib.DictionaryResult(results)
