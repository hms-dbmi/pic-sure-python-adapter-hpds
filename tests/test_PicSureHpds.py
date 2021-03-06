from PicSureHpdsLib import PicSureHpdsDictionary, PicSureHpds, PicSureHpdsQuery
import unittest
from unittest.mock import patch, PropertyMock
import httplib2
import json
import io
import sys



class TestHpdsAdapter(unittest.TestCase):
    @patch('PicSureClient.Connection')
    def test_Adapter_create(self, MockPicSureConnection):
        conn = MockPicSureConnection()
        adapter = PicSureHpds.Adapter(conn)
        # correct type
        self.assertIsInstance(adapter, PicSureHpds.Adapter)
        # correct reference to connection
        self.assertIs(adapter.connection_reference, conn)


    @patch('PicSureClient.Connection')
    def test_Adapter_func_help(self, MockPicSureConnection):
        conn = MockPicSureConnection()
        adapter = PicSureHpds.Adapter(conn)
        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            adapter.help()
            sys.stdout = sys.__stdout__  # Reset redirect. Needed for it to work!
            captured = fake_stdout.getvalue()
            print("Captured:\n" + captured)
            self.assertTrue(len(captured) > 0)


    @patch('PicSureClient.Connection')
    def test_Adapter_func_getResource_uuid_valid(self, MockPicSureConnection):
        # Just have to put some kind of JSON response so that there is a value to parse when PSAMA Profile is called
        MockPicSureConnection.return_value._api_obj.return_value.profile.return_value = '{"testjson":"awesome"}'

        test_uuid = "my-test-uuid"
        conn = MockPicSureConnection()
        conn.resource_uuids = [test_uuid]

        adapter = PicSureHpds.Adapter(conn)
        resource = adapter.useResource(test_uuid)

        # correct type?
        self.assertIsInstance(resource, PicSureHpds.HpdsResourceConnection)
        # correct uuid?
        self.assertEqual(resource.resource_uuid, test_uuid)


    @patch('httplib2.Http.request')
    @patch('PicSureClient.Connection')
    def test_Adapter_func_getResource_uuid_invalid(self, MockHttp, MockPicSureConnection):
        # Just have to put some kind of JSON response so that there is a value to parse when PSAMA Profile is called
        MockPicSureConnection.return_value._api_obj.return_value.profile.return_value = '{"testjson":"awesome"}'

        test_uuid = "my-test-uuid"
        test_uuid_BAD = "my-test-uuid_BAD"
        conn = MockPicSureConnection()
        conn.resource_uuids = [test_uuid]

        adapter = PicSureHpds.Adapter(conn)
        with self.assertRaises(KeyError) as cm:
            resource = adapter.useResource(test_uuid_BAD)

        # should have thrown an exception
        self.assertIsInstance(cm.exception, KeyError)


    @patch('httplib2.Http.request')
    @patch('PicSureClient.Connection')
    def test_Adapter_func_getResource_default_success(self, MockHttp, MockPicSureConnection):
        # Just have to put some kind of JSON response so that there is a value to parse when PSAMA Profile is called
        MockPicSureConnection.return_value._api_obj.return_value.profile.return_value = '{"testjson":"awesome"}'

        test_uuid = "my-test-uuid"
        conn = MockPicSureConnection()
        conn.resource_uuids = [test_uuid]

        adapter = PicSureHpds.Adapter(conn)
        resource = adapter.useResource()

        # correct type?
        self.assertIsInstance(resource, PicSureHpds.HpdsResourceConnection)

        # the resource should be configured for the only uuid provided
        self.assertEqual(resource.resource_uuid, test_uuid, "the resource UUID was not populated correctly")


    @patch('httplib2.Http.request')
    @patch('PicSureClient.Connection')
    def test_Adapter_func_getResource_default_failure(self, MockHttp, MockPicSureConnection):
        # Just have to put some kind of JSON response so that there is a value to parse when PSAMA Profile is called
        MockPicSureConnection.return_value._api_obj.return_value.profile.return_value = '{"testjson":"awesome"}'

        test_uuid1 = "my-test-uuid-1"
        test_uuid2 = "my-test-uuid-2"
        conn = MockPicSureConnection()
        conn.resource_uuids = [test_uuid1, test_uuid2]

        adapter = PicSureHpds.Adapter(conn)
        with self.assertRaises(KeyError) as cm:
            resource = adapter.useResource()

        # should have thrown an exception
        self.assertIsInstance(cm.exception, KeyError)


    @patch('PicSureClient.Connection')
    @patch('httplib2.Http.request')
    def test_Adapter_func_unlockResource(self, MockHttp, MockPicSureConnection):
        test_url = "http://endpoint.url/pic-sure/"
        test_token = "my-JWT-token"
        test_uuid = "my-test-uuid"
        test_key = "0000DEADBEEF00000000DEADBEEF0000"

        resp_headers = {"status": "200"}
        json_content = json.dumps({"resourceCredentials": {"key": test_key}})
        MockHttp.return_value = (resp_headers, json_content.encode("utf-8"))

        conn = MockPicSureConnection()
        conn.url = test_url
        adapter = PicSureHpds.Adapter(conn)
        adapter.unlockResource(test_uuid, test_key)

        MockHttp.assert_called_with(body=json_content, headers={'Content-Type': 'application/json'}, method="POST", uri=test_url + "query")



