import PicSureHpdsLib
import unittest
from unittest.mock import patch, MagicMock
import io
import sys

class TestAttrList(unittest.TestCase):

    @patch('PicSureClient.PicSureConnectionAPI')
    def test_create_key_list(self, mock_api_obj):
        # our inputs for object creation
        my_apiObj = mock_api_obj()
        my_allowVariantSpec = True
        my_help_text = 'test-help-text'
        my_resource_uuid = 'test-resource-uuid'

        # create
        myAttrList = PicSureHpdsLib.AttrListKeys(
            help_text=my_help_text,
            resource_uuid = my_resource_uuid,
            apiObj = my_apiObj,
            allowVariantSpec = my_allowVariantSpec
        )

        # make sure everything is setup correctly
        self.assertIs(my_apiObj, myAttrList._apiObj)
        self.assertIs(my_allowVariantSpec, myAttrList._allow_variant_spec)
        self.assertIs(my_help_text, myAttrList.helpstr)
        self.assertIs(my_resource_uuid, myAttrList._resource_uuid)


    @patch('PicSureClient.PicSureConnectionAPI')
    def test_create_keyvalue_list(self, mock_api_obj):
        # our inputs for object creation
        my_apiObj = mock_api_obj()
        my_allowVariantSpec = True
        my_help_text = 'test-help-text'
        my_resource_uuid = 'test-resource-uuid'

        # create
        myAttrList = PicSureHpdsLib.AttrListKeyValues(
            help_text=my_help_text,
            resource_uuid = my_resource_uuid,
            apiObj = my_apiObj,
            allowVariantSpec = my_allowVariantSpec
        )

        # make sure everything is setup correctly
        self.assertIs(my_apiObj, myAttrList._apiObj)
        self.assertIs(my_allowVariantSpec, myAttrList._allow_variant_spec)
        self.assertIs(my_help_text, myAttrList.helpstr)
        self.assertIs(my_resource_uuid, myAttrList._resource_uuid)


    @patch('PicSureClient.PicSureConnectionAPI')
    def test_func_key_list_add_key(self, mock_api_obj):
        # our inputs for object creation
        my_apiObj = mock_api_obj()
        my_allowVariantSpec = True
        my_help_text = 'test-help-text'
        my_resource_uuid = 'test-resource-uuid'

        # MagicMock the API's search function
        my_apiObj.search = MagicMock(name='search')
        my_apiObj.search.return_value = '{"results": {"phenotypes": {' \
                                        '"term1": {"name": "term1", "categorical": false, "min":0, "max":100},' \
                                        '"term2": {"name": "term2", "categorical": false, "min":0, "max":100},' \
                                        '"term3": {"name": "term3", "categorical": true, "values":["cat1"]},' \
                                        '"term4": {"name": "term4", "categorical": true, "values":["catA","catB","catC"]}' \
                                        '}}}'

        # create
        myAttrList = PicSureHpdsLib.AttrListKeys(
            help_text=my_help_text,
            resource_uuid = my_resource_uuid,
            apiObj = my_apiObj,
            allowVariantSpec = my_allowVariantSpec
        )

        myAttrList.add("term1")
        self.assertDictEqual({"HpdsDataType":"phenotypes", "type":"exists"}, myAttrList.data["term1"])


    @patch('PicSureClient.PicSureConnectionAPI')
    def test_func_keyvalue_add_key(self, mock_api_obj):
        # our inputs for object creation
        my_apiObj = mock_api_obj()
        my_allowVariantSpec = True
        my_help_text = 'test-help-text'
        my_resource_uuid = 'test-resource-uuid'

        # MagicMock the API's search function
        my_apiObj.search = MagicMock(name='search')
        my_apiObj.search.return_value = '{"results": {"phenotypes": {' \
                                        '"term1": {"name": "term1", "categorical": false, "min":0, "max":100},' \
                                        '"term2": {"name": "term2", "categorical": false, "min":0, "max":100},' \
                                        '"term3": {"name": "term3", "categorical": true, "values":["cat1"]},' \
                                        '"term4": {"name": "term4", "categorical": true, "values":["catA","catB","catC"]}' \
                                        '}}}'
        # create
        myAttrList = PicSureHpdsLib.AttrListKeyValues(
            help_text=my_help_text,
            resource_uuid = my_resource_uuid,
            apiObj = my_apiObj,
            allowVariantSpec = my_allowVariantSpec
        )

        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            myAttrList.add("term1")
            sys.stdout = sys.__stdout__  # Reset redirect. Needed for it to work!
            captured = fake_stdout.getvalue()
            print("Captured:\n" + captured)
            # did it generate an error
            self.assertTrue(len(captured) > 0)
            # nothing should have been added
            self.assertEqual(0, len(myAttrList.data))


    @patch('PicSureClient.PicSureConnectionAPI')
    def test_func_key_list_add_key_and_anything(self, mock_api_obj):
        # our inputs for object creation
        my_apiObj = mock_api_obj()
        my_allowVariantSpec = True
        my_help_text = 'test-help-text'
        my_resource_uuid = 'test-resource-uuid'

        # MagicMock the API's search function
        my_apiObj.search = MagicMock(name='search')
        my_apiObj.search.return_value = '{"results": {"phenotypes": {' \
                                        '"term1": {"name": "term1", "categorical": false, "min":0, "max":100},' \
                                        '"term2": {"name": "term2", "categorical": false, "min":0, "max":100},' \
                                        '"term3": {"name": "term3", "categorical": true, "values":["cat1"]},' \
                                        '"term4": {"name": "term4", "categorical": true, "values":["catA","catB","catC"]}' \
                                        '}}}'

        # create
        myAttrList = PicSureHpdsLib.AttrListKeys(
            help_text=my_help_text,
            resource_uuid = my_resource_uuid,
            apiObj = my_apiObj,
            allowVariantSpec = my_allowVariantSpec
        )

        myAttrList.add("term1", 10, 90)
        # should drop any additional info and story key only
        self.assertDictEqual({"HpdsDataType":"phenotypes", "type":"exists"}, myAttrList.data["term1"])


    @patch('PicSureClient.PicSureConnectionAPI')
    def test_func_keyvalue_add_key_int_value(self, mock_api_obj):
        # our inputs for object creation
        my_apiObj = mock_api_obj()
        my_allowVariantSpec = True
        my_help_text = 'test-help-text'
        my_resource_uuid = 'test-resource-uuid'

        # MagicMock the API's search function
        my_apiObj.search = MagicMock(name='search')
        my_apiObj.search.return_value = '{"results": {"phenotypes": {' \
                                        '"term1": {"name": "term1", "categorical": false, "min":0, "max":100},' \
                                        '"term2": {"name": "term2", "categorical": false, "min":0, "max":100},' \
                                        '"term3": {"name": "term3", "categorical": true, "values":["cat1"]},' \
                                        '"term4": {"name": "term4", "categorical": true, "values":["catA","catB","catC"]}' \
                                        '}}}'
        # create
        myAttrList = PicSureHpdsLib.AttrListKeyValues(
            help_text=my_help_text,
            resource_uuid = my_resource_uuid,
            apiObj = my_apiObj,
            allowVariantSpec = my_allowVariantSpec
        )

        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            myAttrList.add("term1", 50)
            sys.stdout = sys.__stdout__  # Reset redirect. Needed for it to work!
            captured = fake_stdout.getvalue()
            print("Captured:\n" + captured)
        # it did not generate an error
        self.assertTrue(len(captured) == 0)
        # should have added a record
        self.assertDictEqual({"HpdsDataType":"phenotypes", "type":"minmax", "min":50, "max":50 }, myAttrList.data["term1"])


    @patch('PicSureClient.PicSureConnectionAPI')
    def test_func_keyvalue_add_key_string_value(self, mock_api_obj):
        # our inputs for object creation
        my_apiObj = mock_api_obj()
        my_allowVariantSpec = True
        my_help_text = 'test-help-text'
        my_resource_uuid = 'test-resource-uuid'

        # MagicMock the API's search function
        my_apiObj.search = MagicMock(name='search')
        my_apiObj.search.return_value = '{"results": {"phenotypes": {' \
                                        '"term1": {"name": "term1", "categorical": false, "min":0, "max":100},' \
                                        '"term2": {"name": "term2", "categorical": false, "min":0, "max":100},' \
                                        '"term3": {"name": "term3", "categorical": true, "values":["cat1"]},' \
                                        '"term4": {"name": "term4", "categorical": true, "values":["catA","catB","catC"]}' \
                                        '}}}'
        # create
        myAttrList = PicSureHpdsLib.AttrListKeyValues(
            help_text=my_help_text,
            resource_uuid = my_resource_uuid,
            apiObj = my_apiObj,
            allowVariantSpec = my_allowVariantSpec
        )

        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            myAttrList.add("term3", "cat1")
            sys.stdout = sys.__stdout__  # Reset redirect. Needed for it to work!
            captured = fake_stdout.getvalue()
            print("Captured:\n" + captured)
        # it did not generate an error
        self.assertTrue(len(captured) == 0)
        # should have added a record
        self.assertDictEqual({"type":"value", "HpdsDataType":"phenotypes", "value":"cat1"}, myAttrList.data["term3"])
