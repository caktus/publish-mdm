# Gunicorn configuration file
# https://docs.gunicorn.org/en/stable/configure.html#configuration-file
# https://docs.gunicorn.org/en/stable/settings.html
import multiprocessing

max_requests = 1000
max_requests_jitter = 50

log_file = "-"
accesslog = "-"

workers = multiprocessing.cpu_count() * 2 + 1
