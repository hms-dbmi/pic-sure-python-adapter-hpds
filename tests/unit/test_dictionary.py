from picsure._models.dictionary import DictionaryEntry


class TestDictionaryEntry:
    def test_from_dict(self):
        data = {
            "conceptPath": "\\phs000007\\sex\\",
            "name": "sex",
            "display": "Sex of participant",
            "description": "Biological sex",
            "type": "categorical",
            "dataset": "phs000007",
            "values": ["Male", "Female"],
        }
        entry = DictionaryEntry.from_dict(data)
        assert entry.concept_path == "\\phs000007\\sex\\"
        assert entry.name == "sex"
        assert entry.display == "Sex of participant"
        assert entry.description == "Biological sex"
        assert entry.data_type == "categorical"
        assert entry.study_id == "phs000007"
        assert entry.values == ["Male", "Female"]

    def test_from_dict_null_description(self):
        data = {"conceptPath": "\\x\\", "name": "x", "description": None}
        entry = DictionaryEntry.from_dict(data)
        assert entry.description == ""

    def test_from_dict_legacy_field_names(self):
        data = {
            "conceptPath": "\\p\\",
            "name": "v",
            "dataType": "categorical",
            "studyId": "phs000007",
        }
        entry = DictionaryEntry.from_dict(data)
        assert entry.data_type == "categorical"
        assert entry.study_id == "phs000007"

    def test_from_dict_missing_optional_fields(self):
        data = {
            "conceptPath": "\\some\\path\\",
            "name": "var",
        }
        entry = DictionaryEntry.from_dict(data)
        assert entry.concept_path == "\\some\\path\\"
        assert entry.name == "var"
        assert entry.display == ""
        assert entry.description == ""
        assert entry.data_type == ""
        assert entry.study_id == ""
        assert entry.values == []
        assert entry.min is None
        assert entry.max is None
        assert entry.allow_filtering is None
        assert entry.meta is None
        assert entry.study_acronym is None

    def test_from_dict_continuous_fields_populated(self):
        data = {
            "conceptPath": "\\phs000007\\age\\",
            "name": "age",
            "type": "Continuous",
            "min": 0.0,
            "max": 100.0,
            "allowFiltering": True,
            "meta": {"k": "v"},
            "studyAcronym": "FHS",
            "dataset": "phs000007",
        }
        entry = DictionaryEntry.from_dict(data)
        assert entry.min == 0.0
        assert entry.max == 100.0
        assert entry.allow_filtering is True
        assert entry.meta == {"k": "v"}
        assert entry.study_acronym == "FHS"
        assert entry.data_type == "Continuous"
        assert entry.study_id == "phs000007"

    def test_from_dict_categorical_no_min_max(self):
        data = {
            "conceptPath": "\\phs000007\\sex\\",
            "name": "sex",
            "type": "Categorical",
            "values": ["Male", "Female"],
            "allowFiltering": True,
            "studyAcronym": "FHS",
            "dataset": "phs000007",
        }
        entry = DictionaryEntry.from_dict(data)
        assert entry.min is None
        assert entry.max is None
        assert entry.allow_filtering is True
        assert entry.study_acronym == "FHS"
        assert entry.meta is None

    def test_from_dict_empty_values(self):
        data = {
            "conceptPath": "\\path\\",
            "name": "age",
            "type": "continuous",
            "values": [],
        }
        entry = DictionaryEntry.from_dict(data)
        assert entry.values == []

    def test_from_dict_extra_fields_ignored(self):
        data = {
            "conceptPath": "\\path\\",
            "name": "var",
            "unknownField": "ignored",
        }
        entry = DictionaryEntry.from_dict(data)
        assert entry.concept_path == "\\path\\"
        assert not hasattr(entry, "unknownField")

    def test_from_dict_list_from_fixture(self, search_response):
        entries = [DictionaryEntry.from_dict(r) for r in search_response["content"]]
        assert len(entries) == 3
        assert entries[0].concept_path == "\\phs000007\\pht000001\\phv00001\\sex\\"
        assert entries[0].study_id == "phs000007"
        assert entries[2].data_type == "continuous"

    def test_frozen(self):
        data = {"conceptPath": "\\path\\", "name": "var"}
        entry = DictionaryEntry.from_dict(data)
        with __import__("pytest").raises(AttributeError):
            entry.name = "changed"  # type: ignore[misc]
