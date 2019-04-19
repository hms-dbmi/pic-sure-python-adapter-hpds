# -*- coding: utf-8 -*-
import PicSureHpdsLib
import json

class Dictionary:
    """ Main class of library """
    def __init__(self, refHpdsResourceConnection):
        self._refResourceConnection = refHpdsResourceConnection
        self.resourceUUID = refHpdsResourceConnection.resource_uuid
        self._apiObj = refHpdsResourceConnection.connection_reference._api_obj()

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
        results = self._apiObj.search(self.resourceUUID, json.dumps(query))
        return PicSureHpdsLib.DictionaryResult(results)
