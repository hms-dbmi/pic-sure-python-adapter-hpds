# -*- coding: utf-8 -*-

import PicSureHpdsLib

class Adapter:
    """ Main class of library used to connect to a HPDS resource via PIC-SURE"""
    def __init__(self, connection):
        self.connection_reference = connection

    def help(self):
        print("""
        [HELP] PicSureHpdsLib.Adapter(picsure_connection)
            .version()                      gives version information for library
            .list()                         lists available resources
            .useResource(resource_uuid)     returns an object for selected resource
        """)

    def version(self):
        print(PicSureHpdsLib.__package__ + " Library (version " + PicSureHpdsLib.__version__ + ")")
        print("URL: ".ljust(12,' ') + self.connection_reference.url)

    def list(self):
        self.connection_reference.list()

    def useResource(self, resource_guid):
        return HpdsResourceConnection(self.connection_reference, resource_guid)

class HpdsResourceConnection:
    def __init__(self, connection, resource_uuid):
        self.connection_reference = connection
        self.resource_uuid = resource_uuid

    def help(self):
        print("""
        [HELP] PicSureHpdsLib.useResource(resource_uuid)
            .dictionary()       Used to access data dictionary of the resource
            .query()            Used to query against data in the resource
            
        [ENVIRONMENT]""")
        print("Endpoint URL: ".rjust(28,' ') + self.connection_reference.url)
        print("Resource UUID: ".rjust(28,' ') + str(self.resource_uuid))

    def dictionary(self):
        return PicSureHpdsLib.Dictionary(self)

    def query(self):
        return PicSureHpdsLib.Query(self)



class BypassAdapter(Adapter):
    """ This class is used to connect directly to a HPDS resource (bypassing PIC-SURE) """
    def __init__(self, url, token=None):
        url = url.strip()
        if not url.endswith("/"):
            url = url + "/"
        self.connection_reference = BypassConnection(url, token)

    def useResource(self, resource_guid=None):
        return HpdsResourceConnection(self.connection_reference, resource_guid)

class BypassConnection:
    def __init__(self, url, token):
        tempurl = url.strip()
        if tempurl.endswith("/"):
            tempurl = url
        else:
            tempurl = tempurl + "/"
        self.url = tempurl
        self._token = token

    def help(self):
        print("""
        [HELP] PicSureClient.BypassClient.connect(url, token)
            .list()                 Prints a list of available resources
            .about(resource_uuid)   Prints details about a specific resource

        [TODO] UPDATE THIS TO BE RELEVANT TO BYPASS BEHAVIOR
        """)

    def about(self, resource_uuid=""):
        # print out info from /info about the endpoint
        # TODO: finish this
        import httplib2
        h = httplib2.Http()
        hdrs = {"Content-Type": "application/json"}
        (resp_headers, content) = h.request(uri=self.url + "info/"+resource_uuid, method="POST", headers=hdrs, body="{}")
        if resp_headers["status"] != "200":
            print("ERROR: HTTP response was bad")
            print(resp_headers)
            print(content)
            return None
        else:
            pprint.pprint(json.JSONDecoder.loads(content))

    def list(self):
        listing = self.getResources()
        if listing != None:
            print("+".ljust(39, '-') + '+'.ljust(55, '-'))
            print("|  Resource UUID".ljust(39, ' ') + '|  Resource Name'.ljust(50, ' '))
            print("+".ljust(39, '-') + '+'.ljust(55, '-'))
            for rec in listing:
                print('| ' + rec['uuid'].ljust(35, ' ') + ' | ' + rec['name'])
                print('| Description: ' + rec['description'])
                print("+".ljust(39, '-') + '+'.ljust(55, '-'))

    def getInfo(self, uuid):
        import httplib2
        pass

    def getResources(self):
        """PicSureClient.resources() function is used to list all resources on the connected endpoint"""
        import httplib2
        import json
        httpConn = httplib2.Http()
        httpHeaders = {'Content-Type': 'application/json'}
        (resp_headers, content) = httpConn.request(self.url + "info", "POST", headers=httpHeaders, body="{}")
        if resp_headers["status"] != "200":
            print("ERROR: HTTP response was bad")
            print(resp_headers)
            print(content)
            return list()
        else:
            temp = json.loads(content)
            ret=[{
                "uuid": temp["id"],
                "name": temp["name"],
                "description":"[Resource accessed directly (bypassing PIC-SURE framework)]"
            }]
            return ret

    def _api_obj(self):
        """PicSureClient._api_obj() function returns a new, preconfigured PicSureConnectionAPI class instance """
        return BypassConnectionAPI(self.url, self._token)

