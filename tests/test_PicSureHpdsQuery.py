from PicSureClient import Connection
import PicSureHpdsLib
from PicSureHpdsLib import PicSureHpdsDictionary, PicSureHpdsQuery, PicSureHpds
import unittest
from unittest.mock import patch
import types
import io
import sys

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
    def test_HpdsQuery_func_help(self, mock_picsure_connection):
        conn = mock_picsure_connection()
        test_uuid = "my-test-uuid"
        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)
        query = resource.query()
        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            query.help()
            sys.stdout = sys.__stdout__  # Reset redirect. Needed for it to work!
            captured = fake_stdout.getvalue()
            print("Captured:\n" + captured)
            self.assertTrue(len(captured) > 0)


    @patch('PicSureClient.Connection')
    def test_HpdsQuery_func_show(self, mock_picsure_connection):
        conn = mock_picsure_connection()
        test_uuid = "my-test-uuid"
        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)
        query = resource.query()

        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            query.show()
            sys.stdout = sys.__stdout__  # Reset redirect. Needed for it to work!
            captured = fake_stdout.getvalue()
            print("Captured:\n" + captured)
            self.assertTrue(len(captured) > 0)


    @patch('PicSureClient.Connection')
    def test_HpdsQuery_list_select(self, mock_picsure_connection):
        conn = mock_picsure_connection()
        test_uuid = "my-test-uuid"
        test_key = "my-test-key"
        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)
        query = resource.query()
        self.assertIsInstance(query.select, types.MethodType)
        my_list = query.select()
        self.assertIsInstance(my_list.add, types.MethodType)
        self.assertIsInstance(my_list.delete, types.MethodType)
        self.assertIsInstance(my_list, PicSureHpdsLib.AttrListKeys)
        # micro test to confirm warning is printed if parameters are passed
        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            query.select("some_attempted_key")
            sys.stdout = sys.__stdout__  # Reset redirect. Needed for it to work!
            captured = fake_stdout.getvalue()
            print("Message on parameter useage:\n" + captured)
            self.assertTrue(len(captured) > 0)


    @patch('PicSureClient.Connection')
    def test_HpdsQuery_list_crosscounts(self, mock_picsure_connection):
        conn = mock_picsure_connection()
        test_uuid = "my-test-uuid"
        test_key = "my-test-key"
        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)
        query = resource.query()
        self.assertIsInstance(query.crosscounts, types.MethodType)
        my_list = query.crosscounts()
        self.assertIsInstance(my_list.add, types.MethodType)
        self.assertIsInstance(my_list.delete, types.MethodType)
        self.assertIsInstance(my_list, PicSureHpdsLib.AttrListKeys)
        # micro test to confirm warning is printed if parameters are passed
        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            query.crosscounts("some_attempted_key")
            sys.stdout = sys.__stdout__  # Reset redirect. Needed for it to work!
            captured = fake_stdout.getvalue()
            print("Message on parameter useage:\n" + captured)
            self.assertTrue(len(captured) > 0)


    @patch('PicSureClient.Connection')
    def test_HpdsQuery_list_require(self, mock_picsure_connection):
        conn = mock_picsure_connection()
        test_uuid = "my-test-uuid"
        test_key = "my-test-key"
        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)
        query = resource.query()
        self.assertIsInstance(query.require, types.MethodType)
        my_list = query.require()
        self.assertIsInstance(my_list.add, types.MethodType)
        self.assertIsInstance(my_list.delete, types.MethodType)
        self.assertIsInstance(my_list, PicSureHpdsLib.AttrListKeys)
        # micro test to confirm warning is printed if parameters are passed
        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            query.require("some_attempted_key")
            sys.stdout = sys.__stdout__  # Reset redirect. Needed for it to work!
            captured = fake_stdout.getvalue()
            print("Message on parameter useage:\n" + captured)
            self.assertTrue(len(captured) > 0)


    @patch('PicSureClient.Connection')
    def test_HpdsQuery_list_anyof(self, mock_picsure_connection):
        conn = mock_picsure_connection()
        test_uuid = "my-test-uuid"
        test_key = "my-test-key"
        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)
        query = resource.query()
        self.assertIsInstance(query.anyof, types.MethodType)
        my_list = query.anyof()
        self.assertIsInstance(my_list.add, types.MethodType)
        self.assertIsInstance(my_list.delete, types.MethodType)
        self.assertIsInstance(my_list, PicSureHpdsLib.AttrListKeys)
        # micro test to confirm warning is printed if parameters are passed
        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            query.anyof("some_attempted_key")
            sys.stdout = sys.__stdout__  # Reset redirect. Needed for it to work!
            captured = fake_stdout.getvalue()
            print("Message on parameter useage:\n" + captured)
            self.assertTrue(len(captured) > 0)


    @patch('PicSureClient.Connection')
    def test_HpdsQuery_list_filter(self, mock_picsure_connection):
        conn = mock_picsure_connection()
        test_uuid = "my-test-uuid"
        test_key = "my-test-key"
        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)
        query = resource.query()
        self.assertIsInstance(query.filter, types.MethodType)
        my_list = query.filter()
        self.assertIsInstance(my_list.add, types.MethodType)
        self.assertIsInstance(my_list.delete, types.MethodType)
        self.assertIsInstance(my_list, PicSureHpdsLib.AttrListKeyValues)
        # micro test to confirm warning is printed if parameters are passed
        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            query.filter("some_attempted_key")
            sys.stdout = sys.__stdout__  # Reset redirect. Needed for it to work!
            captured = fake_stdout.getvalue()
            print("Message on parameter useage:\n" + captured)
            self.assertTrue(len(captured) > 0)


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


    @patch('httplib2.Http.request')
    @patch('PicSureClient.Connection')
    def test_HpdsQuery_func_getResults(self, mock_picsure_connection, mock_http_request):
        test_uuid = "my-test-uuid"
        test_url = "http://my-test.url/"
        test_token = "this.is.my.test.token"
        test_return_CSV = "ROW\tVALUE\n" + "1\tTrue\n" + "2\tFalse\n" + "3\tUnknown\n"

        conn = mock_picsure_connection()
        API = PicSureHpds.BypassConnectionAPI(test_url, test_token)
        def ret_API():
            return API
        conn._api_obj = ret_API

        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)
        query = resource.query()

        resp_headers = {"status": "200"}
        mock_http_request.return_value = (resp_headers, test_return_CSV.encode("utf-8"))
        req_body = query.getQueryCommand("DATAFRAME")

        query.getResults()

        mock_http_request.assert_called_with(uri=test_url+"query/sync", method="POST", body=req_body, headers={'Content-Type': 'application/json'})


    @patch('httplib2.Http.request')
    @patch('PicSureClient.Connection')
    def test_HpdsQuery_func_getResultsDataFrame(self, mock_picsure_connection, mock_http_request):
        test_uuid = "my-test-uuid"
        test_url = "http://my-test.url/"
        test_token = "this.is.my.test.token"
        test_return_CSV = "ROW\tVALUE\n" + "1\tTrue\n" + "2\tFalse\n" + "3\tUnknown\n"

        conn = mock_picsure_connection()
        API = PicSureHpds.BypassConnectionAPI(test_url, test_token)
        def ret_API():
            return API
        conn._api_obj = ret_API

        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)
        query = resource.query()

        resp_headers = {"status": "200"}
        mock_http_request.return_value = (resp_headers, test_return_CSV.encode("utf-8"))
        req_body = query.getQueryCommand("DATAFRAME")

        query.getResultsDataFrame()

        mock_http_request.assert_called_with(uri=test_url+"query/sync", method="POST", body=req_body, headers={'Content-Type': 'application/json'})
