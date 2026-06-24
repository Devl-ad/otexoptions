# OTEX — Options Trading Platform

A real-time binary options trading platform built with Django, Channels, Celery, and PostgreSQL.

---

## Tech Stack

| Layer          | Technology                   |
| -------------- | ---------------------------- |
| Backend        | Django 4.x + Django Channels |
| ASGI Server    | Gunicorn + Uvicorn workers   |
| WebSockets     | Django Channels + Redis      |
| Task Queue     | Celery + Celery Beat         |
| Database       | PostgreSQL                   |
| Cache / Broker | Redis                        |
| Reverse Proxy  | Nginx                        |
| SSL            | Let's Encrypt (Certbot)      |

## License

Private — All rights reserved.
