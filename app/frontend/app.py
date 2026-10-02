import json
import os
import pika
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", 5672))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "guest")
QUEUE_NAME = "weather_queries"


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
    </style>
</head>
<body>
    <div class="card">
        <h2>SkyWatch Weather Query</h2>
        <form action="/query" method="post">
            <input type="text" name="city" placeholder="Enter city name..." required />
            <button type="submit">Send Query</button>
        </form>
    </div>
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

    payload = json.dumps({"city": city})

    try:
        connection = get_rabbitmq_connection()
        channel = connection.channel()
        channel.queue_declare(queue=QUEUE_NAME, durable=True)
        channel.basic_publish(
            exchange="",
            routing_key=QUEUE_NAME,
            body=payload,
            properties=pika.BasicProperties(delivery_mode=2),
        )
        connection.close()
        return jsonify({"status": "queued", "city": city, "message": "Query sent to RabbitMQ"}), 200
    except Exception as exc:
        return jsonify({"error": "Failed to publish job", "details": str(exc)}), 500


@app.route("/healthz", methods=["GET"])
def health():
    return jsonify({"status": "healthy"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
