import PicSureHpdsLib
import json
import time


class QueryBatch(self):
    """ A class that allows parallel execution of queries """
    def __init__(self, refHpdsResourceConnection, max_simultaneous = 4, timeout_secs = None):
        self.max_queries = max_simultaneous
        self.batch_timeout = timeout_secs
        self._queries = {}

    def add(self, query_name, query_object, results_type):
        if query_name in self._queries:
            print('NOT ADDED: A query named "' + query_name + '" already exists in this execution batch.')
            return False
        # TODO: Check the validity of query_object's object type
        # add the query to our list
        self._queries[query_name] = {
            "submitted": False,
            "finished": False,
            "query": query_object.save(results_type),
            "results": None,
            "error": None
        }
        print('Added a query named "' + query_name + '" to this execution batch.')

    def delete(self, query_name):
        if query_name in self._queries:
            del self._queries[query_name]
            print('Removed "' + query_name + '" from the query batch.')
        else:
            print('NOT FOUND: Could not remove "' + query_name + '" from the query batch.')

    def execute(self):
        # TODO: write this
        pass
