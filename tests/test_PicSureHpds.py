from PicSureHpdsLib import PicSureHpdsDictionary, PicSureHpds, PicSureHpdsQuery
import unittest
from unittest.mock import patch
import httplib2
import json

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
    def test_Adapter_getResource(self, MockPicSureConnection):
        test_uuid = "my-test-uuid"
        conn = MockPicSureConnection()
        adapter = PicSureHpds.Adapter(conn)
        resource = adapter.useResource(test_uuid)

        # correct type?
        self.assertIsInstance(resource, PicSureHpds.HpdsResourceConnection)
        # correct uuid?
        self.assertEqual(resource.resource_uuid, test_uuid)


class TestHpdsResourceConnection(unittest.TestCase):
    @patch('PicSureClient.Connection')
    def test_HpdsResourceConnection_create(self, MockPicSureConnection):
        conn = MockPicSureConnection()
        test_uuid = "my-test-uuid"
        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)

        self.assertIsInstance(resource, PicSureHpds.HpdsResourceConnection)
        self.assertIs(test_uuid, resource.resource_uuid)
        self.assertIs(conn, resource.connection_reference)


    @patch('PicSureClient.Connection')
    def test_HpdsResourceConnection_func_dictionary(self, MockPicSureConnection):
        conn = MockPicSureConnection()
        test_uuid = "my-test-uuid"
        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)

        self.assertIsInstance(resource, PicSureHpds.HpdsResourceConnection)
        self.assertIs(resource.resource_uuid, test_uuid)

        dictionary = resource.dictionary()
        self.assertIsInstance(dictionary, PicSureHpdsDictionary.Dictionary)

    @patch('PicSureClient.Connection')
    def test_HpdsResourceConnection_func_query(self, MockPicSureConnection):
        conn = MockPicSureConnection()
        test_uuid = "my-test-uuid"
        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)

        query = resource.query()
        self.assertIsInstance(query, PicSureHpdsQuery.Query)


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
