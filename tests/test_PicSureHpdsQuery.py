from PicSureClient import Connection
import PicSureHpdsLib
from PicSureHpdsLib import PicSureHpdsDictionary, PicSureHpdsQuery, PicSureHpds
import unittest
from unittest.mock import patch
import types

class TestHpdsQuery(unittest.TestCase):

    @patch('PicSureClient.Connection')
    def test_HpdsQuery_create(self, mock_picsure_connection):
        conn = mock_picsure_connection()
        test_uuid = "my-test-uuid"
        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)
        query = resource.query()
        # test that it was created correctly
        self.assertIsInstance(query, PicSureHpdsQuery.Query)
        self.assertEqual(query._resourceUUID, test_uuid)
        self.assertIs(query._refHpdsResourceConnection, resource)

    @patch('PicSureClient.Connection')
    def test_HpdsQuery_select_list(self, mock_picsure_connection):
        conn = mock_picsure_connection()
        test_uuid = "my-test-uuid"
        test_key = "my-test-key"
        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)
        query = resource.query()
        self.assertIsInstance(query.select, types.MethodType)
        self.assertIsInstance(query.select().add, types.MethodType)
        self.assertIsInstance(query.select().delete, types.MethodType)
        self.assertIsInstance(query.select(), PicSureHpdsLib.AttrListKeys)


    @patch('PicSureClient.Connection')
    def test_HpdsQuery_crosscounts_list(self, mock_picsure_connection):
        conn = mock_picsure_connection()
        test_uuid = "my-test-uuid"
        test_key = "my-test-key"
        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)
        query = resource.query()
        self.assertIsInstance(query.crosscounts, types.MethodType)
        self.assertIsInstance(query.crosscounts().add, types.MethodType)
        self.assertIsInstance(query.crosscounts().delete, types.MethodType)
        self.assertIsInstance(query.crosscounts(), PicSureHpdsLib.AttrListKeys)

    @patch('PicSureClient.Connection')
    def test_HpdsQuery_require_list(self, mock_picsure_connection):
        conn = mock_picsure_connection()
        test_uuid = "my-test-uuid"
        test_key = "my-test-key"
        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)
        query = resource.query()
        self.assertIsInstance(query.require, types.MethodType)
        self.assertIsInstance(query.require().add, types.MethodType)
        self.assertIsInstance(query.require().delete, types.MethodType)
        self.assertIsInstance(query.require(), PicSureHpdsLib.AttrListKeys)

    @patch('PicSureClient.Connection')
    def test_HpdsQuery_anyof_list(self, mock_picsure_connection):
        conn = mock_picsure_connection()
        test_uuid = "my-test-uuid"
        test_key = "my-test-key"
        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)
        query = resource.query()
        self.assertIsInstance(query.anyof, types.MethodType)
        self.assertIsInstance(query.anyof().add, types.MethodType)
        self.assertIsInstance(query.anyof().delete, types.MethodType)
        self.assertIsInstance(query.anyof(), PicSureHpdsLib.AttrListKeys)

    @patch('PicSureClient.Connection')
    def test_HpdsQuery_filter_list(self, mock_picsure_connection):
        conn = mock_picsure_connection()
        test_uuid = "my-test-uuid"
        test_key = "my-test-key"
        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)
        query = resource.query()
        self.assertIsInstance(query.filter, types.MethodType)
        self.assertIsInstance(query.filter().add, types.MethodType)
        self.assertIsInstance(query.filter().delete, types.MethodType)
        self.assertIsInstance(query.filter(), PicSureHpdsLib.AttrListKeyValues)



    @patch('httplib2.Http.request')
    @patch('PicSureClient.Connection')
    def test_HpdsQuery_func_getCount(self, mock_picsure_connection, mock_http_request):
        test_uuid = "my-test-uuid"
        test_url = "http://my-test.url/"
        test_token = "this.is.my.test.token"

        conn = mock_picsure_connection()
        API = PicSureHpds.BypassConnectionAPI(test_url, test_token)
        def ret_API():
            return API
        conn._api_obj = ret_API

        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)
        query = resource.query()

        resp_headers = {"status": "200"}
        mock_http_request.return_value = (resp_headers, "1000".encode("utf-8"))
        req_body = query.getQueryCommand("COUNT")

        query.getCount()

        mock_http_request.assert_called_with(uri=test_url+"query/sync", method="POST", body=req_body, headers={'Content-Type': 'application/json'})

