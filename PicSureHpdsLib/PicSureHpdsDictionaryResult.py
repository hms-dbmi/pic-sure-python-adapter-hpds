# -*- coding: utf-8 -*-

class DictionaryResult:
    """ Main class of library """
    def __init__(self, results):
        self.results = results

    def help(self):
        print("""
        [HELP] PicSureHpdsLib.Client(connection).useResource(uuid).dictionary().find(term)
            .count()        Returns the number of entries in the dictionary that match the given term
            .keys()         Return the keys of the matching entries
            .entries()      Return a list of matching dictionary entries
            .DataFrame()    Return the entries in a Pandas-compatible format
             
        [Examples]
            results = PicSureHpdsLib.Client(connection).useResource(uuid).dictionary().find("asthma")
            df = results.DataFrame()
        """)

    def count(self):
        return len(self.results['results'])

    def keys(self):
        return list(self.results['results'])

    def entries(self):
        ret = []
        for key in self.results['results']:
            ret.append(self.results['results'][key])
        return ret

    def DataFrame(self):
        import pandas
        ret = {}

        # return an empty dataframe if there are no records
        if len(self.results['results']) == 0:
            return pandas.DataFrame(data=ret)

        # build the column list from the attributes found in ALL result records
        for i, d in self.results['results'].items():
            for c in list(d):
                if not c in ret:
                    ret[c] = []
        # remove the name column if it exists
        if "name" in ret:
            del ret["name"]

        # now populate the dataframe columns
        colNames = list(ret)
        idx = []
        for key, record in self.results['results'].items():
#            idx.append(key.replace('\\','\\\\'))
            idx.append(key)
            for col in colNames:
                if col != 'name':
                    if col in record:
                        ret[col].append(record[col])
                    else:
                        ret[col].append(None)
        df = pandas.DataFrame(data=ret, index=idx)
        df.index.name = 'KEY'
        return df
