from picsure._models.resource import Resource


class TestResource:
    def test_from_dict(self):
        data = {
            "uuid": "abc-123",
            "name": "Test Resource",
            "description": "A test resource",
        }
        resource = Resource.from_dict(data)
        assert resource.uuid == "abc-123"
        assert resource.name == "Test Resource"
        assert resource.description == "A test resource"

    def test_from_dict_missing_description_defaults_empty(self):
        data = {"uuid": "abc-123", "name": "Test Resource"}
        resource = Resource.from_dict(data)
        assert resource.description == ""

    def test_from_dict_with_extra_fields_ignored(self):
        data = {
            "uuid": "abc-123",
            "name": "Test",
            "description": "Desc",
            "extra_field": "ignored",
        }
        resource = Resource.from_dict(data)
        assert resource.uuid == "abc-123"
        assert not hasattr(resource, "extra_field")

    def test_from_dict_list(self, resources_response):
        resources = [Resource.from_dict(r) for r in resources_response]
        assert len(resources) == 2
        assert resources[0].uuid == "resource-uuid-aaaa-1111"
        assert resources[1].name == "BDC Open Access"
