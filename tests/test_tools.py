from src.tools import (
    get_firm_history,
    get_control_history,
    score_firm,
    get_percentile,
    get_deviation,
    get_peer_cohort,
    get_cohort_rate,
    get_industry_context,
    get_filing_excerpt,
)


def assert_tool_envelope(result):
    """Every tool must return exactly value, source, and notes."""
    assert set(result.keys()) == {"value", "source", "notes"}
    assert isinstance(result["source"], str)
    assert isinstance(result["notes"], str)


def test_get_firm_history():
    result = get_firm_history("001004", 2018)

    assert_tool_envelope(result)
    assert isinstance(result["value"], list)

    if result["value"]:
        record = result["value"][0]
        assert "fyear" in record
        assert "auopic" in record
        assert "auop" in record
        assert "SIC" in record


def test_get_control_history():
    result = get_control_history("001004")

    assert_tool_envelope(result)

    value = result["value"]
    assert "adverse_years" in value
    assert "effective_years" in value
    assert "not_assessed_years" in value
    assert "current_status" in value
    assert "prior_year_status" in value


def test_score_firm():
    result = score_firm("001004", 2018)

    assert_tool_envelope(result)

    value = result["value"]
    assert "probability" in value
    assert "percentile" in value
    assert "cohort_base_rate" in value
    assert "model_version" in value
    assert "uses_prior_opinion" in value

    assert value["uses_prior_opinion"] is False


def test_get_percentile():
    result = get_percentile("001004", 2018, "ROA")

    assert_tool_envelope(result)
    assert isinstance(result["value"], float)


def test_get_deviation():
    result = get_deviation("001004", 2018, "ROA")

    assert_tool_envelope(result)

    value = result["value"]
    assert "current" in value
    assert "own_median" in value
    assert "difference" in value
    assert "years_used" in value
    assert "direction" in value


def test_get_peer_cohort():
    result = get_peer_cohort("001004", 2018)

    assert_tool_envelope(result)

    value = result["value"]
    assert "k" in value
    assert "matched_on" in value
    assert "peer_adverse_rate" in value
    assert "cohort_base_rate" in value
    assert "lift" in value
    assert "peers_resolved" in value


def test_get_cohort_rate():
    result = get_cohort_rate("size_decile_2", 2018)

    assert_tool_envelope(result)

    value = result["value"]
    assert value["slice"] == "size_decile_2"
    assert "adverse_rate" in value
    assert "n" in value
    assert "fyear" in value


def test_get_industry_context():
    result = get_industry_context("001004", 2018)

    assert_tool_envelope(result)

    value = result["value"]
    assert "sic" in value
    assert "sic2" in value
    assert "industry_label" in value
    assert "industry_rate" in value
    assert "n_firms" in value
    assert "within_industry_percentiles" in value


def test_get_filing_excerpt():
    result = get_filing_excerpt("001004", 2018, "item9a")

    assert_tool_envelope(result)

    # The filing tool is currently gated.
    assert result["value"] is None
    assert "gated" in result["notes"].lower()