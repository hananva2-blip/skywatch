import json
import os
import time
import uuid
import pika
from flask import Flask, jsonify, render_template_string, request
from prometheus_flask_exporter import PrometheusMetrics


app = Flask(__name__)
metrics = PrometheusMetrics(app)


RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", 5672))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "guest")
QUEUE_NAME = "weather_queries"
REPLY_QUEUE = "amq.rabbitmq.reply-to"  # RabbitMQ direct reply-to pseudo-queue
RESULT_TIMEOUT = float(os.getenv("RESULT_TIMEOUT", 15))


def get_rabbitmq_connection():
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        credentials=credentials,
        connection_attempts=3,
        retry_delay=2,
    )
    return pika.BlockingConnection(parameters)


def request_weather(city, timeout=RESULT_TIMEOUT):
    """Publish a job and wait for the worker's reply. Returns None on timeout."""
    connection = get_rabbitmq_connection()
    try:
        channel = connection.channel()
        channel.queue_declare(queue=QUEUE_NAME, durable=True)

        correlation_id = str(uuid.uuid4())
        reply = {}

        def on_reply(ch, method, properties, body):
            if properties.correlation_id == correlation_id:
                reply["body"] = json.loads(body)

        # Must consume from the reply-to queue before publishing
        channel.basic_consume(queue=REPLY_QUEUE, on_message_callback=on_reply, auto_ack=True)
        channel.basic_publish(
            exchange="",
            routing_key=QUEUE_NAME,
            body=json.dumps({"city": city}),
            properties=pika.BasicProperties(
                delivery_mode=2,
                reply_to=REPLY_QUEUE,
                correlation_id=correlation_id,
            ),
        )

        deadline = time.monotonic() + timeout
        while "body" not in reply and time.monotonic() < deadline:
            connection.process_data_events(time_limit=0.5)
        return reply.get("body")
    finally:
        connection.close()


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>SkyWatch Weather</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background-color: #f4f4f9; }
        .card { background: white; padding: 20px; border-radius: 8px; max-width: 400px; }
        input[type="text"] { width: 90%; padding: 10px; margin-bottom: 10px; }
        button { padding: 10px 15px; background: #007bff; color: white; border: none; border-radius: 4px; }
        #result { margin-top: 15px; }
        .error { color: #c0392b; }
    </style>
</head>
<body>
    <div class="card">
        <h2>SkyWatch Weather Query</h2>
        <form id="query-form" action="/query" method="post">
            <input type="text" name="city" placeholder="Enter city name..." required />
            <button type="submit">Send Query</button>
        </form>
        <div id="result"></div>
    </div>
    <script>
        const form = document.getElementById("query-form");
        const result = document.getElementById("result");
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            result.textContent = "Waiting for a worker...";
            const response = await fetch("/query", { method: "POST", body: new FormData(form) });
            const data = await response.json();
            if (!response.ok) {
                result.innerHTML = "";
                const p = document.createElement("p");
                p.className = "error";
                p.textContent = data.error;
                result.appendChild(p);
                return;
            }
            const w = data.weather;
            result.innerHTML = "";
            [
                `${w.city}, ${w.country}`,
                `Temperature: ${w.temperature_c} °C`,
                `Humidity: ${w.humidity_pct}%`,
                `Wind: ${w.wind_speed_kmh} km/h`,
            ].forEach((line) => {
                const p = document.createElement("p");
                p.textContent = line;
                result.appendChild(p);
            });
        });
    </script>
</body>
</html>
"""


@app.route("/", methods=["GET"])
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/query", methods=["POST"])
def query_weather():
    city = request.form.get("city", "").strip()
    if not city:
        return jsonify({"error": "City name is required"}), 400

    try:
        reply = request_weather(city)
    except Exception as exc:
        return jsonify({"error": "Failed to publish job", "details": str(exc)}), 500

    if reply is None:
        return jsonify({"error": "Timed out waiting for a worker", "city": city}), 504
    if reply.get("status") == "error":
        return jsonify({"error": reply["error"], "city": city}), 404
    return jsonify({"status": "done", "city": city, "weather": reply["weather"]}), 200


@app.route("/healthz", methods=["GET"])
def health():
    return jsonify({"status": "healthy"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
