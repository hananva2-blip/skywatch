import json
import logging
import os
import time
import pika

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", 5672))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "guest")
QUEUE_NAME = "weather_queries"


def callback(ch, method, properties, body):
    try:
        data = json.loads(body.decode("utf-8"))
        city = data.get("city", "Unknown")
        logging.info("Processing weather query for city: %s", city)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as exc:
        logging.error("Failed to process message: %s", exc)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def main():
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        credentials=credentials,
        heartbeat=600,
        blocked_connection_timeout=300,
    )

    while True:
        try:
            logging.info("Connecting to RabbitMQ at %s:%s...", RABBITMQ_HOST, RABBITMQ_PORT)
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            channel.queue_declare(queue=QUEUE_NAME, durable=True)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback)

            logging.info("Worker is waiting for messages in '%s'...", QUEUE_NAME)
            channel.start_consuming()
        except pika.exceptions.AMQPConnectionError as err:
            logging.warning("RabbitMQ connection error: %s. Retrying in 5s...", err)
            time.sleep(5)
        except Exception as err:
            logging.error("Unexpected worker error: %s. Retrying in 5s...", err)
            time.sleep(5)


if __name__ == "__main__":
    main()
