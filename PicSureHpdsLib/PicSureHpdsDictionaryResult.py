# -*- coding: utf-8 -*-

class DictionaryResult:
    """ Main class of library """
    def __init__(self, results):
        self.results = results
        pass

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
        return len(self.results["results"])

    def keys(self):
        return list(self.results["results"])

    def entries(self):
        ret = []
        for key in self.results["results"]:
            ret.append(self.results["results"][key])
        return ret

    def DataFrame(self):
        import pandas
        ret = {}

        # build the column list from the attributes found in the first result record
        key = list(self.results["results"]).pop()
        colNames = list(self.results["results"][key])
        for key in colNames:
            if key != 'name':
                ret[key] = []

        # now populate the dataframe columns
        i = []
        for key in self.results["results"]:
            i.append(key.replace('\\','\\\\'))
            for col in colNames:
                if col != 'name':
                    ret[col].append(self.results["results"][key][col])

        return pandas.DataFrame(data=ret, index=i);
