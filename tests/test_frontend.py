import json
import pytest
from unittest.mock import MagicMock
from app.frontend import app as frontend
from app.frontend.app import app


WEATHER = {"city": "Tel Aviv", "country": "Israel", "temperature_c": 24.1}


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
    mock_request = mocker.patch(
        "app.frontend.app.request_weather", return_value={"status": "done", "weather": WEATHER}
    )

    response = client.post("/query", data={"city": "  Tel Aviv "})

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "done"
    assert data["city"] == "Tel Aviv"
    assert data["weather"] == WEATHER
    mock_request.assert_called_once_with("Tel Aviv")


def test_query_missing_city(client):
    response = client.post("/query", data={"city": "   "})
    assert response.status_code == 400
    assert "City name is required" in response.get_json()["error"]


def test_query_city_not_found(client, mocker):
    mocker.patch(
        "app.frontend.app.request_weather",
        return_value={"status": "error", "error": "City 'Atlantis' not found"},
    )

    response = client.post("/query", data={"city": "Atlantis"})
    assert response.status_code == 404
    assert "not found" in response.get_json()["error"]


def test_query_worker_timeout(client, mocker):
    mocker.patch("app.frontend.app.request_weather", return_value=None)

    response = client.post("/query", data={"city": "Haifa"})
    assert response.status_code == 504
    assert "Timed out" in response.get_json()["error"]


def test_query_rabbitmq_failure(client, mocker):
    mocker.patch("app.frontend.app.get_rabbitmq_connection", side_effect=Exception("AMQP Connection Refused"))

    response = client.post("/query", data={"city": "Haifa"})
    assert response.status_code == 500
    data = response.get_json()
    assert data["error"] == "Failed to publish job"
    assert "AMQP Connection Refused" in data["details"]


def _fake_connection(reply_body):
    """A connection whose channel delivers reply_body to the reply consumer on publish."""
    mock_conn = MagicMock()
    mock_channel = MagicMock()
    mock_conn.channel.return_value = mock_channel
    consumers = {}

    def basic_consume(queue, on_message_callback, auto_ack):
        consumers[queue] = on_message_callback

    def basic_publish(exchange, routing_key, body, properties):
        if reply_body is not None:
            reply_props = MagicMock(correlation_id=properties.correlation_id)
            consumers[properties.reply_to](mock_channel, MagicMock(), reply_props, json.dumps(reply_body))

    mock_channel.basic_consume.side_effect = basic_consume
    mock_channel.basic_publish.side_effect = basic_publish
    return mock_conn, mock_channel


def test_request_weather_returns_worker_reply(mocker):
    reply = {"status": "done", "weather": WEATHER}
    mock_conn, mock_channel = _fake_connection(reply)
    mocker.patch("app.frontend.app.get_rabbitmq_connection", return_value=mock_conn)

    assert frontend.request_weather("Tel Aviv", timeout=1) == reply

    mock_channel.queue_declare.assert_called_once_with(queue="weather_queries", durable=True)
    _, kwargs = mock_channel.basic_publish.call_args
    assert kwargs["routing_key"] == "weather_queries"
    assert json.loads(kwargs["body"]) == {"city": "Tel Aviv"}
    assert kwargs["properties"].reply_to == "amq.rabbitmq.reply-to"
    mock_conn.close.assert_called_once()


def test_request_weather_times_out(mocker):
    mock_conn, _ = _fake_connection(None)
    mocker.patch("app.frontend.app.get_rabbitmq_connection", return_value=mock_conn)

    assert frontend.request_weather("Haifa", timeout=0.1) is None
    mock_conn.close.assert_called_once()
