import os
import json
import pika
import redis
from database import SessionLocal, LogTable
from sqlalchemy import text

redis_client = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=6379, decode_responses=True)

def callback(ch, method, properties, body):
    message = json.loads(body)
    group = message.get("group")
    action = message.get("action")
    print(f" [x] Log alındı: Group={group}, Action={action}")
    
    # Log'u veritabanına da yazalım (isteğe bağlı)
    db = SessionLocal()
    try:
        # Örnek: log_table'ye direkt ekle (trigger kullanmadan)
        db.execute(text("INSERT INTO log_table (table_name, operation, new_data) VALUES (:tbl, :op, :data)"),
                   {"tbl": "rabbitmq_log", "op": action, "data": json.dumps({"group": group})})
        db.commit()
    except Exception as e:
        print("DB log hatası:", e)
    finally:
        db.close()
    
    # RPC: mesajın işlendiğini bildir
    if properties.reply_to:
        response = {"status": "logged", "group": group, "action": action}
        ch.basic_publish(exchange='',
                         routing_key=properties.reply_to,
                         properties=pika.BasicProperties(correlation_id=properties.correlation_id),
                         body=json.dumps(response))
    ch.basic_ack(delivery_tag=method.delivery_tag)

def main():
    rabbitmq_host = os.getenv("RABBITMQ_HOST", "localhost")
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=rabbitmq_host))
    channel = connection.channel()
    channel.queue_declare(queue='task_logs', durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue='task_logs', on_message_callback=callback)
    print(' [*] Worker başladı, logları bekliyor. Çıkmak için CTRL+C')
    channel.start_consuming()

if __name__ == "__main__":
    main()