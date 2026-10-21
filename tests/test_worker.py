import json
from unittest.mock import MagicMock
import pytest
import requests
from app.worker import worker


GEO_RESPONSE = {"results": [{"name": "Tel Aviv", "country": "Israel", "latitude": 32.08, "longitude": 34.78}]}
FORECAST_RESPONSE = {
    "current": {
        "time": "2026-10-21T12:00",
        "temperature_2m": 24.1,
        "relative_humidity_2m": 60,
        "wind_speed_10m": 12.5,
        "weather_code": 1,
    }
}


def _http_response(payload):
    response = MagicMock()
    response.json.return_value = payload
    return response


def test_fetch_weather(mocker):
    mock_get = mocker.patch(
        "app.worker.worker.requests.get",
        side_effect=[_http_response(GEO_RESPONSE), _http_response(FORECAST_RESPONSE)],
    )

    weather = worker.fetch_weather("Tel Aviv")

    assert weather["city"] == "Tel Aviv"
    assert weather["country"] == "Israel"
    assert weather["temperature_c"] == 24.1
    assert weather["wind_speed_kmh"] == 12.5
    forecast_params = mock_get.call_args_list[1].kwargs["params"]
    assert forecast_params["latitude"] == 32.08
    assert forecast_params["longitude"] == 34.78


def test_fetch_weather_city_not_found(mocker):
    mocker.patch("app.worker.worker.requests.get", return_value=_http_response({}))

    with pytest.raises(worker.CityNotFound):
        worker.fetch_weather("Atlantis")


def test_handle_query_api_failure(mocker):
    mocker.patch("app.worker.worker.requests.get", side_effect=requests.ConnectionError("down"))

    result = worker.handle_query("Haifa")
    assert result["status"] == "error"
    assert "Weather API request failed" in result["error"]


def test_callback_replies_and_acks(mocker):
    mocker.patch("app.worker.worker.handle_query", return_value={"status": "done", "weather": {"city": "Haifa"}})
    channel = MagicMock()
    method = MagicMock(delivery_tag=7)
    properties = MagicMock(reply_to="amq.rabbitmq.reply-to.abc", correlation_id="123")

    worker.callback(channel, method, properties, json.dumps({"city": "Haifa"}).encode())

    _, kwargs = channel.basic_publish.call_args
    assert kwargs["routing_key"] == "amq.rabbitmq.reply-to.abc"
    assert kwargs["properties"].correlation_id == "123"
    assert json.loads(kwargs["body"])["weather"]["city"] == "Haifa"
    channel.basic_ack.assert_called_once_with(delivery_tag=7)


def test_callback_bad_message_is_nacked():
    channel = MagicMock()
    method = MagicMock(delivery_tag=9)

    worker.callback(channel, method, MagicMock(), b"not json")

    channel.basic_nack.assert_called_once_with(delivery_tag=9, requeue=False)
    channel.basic_publish.assert_not_called()
