from app.modules.deployfilemanage.filereplace.simple_properties_replace import SimplePropertiesContentReplace


class FakeRepo:
    def __init__(self, data):
        self.data = data

    def get_global_details(self, hospital, env, group):
        return self.data


def test_replace_properties():
    repo = FakeRepo({"key1": "value1", "key2": "override"})
    replacer = SimplePropertiesContentReplace(repo)
    original = "key1=old\nkey2=old\nkey3=value\n# comment\n"

    result = replacer.replace(original, "H001.cbh.omnis")

    assert "key1=value1" in result
    assert "key2=override" in result
    assert "key3=value" in result
    assert "# comment" in result
