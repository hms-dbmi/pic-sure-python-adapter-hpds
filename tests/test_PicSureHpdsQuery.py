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
        # Just have to put some kind of JSON response so that there is a value to parse
        mock_picsure_connection.return_value._api_obj.return_value.profile.return_value = '{"testjson":"awesome"}'

        conn = mock_picsure_connection()
        test_uuid = "my-test-uuid"
        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)
        query = resource.query()
        # test that it was created correctly
        self.assertIsInstance(query, PicSureHpdsQuery.Query)
        self.assertEqual(query._resourceUUID, test_uuid)
        self.assertIs(query._refHpdsResourceConnection, resource)


    @patch('PicSureClient.Connection')
    def test_HpdsQuery_create_load_query(self, mock_picsure_connection):
        # Just have to put some kind of JSON response so that there is a value to parse
        mock_picsure_connection.return_value._api_obj.return_value.profile.return_value = '{"testjson":"awesome"}'

        conn = mock_picsure_connection()
        test_uuid = "my-test-uuid"
        query_obj = {"query": {
            "fields": ["\\select\\key"],
            "crossCountFields": [
                "\\crosscounts\\key1",
                "\\crosscounts\\key2"
            ],
            "requiredFields": [
                "\\require\\key"
            ],
            "anyRecordOf": [
                "\\anyof\\key1",
                "\\anyof\\key2"
            ],
            "numericFilters": {
                "\\filter_numeric\\range1": {
                    "min": 40,
                    "max": 60
                },
                "\\filter_numeric\\value1": {
                    "min": 50,
                    "max": 50
                }
            },
            "categoryFilters": {
                "\\filter_categorical\\set1": ["cat1"],
                "\\filter_categorical\\set2": ["catA", "catC"]
            },
            "variantInfoFilters": [
                {
                    "categoryVariantInfoFilters": {
                        "Variant_severity": ["HIGH"]
                    },
                    "numericVariantInfoFilters": {
                        "AF": {"min": 0.1, "max": 0.9}
                    }
                }
            ]}, "resourceUUID": str(test_uuid)}
        query_json = json.dumps(query_obj)

        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)
        query = resource.query(load_query=query_json)

        query_as_loaded = query.save()


        # test that it was created correctly
        self.assertIsInstance(query, PicSureHpdsQuery.Query)
        self.assertEqual(query_json, query_as_loaded)
        self.assertIs(query._refHpdsResourceConnection, resource)

    @patch('PicSureClient.Connection')
    def test_HpdsQuery_func_help(self, mock_picsure_connection):
        # Just have to put some kind of JSON response so that there is a value to parse
        mock_picsure_connection.return_value._api_obj.return_value.profile.return_value = '{"testjson":"awesome"}'

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
        # Just have to put some kind of JSON response so that there is a value to parse
        mock_picsure_connection.return_value._api_obj.return_value.profile.return_value = '{"testjson":"awesome"}'

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
        # Just have to put some kind of JSON response so that there is a value to parse
        mock_picsure_connection.return_value._api_obj.return_value.profile.return_value = '{"testjson":"awesome"}'

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
        # Just have to put some kind of JSON response so that there is a value to parse
        mock_picsure_connection.return_value._api_obj.return_value.profile.return_value = '{"testjson":"awesome"}'

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
        # Just have to put some kind of JSON response so that there is a value to parse
        mock_picsure_connection.return_value._api_obj.return_value.profile.return_value = '{"testjson":"awesome"}'

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
        # Just have to put some kind of JSON response so that there is a value to parse
        mock_picsure_connection.return_value._api_obj.return_value.profile.return_value = '{"testjson":"awesome"}'

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
        # Just have to put some kind of JSON response so that there is a value to parse
        mock_picsure_connection.return_value._api_obj.return_value.profile.return_value = '{"testjson":"awesome"}'

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



    @patch('PicSureClient.Connection')
    def test_HpdsQuery_func_save(self, mock_picsure_connection):
        test_uuid = "my-test-uuid"
        test_value = 50

        return_vals = {"results": { "phenotypes": {
                "\\select\\key": {},
                "\\require\\key": {},
                "\\crosscounts\\key1": {},
                "\\crosscounts\\key2": {},
                "\\anyof\\key1": {},
                "\\anyof\\key2": {},
                "\\filter_numeric\\key1": {"name": "key1", "categorical": False, "min": 0, "max": 100},
                "\\filter_numeric\\range1": {"name": "term1", "categorical": False, "min": 0, "max": 100},
                "\\filter_numeric\\value1": {"name": "value1", "categorical": False, "min": 0, "max": 100},
                "\\filter_categorical\\set1": {"name": "set1", "categorical": True, "categoryValues": ["cat1"]},
                "\\filter_categorical\\set2": {"name": "set2", "categorical": True, "categoryValues": ["catA", "catB", "catC"]}},
            "info": {
                "Variant_severity": {"values": ["HIGH", "LOW"], "continuous": False},
                "AF": {"values": [], "continuous": True}
            }}}

        conn = mock_picsure_connection()
        API = PicSureHpds.BypassConnectionAPI("", "")
        API.search = MagicMock(return_value=json.dumps(return_vals))
        def ret_API():
            return API
        conn._api_obj = ret_API

        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)
        query = resource.query()

        # micro test to confirm warning is printed if parameters are passed
        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            query.select().add("\\select\\key")
            query.crosscounts().add(["\\crosscounts\\key1", "\\crosscounts\\key2"])
            query.require().add("\\require\\key")
            query.anyof().add(["\\anyof\\key1","\\anyof\\key2"])
            query.filter().add("\\filter_numeric\\range1", test_value - 10, test_value + 10)
            query.filter().add("\\filter_numeric\\value1", test_value)
            query.filter().add("\\filter_categorical\\set1", "cat1")
            query.filter().add("\\filter_categorical\\set2", ["catA","catC"])
            query.filter().add("Variant_severity", ["HIGH"])
            query.filter().add("AF", min=0.1, max=0.9)

            sys.stdout = sys.__stdout__  # Reset redirect. Needed for it to work!
            captured = fake_stdout.getvalue()
            print("Message on parameter useage:\n" + captured)

            query_obj = {"query": {
            "fields": ["\\select\\key"],
            "crossCountFields": [
              "\\crosscounts\\key1",
              "\\crosscounts\\key2"
            ],
            "requiredFields": [
              "\\require\\key"
            ],
            "anyRecordOf": [
              "\\anyof\\key1",
              "\\anyof\\key2"
            ],
            "numericFilters": {
              "\\filter_numeric\\range1": {
                "min": 40,
                "max": 60
              },
              "\\filter_numeric\\value1": {
                "min": 50,
                "max": 50
              }
            },
            "categoryFilters": {
              "\\filter_categorical\\set1": ["cat1"],
              "\\filter_categorical\\set2": ["catA","catC"]
            },
            "variantInfoFilters": [
              {
                "categoryVariantInfoFilters": {
                    "Variant_severity": ["HIGH"]
                },
                "numericVariantInfoFilters": {
                    "AF": {"min": 0.1, "max": 0.9}
                }
              }
            ]}, "resourceUUID": "my-test-uuid"}

            self.assertDictEqual(query_obj, json.loads(query.save()))


    @patch('PicSureClient.Connection')
    def test_HpdsQuery_func_load(self, mock_picsure_connection):
        test_uuid = "my-test-uuid"

        query_obj = {"query": {
            "fields": ["\\select\\key"],
            "crossCountFields": [
                "\\crosscounts\\key1",
                "\\crosscounts\\key2"
            ],
            "requiredFields": [
                "\\require\\key"
            ],
            "anyRecordOf": [
                "\\anyof\\key1",
                "\\anyof\\key2"
            ],
            "numericFilters": {
                "\\filter_numeric\\range1": {
                    "min": 40,
                    "max": 60
                },
                "\\filter_numeric\\value1": {
                    "min": 50,
                    "max": 50
                }
            },
            "categoryFilters": {
                "\\filter_categorical\\set1": ["cat1"],
                "\\filter_categorical\\set2": ["catA", "catC"]
            },
            "variantInfoFilters": [
              {
                "categoryVariantInfoFilters": {
                    "Variant_severity": ["HIGH"]
                },
                "numericVariantInfoFilters": {
                    "AF": {"min": 0.1, "max": 0.9}
                }
              }
            ]}, "resourceUUID": "my-test-uuid"}
        query_str = json.dumps(query_obj)

        return_vals = {}
        conn = mock_picsure_connection()
        API = PicSureHpds.BypassConnectionAPI("", "")
        API.search = MagicMock(return_value=json.dumps(return_vals))
        def ret_API():
            return API
        conn._api_obj = ret_API

        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)
        query = resource.query()

        # micro test to confirm warning is printed if parameters are passed
        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            query.load(query_str)

            sys.stdout = sys.__stdout__  # Reset redirect. Needed for it to work!
            captured = fake_stdout.getvalue()
            print("Message on parameter useage:\n" + captured)

            self.assertDictEqual(query_obj, json.loads(query.save()))



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
