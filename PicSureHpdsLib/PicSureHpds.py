# -*- coding: utf-8 -*-

import PicSureHpdsLib
import json
import time

class Adapter:
    """ Main class of library used to connect to a HPDS resource via PIC-SURE"""
    def __init__(self, connection):
        self.connection_reference = connection

    def help(self):
        print("""
        [HELP] PicSureHpdsLib.Adapter(picsure_connection)
            .version()                      gives version information for library
            .useResource(resource_uuid)     returns an object for selected resource
            .unlockResource(resource_uuid, key)     For Administrators Use
        """)

    def version(self):
        print(PicSureHpdsLib.__package__ + " Library (version " + PicSureHpdsLib.__version__ + ")")
        print("URL: ".ljust(12,' ') + self.connection_reference.url)

    def useResource(self, resource_uuid = None):
        uuid = resource_uuid
        if uuid is None and len(self.connection_reference.resource_uuids) == 1:
            uuid = self.connection_reference.resource_uuids[0]
        else:
            if uuid is None:
                # throw exception if a resource uuid wass not provided and more than 1 resource exists
                raise KeyError('Please specify a UUID, there is more than 1 resource.')

        if uuid in self.connection_reference.resource_uuids:
            return HpdsResourceConnection(self.connection_reference, uuid)
        else:
            raise KeyError('Resource UUID "'+uuid+'" was not found!')

    def unlockResource(self, resource_uuid, key = False):
        """ unlockResource(resource_uuid, key=str) Unlocks a newly-started HPDS resource"""
        if key is False:
            import getpass
            key = getpass.getpass("Key to unlock the HPDS resource: ")

        # ===== TODO: This is the correct way to do this, thru the API object =====
        # api_obj = self.connection_reference._api_obj()
        # results = BypassConnectionAPI.asyncQuery(resource_uuid, '{"resourceCredentials": {"key": "'+key+'"}}')
        # ===== NOT AS FOLLOWS ====================================================
        import httplib2
        httpConn = httplib2.Http()
        httpHeaders = {'Content-Type': 'application/json'}
        (resp_headers, content) = httpConn.request(uri=self.connection_reference.url + "query", method="POST", headers=httpHeaders, body='{"resourceCredentials": {"key": "'+key+'"}}')
        if resp_headers["status"] != "200":
            print("ERROR: HTTP response was bad")
            print(resp_headers)
            print(content.decode("utf-8"))
            return False
        else:
            print(content.decode("utf-8"))
            return True


class HpdsResourceConnection:
    def __init__(self, connection, resource_uuid):
        self.connection_reference = connection
        self.resource_uuid = resource_uuid

        # connect to PSAMA and get profile information
        profile_str = self.connection_reference._api_obj().profile()
        self._profile_info = json.loads(profile_str)

        # validate query template
        # if user has null or missing query template create a blank template
        if("queryTemplate" in self._profile_info):
            if(self._profile_info["queryTemplate"] == None or self._profile_info["queryTemplate"].lower() == 'null'):
                self._profile_info["queryTemplate"] = '{}'
        else:
            self._profile_info["queryTemplate"] = '{}'

    def help(self):
        print("""
        [HELP] PicSureHpdsLib.useResource(resource_uuid)
            .dictionary()       Used to access data dictionary of the resource
            .query()            Used to query against data in the resource
            .retrieveQueryResults(query_uuid) returns the results of an asynchronous query that has already been submitted to PICSURE

        [ENVIRONMENT]""")
        print("Endpoint URL: ".rjust(28,' ') + self.connection_reference.url)
        print("Resource UUID: ".rjust(28,' ') + str(self.resource_uuid))


    def dictionary(self):
        return PicSureHpdsLib.Dictionary(self)

    def getQueryByUUID(self, query_uuid):
        metadataStr = self.connection_reference._api_obj().queryMetadata(query_uuid)
        print("STR ", metadataStr)
        metadata = json.loads( metadataStr )
        print("JSON ", metadata)
        query = PicSureHpdsLib.Query(self)
        # use 'load' here instead of passing in as a param to avoid parsing to a string and back
        query.load(metadata["resultMetadata"]["queryJson"])
        return query;

    def query(self, load_query=None):
        # retrieve PSAMA profile info if not previously done
        if "queryTemplate" in self._profile_info and load_query is None:
            if(self._profile_info["queryTemplate"] is None):
                # Set to empty query if template from profile is null
                load_query = '{}'
            if len(str(self._profile_info["queryTemplate"])) > 0:
                # Set to queryTemplate if it exists in the psama profile
                load_query = self._profile_info["queryTemplate"]
        else:
            # If query template does not exist in profile then make an empty load query
            # Do this to to avoid null exceptions
            load_query = '{}'
        return PicSureHpdsLib.Query(self, load_query)

    def retrieveQueryResults(self, query_uuid):
        load_query = False
        if "queryTemplate" in self._profile_info:
            if(self._profile_info["queryTemplate"] is None):
                # Set to empty query if template from profile is null
                load_query = '{}'
            if len(str(self._profile_info["queryTemplate"])) > 0:
                # Set to queryTemplate if it exists in the psama profile
                load_query = self._profile_info["queryTemplate"]
        if load_query is False:
            load_query = "{}"

        while True:
            status_json = self.connection_reference._api_obj().queryStatus(self.resource_uuid, query_uuid, load_query)
            print(status_json)
            status = json.loads(status_json)
            if status["status"] == "AVAILABLE":
               break
            elif status["status"] == "ERROR":
                print("An error occurred retrieving this query; please check the server logs")
                return {}
            else:
               time.sleep(1)
        return self.connection_reference._api_obj().queryResult(self.resource_uuid, query_uuid)
    
