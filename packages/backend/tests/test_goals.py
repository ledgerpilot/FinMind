import pytest
from datetime import date, timedelta
from app.models import Goal, Milestone


def test_goal_crud_flow(client, auth_header):
    # Initially empty
    r = client.get("/goals", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create goal
    payload = {
        "name": "Buy a Car",
        "description": "Saving up for a new car",
        "target_amount": 15000.00,
        "currency": "USD",
        "due_date": (date.today() + timedelta(days=365)).isoformat(),
    }
    r = client.post("/goals", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal_data = r.get_json()
    goal_id = goal_data["id"]
    assert goal_data["name"] == "Buy a Car"
    assert goal_data["target_amount"] == 15000.00
    assert goal_data["current_amount"] == 0.0
    assert goal_data["currency"] == "USD"
    assert not goal_data["is_achieved"]
    assert "progress_percent" in goal_data
    assert goal_data["progress_percent"] == 0.0

    # Duplicate create should 409
    r = client.post("/goals", json=payload, headers=auth_header)
    assert r.status_code == 409

    # List should have 1
    r = client.get("/goals", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    assert any(g["id"] == goal_id for g in items)

    # Get single goal
    r = client.get(f"/goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["id"] == goal_id

    # Update goal
    update_payload = {"name": "Buy a Hybrid Car", "target_amount": 20000.00}
    r = client.patch(f"/goals/{goal_id}", json=update_payload, headers=auth_header)
    assert r.status_code == 200
    updated_goal = r.get_json()
    assert updated_goal["name"] == "Buy a Hybrid Car"
    assert updated_goal["target_amount"] == 20000.00

    # Delete goal
    r = client.delete(f"/goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "Goal deleted"

    # List should be empty again
    r = client.get("/goals", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_goal_contribution_and_achievement(client, auth_header):
    # Create goal
    payload = {
        "name": "Dream Vacation",
        "target_amount": 1000.00,
        "currency": "EUR",
    }
    r = client.post("/goals", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    # Contribute to goal
    r = client.post(
        f"/goals/{goal_id}/contribute", json={"amount": 200.00}, headers=auth_header
    )
    assert r.status_code == 200
    goal = r.get_json()
    assert goal["current_amount"] == 200.00
    assert goal["progress_percent"] == 20.0
    assert not goal["is_achieved"]

    r = client.post(
        f"/goals/{goal_id}/contribute", json={"amount": 300.00}, headers=auth_header
    )
    assert r.status_code == 200
    goal = r.get_json()
    assert goal["current_amount"] == 500.00
    assert goal["progress_percent"] == 50.0
    assert not goal["is_achieved"]

    # Achieve goal with final contribution
    r = client.post(
        f"/goals/{goal_id}/contribute", json={"amount": 500.00}, headers=auth_header
    )
    assert r.status_code == 200
    goal = r.get_json()
    assert goal["current_amount"] == 1000.00
    assert goal["progress_percent"] == 100.0
    assert goal["is_achieved"]
    assert goal["achieved_at"] is not None

    # Contribute over target
    r = client.post(
        f"/goals/{goal_id}/contribute", json={"amount": 100.00}, headers=auth_header
    )
    assert r.status_code == 200
    goal = r.get_json()
    assert goal["current_amount"] == 1100.00
    assert goal["progress_percent"] == 100.0  # Still 100% or clamped at 100%
    assert goal["is_achieved"]

    # Manually un-achieve and then re-achieve
    r = client.patch(
        f"/goals/{goal_id}", json={"is_achieved": False}, headers=auth_header
    )
    assert r.status_code == 200
    goal = r.get_json()
    assert not goal["is_achieved"]
    assert goal["achieved_at"] is None

    r = client.patch(
        f"/goals/{goal_id}", json={"is_achieved": True}, headers=auth_header
    )
    assert r.status_code == 200
    goal = r.get_json()
    assert goal["is_achieved"]
    assert goal["achieved_at"] is not None


def test_milestone_crud_and_auto_achievement(client, auth_header):
    # Create goal first
    goal_payload = {
        "name": "Big Project",
        "target_amount": 10000.00,
        "currency": "USD",
    }
    r = client.post("/goals", json=goal_payload, headers=auth_header)
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    # Initially no milestones
    r = client.get(f"/goals/{goal_id}/milestones", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create milestone 1 (not achieved yet)
    m1_payload = {"name": "Phase 1 Complete", "target_amount": 2000.00}
    r = client.post(
        f"/goals/{goal_id}/milestones", json=m1_payload, headers=auth_header
    )
    assert r.status_code == 201
    m1_data = r.get_json()
    m1_id = m1_data["id"]
    assert m1_data["name"] == "Phase 1 Complete"
    assert m1_data["target_amount"] == 2000.00
    assert not m1_data["is_achieved"]

    # Create milestone 2 (not achieved yet)
    m2_payload = {"name": "Phase 2 Complete", "target_amount": 5000.00}
    r = client.post(
        f"/goals/{goal_id}/milestones", json=m2_payload, headers=auth_header
    )
    assert r.status_code == 201
    m2_data = r.get_json()
    m2_id = m2_data["id"]
    assert not m2_data["is_achieved"]

    # Duplicate milestone name for same goal should fail
    r = client.post(
        f"/goals/{goal_id}/milestones", json=m1_payload, headers=auth_header
    )
    assert r.status_code == 409

    # List milestones for goal
    r = client.get(f"/goals/{goal_id}/milestones", headers=auth_header)
    assert r.status_code == 200
    milestones = r.get_json()
    assert len(milestones) == 2
    assert any(m["id"] == m1_id for m in milestones)
    assert any(m["id"] == m2_id for m in milestones)

    # Contribute to goal to achieve M1
    r = client.post(
        f"/goals/{goal_id}/contribute", json={"amount": 2500.00}, headers=auth_header
    )
    assert r.status_code == 200
    goal_updated = r.get_json()
    assert goal_updated["current_amount"] == 2500.00

    # Check M1 status (should be achieved)
    r = client.get(f"/goals/{goal_id}/milestones", headers=auth_header)
    milestones = r.get_json()
    m1_status = next(m for m in milestones if m["id"] == m1_id)
    assert m1_status["is_achieved"]
    assert m1_status["achieved_at"] is not None

    # Get single milestone
    r = client.get(f"/milestones/{m1_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["id"] == m1_id

    # Update milestone (e.g., description or target amount)
    r = client.patch(
        f"/milestones/{m1_id}",
        json={"name": "Phase 1 Completed Early", "target_amount": 1500.00},
        headers=auth_header,
    )
    assert r.status_code == 200
    updated_m1 = r.get_json()
    assert updated_m1["name"] == "Phase 1 Completed Early"
    assert updated_m1["target_amount"] == 1500.00
    assert updated_m1["is_achieved"]  # Still achieved, as current_amount is 2500

    # Contribute more to goal to achieve M2
    r = client.post(
        f"/goals/{goal_id}/contribute", json={"amount": 3000.00}, headers=auth_header
    )
    assert r.status_code == 200
    goal_updated = r.get_json()
    assert goal_updated["current_amount"] == 5500.00

    # Check M2 status (should be achieved)
    r = client.get(f"/milestones/{m2_id}", headers=auth_header)
    m2_status = r.get_json()
    assert m2_status["is_achieved"]
    assert m2_status["achieved_at"] is not None

    # Delete milestone
    r = client.delete(f"/milestones/{m1_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "Milestone deleted"

    # List should now have 1 milestone
    r = client.get(f"/goals/{goal_id}/milestones", headers=auth_header)
    assert r.status_code == 200
    milestones = r.get_json()
    assert len(milestones) == 1
    assert milestones[0]["id"] == m2_id


def test_goal_with_no_due_date_and_default_currency(client, auth_header):
    r = client.patch(
        "/auth/me", json={"preferred_currency": "AUD"}, headers=auth_header
    )
    assert r.status_code == 200

    payload = {
        "name": "New Phone",
        "target_amount": 1200.00,
    }
    r = client.post("/goals", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal = r.get_json()
    assert goal["currency"] == "AUD"
    assert goal["due_date"] is None