class BypassConnectionAPI:
    def __init__(self, url, token):
        # make sure passed URL ends in slash
        url = url.strip()
        if not url.endswith("/"):
            url = url + "/"

        # save values
        self.url = url
        self._token = token

    def info(self, resource_uuid):
        # https://github.com/hms-dbmi/pic-sure/blob/master/pic-sure-resources/pic-sure-resource-api/src/main/java/edu/harvard/dbmi/avillach/service/ResourceWebClient.java#L43
        import httplib2
        import json
        httpConn = httplib2.Http()
        httpHeaders = {'Content-Type': 'application/json'}
        (resp_headers, content) = httpConn.request(self.url + "info", "POST", headers=httpHeaders, body="{}")
        if resp_headers["status"] != "200":
            print("ERROR: HTTP response was bad")
            print(self.url+"info")
            print(resp_headers)
            print(content)
            return list()
        else:
            return json.loads(content)

    def search(self, resource_uuid, query=None):
        # make sure a Resource UUID is passed via the body of these commands
        # https://github.com/hms-dbmi/pic-sure/blob/master/pic-sure-resources/pic-sure-resource-api/src/main/java/edu/harvard/dbmi/avillach/service/ResourceWebClient.java#L69
        import httplib2
        import json
        httpConn = httplib2.Http()
        httpHeaders = {'Content-Type': 'application/json'}
        if query == None:
            bodystr = json.dumps({"query":""})
        else:
            bodystr = str(query)
        (resp_headers, content) = httpConn.request(self.url + "search", "POST", headers=httpHeaders, body=bodystr)
        if resp_headers["status"] != "200":
            print("ERROR: HTTP response was bad")
            print(self.url+"search")
            print(resp_headers)
            print(content)
            return '{"results":{}, "error":true}'
        else:
            return content.decode("utf-8")

    def asyncQuery(self, resource_uuid, query):
        # make sure a Resource UUID is passed via the body of these commands
        # https://github.com/hms-dbmi/pic-sure/blob/master/pic-sure-resources/pic-sure-resource-api/src/main/java/edu/harvard/dbmi/avillach/service/ResourceWebClient.java#L98
        import httplib2
        pass

    def syncQuery(self, resource_uuid, query):
        # make sure a Resource UUID is passed via the body of these commands
        # https://github.com/hms-dbmi/pic-sure/blob/master/pic-sure-resources/pic-sure-resource-api/src/main/java/edu/harvard/dbmi/avillach/service/ResourceWebClient.java#L186
        import httplib2
        httpConn = httplib2.Http()
        httpHeaders = {'Content-Type': 'application/json'}
        (resp_headers, content) = httpConn.request(self.url + "query/sync", "POST", headers=httpHeaders, body=query)
        if resp_headers["status"] != "200":
            print("ERROR: HTTP response was bad")
            print(self.url+"query/sync")
            print(resp_headers)
            print(content)
            return ""
        else:
            return content

    def queryStatus(self, resource_uuid, query_uuid):
        # https://github.com/hms-dbmi/pic-sure/blob/master/pic-sure-resources/pic-sure-resource-api/src/main/java/edu/harvard/dbmi/avillach/service/ResourceWebClient.java#L124
        import httplib2
        pass

    def queryResult(self, resource_uuid, query_uuid):
        # https://github.com/hms-dbmi/pic-sure/blob/master/pic-sure-resources/pic-sure-resource-api/src/main/java/edu/harvard/dbmi/avillach/service/ResourceWebClient.java#L155
        import httplib2
        pass
