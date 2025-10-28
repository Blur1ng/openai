import sys


sys.path.insert(0, '/app') 

import redis
from rq import Worker, Queue

redis_conn = redis.Redis(host='redis', port=6379)
queues = [Queue('to_aimodel', connection=redis_conn)]

worker = Worker(queues, connection=redis_conn)
worker.work()