class TestHpdsResourceConnection(unittest.TestCase):
    @patch('PicSureClient.Connection')
    def test_HpdsResourceConnection_create(self, MockPicSureConnection):
        # Just have to put some kind of JSON response so that there is a value to parse
        MockPicSureConnection.return_value._api_obj.return_value.profile.return_value = '{"testjson":"awesome"}'

        conn = MockPicSureConnection()
        test_uuid = "my-test-uuid"
        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)

        self.assertIsInstance(resource, PicSureHpds.HpdsResourceConnection)
        self.assertIs(test_uuid, resource.resource_uuid)
        self.assertIs(conn, resource.connection_reference)


    @patch('PicSureClient.Connection')
    def test_HpdsResourceConnection_func_help(self, MockPicSureConnection):
        # Just have to put some kind of JSON response so that there is a value to parse
        MockPicSureConnection.return_value._api_obj.return_value.profile.return_value = '{"testjson":"awesome"}'

        conn = MockPicSureConnection()
        test_uuid = "my-test-uuid"
        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)
        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            resource.help()
            sys.stdout = sys.__stdout__  # Reset redirect. Needed for it to work!
            captured = fake_stdout.getvalue()
            print("Captured:\n" + captured)
            self.assertTrue(len(captured) > 0)


    @patch('PicSureClient.Connection')
    def test_HpdsResourceConnection_func_dictionary(self, MockPicSureConnection):
        # Just have to put some kind of JSON response so that there is a value to parse
        MockPicSureConnection.return_value._api_obj.return_value.profile.return_value = '{"testjson":"awesome"}'

        conn = MockPicSureConnection()
        test_uuid = "my-test-uuid"
        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)

        self.assertIsInstance(resource, PicSureHpds.HpdsResourceConnection)
        self.assertIs(resource.resource_uuid, test_uuid)

        dictionary = resource.dictionary()
        self.assertIsInstance(dictionary, PicSureHpdsDictionary.Dictionary)


    @patch('PicSureClient.Connection')
    def test_HpdsResourceConnection_func_query(self, MockPicSureConnection):
        # Just have to put some kind of JSON response so that there is a value to parse
        MockPicSureConnection.return_value._api_obj.return_value.profile.return_value = '{"testjson":"awesome"}'

        conn = MockPicSureConnection()
        test_uuid = "my-test-uuid"
        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)

        query = resource.query()
        self.assertIsInstance(query, PicSureHpdsQuery.Query)


    @patch('PicSureClient.Connection')
    def test_HpdsResourceConnection_func_query_withTemplate(self, MockPicSureConnection):
        test_uuid = "my-test-uuid"
        query_obj = {"queryTemplate":
                     ''' { "fields": ["\\\\select\\\\key"],
                     "categoryFilters": { "\\\\filter_categorical\\\\set1": ["cat1"],
                     "\\\\filter_categorical\\\\set2": ["catA", "catC"]}}''',
                     "resourceUUID": str(test_uuid)}

        # Just have to put some kind of JSON response so that there is a value to parse
        MockPicSureConnection.return_value._api_obj.return_value.profile.return_value = json.dumps(query_obj)

        conn = MockPicSureConnection()

        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)

        query = resource.query()
        self.assertIsInstance(query, PicSureHpdsQuery.Query)

        query_as_loaded = json.loads(query.save())

        # test that it was created correctly
        #self.assertEqual(json.dumps(query_obj), query_as_loaded)
        self.assertIs(query._refHpdsResourceConnection, resource)
        self.assertTrue("\\select\\key" in query_as_loaded["query"]["fields"])
        self.assertTrue("\\filter_categorical\\set1" in query_as_loaded["query"]["categoryFilters"])



