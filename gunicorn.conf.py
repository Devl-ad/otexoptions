import multiprocessing

bind = "127.0.0.1:8000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"  # ASGI worker — handles WebSockets
timeout = 120
keepalive = 5
max_requests = 1000
max_requests_jitter = 100  # prevents all workers restarting at the same time
accesslog = "/var/log/gunicorn/access.log"
errorlog = "/var/log/gunicorn/error.log"
loglevel = "info"
