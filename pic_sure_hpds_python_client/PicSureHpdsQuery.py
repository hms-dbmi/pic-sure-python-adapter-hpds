# -*- coding: utf-8 -*-

class PicSureHpdsQuery:
    """ Main class of library """
    def __init__(self):
        self._lstSelect = PicSureHpdsAttrList()
        self._lstRequire = PicSureHpdsAttrList()
        self._lstFilter = PicSureHpdsAttrList()
        pass

    def Select(self):
        return self._lstSelect
    def Require(self):
        return self._lstRequire
    def Filter(self):
        return self._lstFilter


    def getCount(self):
        pass
    def getResults(self):
        pass