class TestHpdsBypass(unittest.TestCase):
    def test_HpdsBypass_Adapter_create(self):
        test_url = "http://endpoint.url/pic-sure/"
        test_token = "my-JWT-token"

        adapter = PicSureHpds.BypassAdapter(test_url, test_token)

        self.assertIsInstance(adapter, PicSureHpds.BypassAdapter, "Should be of BypassAdapter type")
        self.assertIsInstance(adapter.connection_reference, PicSureHpds.BypassConnection, "Should be of BypassConnection type")

        self.assertEqual(test_url, adapter.connection_reference.url, "correct url should be passed into BypassConnection")
        self.assertEqual(test_token, adapter.connection_reference._token, "correct JWT token should be passed into BypassConnection")


    def test_HpdsBypass_Adapter_endpoint_trailing_slash(self):
        test_bad_url = "http://endpoint.url/pic-sure"
        test_expected_url = "http://endpoint.url/pic-sure/"
        test_token = "my-JWT-token"

        adapter = PicSureHpds.BypassAdapter(test_expected_url, test_token)
        self.assertEqual(test_expected_url, adapter.connection_reference.url, "correct url should be passed unchanged into BypassConnection")

        adapter = PicSureHpds.BypassAdapter(test_bad_url, test_token)
        self.assertEqual(test_expected_url, adapter.connection_reference.url, "incorrect url should add trailing backslash to endpoint url")


    def test_HpdsBypass_Adapter_func_useResource(self):
        test_url = "http://endpoint.url/pic-sure/"
        test_token = "my-JWT-token"

        adapter = PicSureHpds.BypassAdapter(test_url, test_token)
        resource = adapter.useResource()
        self.assertIsInstance(resource, PicSureHpds.HpdsResourceConnection)


    @patch('PicSureClient.Connection')
    @patch('httplib2.Http.request')
    def test_HpdsBypass_Adapter_func_unlockResource(self, MockHttp, MockPicSureConnection):
        test_url = "http://endpoint.url/pic-sure/"
        test_token = "my-JWT-token"
        test_uuid = "my-test-uuid"
        test_key = "0000DEADBEEF00000000DEADBEEF0000"

        resp_headers = {"status": "200"}
        json_content = json.dumps({"resourceCredentials": {"key": test_key}})
        MockHttp.return_value = (resp_headers, json_content.encode("utf-8"))

        conn = MockPicSureConnection()
        conn.url = test_url
        adapter = PicSureHpds.Adapter(conn)
        adapter.unlockResource(test_uuid, test_key)

        MockHttp.assert_called_with(body=json_content, headers={'Content-Type': 'application/json'}, method="POST", uri=test_url + "query")


    @patch('sys.stdout', new_callable=io.StringIO)
    def test_HpdsBypass_Connection_func_help(self, fake_stdout):
        test_url = "http://endpoint.url/pic-sure/"
        test_token = "my-JWT-token"

        conn = PicSureHpds.BypassConnection(test_url, test_token)
        conn.help()
        sys.stdout = sys.__stdout__  # Reset redirect. Needed for it to work!
        captured = fake_stdout.getvalue()
        print("Captured:\n" + captured)
        self.assertTrue(len(captured) > 0)


    @patch('httplib2.Http.request')
    def test_HpdsBypass_Connection_func_about(self, MockHttp):
        resp_headers = {"status": "200"}
        content = '{"test": "this is a test of bypass.about()"}'
        MockHttp.return_value = (resp_headers, content.encode("utf-8"))

        test_url = "http://endpoint.url/pic-sure/"
        test_token = "my-JWT-token"
        test_uuid = "my-test-uuid"

        conn = PicSureHpds.BypassConnection(test_url, test_token)
        conn.about(test_uuid)

        MockHttp.assert_called_with(uri=test_url+"info/"+test_uuid, method="POST", body="{}", headers={'Content-Type': 'application/json'})


    @patch('httplib2.Http.request')
    def test_HpdsBypass_Connection_func_getResources(self, MockHttp):
        resp_headers = {"status": "200"}
        content = ["test-uuid-1", "test-uuid-2", "test-uuid-3"]
        json_content = json.dumps(content)
        MockHttp.return_value = (resp_headers, json_content.encode("utf-8"))

        test_url = "http://endpoint.url/pic-sure/"
        test_token = "my-JWT-token"
        test_uuid = "my-test-uuid"

        conn = PicSureHpds.BypassConnection(test_url, test_token)
        uuid_list = conn.getResources()

        MockHttp.assert_called_with(uri=test_url+"info", method="POST", body="{}", headers={'Content-Type': 'application/json'})


    @patch('httplib2.Http.request')
    def test_HpdsBypass_Connection_func_list(self, MockHttp):
        resp_headers = {"status": "200"}
        content = ["test-uuid-1", "test-uuid-2", "test-uuid-3"]
        json_content = json.dumps(content)
        MockHttp.return_value = (resp_headers, json_content.encode("utf-8"))

        test_url = "http://endpoint.url/pic-sure/"
        test_token = "my-JWT-token"
        test_uuid = "my-test-uuid"

        conn = PicSureHpds.BypassConnection(test_url, test_token)
        conn.list()

        MockHttp.assert_called_with(uri=test_url+"info", method="POST", body="{}", headers={'Content-Type': 'application/json'})



