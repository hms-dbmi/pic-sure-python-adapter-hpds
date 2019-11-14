import PicSureHpdsLib
import unittest
from unittest.mock import patch, MagicMock

class TestAttrList(unittest.TestCase):

    @patch('PicSureClient.PicSureConnectionAPI')
    def test_create(self, mock_api_obj):
        # our inputs for object creation
        my_apiObj = mock_api_obj()
        my_allowVariantSpec = True
        my_help_text = 'test-help-text'
        my_resource_uuid = 'test-resource-uuid'

        # create
        myAttrList = PicSureHpdsLib.AttrList(
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
    def test_add_with_valid_lookup(self, mock_api_obj):
        my_term = "testing_term"

        # our inputs for object creation
        my_apiObj = mock_api_obj()
        my_allowVariantSpec = True
        my_help_text = 'test-help-text'
        my_resource_uuid = 'test-resource-uuid'
        # MagicMock the API's search function
        my_apiObj.search = MagicMock(name='search')
        my_apiObj.search.return_value = '{"results": {"phenotypes": {"' + my_term + '": true}}}'

        # create list
        myAttrList = PicSureHpdsLib.AttrList(
            help_text=my_help_text,
            resource_uuid = my_resource_uuid,
            apiObj = my_apiObj,
            allowVariantSpec = my_allowVariantSpec
        )

        # add term
        myAttrList.add(my_term)
        # confirm that the lookup call was issued
        my_apiObj.search.assert_called_once()
        # confirm that the term was added to the internal list
        self.assertIn(my_term, myAttrList.data)


    @patch('PicSureClient.PicSureConnectionAPI')
    def test_add_with_bad_lookup(self, mock_api_obj):
        my_term = "testing_term"

        # our inputs for object creation
        my_apiObj = mock_api_obj()
        my_allowVariantSpec = True
        my_help_text = 'test-help-text'
        my_resource_uuid = 'test-resource-uuid'
        # MagicMock the API's search function
        my_apiObj.search = MagicMock(name='search')
        my_apiObj.search.return_value = '{"results": {"phenotypes": {"BAD_' + my_term + '": true}}}'

        # create list
        myAttrList = PicSureHpdsLib.AttrList(
            help_text=my_help_text,
            resource_uuid=my_resource_uuid,
            apiObj=my_apiObj,
            allowVariantSpec=my_allowVariantSpec
        )

        # add term
        myAttrList.add(my_term)
        # confirm that the lookup call was issued
        my_apiObj.search.assert_called_once()
        # confirm that the term was NOT added to the internal list
        self.assertNotIn(my_term, myAttrList.data)


    @patch('PicSureClient.PicSureConnectionAPI')
    def test_delete_with_existing_key(self, mock_api_obj):
        my_term = "testing_term"

        # our inputs for object creation
        my_apiObj = mock_api_obj()
        my_allowVariantSpec = True
        my_help_text = 'test-help-text'
        my_resource_uuid = 'test-resource-uuid'
        # MagicMock the API's search function
        my_apiObj.search = MagicMock(name='search')
        my_apiObj.search.return_value = '{"results": {"phenotypes": {"' + my_term + '": true}}}'

        # create list
        myAttrList = PicSureHpdsLib.AttrList(
            help_text=my_help_text,
            resource_uuid=my_resource_uuid,
            apiObj=my_apiObj,
            allowVariantSpec=my_allowVariantSpec
        )

        # add targeted term
        myAttrList.add(my_term)
        # delete targeted term
        myAttrList.delete(my_term)
        # confirm that the targeted term was deleted from the internal list
        self.assertNotIn(my_term, myAttrList.data)


    @patch('PicSureClient.PicSureConnectionAPI')
    def test_delete_with_missing_key(self, mock_api_obj):
        my_term = "testing_term"

        # our inputs for object creation
        my_apiObj = mock_api_obj()
        my_allowVariantSpec = True
        my_help_text = 'test-help-text'
        my_resource_uuid = 'test-resource-uuid'
        # MagicMock the API's search function
        my_apiObj.search = MagicMock(name='search')
        my_apiObj.search.return_value = '{"results": {"phenotypes": {"' + my_term + '": true}}}'

        # create list
        myAttrList = PicSureHpdsLib.AttrList(
            help_text=my_help_text,
            resource_uuid=my_resource_uuid,
            apiObj=my_apiObj,
            allowVariantSpec=my_allowVariantSpec
        )

        # add a non-targeted term
        myAttrList.add(my_term)
        # delete (non-existing) term
        myAttrList.delete("NOT_"+my_term)
        # confirm that the existing term was NOT deleted from the internal list
        self.assertIn(my_term, myAttrList.data)



    @patch('PicSureClient.PicSureConnectionAPI')
    def test_clear(self, mock_api_obj):
        my_term1 = "testing_term1"
        my_term2 = "testing_term2"

        # our inputs for object creation
        my_apiObj = mock_api_obj()
        my_allowVariantSpec = True
        my_help_text = 'test-help-text'
        my_resource_uuid = 'test-resource-uuid'
        # MagicMock the API's search function
        my_apiObj.search = MagicMock(name='search')

        # create list
        myAttrList = PicSureHpdsLib.AttrList(
            help_text=my_help_text,
            resource_uuid=my_resource_uuid,
            apiObj=my_apiObj,
            allowVariantSpec=my_allowVariantSpec
        )

        # add 1st term
        my_apiObj.search.return_value = '{"results": {"phenotypes": {"' + my_term1 + '": true}}}'
        myAttrList.add(my_term1)
        # add 2nd term
        my_apiObj.search.return_value = '{"results": {"phenotypes": {"' + my_term2 + '": true}}}'
        myAttrList.add(my_term2)

        # make sure both entries were added
        self.assertEqual(len(myAttrList.data), 2)

        # clear list and then confirm
        myAttrList.clear()
        self.assertEqual(len(myAttrList.data), 0)

    def test_ZZZZ(self):
        print("testing needed for adding/deleting of each data type!")
