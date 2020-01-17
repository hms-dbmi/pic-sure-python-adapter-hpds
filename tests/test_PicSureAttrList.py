import PicSureHpdsLib
import unittest
from unittest.mock import patch, MagicMock
import io
import sys

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
    def test_func_help(self, mock_api_obj):
        # our inputs for object creation
        my_apiObj = mock_api_obj()
        my_allowVariantSpec = True
        my_help_text = 'test-help-text'
        my_resource_uuid = 'test-resource-uuid'

        # create list
        myAttrList = PicSureHpdsLib.AttrList(
            help_text = my_help_text,
            resource_uuid = my_resource_uuid,
            apiObj = my_apiObj,
            allowVariantSpec = my_allowVariantSpec
        )
        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            myAttrList.help()
            sys.stdout = sys.__stdout__  # Reset redirect. Needed for it to work!
            captured = fake_stdout.getvalue()
            print("Captured:\n" + captured)
            self.assertEqual(captured.strip(), my_help_text.strip())


    @patch('PicSureClient.PicSureConnectionAPI')
    def test_func_show(self, mock_api_obj):
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

        # create list
        myAttrList = PicSureHpdsLib.AttrList(
            help_text=my_help_text,
            resource_uuid = my_resource_uuid,
            apiObj = my_apiObj,
            allowVariantSpec = my_allowVariantSpec
        )

        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            myAttrList.add("term1", 50)
            myAttrList.add("term2", 1, 99)
            myAttrList.add("term3", "cat1")
            myAttrList.add("term3", ["catA", "catB", "catC"])
            myAttrList.show()
            sys.stdout = sys.__stdout__  # Reset redirect. Needed for it to work!
            captured = fake_stdout.getvalue()
            print("Captured:\n" + captured)
            self.assertTrue(len(captured) > 0)



    @patch('PicSureClient.PicSureConnectionAPI')
    def test_func_add_with_valid_lookup(self, mock_api_obj):
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
    def test_func_add_with_bad_lookup(self, mock_api_obj):
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
    def test_func_delete_with_existing_key(self, mock_api_obj):
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
    def test_func_delete_with_missing_key(self, mock_api_obj):
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
    def test_func_clear(self, mock_api_obj):
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
        self.assertEqual(my_apiObj.search.call_count, 1)
        # add 2nd term
        my_apiObj.search.return_value = '{"results": {"phenotypes": {"' + my_term2 + '": true}}}'
        myAttrList.add(my_term2)
        self.assertEqual(my_apiObj.search.call_count, 2)

        # make sure both entries were added
        self.assertEqual(len(myAttrList.data), 2)

        # clear list and then confirm
        myAttrList.clear()
        self.assertEqual(len(myAttrList.data), 0)


    @patch('PicSureClient.PicSureConnectionAPI')
    def test_func_add_categorical_bad_values(self, mock_api_obj):
        my_term = "testing_term"
        my_cat1 = "cat_value_1"
        my_cat2 = "cat_value_2"

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

        # return only a single non-matching categorical value
        my_apiObj.search.return_value = '{"results": {"phenotypes": {"' + my_term + '": {"description": "my_description", "values": ["NON-MATCH-VALUE"], "continuous": false}}}}'
        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            # attempt adding categorical term with 2 values
            myAttrList.add(my_term, [my_cat1, my_cat2])
            sys.stdout = sys.__stdout__  # Reset redirect. Needed for it to work!
            captured = fake_stdout.getvalue()
            print("Captured:\n" + captured)

        # make sure no entries were added
        self.assertEqual(len(myAttrList.data), 0)

        # make sure that an error message was printed
        self.assertTrue(len(captured) > 0)

    @patch('PicSureClient.PicSureConnectionAPI')
    def test_func_add_categorical_good_values(self, mock_api_obj):
        my_term = "testing_term"
        my_cat1 = "cat_value_1"
        my_cat2 = "cat_value_2"

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

        my_apiObj.search.return_value = '{"results": {"phenotypes": {"' + my_term + '": {"description": "my_description", "values": ["'+my_cat1+'","'+my_cat2+'"], "continuous": false}}}}'
        # attempt adding categorical term with 2 values
        myAttrList.add(my_term, [my_cat1, my_cat2])

        # make sure no entries were added
        self.assertEqual(len(myAttrList.data), 1)


    @patch('PicSureClient.PicSureConnectionAPI')
    def test_func_add_continuous_outside_range(self, mock_api_obj):
        my_term = "testing_term"
        my_min = 0
        my_max = 9000
        my_range_min = 1
        my_range_max = 10

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

        # return only a single non-matching categorical value
        my_apiObj.search.return_value = '{"results": {"phenotypes": {"' + my_term + '": {"description":"my_description", "categorical":"false", "min":'+str(my_range_min)+', "max":'+str(my_max)+'}}}}'
        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            # attempt adding categorical term with 2 values
            myAttrList.add(my_term, my_min, my_max)
            sys.stdout = sys.__stdout__  # Reset redirect. Needed for it to work!
            captured = fake_stdout.getvalue()
            print("Captured:\n" + captured)

        # make sure no entries were added
        self.assertEqual(len(myAttrList.data), 0)

        # make sure that an error message was printed
        self.assertTrue(len(captured) > 0)

    @patch('PicSureClient.PicSureConnectionAPI')
    def test_func_add_continuous_within_range(self, mock_api_obj):
        my_term = "testing_term"
        my_min = 2
        my_max = 9
        my_max = 9
        my_range_min = 1
        my_range_max = 10

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

        my_apiObj.search.return_value = '{"results": {"phenotypes": {"' + my_term + '": {"description":"my_description", "categorical":"false", "min":'+str(my_range_min)+', "max":'+str(my_range_max)+'}}}}'

        # attempt adding continuous term with min/max by position  -- type int
        myAttrList.add(my_term, my_min, my_max)
        # make sure entry was added correctly
        self.assertEqual(len(myAttrList.data), 1)
        self.assertEqual(myAttrList.data[my_term]['min'], my_min)
        self.assertEqual(myAttrList.data[my_term]['max'], my_max)

        # reset
        myAttrList.data = {}

        # attempt adding continuous term with min/max by position -- type float
        myAttrList.add(my_term, (my_min + 0.1), (my_max - 0.1))
        # make sure entry was added correctly
        self.assertEqual(len(myAttrList.data), 1)
        self.assertEqual(myAttrList.data[my_term]['min'], (my_min + 0.1))
        self.assertEqual(myAttrList.data[my_term]['max'], (my_max - 0.1))

        # reset
        myAttrList.data = {}

        # attempt adding continuous term with min/max by position -- type float
        myAttrList.add(my_term, my_min, (my_max - 0.1))
        # make sure entry was added correctly
        self.assertEqual(len(myAttrList.data), 1)
        self.assertEqual(myAttrList.data[my_term]['min'], my_min)
        self.assertEqual(myAttrList.data[my_term]['max'], (my_max - 0.1))


        # reset
        myAttrList.data = {}

        # attempt adding continuous term with min/max by position -- type float
        myAttrList.add(my_term, (my_min +0.1), my_max)
        # make sure entry was added correctly
        self.assertEqual(len(myAttrList.data), 1)
        self.assertEqual(myAttrList.data[my_term]['min'], my_min + 0.1)
        self.assertEqual(myAttrList.data[my_term]['max'], my_max)

        # reset
        myAttrList.data = {}


        # attempt adding continuous term with min/max by name
        myAttrList.add(my_term, max=my_max, min=my_min)
        # make sure entry was added correctly
        self.assertEqual(len(myAttrList.data), 1)
        self.assertEqual(myAttrList.data[my_term]['min'], my_min)
        self.assertEqual(myAttrList.data[my_term]['max'], my_max)

        # reset
        myAttrList.data = {}

        # attempt adding continuous term with min/max where min and max are inclusive
        myAttrList.add(my_term, min=my_range_min, max=my_range_max)
        # make sure entry was added correctly
        self.assertEqual(len(myAttrList.data), 1)
        self.assertEqual(myAttrList.data[my_term]['min'], my_range_min)
        self.assertEqual(myAttrList.data[my_term]['max'], my_range_max)


    @patch('PicSureClient.PicSureConnectionAPI')
    def test_func_add_using_single_value(self, mock_api_obj):
        my_term = "testing_term"
        my_value_int = 2
        my_value_float = 2.02
        my_value_str = "test"
        my_range_min = 1
        my_range_max = 10

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

        my_apiObj.search.return_value = '{"results": {"phenotypes": {"' + my_term + '": {"description":"my_description", "categorical":"false", "min":'+str(my_range_min)+', "max":'+str(my_range_max)+'}}}}'
        # attempt adding continuous term by single int value
        myAttrList.add(my_term, my_value_int)
        # make sure entry was added correctly
        self.assertEqual(len(myAttrList.data), 1)
        self.assertEqual(myAttrList.data[my_term]['type'], "minmax")
        self.assertEqual(myAttrList.data[my_term]['min'], my_value_int)
        self.assertEqual(myAttrList.data[my_term]['max'], my_value_int)

        # reset
        myAttrList.data = {}

        # attempt adding continuous term by single float value
        myAttrList.add(my_term, my_value_float)
        # make sure entry was added correctly
        self.assertEqual(len(myAttrList.data), 1)
        self.assertEqual(myAttrList.data[my_term]['type'], "minmax")
        self.assertEqual(myAttrList.data[my_term]['min'], my_value_float)
        self.assertEqual(myAttrList.data[my_term]['max'], my_value_float)

        # reset
        myAttrList.data = {}

        # attempt adding categorical term by single string value
        myAttrList.add(my_term, my_value_str)
        # make sure entry was added correctly
        self.assertEqual(len(myAttrList.data), 1)
        self.assertEqual(myAttrList.data[my_term]['type'], "value")
        self.assertEqual(myAttrList.data[my_term]['value'], my_value_str)

        # reset
        myAttrList.data = {}


    @patch('PicSureClient.PicSureConnectionAPI')
    def test_func_add_prexisting_key(self, mock_api_obj):
        my_term = "testing_term"
        my_cat = "some_category"

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

        my_apiObj.search.return_value = '{"results": {"phenotypes": {"' + my_term + '": {"description":"my_description", "categorical":"true", "values":["'+my_cat+'"]}}}}'
        # add a term
        myAttrList.add(my_term)
        # make sure entry was added correctly
        self.assertEqual(len(myAttrList.data), 1)
        self.assertEqual(myAttrList.data[my_term]['type'], "exists")

        # save entry for later
        saved_record = myAttrList.data[my_term]

        # start console capture
        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            myAttrList.add(my_term, my_cat)
            sys.stdout = sys.__stdout__  # Reset redirect. Needed for it to work!
            captured = fake_stdout.getvalue()
            print("Captured:\n" + captured)

        # make sure no entries were added
        self.assertEqual(len(myAttrList.data), 1)

        #make sure that the existing entry was not changed
        self.assertDictEqual(saved_record, myAttrList.data[my_term])

        # make sure that an error message was printed
        self.assertTrue(len(captured) > 0)



        # attempt adding category term by parameter value WHEN THE KEY ALREADY EXISTS
        myAttrList.add(my_term, my_cat)
        # make sure the entry was not added
        self.assertEqual(len(myAttrList.data), 1)
