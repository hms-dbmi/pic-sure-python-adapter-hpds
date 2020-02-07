from PicSureClient import Connection
import PicSureHpdsLib
from PicSureHpdsLib import PicSureHpdsDictionary, PicSureHpdsQuery, PicSureHpds
import unittest
from unittest.mock import patch, MagicMock
import types
import io
import sys
import json

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

        # MagicMock the API's search function
        query._apiObj.search.return_value = '{"results": {"phenotypes": {' \
                                        '"somekey": {"name": "term1", "categorical": false, "min":0, "max":100}' \
                                        '}}}'

        my_list.add("somekey")
        self.assertEqual(1, len(my_list.data))
        output = query.save()
        print(output)


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
            query.filter(test_key)
            sys.stdout = sys.__stdout__  # Reset redirect. Needed for it to work!
            captured = fake_stdout.getvalue()
            print("Message on parameter useage:\n" + captured)
            self.assertTrue(len(captured) > 0)


    @patch('PicSureClient.Connection')
    def test_HpdsQuery_list_filter_input_a_list(self, mock_picsure_connection):
        test_uuid = "my-test-uuid"
        test_key1 = "my-test-key1"
        test_key2 = "my-test-key2"
        test_value = 1000
        test_class = "my-test-class"


        conn = mock_picsure_connection()
        API = PicSureHpds.BypassConnectionAPI("", "")
        API.search = MagicMock(return_value='{"results": {"'+test_class+'": {"'+test_key1+'": "foo", "'+test_key2+'": "bar"}}}')
        def ret_API():
            return API
        conn._api_obj = ret_API

        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)
        query = resource.query()

        # micro test to confirm warning is printed if parameters are passed
        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            query.filter().add([test_key1, test_key2], test_value)
            self.assertEqual(len(query.filter().data), 2)
            self.assertDictEqual(query.filter().data[test_key1], {'type': 'minmax', 'min': test_value, 'max': test_value, 'HpdsDataType': test_class})
            self.assertDictEqual(query.filter().data[test_key2], {'type': 'minmax', 'min': test_value, 'max': test_value, 'HpdsDataType': test_class})

            sys.stdout = sys.__stdout__  # Reset redirect. Needed for it to work!
            captured = fake_stdout.getvalue()
            print("Message on parameter useage:\n" + captured)
            self.assertTrue(len(captured) == 0)


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
        req_body = json.dumps(query.buildQuery("COUNT"))

        query.getCount()

        mock_http_request.assert_called_with(uri=test_url+"query/sync", method="POST", body=req_body, headers={'Content-Type': 'application/json'})


    @patch('httplib2.Http.request')
    @patch('PicSureClient.Connection')
    def test_HpdsQuery_func_getCount_handles_connection_error(self, mock_picsure_connection, mock_http_request):
        test_uuid = "my-test-uuid"
        test_url = "http://my-test.url/"
        test_token = "this.is.my.test.token"
        test_connection_error = '{"results":{}, "error":"true"}'

        conn = mock_picsure_connection()
        API = PicSureHpds.BypassConnectionAPI(test_url, test_token)
        def ret_API():
            return API
        conn._api_obj = ret_API

        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)
        query = resource.query()

        resp_headers = {"status": "200"}
        mock_http_request.return_value = (resp_headers, test_connection_error.encode("utf-8"))
        req_body = json.dumps(query.buildQuery("COUNT"))

        # micro test to confirm warning is printed on error
        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            test = query.getCount()
            sys.stdout = sys.__stdout__  # Reset redirect. Needed for it to work!
            captured = fake_stdout.getvalue()
            print("Message on parameter useage:\n" + captured)

            self.assertTrue(len(captured) > 0)
            self.assertEqual(test, test_connection_error)


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
        req_body = json.dumps(query.buildQuery("DATAFRAME"))

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
        req_body = json.dumps(query.buildQuery("DATAFRAME"))

        query.getResultsDataFrame()

        mock_http_request.assert_called_with(uri=test_url+"query/sync", method="POST", body=req_body, headers={'Content-Type': 'application/json'})
