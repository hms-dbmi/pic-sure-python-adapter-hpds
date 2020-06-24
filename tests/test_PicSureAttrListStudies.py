import PicSureHpdsLib
import unittest
from unittest.mock import patch, MagicMock
import io
import sys
import json

class TestAttrListStudies(unittest.TestCase):



    @patch('PicSureClient.PicSureConnectionAPI')
    def test_func_show_select_none(self, mock_api_obj):
        # our inputs for object creation
        my_apiObj = mock_api_obj()
        my_allowVariantSpec = False
        my_help_text = 'test-help-text'
        my_resource_uuid = 'test-resource-uuid'

        # MagicMock the API's search function
        my_apiObj.search = MagicMock(name='search')
        my_apiObj.search.return_value = '{"results": {"phenotypes": {' \
                                        '"\\\\_studies\\\\STUDY_1\\\\": {"name": "Study 1", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_2\\\\": {"name": "Study 2", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_3\\\\": {"name": "Study 3", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_4\\\\": {"name": "Study 4", "categorical": true, "categoryValues":["True"]}' \
                                        '}}}'

        # create list
        myAttrListStudies = PicSureHpdsLib.AttrListStudies(
            help_text=my_help_text,
            resource_uuid=my_resource_uuid,
            apiObj=my_apiObj,
            allowVariantSpec=my_allowVariantSpec
        )

        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            myAttrListStudies.show()
            sys.stdout = sys.__stdout__  # Reset redirect. Needed for it to work!
            captured = fake_stdout.getvalue()
            print("Captured:\n" + captured)
            self.assertTrue(len(captured) > 0)



    @patch('PicSureClient.PicSureConnectionAPI')
    def test_func_show_select_none_loaded(self, mock_api_obj):
        # our inputs for object creation
        my_apiObj = mock_api_obj()
        my_allowVariantSpec = False
        my_help_text = 'test-help-text'
        my_resource_uuid = 'test-resource-uuid'

        # MagicMock the API's search function
        my_apiObj.search = MagicMock(name='search')
        my_apiObj.search.return_value = '{"results": {"phenotypes": {' \
                                        '"\\\\_studies\\\\STUDY_1\\\\": {"name": "Study 1", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_2\\\\": {"name": "Study 2", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_3\\\\": {"name": "Study 3", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_4\\\\": {"name": "Study 4", "categorical": true, "categoryValues":["True"]}' \
                                        '}}}'

        # create list
        myAttrListStudies = PicSureHpdsLib.AttrListStudies(
            help_text=my_help_text,
            resource_uuid=my_resource_uuid,
            apiObj=my_apiObj,
            allowVariantSpec=my_allowVariantSpec
        )

        myAttrListStudies.add("STUDY_1")
        myAttrListStudies.delete("STUDY_1")
        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            myAttrListStudies.show()
            sys.stdout = sys.__stdout__  # Reset redirect. Needed for it to work!
            captured = fake_stdout.getvalue()
            print("Captured:\n" + captured)
            self.assertTrue(len(captured) > 0)



    @patch('PicSureClient.PicSureConnectionAPI')
    def test_func_show_select_some(self, mock_api_obj):
        # our inputs for object creation
        my_apiObj = mock_api_obj()
        my_allowVariantSpec = False
        my_help_text = 'test-help-text'
        my_resource_uuid = 'test-resource-uuid'

        # MagicMock the API's search function
        my_apiObj.search = MagicMock(name='search')
        my_apiObj.search.return_value = '{"results": {"phenotypes": {' \
                                        '"\\\\_studies\\\\STUDY_1\\\\": {"name": "Study 1", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_2\\\\": {"name": "Study 2", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_3\\\\": {"name": "Study 3", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_4\\\\": {"name": "Study 4", "categorical": true, "categoryValues":["True"]}' \
                                        '}}}'

        # create list
        myAttrListStudies = PicSureHpdsLib.AttrListStudies(
            help_text=my_help_text,
            resource_uuid=my_resource_uuid,
            apiObj=my_apiObj,
            allowVariantSpec=my_allowVariantSpec
        )

        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            myAttrListStudies.add("STUDY_1")
            myAttrListStudies.add("STUDY_2")
            myAttrListStudies.show()
            sys.stdout = sys.__stdout__  # Reset redirect. Needed for it to work!
            captured = fake_stdout.getvalue()
            print("Captured:\n" + captured)
            self.assertTrue(len(captured) > 0)



    @patch('PicSureClient.PicSureConnectionAPI')
    def test_func_show_select_all(self, mock_api_obj):
        # our inputs for object creation
        my_apiObj = mock_api_obj()
        my_allowVariantSpec = False
        my_help_text = 'test-help-text'
        my_resource_uuid = 'test-resource-uuid'

        # MagicMock the API's search function
        my_apiObj.search = MagicMock(name='search')
        my_apiObj.search.return_value = '{"results": {"phenotypes": {' \
                                        '"\\\\_studies\\\\STUDY_1\\\\": {"name": "Study 1", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_2\\\\": {"name": "Study 2", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_3\\\\": {"name": "Study 3", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_4\\\\": {"name": "Study 4", "categorical": true, "categoryValues":["True"]}' \
                                        '}}}'

        # create list
        myAttrListStudies = PicSureHpdsLib.AttrListStudies(
            help_text=my_help_text,
            resource_uuid=my_resource_uuid,
            apiObj=my_apiObj,
            allowVariantSpec=my_allowVariantSpec
        )

        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            myAttrListStudies.add("STUDY_1")
            myAttrListStudies.add("STUDY_2")
            myAttrListStudies.add("STUDY_3")
            myAttrListStudies.add("STUDY_4")
            myAttrListStudies.show()
            sys.stdout = sys.__stdout__  # Reset redirect. Needed for it to work!
            captured = fake_stdout.getvalue()
            print("Captured:\n" + captured)
            self.assertTrue(len(captured) > 0)



    @patch('PicSureClient.PicSureConnectionAPI')
    def test_func_add_with_valid_lookup(self, mock_api_obj):
        my_study = "STUDY_1"
        my_study_key = "\\_studies\\" + my_study + "\\"

        # our inputs for object creation
        my_apiObj = mock_api_obj()
        my_allowVariantSpec = False
        my_help_text = 'test-help-text'
        my_resource_uuid = 'test-resource-uuid'
        # MagicMock the API's search function
        my_apiObj.search = MagicMock(name='search')
        my_apiObj.search.return_value = '{"results": {"phenotypes": {' \
                                        '"\\\\_studies\\\\STUDY_1\\\\": {"name": "Study 1", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_2\\\\": {"name": "Study 2", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_3\\\\": {"name": "Study 3", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_4\\\\": {"name": "Study 4", "categorical": true, "categoryValues":["True"]}' \
                                        '}}}'

        # create list
        myAttrListStudies = PicSureHpdsLib.AttrListStudies(
            help_text=my_help_text,
            resource_uuid=my_resource_uuid,
            apiObj=my_apiObj,
            allowVariantSpec=my_allowVariantSpec
        )

        # add study
        myAttrListStudies.add(my_study)
        # confirm that the lookup call was issued
        my_apiObj.search.assert_called_once()
        # confirm that the term was added to the internal list
        self.assertIn(my_study_key, myAttrListStudies.data)


    @patch('PicSureClient.PicSureConnectionAPI')
    def test_func_add_with_bad_lookup(self, mock_api_obj):
        my_study = "STUDY_X"
        my_study_key = "\\_studies\\" + my_study + "\\"

        # our inputs for object creation
        my_apiObj = mock_api_obj()
        my_allowVariantSpec = False
        my_help_text = 'test-help-text'
        my_resource_uuid = 'test-resource-uuid'
        # MagicMock the API's search function
        my_apiObj.search = MagicMock(name='search')
        my_apiObj.search.return_value = '{"results": {"phenotypes": {' \
                                        '"\\\\_studies\\\\STUDY_1\\\\": {"name": "Study 1", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_2\\\\": {"name": "Study 2", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_3\\\\": {"name": "Study 3", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_4\\\\": {"name": "Study 4", "categorical": true, "categoryValues":["True"]}' \
                                        '}}}'

        # create list
        myAttrListStudies = PicSureHpdsLib.AttrListStudies(
            help_text=my_help_text,
            resource_uuid=my_resource_uuid,
            apiObj=my_apiObj,
            allowVariantSpec=my_allowVariantSpec
        )

        # add term
        myAttrListStudies.add(my_study)
        # confirm that the lookup call was issued
        my_apiObj.search.assert_called_once()
        # confirm that the term was NOT added to the internal list
        self.assertNotIn(my_study_key, myAttrListStudies.data)


    @patch('PicSureClient.PicSureConnectionAPI')
    def test_func_delete_with_existing_key(self, mock_api_obj):
        my_study = "STUDY_1"
        my_study_key = "\\_studies\\" + my_study + "\\"

        # our inputs for object creation
        my_apiObj = mock_api_obj()
        my_allowVariantSpec = False
        my_help_text = 'test-help-text'
        my_resource_uuid = 'test-resource-uuid'
        # MagicMock the API's search function
        my_apiObj.search = MagicMock(name='search')
        my_apiObj.search.return_value = '{"results": {"phenotypes": {' \
                                        '"\\\\_studies\\\\STUDY_1\\\\": {"name": "Study 1", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_2\\\\": {"name": "Study 2", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_3\\\\": {"name": "Study 3", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_4\\\\": {"name": "Study 4", "categorical": true, "categoryValues":["True"]}' \
                                        '}}}'

        # create list
        myAttrListStudies = PicSureHpdsLib.AttrListStudies(
            help_text=my_help_text,
            resource_uuid=my_resource_uuid,
            apiObj=my_apiObj,
            allowVariantSpec=my_allowVariantSpec
        )

        # add targeted study
        myAttrListStudies.add(my_study)
        # delete targeted term
        myAttrListStudies.delete(my_study)
        # confirm that the targeted study was deleted from the internal list
        self.assertNotIn(my_study_key, myAttrListStudies.data)


    @patch('PicSureClient.PicSureConnectionAPI')
    def test_func_delete_with_missing_key(self, mock_api_obj):
        my_study = "STUDY_1"
        my_study_key = "\\_studies\\" + my_study + "\\"

        # our inputs for object creation
        my_apiObj = mock_api_obj()
        my_allowVariantSpec = False
        my_help_text = 'test-help-text'
        my_resource_uuid = 'test-resource-uuid'
        # MagicMock the API's search function
        my_apiObj.search = MagicMock(name='search')
        my_apiObj.search.return_value = '{"results": {"phenotypes": {' \
                                        '"\\\\_studies\\\\STUDY_1\\\\": {"name": "Study 1", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_2\\\\": {"name": "Study 2", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_3\\\\": {"name": "Study 3", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_4\\\\": {"name": "Study 4", "categorical": true, "categoryValues":["True"]}' \
                                        '}}}'

        # create list
        myAttrListStudies = PicSureHpdsLib.AttrListStudies(
            help_text=my_help_text,
            resource_uuid=my_resource_uuid,
            apiObj=my_apiObj,
            allowVariantSpec=my_allowVariantSpec
        )

        # add a non-targeted study
        myAttrListStudies.add(my_study)
        # delete (non-existing) term
        myAttrListStudies.delete("NOT_" + my_study)
        # confirm that the existing term was NOT deleted from the internal list
        self.assertIn(my_study_key, myAttrListStudies.data)

    @patch('PicSureClient.PicSureConnectionAPI')
    def test_trimming_internal_dict_to_only_studies(self, mock_api_obj):
        my_study = "STUDY_1"
        my_study_key = "\\_studies\\" + my_study + "\\"

        # our inputs for object creation
        my_apiObj = mock_api_obj()
        my_allowVariantSpec = False
        my_help_text = 'test-help-text'
        my_resource_uuid = 'test-resource-uuid'
        # MagicMock the API's search function
        my_apiObj.search = MagicMock(name='search')
        my_apiObj.search.return_value = '{"results": {"phenotypes": {' \
                                        '"\\\\_studies\\\\STUDY_1\\\\": {"name": "Study 1", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_2\\\\": {"name": "Study 2", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_3\\\\": {"name": "Study 3", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_4\\\\": {"name": "Study 4", "categorical": true, "categoryValues":["True"]},' \
                                        '"term1": {"name": "term1", "categorical": false, "min":0, "max":100},' \
                                        '"term2": {"name": "term2", "categorical": false, "min":0, "max":100},' \
                                        '"term3": {"name": "term3", "categorical": true, "categoryValues":["cat1"]},' \
                                        '"term4": {"name": "term4", "categorical": true, "categoryValues":["catA","catB","catC"]}' \
                                        '}}}'

        # create list
        myAttrListStudies = PicSureHpdsLib.AttrListStudies(
            help_text=my_help_text,
            resource_uuid=my_resource_uuid,
            apiObj=my_apiObj,
            allowVariantSpec=my_allowVariantSpec
        )

        # add a valid study (to trigger download of data dictionary
        myAttrListStudies.add(my_study)
        # confirm that only studies remain in the lookup dictionary
        for key in myAttrListStudies.all_keys['phenotypes'].keys():
            self.assertTrue(key.startswith("\\_studies\\"))



    @patch('PicSureClient.PicSureConnectionAPI')
    def test_valid_query_output(self, mock_api_obj):
        my_study = "STUDY_1"
        my_study_key = "\\_studies\\" + my_study + "\\"

        # our inputs for object creation
        my_apiObj = mock_api_obj()
        my_allowVariantSpec = False
        my_help_text = 'test-help-text'
        my_resource_uuid = 'test-resource-uuid'
        # MagicMock the API's search function
        my_apiObj.search = MagicMock(name='search')
        my_apiObj.search.return_value = '{"results": {"phenotypes": {' \
                                        '"\\\\_studies\\\\STUDY_1\\\\": {"name": "Study 1", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_2\\\\": {"name": "Study 2", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_3\\\\": {"name": "Study 3", "categorical": true, "categoryValues":["True"]},' \
                                        '"\\\\_studies\\\\STUDY_4\\\\": {"name": "Study 4", "categorical": true, "categoryValues":["True"]}' \
                                        '}}}'

        # create list
        myAttrListStudies = PicSureHpdsLib.AttrListStudies(
            help_text=my_help_text,
            resource_uuid=my_resource_uuid,
            apiObj=my_apiObj,
            allowVariantSpec=my_allowVariantSpec
        )

        # add a valid study (to trigger download of data dictionary
        myAttrListStudies.add(my_study)

        my_query = myAttrListStudies.getQueryValues()
        self.assertDictEqual(my_query, {'\\_studies\\STUDY_1\\': [True]})

        # this code tests the process in the query.build functionality
        ret = {"query": {"categoryFilters": {}}}
        # append the studies list to the existing categoryFilters
        for key, item in my_query.items():
            ret['query']['categoryFilters'][key] = item

