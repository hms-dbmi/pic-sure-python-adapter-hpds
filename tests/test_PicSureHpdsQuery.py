from PicSureClient import Connection
import PicSureHpdsLib
from PicSureHpdsLib import PicSureHpdsDictionary, PicSureHpdsQuery, PicSureHpds
import unittest
from unittest.mock import patch

class TestHpdsQuery(unittest.TestCase):

    @patch('PicSureClient.Connection')
    def test_HpdsQuery_create(self, mock_picsure_connection):
        conn = mock_picsure_connection()
        test_uuid = "my-test-uuid"
        resource = PicSureHpds.HpdsResourceConnection(conn, test_uuid)
        query = resource.query()
        self.assertIsInstance(query, PicSureHpdsQuery.Query)


    def test_HpdsQuery
