import json
import pytest
from unittest.mock import MagicMock
from app.frontend.app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def test_healthz_endpoint(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json() == {"status": "healthy"}


def test_query_success(client, mocker):
    mock_conn = MagicMock()
    mock_channel = MagicMock()
    mock_conn.channel.return_value = mock_channel
    mocker.patch("app.frontend.app.get_rabbitmq_connection", return_value=mock_conn)

    response = client.post("/query", data={"city": "Tel Aviv"})

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "queued"
    assert data["city"] == "Tel Aviv"

    # אימות שליחת הודעה תקינה ל-RabbitMQ
    mock_channel.queue_declare.assert_called_once_with(queue="weather_queries", durable=True)
    mock_channel.basic_publish.assert_called_once()
    mock_conn.close.assert_called_once()


def test_query_missing_city(client):
    response = client.post("/query", data={"city": "   "})
    assert response.status_code == 400
    assert "City name is required" in response.get_json()["error"]


def test_query_rabbitmq_failure(client, mocker):
    mocker.patch("app.frontend.app.get_rabbitmq_connection", side_effect=Exception("AMQP Connection Refused"))

    response = client.post("/query", data={"city": "Haifa"})
    assert response.status_code == 500
    data = response.get_json()
    assert data["error"] == "Failed to publish job"
    assert "AMQP Connection Refused" in data["details"]
