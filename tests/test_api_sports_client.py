import pytest
from unittest import mock

import src.ingest.api_sports_client as client

def test_sport_host_map_contains_football():
    assert "football" in client.SPORT_HOST

def test_get_for_sport_invalid():
    with pytest.raises(ValueError):
        client.get_for_sport("sport_que_no_existe", "/fixtures")

@mock.patch("src.ingest.api_sports_client.requests.get")
def test_do_get_success(mock_get):
    class DummyResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"response": [{"id": 1}]}
    mock_get.return_value = DummyResp()
    res = client.get_for_sport("football", "/fixtures", params={"league": 1})
    assert isinstance(res, dict)
    assert "response" in res
