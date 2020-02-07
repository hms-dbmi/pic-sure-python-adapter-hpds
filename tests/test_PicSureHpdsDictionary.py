import PicSureHpdsLib
from PicSureHpdsLib import PicSureHpdsDictionary
from PicSureHpdsLib import PicSureHpds
import unittest
from unittest.mock import Mock, patch
import json
import io
import sys

class TestHpdsDictionary(unittest.TestCase):



    def test_HpdsDictionary_create(self):
        test_url = "http://endpoint.url/pic-sure/"
        test_token = "my-JWT-token"

        adapter = PicSureHpds.BypassAdapter(test_url, test_token)
        resource = adapter.useResource()
        dictionary = resource.dictionary()
        # test that it was created correctly
        self.assertIsInstance(dictionary, PicSureHpdsDictionary.Dictionary)



    def test_HpdsDictionary_func_help(self):
        test_uuid = "my-test-uuid"

        mock_picsure_API = Mock()
        test = {"results": {"phenotypes": {}, "info": {} }, "searchQuery": "test_term"}
        test = json.dumps(test)
        mock_picsure_API.search.return_value = test

        mock_picsure_resource = Mock()
        mock_picsure_resource.resource_uuid = test_uuid
        mock_picsure_resource.connection_reference._api_obj.return_value = mock_picsure_API

        dictionary = PicSureHpdsLib.Dictionary(mock_picsure_resource)

        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            dictionary.help()
            sys.stdout = sys.__stdout__  # Reset redirect. Needed for it to work!
            captured = fake_stdout.getvalue()
            print("Captured:\n" + captured)
            self.assertTrue(len(captured) > 0)



    def test_HpdsDictionary_func_find(self):
        test_uuid = "my-test-uuid"

        mock_picsure_API = Mock()
        test = {"results": {"phenotypes": {"\\Demographics\\Gender\\": {"name": "\\Demographics\\Gender\\","patientCount": 0,"categoryValues": ["Do not know",  "Male","Female"], "categorical": True,"observationCount": 10}},
                            "info": {"AA": {"description": "Ancestral Allele. Format: AA|REF|ALT|IndelType. AA: Ancestral allele, REF:Reference Allele, ALT:Alternate Allele, IndelType:Type of Indel (REF, ALT and IndelType are only defined for indels)", "values": ["AAAA|AAAAA|AAAA|insertion","AAAAAAAA|AAAAAAAA|AAAAAAA|deletion","?|GG|GGG|unsure","-|C|CC|cryptic_indel","AATAAA|AAAAAAA|AAAAAA|complex_insertion","TC|T|TT|complex_deletion","T|||"],"continuous": False}},
                            },
                "searchQuery": "test_term"
                }
        test = json.dumps(test)
        mock_picsure_API.search.return_value = test
        mock_picsure_API.profile.return_value = '{}'

        mock_picsure_resource = Mock()
        mock_picsure_resource.resource_uuid = test_uuid
        mock_picsure_resource.connection_reference._api_obj.return_value = mock_picsure_API

        dictionary = PicSureHpdsLib.Dictionary(mock_picsure_resource)
        dictionary.find("test_term")

        mock_picsure_API.search.assert_called_with(test_uuid, '{"query": "test_term"}')



    def test_HpdsDictionary_func_findAll(self):
        test_uuid = "my-test-uuid"

        mock_picsure_API = Mock()
        test = {"results": {"phenotypes": {"\\Demographics\\Gender\\": {"name": "\\Demographics\\Gender\\","patientCount": 0,"categoryValues": ["Do not know",  "Male","Female"], "categorical": True,"observationCount": 10}},
                            "info": {"AA": {"description": "Ancestral Allele. Format: AA|REF|ALT|IndelType. AA: Ancestral allele, REF:Reference Allele, ALT:Alternate Allele, IndelType:Type of Indel (REF, ALT and IndelType are only defined for indels)", "values": ["AAAA|AAAAA|AAAA|insertion","AAAAAAAA|AAAAAAAA|AAAAAAA|deletion","?|GG|GGG|unsure","-|C|CC|cryptic_indel","AATAAA|AAAAAAA|AAAAAA|complex_insertion","TC|T|TT|complex_deletion","T|||"],"continuous": False}},
                            },
                "searchQuery": "test_term"
                }
        test = json.dumps(test)
        mock_picsure_API.search.return_value = test
        mock_picsure_API.profile.return_value = '{}'

        mock_picsure_resource = Mock()
        mock_picsure_resource.resource_uuid = test_uuid
        mock_picsure_resource.connection_reference._api_obj.return_value = mock_picsure_API

        dictionary = PicSureHpdsLib.Dictionary(mock_picsure_resource)
        dictionary.find()

        mock_picsure_API.search.assert_called_with(test_uuid, '{"query": ""}')



    def test_HpdsDictionary_func_find_queryScope_given(self):
        test_uuid = "my-test-uuid"

        mock_picsure_API = Mock()
        test = {"results": {"phenotypes": {"\\Demographics\\Gender\\": {"name": "\\Demographics\\Gender\\","patientCount": 0,"categoryValues": ["Do not know",  "Male","Female"], "categorical": True,"observationCount": 10}},
                            "info": {"AA": {"description": "Ancestral Allele. Format: AA|REF|ALT|IndelType. AA: Ancestral allele, REF:Reference Allele, ALT:Alternate Allele, IndelType:Type of Indel (REF, ALT and IndelType are only defined for indels)", "values": ["AAAA|AAAAA|AAAA|insertion","AAAAAAAA|AAAAAAAA|AAAAAAA|deletion","?|GG|GGG|unsure","-|C|CC|cryptic_indel","AATAAA|AAAAAAA|AAAAAA|complex_insertion","TC|T|TT|complex_deletion","T|||"],"continuous": False}},
                            },
                "searchQuery": "test_term"
                }
        mock_picsure_API.search.return_value = json.dumps(test)
        mock_picsure_API.profile.return_value = '{"uuid":"e2fb9de0-d9a9-47bc-aff3-c1ea9cb2b134","email":"nbenik@gmail.com","privileges":["ROLE_SYSTEM","PIC-SURE Unrestricted Query","ADMIN"], "queryScopes":["\\\\Demographics"]}'


        mock_picsure_resource = Mock()
        mock_picsure_resource.resource_uuid = test_uuid
        mock_picsure_resource.connection_reference._api_obj.return_value = mock_picsure_API

        dictionary = PicSureHpdsLib.Dictionary(mock_picsure_resource)
        results = dictionary.find("test_term")

        mock_picsure_API.search.assert_called_with(test_uuid, '{"query": "test_term"}')
        mock_picsure_API.profile.assert_called()

        for key in results.keys():
            self.assertTrue(key.startswith("\\Demographics"))

    def test_HpdsDictionary_func_find_queryScope_notgiven(self):
        test_uuid = "my-test-uuid"

        mock_picsure_API = Mock()
        test = {"results": {"phenotypes": {"\\Demographics\\Gender\\": {"name": "\\Demographics\\Gender\\","patientCount": 0,"categoryValues": ["Do not know",  "Male","Female"], "categorical": True,"observationCount": 10}},
                            "info": {"AA": {"description": "Ancestral Allele. Format: AA|REF|ALT|IndelType. AA: Ancestral allele, REF:Reference Allele, ALT:Alternate Allele, IndelType:Type of Indel (REF, ALT and IndelType are only defined for indels)", "values": ["AAAA|AAAAA|AAAA|insertion","AAAAAAAA|AAAAAAAA|AAAAAAA|deletion","?|GG|GGG|unsure","-|C|CC|cryptic_indel","AATAAA|AAAAAAA|AAAAAA|complex_insertion","TC|T|TT|complex_deletion","T|||"],"continuous": False}},
                            },
                "searchQuery": "test_term"
                }
        mock_picsure_API.search.return_value = json.dumps(test)
        mock_picsure_API.profile.return_value = '{"uuid":"e2fb9de0-d9a9-47bc-aff3-c1ea9cb2b134","email":"nbenik@gmail.com","privileges":["ROLE_SYSTEM","PIC-SURE Unrestricted Query","ADMIN"]}'


        mock_picsure_resource = Mock()
        mock_picsure_resource.resource_uuid = test_uuid
        mock_picsure_resource.connection_reference._api_obj.return_value = mock_picsure_API

        dictionary = PicSureHpdsLib.Dictionary(mock_picsure_resource)
        results = dictionary.find("test_term")

        mock_picsure_API.search.assert_called_with(test_uuid, '{"query": "test_term"}')
        mock_picsure_API.profile.assert_called()

        self.assertTrue(len(results.keys()) == 2)
