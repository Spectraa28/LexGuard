import json
import pika
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from processor import process_PARSED, process_embedding


engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def message_callback(ch, method, properties, body):
    """
    Main orchestrator callback. Parses incoming messages, dispatches them 
    through the pipeline checkpoints, and issues protocol ACKs/NACKs.
    """
    session = SessionLocal()
    try:
        # Deserialize payload
        payload = json.loads(body.decode('utf-8'))
        document_id = payload.get("documentId")
        
        if not document_id:
            print("[Worker] Invalid payload: Missing 'document_id'. Rejecting message.")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return

        print(f"[Worker] Received processing request for Document: {document_id}")

        #  PARSED
        parse_signal = process_PARSED(session, document_id)
        
        if parse_signal == "NACK":
            print(f"[Worker] Transient error in PARSED for {document_id}. Requeueing.")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            return
        elif parse_signal == "FAILED":
            print(f"[Worker] Terminal error in PARSED for {document_id}. Rejecting.")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return
        elif parse_signal in ["SKIP_CLAIMED", "SKIP_STATE"]:
            print(f"[Worker] Checkpoint skip signal ({parse_signal}) for {document_id}. Acknowledging.")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        #  Embedding 
        embed_signal = process_embedding(session, document_id)
        
        if embed_signal == "FAILED":
            print(f"[Worker] Terminal error in embedding for {document_id}. Rejecting.")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return
        elif embed_signal == "SKIP_STATE":
            print(f"[Worker] Document {document_id} already processed or skipped. Acknowledging.")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        print(f"[Worker] Document {document_id} successfully parsed and embedded.")
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except json.JSONDecodeError:
        print("[Worker] Failed to decode message JSON. Rejecting bad payload.")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        
    except Exception as e:
        print(f"[Worker] Unhandled critical exception during orchestration: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        
    finally:
        session.close()


def main():
    credentials = pika.PlainCredentials(settings.RABBITMQ_USER, settings.RABBITMQ_PASS)
    parameters = pika.ConnectionParameters(
        host=settings.RABBITMQ_HOST,
        port=settings.RABBITMQ_PORT,
        credentials=credentials,
        heartbeat=600  # 10-minute heartbeat to survive heavy CPU-bound PARSED
    )
    
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    channel.queue_declare(queue=settings.RABBITMQ_QUEUE, durable=True)
    channel.basic_qos(prefetch_count=1)

    print(f"[*] Embedding Worker successfully started. Listening on queue: '{settings.RABBITMQ_QUEUE}'")
    
    channel.basic_consume(
        queue=settings.RABBITMQ_QUEUE,
        on_message_callback=message_callback
    )

    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        print("\n[*] Stopping worker gracefully...")
        channel.stop_consuming()
    finally:
        connection.close()


if __name__ == "__main__":
    main()