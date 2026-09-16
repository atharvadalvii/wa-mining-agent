from unittest.mock import MagicMock, patch

import pytest

from geoagent.geospatial.wa_mining import (
    MiningDataError,
    _safe_literal,
    find_mining_deposits,
    find_mining_tenements,
)


def _mock_response(json_data):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = json_data
    return resp


def test_safe_literal_strips_sql_metacharacters():
    cleaned = _safe_literal("iron' OR '1'='1; --")
    assert "'" not in cleaned
    assert ";" not in cleaned
    assert "-" in cleaned or cleaned == "iron OR 11"


def test_safe_literal_keeps_normal_words():
    assert _safe_literal("Mining Lease") == "Mining Lease"
    assert _safe_literal("iron ore") == "iron ore"


@patch("requests.get")
def test_find_mining_deposits_parses_results(mock_get):
    mock_get.side_effect = [
        _mock_response({"count": 2}),
        _mock_response(
            {
                "features": [
                    {
                        "attributes": {
                            "site_title": "Test Mine",
                            "commodity": "IRON",
                            "site_type_": "Mine",
                            "site_stage": "Producer",
                            "latitude": -20.0,
                            "longitude": 118.0,
                        }
                    },
                    {
                        "attributes": {
                            "site_title": "Test Deposit",
                            "commodity": "IRON",
                            "site_type_": "Deposit",
                            "site_stage": "Undeveloped",
                            "latitude": -20.1,
                            "longitude": 118.1,
                        }
                    },
                ]
            }
        ),
    ]

    # A "lat,lon" string is used so resolve_point() never needs to geocode via Nominatim.
    result = find_mining_deposits("-20.3,118.5", radius_km=50, commodity="iron")

    assert result.total_count == 2
    assert len(result.sites) == 2
    text = result.to_tool_text()
    assert "Test Mine" in text
    assert "Found 2 MINEDEX mining site(s)" in text


@patch("requests.get")
def test_find_mining_deposits_commodity_filter_checks_target_com(mock_get):
    # Regression test: MINEDEX's `commodity` field is a coarse category (nickel
    # falls under "STEEL ALLOY METAL", gold under "PRECIOUS METAL") — the
    # specific mineral name lives in `target_com`. Filtering on `commodity`
    # alone silently returns zero results for most real mineral-name searches.
    mock_get.side_effect = [_mock_response({"count": 0})]

    find_mining_deposits("-20.3,118.5", commodity="nickel")

    count_call_params = mock_get.call_args_list[0].kwargs["params"]
    where = count_call_params["where"]
    assert "TARGET_COM" in where.upper()
    assert "NICKEL" in where.upper()


@patch("requests.get")
def test_find_mining_deposits_prefers_target_com_for_display(mock_get):
    # A site whose broad `commodity` category ("STEEL ALLOY METAL") differs
    # from its specific `target_com` ("NICKEL") should display the specific
    # name — that's what a user searching "nickel" actually wants to see.
    mock_get.side_effect = [
        _mock_response({"count": 1}),
        _mock_response(
            {
                "features": [
                    {
                        "attributes": {
                            "site_title": "Otter-Juan",
                            "commodity": "STEEL ALLOY METAL",
                            "target_com": "NICKEL",
                            "site_type_": "Mine",
                            "site_stage": "Care and Maintenance",
                            "latitude": -31.2,
                            "longitude": 121.6,
                        }
                    }
                ]
            }
        ),
    ]

    result = find_mining_deposits("-20.3,118.5", commodity="nickel")

    text = result.to_tool_text()
    assert "NICKEL" in text
    assert "STEEL ALLOY METAL" not in text

    features = result.to_geojson_features()
    assert features[0]["properties"]["commodity"] == "NICKEL"
    assert features[0]["properties"]["commodity_category"] == "STEEL ALLOY METAL"


@patch("requests.get")
def test_find_mining_deposits_no_results(mock_get):
    mock_get.side_effect = [_mock_response({"count": 0})]

    result = find_mining_deposits("-20.3,118.5", radius_km=10)

    assert result.total_count == 0
    assert "No MINEDEX mining sites found" in result.to_tool_text()


@patch("requests.get")
def test_find_mining_tenements_parses_results(mock_get):
    mock_get.side_effect = [
        _mock_response({"count": 1}),
        _mock_response(
            {
                "features": [
                    {
                        "attributes": {
                            "tenid": "M12/345",
                            "type": "MINING LEASE",
                            "tenstatus": "LIVE",
                            "holder1": "Test Co Pty Ltd",
                            "legal_area": 120.5,
                            "unit_of_me": "Ha",
                        }
                    }
                ]
            }
        ),
    ]

    result = find_mining_tenements("-20.3,118.5", radius_km=100, status="LIVE")

    assert result.total_count == 1
    text = result.to_tool_text()
    assert "M12/345" in text
    assert "Test Co Pty Ltd" in text


@patch("requests.get")
def test_query_service_error_raises_mining_data_error(mock_get):
    mock_get.side_effect = [
        _mock_response({"error": {"message": "Service unavailable"}}),
    ]

    with pytest.raises(MiningDataError):
        find_mining_deposits("-20.3,118.5")


@patch("time.sleep")
@patch("requests.get")
def test_query_transient_failure_retries_then_raises(mock_get, mock_sleep):
    mock_get.side_effect = ConnectionError("boom")

    with pytest.raises(MiningDataError):
        find_mining_deposits("-20.3,118.5")

    assert mock_get.call_count == 2
