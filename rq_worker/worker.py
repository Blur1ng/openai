import redis
from rq import Worker, Queue

redis_conn = redis.Redis(host='redis', port=6379)
queues = [Queue('to_aimodel', connection=redis_conn)]

if __name__ == "__main__":
    worker = Worker(queues, connection=redis_conn)
    print("Воркер запущен...")
    worker.work()