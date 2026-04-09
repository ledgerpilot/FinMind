from unittest.mock import patch
from datetime import date, timedelta
import pytest

# Assuming the default test user created by auth_header fixture has uid = 1.
DEFAULT_TEST_USER_ID = 1

def test_weekly_summary_unauthenticated(client):
    """Test that accessing the weekly summary endpoint without authentication returns 401."""
    r = client.get("/insights/weekly-summary")
    assert r.status_code == 401


@patch("app.services.ai.weekly_financial_summary")
def test_weekly_summary_authenticated_default_week(mock_weekly_financial_summary, client, auth_header):
    """
    Test authenticated access to the weekly summary endpoint with default week (current week).
    Verify the service function is called correctly and response structure.
    """
    # Mock the return value of the service function
    mock_weekly_financial_summary.return_value = {
        "week_start": "2024-10-07", # Example fixed date for mock
        "total_spending": 115.0,
        "income": 100.0,
        "net_flow": -15.0,
        "top_categories": [
            {"category_id": "Groceries", "amount": 65.0},
            {"category_id": "Dining Out", "amount": 30.0},
        ],
        "week_over_week_change_pct": 15.0,
        "insights": ["AI insight 1", "AI insight 2"],
        "persona": None,
        "method": "gemini",
    }

    r = client.get("/insights/weekly-summary", headers=auth_header)
    assert r.status_code == 200
    summary = r.get_json()

    assert summary["week_start"] == "2024-10-07"
    assert "insights" in summary
    assert summary["total_spending"] == 115.0
    assert summary["income"] == 100.0
    assert summary["net_flow"] == -15.0
    assert len(summary["top_categories"]) == 2
    assert summary["week_over_week_change_pct"] == 15.0
    assert summary["method"] == "gemini"

    # Verify that the service function was called with the correct arguments (default week_start_str=None)
    mock_weekly_financial_summary.assert_called_once()
    call_args, call_kwargs = mock_weekly_financial_summary.call_args
    assert call_kwargs["uid"] == DEFAULT_TEST_USER_ID
    assert call_kwargs["week_start_str"] is None
    assert call_kwargs["gemini_api_key"] is None
    assert call_kwargs["persona"] is None


@patch("app.services.ai.weekly_financial_summary")
def test_weekly_summary_with_params(mock_weekly_financial_summary, client, auth_header):
    """
    Test authenticated access to the weekly summary endpoint with explicit week,
    Gemini API key, and persona parameters.
    """
    mock_weekly_financial_summary.return_value = {
        "week_start": "2023-01-02", # Example fixed date for mock
        "total_spending": 200.0,
        "income": 300.0,
        "net_flow": 100.0,
        "top_categories": [],
        "week_over_week_change_pct": -5.0,
        "insights": ["Custom AI insight for Investor"],
        "persona": "Investor",
        "method": "gemini",
    }

    # Use a specific Monday date for the test
    test_date_str = "2023-01-02"  # A Monday

    r = client.get(
        f"/insights/weekly-summary?week={test_date_str}",
        headers={**auth_header, "X-Insight-Persona": "Investor", "X-Gemini-Api-Key": "test-gemini-key"},
    )
    assert r.status_code == 200
    summary = r.get_json()

    assert summary["week_start"] == "2023-01-02"
    assert "Custom AI insight for Investor" in summary["insights"]
    assert summary["persona"] == "Investor"
    assert summary["method"] == "gemini"

    # Verify that the service function was called with the correct arguments
    mock_weekly_financial_summary.assert_called_once()
    call_args, call_kwargs = mock_weekly_financial_summary.call_args
    assert call_kwargs["uid"] == DEFAULT_TEST_USER_ID
    assert call_kwargs["week_start_str"] == test_date_str
    assert call_kwargs["gemini_api_key"] == "test-gemini-key"
    assert call_kwargs["persona"] == "Investor"


@patch("app.services.ai.weekly_financial_summary")
def test_weekly_summary_service_returns_heuristic(mock_weekly_financial_summary, client, auth_header):
    """
    Test endpoint when the AI service returns a heuristic summary (e.g., if AI generation fails).
    """
    mock_weekly_financial_summary.return_value = {
        "week_start": (date.today() - timedelta(days=date.today().weekday())).isoformat(),
        "total_spending": 0.0,
        "income": 0.0,
        "net_flow": 0.0,
        "top_categories": [],
        "week_over_week_change_pct": 0.0,
        "insights": ["Could not generate AI insights at this time. Falling back to heuristic."],
        "persona": None,
        "method": "heuristic_fallback",
    }

    r = client.get("/insights/weekly-summary", headers=auth_header)
    assert r.status_code == 200
    summary = r.get_json()

    assert summary["method"] == "heuristic_fallback"
    assert "Could not generate AI insights" in summary["insights"][0]
