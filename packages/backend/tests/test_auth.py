def test_auth_refresh_flow(client):
    # Register user
    email = "refresh@test.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)  # 409 if already exists

    # Login to get tokens
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    data = r.get_json()
    assert "access_token" in data and "refresh_token" in data

    # Use refresh to get a new access token
    refresh_token = data["refresh_token"]
    r = client.post(
        "/auth/refresh", headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert r.status_code == 200
    new_access = r.get_json().get("access_token")
    assert isinstance(new_access, str) and len(new_access) > 10


def test_auth_login_records_last_login_details(client):
    """Verify that user's last login IP, User-Agent, and timestamp are recorded."""
    email = "record@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})

    # First login
    from unittest.mock import patch
    from datetime import datetime, timedelta, timezone
    from app.models import User

    with patch("app.auth.routes.request") as mock_request:
        mock_request.remote_addr = "192.168.1.1"
        mock_request.headers.get.return_value = "Test-Agent-1"
        r = client.post("/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200

        # Verify the details were recorded
        user = User.query.filter_by(email=email).first()
        assert user.last_login_ip == "192.168.1.1"
        assert user.last_login_user_agent == "Test-Agent-1"
        assert user.last_login_at is not None
        # Check that the timestamp is recent (within a few seconds)
        assert user.last_login_at >= datetime.now(timezone.utc) - timedelta(seconds=5)


@patch("app.utils.alerts.send_alert_email")
def test_auth_login_alerts_on_new_ip_address(mock_send_alert_email, client):
    """Test that an alert is sent when login occurs from a new IP address."""
    email = "newip@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})

    # First login from IP 1 (should not alert)
    from unittest.mock import patch
    from datetime import datetime
    with patch("app.auth.routes.request") as mock_request:
        mock_request.remote_addr = "192.168.1.1"
        mock_request.headers.get.return_value = "Test-Agent-A"
        r = client.post("/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200
        mock_send_alert_email.assert_not_called()

    # Second login from IP 2 (new IP, should alert)
    with patch("app.auth.routes.request") as mock_request:
        mock_request.remote_addr = "192.168.1.2"  # Different IP
        mock_request.headers.get.return_value = "Test-Agent-A"  # Same UA
        r = client.post("/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200
        mock_send_alert_email.assert_called_once()
        args, kwargs = mock_send_alert_email.call_args
        assert args[0] == email
        assert args[1] == "192.168.1.2"
        assert args[2] == "Test-Agent-A"
        assert isinstance(args[3], datetime)
        mock_send_alert_email.reset_mock() # Clear mock history for subsequent checks

    # Third login from same IP 2 and same UA (should not alert again)
    with patch("app.auth.routes.request") as mock_request:
        mock_request.remote_addr = "192.168.1.2"
        mock_request.headers.get.return_value = "Test-Agent-A"
        r = client.post("/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200
        mock_send_alert_email.assert_not_called()


@patch("app.utils.alerts.send_alert_email")
def test_auth_login_alerts_on_new_user_agent(mock_send_alert_email, client):
    """Test that an alert is sent when login occurs from a new User-Agent."""
    email = "newua@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})

    # First login from UA A (should not alert)
    from unittest.mock import patch
    from datetime import datetime
    with patch("app.auth.routes.request") as mock_request:
        mock_request.remote_addr = "192.168.2.1"
        mock_request.headers.get.return_value = "Test-Agent-A"
        r = client.post("/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200
        mock_send_alert_email.assert_not_called()

    # Second login from UA B (new UA, should alert)
    with patch("app.auth.routes.request") as mock_request:
        mock_request.remote_addr = "192.168.2.1"  # Same IP
        mock_request.headers.get.return_value = "Test-Agent-B"  # Different UA
        r = client.post("/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200
        mock_send_alert_email.assert_called_once()
        args, kwargs = mock_send_alert_email.call_args
        assert args[0] == email
        assert args[1] == "192.168.2.1"
        assert args[2] == "Test-Agent-B"
        assert isinstance(args[3], datetime)
        mock_send_alert_email.reset_mock()

    # Third login from same IP and same UA B (should not alert again)
    with patch("app.auth.routes.request") as mock_request:
        mock_request.remote_addr = "192.168.2.1"
        mock_request.headers.get.return_value = "Test-Agent-B"
        r = client.post("/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200
        mock_send_alert_email.assert_not_called()


@patch("app.utils.alerts.send_alert_email")
def test_auth_login_alerts_on_new_ip_and_user_agent(mock_send_alert_email, client):
    """Test that an alert is sent when login occurs from both a new IP and User-Agent."""
    email = "newipua@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})

    # First login from IP 1, UA A (should not alert)
    from unittest.mock import patch
    from datetime import datetime
    with patch("app.auth.routes.request") as mock_request:
        mock_request.remote_addr = "192.168.3.1"
        mock_request.headers.get.return_value = "Test-Agent-A"
        r = client.post("/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200
        mock_send_alert_email.assert_not_called()

    # Second login from IP 2, UA B (both new, should alert)
    with patch("app.auth.routes.request") as mock_request:
        mock_request.remote_addr = "192.168.3.2"  # Different IP
        mock_request.headers.get.return_value = "Test-Agent-B"  # Different UA
        r = client.post("/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200
        mock_send_alert_email.assert_called_once()
        args, kwargs = mock_send_alert_email.call_args
        assert args[0] == email
        assert args[1] == "192.168.3.2"
        assert args[2] == "Test-Agent-B"
        assert isinstance(args[3], datetime)
        mock_send_alert_email.reset_mock()

    # Third login from same IP 2 and same UA B (should not alert again)
    with patch("app.auth.routes.request") as mock_request:
        mock_request.remote_addr = "192.168.3.2"
        mock_request.headers.get.return_value = "Test-Agent-B"
        r = client.post("/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200
        mock_send_alert_email.assert_not_called()


def test_auth_logout_revokes_refresh_token(client):
    """Tests the logout functionality to ensure refresh tokens are revoked."""
    email = "logout@test.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)

    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    refresh_token = r.get_json()["refresh_token"]

    r = client.post(
        "/auth/logout", headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert r.status_code == 200

    r = client.post(
        "/auth/refresh", headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert r.status_code == 401


def test_auth_me_and_update_preferred_currency(client):
    email = "profile@test.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)

    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    access = r.get_json()["access_token"]
    auth = {"Authorization": f"Bearer {access}"}

    r = client.get("/auth/me", headers=auth)
    assert r.status_code == 200
    me = r.get_json()
    assert me["email"] == email
    assert me["preferred_currency"] == "INR"

    r = client.patch("/auth/me", json={"preferred_currency": "inr"}, headers=auth)
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["preferred_currency"] == "INR"

    r = client.patch("/auth/me", json={"preferred_currency": "ZZZ"}, headers=auth)
    assert r.status_code == 400
