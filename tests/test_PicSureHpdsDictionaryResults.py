import PicSureHpdsLib
from PicSureHpdsLib import PicSureHpdsDictionaryResult
import unittest
from unittest.mock import Mock, patch
import json
import io
import sys

class TestHpdsDictionaryResults(unittest.TestCase):

    def test_HpdsDictionaryResults_create(self):
        test_uuid = "my-test-uuid"

        mock_picsure_API = Mock()
        test = {"results": {"phenotypes": {"\\Demographics\\Gender\\": {"name": "\\Demographics\\Gender\\","patientCount": 0,"categoryValues": ["Do not know",  "Male","Female"], "categorical": True,"observationCount": 10}},
                            "info": {"AA": {"description": "Ancestral Allele. Format: AA|REF|ALT|IndelType. AA: Ancestral allele, REF:Reference Allele, ALT:Alternate Allele, IndelType:Type of Indel (REF, ALT and IndelType are only defined for indels)", "values": ["AAAA|AAAAA|AAAA|insertion","AAAAAAAA|AAAAAAAA|AAAAAAA|deletion","?|GG|GGG|unsure","-|C|CC|cryptic_indel","AATAAA|AAAAAAA|AAAAAA|complex_insertion","TC|T|TT|complex_deletion","T|||"],"continuous": False}},
                            },
                "searchQuery": "test_term"
                }
        mock_picsure_API.search.return_value = json.dumps(test)
        mock_picsure_API.profile.return_value = '{}'

        mock_picsure_resource = Mock()
        mock_picsure_resource.resource_uuid = test_uuid
        mock_picsure_resource.connection_reference._api_obj.return_value = mock_picsure_API

        dictionary = PicSureHpdsLib.Dictionary(mock_picsure_resource)
        results = dictionary.find("test_term")

        self.assertIsInstance(results, PicSureHpdsLib.PicSureHpdsDictionaryResult.DictionaryResult)


    def test_HpdsDictionaryResults_func_help(self):
        test_uuid = "my-test-uuid"

        mock_picsure_API = Mock()
        test = {"results": {"phenotypes": {}, "info": {}}, "searchQuery": "test_term"}
        mock_picsure_API.search.return_value = json.dumps(test)
        mock_picsure_API.profile.return_value = '{}'

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


    def test_HpdsDictionaryResults_func_count(self):
        test_uuid = "my-test-uuid"

        mock_picsure_API = Mock()
        test = {"results": {"phenotypes": {"\\Demographics\\Gender\\": {"name": "\\Demographics\\Gender\\","patientCount": 0,"categoryValues": ["Do not know",  "Male","Female"], "categorical": True,"observationCount": 10}},
                            "info": {"AA": {"description": "Ancestral Allele. Format: AA|REF|ALT|IndelType. AA: Ancestral allele, REF:Reference Allele, ALT:Alternate Allele, IndelType:Type of Indel (REF, ALT and IndelType are only defined for indels)", "values": ["AAAA|AAAAA|AAAA|insertion","AAAAAAAA|AAAAAAAA|AAAAAAA|deletion","?|GG|GGG|unsure","-|C|CC|cryptic_indel","AATAAA|AAAAAAA|AAAAAA|complex_insertion","TC|T|TT|complex_deletion","T|||"],"continuous": False}},
                            },
                "searchQuery": "test_term"
                }
        mock_picsure_API.search.return_value = json.dumps(test)
        mock_picsure_API.profile.return_value = '{}'

        mock_picsure_resource = Mock()
        mock_picsure_resource.resource_uuid = test_uuid
        mock_picsure_resource.connection_reference._api_obj.return_value = mock_picsure_API

        dictionary = PicSureHpdsLib.Dictionary(mock_picsure_resource)
        results = dictionary.find("test_term")

        self.assertEqual(results.count(), 2)

    def test_HpdsDictionaryResults_func_keys(self):
        test_uuid = "my-test-uuid"

        mock_picsure_API = Mock()
        test = {"results": {"phenotypes": {"\\Demographics\\Gender\\": {"name": "\\Demographics\\Gender\\","patientCount": 0,"categoryValues": ["Do not know",  "Male","Female"], "categorical": True,"observationCount": 10}},
                            "info": {"AA": {"description": "Ancestral Allele. Format: AA|REF|ALT|IndelType. AA: Ancestral allele, REF:Reference Allele, ALT:Alternate Allele, IndelType:Type of Indel (REF, ALT and IndelType are only defined for indels)", "values": ["AAAA|AAAAA|AAAA|insertion","AAAAAAAA|AAAAAAAA|AAAAAAA|deletion","?|GG|GGG|unsure","-|C|CC|cryptic_indel","AATAAA|AAAAAAA|AAAAAA|complex_insertion","TC|T|TT|complex_deletion","T|||"],"continuous": False}},
                            },
                "searchQuery": "test_term"
                }
        mock_picsure_API.search.return_value = json.dumps(test)
        mock_picsure_API.profile.return_value = '{}'

        mock_picsure_resource = Mock()
        mock_picsure_resource.resource_uuid = test_uuid
        mock_picsure_resource.connection_reference._api_obj.return_value = mock_picsure_API

        dictionary = PicSureHpdsLib.Dictionary(mock_picsure_resource)
        results = dictionary.find("test_term")

        self.assertListEqual(
            results.keys(),
            ['\\Demographics\\Gender\\', 'AA']
        )



    def test_HpdsDictionaryResults_func_entries(self):
        test_uuid = "my-test-uuid"

        mock_picsure_API = Mock()
        test = {"results": {"phenotypes": {"\\Demographics\\Gender\\": {"name": "\\Demographics\\Gender\\","patientCount": 0,"categoryValues": ["Do not know",  "Male","Female"], "categorical": True,"observationCount": 10}},
                            "info": {"AA": {"description": "Ancestral Allele. Format: AA|REF|ALT|IndelType. AA: Ancestral allele, REF:Reference Allele, ALT:Alternate Allele, IndelType:Type of Indel (REF, ALT and IndelType are only defined for indels)", "values": ["AAAA|AAAAA|AAAA|insertion","AAAAAAAA|AAAAAAAA|AAAAAAA|deletion","?|GG|GGG|unsure","-|C|CC|cryptic_indel","AATAAA|AAAAAAA|AAAAAA|complex_insertion","TC|T|TT|complex_deletion","T|||"],"continuous": False}},
                            },
                "searchQuery": "test_term"
                }
        mock_picsure_API.search.return_value = json.dumps(test)
        mock_picsure_API.profile.return_value = '{}'

        mock_picsure_resource = Mock()
        mock_picsure_resource.resource_uuid = test_uuid
        mock_picsure_resource.connection_reference._api_obj.return_value = mock_picsure_API

        dictionary = PicSureHpdsLib.Dictionary(mock_picsure_resource)
        results = dictionary.find("test_term")

        self.assertListEqual(
            results.entries(),
            [
                {'name': '\\Demographics\\Gender\\', 'patientCount': 0, 'categoryValues': ['Do not know', 'Male', 'Female'], 'categorical': True, 'observationCount': 10, 'HpdsDataType': 'phenotypes'},
                {'description': 'Ancestral Allele. Format: AA|REF|ALT|IndelType. AA: Ancestral allele, REF:Reference Allele, ALT:Alternate Allele, IndelType:Type of Indel (REF, ALT and IndelType are only defined for indels)',
                    'values': ['AAAA|AAAAA|AAAA|insertion', 'AAAAAAAA|AAAAAAAA|AAAAAAA|deletion', '?|GG|GGG|unsure','-|C|CC|cryptic_indel', 'AATAAA|AAAAAAA|AAAAAA|complex_insertion','TC|T|TT|complex_deletion', 'T|||'],
                 'continuous': False, 'HpdsDataType': 'info'}
            ]
        )



    def test_HpdsDictionaryResults_func_dataframe(self):
        test_uuid = "my-test-uuid"

        mock_picsure_API = Mock()
        test = {"results": {"phenotypes": {"\\Demographics\\Gender\\": {"name": "\\Demographics\\Gender\\","patientCount": 0,"categoryValues": ["Do not know",  "Male","Female"], "categorical": True,"observationCount": 10}},
                            "info": {"AA": {"description": "Ancestral Allele. Format: AA|REF|ALT|IndelType. AA: Ancestral allele, REF:Reference Allele, ALT:Alternate Allele, IndelType:Type of Indel (REF, ALT and IndelType are only defined for indels)", "values": ["AAAA|AAAAA|AAAA|insertion","AAAAAAAA|AAAAAAAA|AAAAAAA|deletion","?|GG|GGG|unsure","-|C|CC|cryptic_indel","AATAAA|AAAAAAA|AAAAAA|complex_insertion","TC|T|TT|complex_deletion","T|||"],"continuous": False}},
                            },
                "searchQuery": "test_term"
                }
        mock_picsure_API.search.return_value = json.dumps(test)
        mock_picsure_API.profile.return_value = '{}'

        mock_picsure_resource = Mock()
        mock_picsure_resource.resource_uuid = test_uuid
        mock_picsure_resource.connection_reference._api_obj.return_value = mock_picsure_API

        dictionary = PicSureHpdsLib.Dictionary(mock_picsure_resource)
        results = dictionary.find("test_term")
        df = results.DataFrame()
        print(df.head())
        print(dir(df))

        self.assertListEqual(
            df.columns.tolist(),
            ['patientCount', 'categoryValues', 'categorical', 'observationCount', 'HpdsDataType', 'description', 'values', 'continuous']
        )



        df = df.fillna(-999) # handle issues with NaN !== NaN
        print(df.loc["AA":].values.tolist()[0])
        self.assertListEqual(
            df.loc["AA":].values.tolist()[0],
            [
                -999.0,
                -999,
                -999,
                -999.0,
                'info',
                'Ancestral Allele. Format: AA|REF|ALT|IndelType. AA: Ancestral allele, REF:Reference Allele, ALT:Alternate Allele, IndelType:Type of Indel (REF, ALT and IndelType are only defined for indels)',
                [
                    'AAAA|AAAAA|AAAA|insertion',
                    'AAAAAAAA|AAAAAAAA|AAAAAAA|deletion',
                    '?|GG|GGG|unsure',
                    '-|C|CC|cryptic_indel',
                    'AATAAA|AAAAAAA|AAAAAA|complex_insertion',
                    'TC|T|TT|complex_deletion', 'T|||'
                ],
                False]
        )