class TestHpdsBypassAPI(unittest.TestCase):
    def test_HpdsBypassAPI_create(self):
        test_url = "http://endpoint.url/pic-sure/"
        test_token = "my-JWT-token"

        api_obj = PicSureHpds.BypassConnectionAPI(test_url, test_token)

        self.assertIsInstance(api_obj, PicSureHpds.BypassConnectionAPI, "Should be of BypassConnectionAPI type")
        self.assertEqual(test_url, api_obj.url, "correct url should be passed into BypassConnection")
        self.assertEqual(test_token, api_obj._token, "correct JWT token should be passed into BypassConnection")


    def test_HpdsBypassAPI_endpoint_trailing_slash(self):
        test_bad_url = "http://endpoint.url/pic-sure"
        test_expected_url = "http://endpoint.url/pic-sure/"
        test_token = "my-JWT-token"

        api_obj = PicSureHpds.BypassConnectionAPI(test_expected_url, test_token)
        self.assertEqual(test_expected_url, api_obj.url, "correct url should be passed unchanged into BypassConnectionAPI")

        api_obj = PicSureHpds.BypassConnectionAPI(test_bad_url, test_token)
        self.assertEqual(test_expected_url, api_obj.url, "incorrect url should add trailing backslash to endpoint url")


    @patch('httplib2.Http.request')
    def test_HpdsBypassAPI_func_info(self, MockHttp):
        self.fail("This is not yet implemented into the API codebase")
        resp_headers = {"status": "200"}
        content = {"test": "success"}
        json_content = json.dumps(content)
        MockHttp.return_value = (resp_headers, json_content.encode("utf-8"))

        test_url = "http://endpoint.url/pic-sure/"
        test_token = "my-JWT-token"
        test_uuid = "my-test-uuid"

        api_obj = PicSureHpds.BypassConnectionAPI(test_url, test_token)
        api_obj.info(test_uuid)

        MockHttp.assert_called_with(uri=test_url+"info", method="POST", body="{}", headers={'Content-Type': 'application/json'})


    # @patch('httplib2.Http.request')
    # def test_HpdsBypassAPI_func_search_no_term(self, MockHttp):
    #     resp_headers = {"status": "200"}
    #     content = {"test": "success"}
    #     json_content = json.dumps(content)
    #     MockHttp.return_value = (resp_headers, json_content.encode("utf-8"))
    #
    #     test_url = "http://endpoint.url/pic-sure/"
    #     test_token = "my-JWT-token"
    #     test_uuid = "my-test-uuid"
    #
    #     api_obj = PicSureHpds.BypassConnectionAPI(test_url, test_token)
    #     api_obj.search(test_uuid)
    #
    #     MockHttp.assert_called_with(uri=test_url+"info", method="POST", body="{}", headers={'Content-Type': 'application/json'})


    @patch('httplib2.Http.request')
    def test_HpdsBypassAPI_func_search_no_term(self, MockHttp):
        resp_headers = {"status": "200"}
        content = ["test-uuid-1", "test-uuid-2", "test-uuid-3"]
        json_content = json.dumps(content)
        MockHttp.return_value = (resp_headers, json_content.encode("utf-8"))

        test_url = "http://endpoint.url/pic-sure/"
        test_token = "my-JWT-token"
        test_uuid = "my-test-uuid"
        search_term = "asthma"

        api_obj = PicSureHpds.BypassConnectionAPI(test_url, test_token)
        api_obj.search(test_uuid, search_term)

        MockHttp.assert_called_with(uri=test_url+"search", method="POST", body=search_term, headers={'Content-Type': 'application/json'})


    def test_HpdsBypassAPI_func_asyncQuery(self):
        test_url = "http://endpoint.url/pic-sure/"
        test_token = "my-JWT-token"
        test_uuid = "my-test-uuid"
        api_obj = PicSureHpds.BypassConnectionAPI(test_url, test_token)
        api_obj.asyncQuery(test_uuid, "{}")
        self.fail("This is not yet implemented by HPDS")


    @patch('httplib2.Http.request')
    def test_HpdsBypassAPI_func_syncQuery(self, MockHttp):
        resp_headers = {"status": "200"}
        content = ["test-uuid-1", "test-uuid-2", "test-uuid-3"]
        json_content = json.dumps(content)
        MockHttp.return_value = (resp_headers, json_content.encode("utf-8"))


    def test_HpdsBypassAPI_func_queryStatus(self):
        test_url = "http://endpoint.url/pic-sure/"
        test_token = "my-JWT-token"
        test_uuid = "my-test-uuid"
        api_obj = PicSureHpds.BypassConnectionAPI(test_url, test_token)
        api_obj.queryStatus(test_uuid, test_uuid)
        self.fail("This is not yet implemented by HPDS")


    def test_HpdsBypassAPI_func_queryResult(self):
        test_url = "http://endpoint.url/pic-sure/"
        test_token = "my-JWT-token"
        test_uuid = "my-test-uuid"
        api_obj = PicSureHpds.BypassConnectionAPI(test_url, test_token)
        api_obj.queryResult(test_uuid, test_uuid)
        self.fail("This is not yet implemented by HPDS")
