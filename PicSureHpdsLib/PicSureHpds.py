# -*- coding: utf-8 -*-

import PicSureHpdsLib


class Client:
    """ Main class of library """
    def __init__(self, connection):
        self.connection_reference = connection
        pass

    def version(self):
        print(PicSureHpdsLib.__package__ + " Library (version " + PicSureHpdsLib.__version__ + ")\n")

    def useResource(resource_guid):
        return HpdsResourceConnection(self.connection_reference, resource_guid)

class HpdsResourceConnection:
    def __init__(self, connection, resource_uuid):
        self.connection_reference = connection
        self.resource_uuid = resource_uuid

    def dictionary(self):
        return PicSureHpdsLib.Dictionary(self)

    def query(self):
        return PicSureHpdsLib.Query(self)
