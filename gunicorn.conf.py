# gunicorn.conf.py — Production WSGI server configuration
# Usage: gunicorn -c gunicorn.conf.py wsgi:app

import os
import multiprocessing

# Bind
bind = f"127.0.0.1:{os.getenv('PORT', '5000')}"

# Workers: 1 sync worker is correct for APScheduler (avoid duplicate scheduler instances)
# Use 1 worker + threads for concurrency without multiple scheduler instances
workers = 1
threads = 4
worker_class = "sync"

# Timeouts
timeout = 120          # request timeout (seconds)
keepalive = 5          # keep-alive connections
graceful_timeout = 30  # graceful shutdown window

# Logging
accesslog = "logs/access.log"
errorlog  = "logs/error.log"
loglevel  = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" %(D)sµs'

# Process naming
proc_name = "sukoon_pms"

# Reload on code change (development only — set via env)
reload = os.getenv("FLASK_ENV") == "development"

# Preload app to catch startup errors early
preload_app = True

def on_starting(server):
    import logging
    logging.getLogger("gunicorn.error").info("FinalGrid starting...")

def post_fork(server, worker):
    # Ensure logs directory exists in each worker
    import os
    os.makedirs("logs", exist_ok=True)
