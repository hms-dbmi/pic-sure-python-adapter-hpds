# -*- coding: utf-8 -*-
import PicSureHpdsLib

class Dictionary:
    """ Main class of library """
    def __init__(self, refHpdsResourceConnection):
        self._refResourceConnection = refHpdsResourceConnection
        self._apiObj = refHpdsResourceConnection.connection_reference._api_obj()

    def help(self):
        print("""
        [HELP] PicSureHpdsLib.Client(connection).useResource(uuid).dictionary()
            .find()                 Lists all data dictionary entries
            .find(search_string)    Lists matching data dictionary entries
        """)

    def find(self, term=None):
        results = self._apiObj.search(term)
        return PicSureHpdsLib.DictionaryResult(results)
