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

---

## Project Structure

```
PAI/
├── baseapp/               # Core Django config
│   ├── settings.py
│   ├── asgi.py
│   ├── wsgi.py
│   ├── celery.py
│   └── routing.py
├── apps/
│   └── dashboard/         # Trading app
│       ├── models.py      # TradingPair, PriceTick, Trade, Wallet
│       ├── consumers.py   # WebSocket consumers
│       ├── tasks.py       # Celery tasks (price updates, trade resolution)
│       ├── signals.py     # Auto-create wallet on user creation
│       └── views.py
├── templates/
├── static/
├── staticfiles/           # Collected static (production)
├── gunicorn.conf.py
├── manage.py
├── requirements.txt
├── deploy.sh
└── .env                   # Never commit this
```

---

## Local Development Setup

### 1. Clone the repo

```bash
git clone git@github.com:yourusername/PAI.git
cd PAI
```

### 2. Create virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Create `.env` file

```env
SECRET_KEY=your-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

DB_NAME=otex_db
DB_USER=otex_user
DB_PASSWORD=yourpassword
DB_HOST=localhost
DB_PORT=5432

REDIS_URL=redis://127.0.0.1:6379/0

SECURE_SSL_REDIRECT=False
```

### 4. Setup PostgreSQL

```bash
sudo -u postgres psql
```

```sql
CREATE DATABASE otex_db;
CREATE USER otex_user WITH PASSWORD 'yourpassword';
GRANT ALL PRIVILEGES ON DATABASE otex_db TO otex_user;
GRANT ALL ON SCHEMA public TO otex_user;
ALTER DATABASE otex_db OWNER TO otex_user;
\q
```

### 5. Run migrations

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 6. Start Redis

```bash
sudo systemctl start redis
```

### 7. Start Celery worker and beat (separate terminals)

```bash
celery -A baseapp worker --loglevel=info
celery -A baseapp beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

### 8. Run the dev server

```bash
python manage.py runserver
```

---

## Production Setup

### Services (systemd)

| Service       | File                                      | Purpose               |
| ------------- | ----------------------------------------- | --------------------- |
| `otex`        | `/etc/systemd/system/otex.service`        | Gunicorn ASGI server  |
| `otex-celery` | `/etc/systemd/system/otex-celery.service` | Celery worker         |
| `otex-beat`   | `/etc/systemd/system/otex-beat.service`   | Celery beat scheduler |

### Start all services

```bash
sudo systemctl enable otex otex-celery otex-beat
sudo systemctl start otex otex-celery otex-beat
```

### Check status

```bash
sudo systemctl status otex otex-celery otex-beat
```

### View logs

```bash
# Gunicorn
tail -f /var/log/gunicorn/error.log

# Celery
sudo journalctl -u otex-celery -f

# Nginx
sudo tail -f /var/log/nginx/error.log
```

---

## Deploying Updates

```bash
./deploy.sh
```

Which runs:

```bash
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart otex otex-celery otex-beat
```

> **Never run `makemigrations` on the server.** Only run it locally and commit the migration files.

---

## Key Features

- **Real-time price feed** — prices update every second via WebSocket
- **Trade types** — Rise/Fall, Over/Under, Accumulator
- **Demo & Live accounts** — separate balances, switch anytime
- **Auto wallet creation** — wallet created via signal on user registration
- **Auto-generated username** — `CR-XXXXXX` format, no user input needed
- **Trade resolution** — Celery resolves trades with configurable house edge
- **WebSocket notifications** — trade results pushed to user on any page

---

## Environment Variables

| Variable              | Description                            |
| --------------------- | -------------------------------------- |
| `SECRET_KEY`          | Django secret key                      |
| `DEBUG`               | `True` for dev, `False` for production |
| `ALLOWED_HOSTS`       | Comma-separated list of allowed hosts  |
| `DB_NAME`             | PostgreSQL database name               |
| `DB_USER`             | PostgreSQL user                        |
| `DB_PASSWORD`         | PostgreSQL password                    |
| `DB_HOST`             | Database host (usually `localhost`)    |
| `DB_PORT`             | Database port (usually `5432`)         |
| `REDIS_URL`           | Redis connection URL                   |
| `SECURE_SSL_REDIRECT` | `True` in production, `False` in dev   |

---

## Firewall (UFW)

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

---

## House Edge Configuration

Trades are resolved in `apps/dashboard/tasks.py`. The house edge is controlled per trading pair via `house_settings.favourability`:

| Value | Effect                       |
| ----- | ---------------------------- |
| 0     | Pure market result           |
| 10–20 | Slight house edge            |
| 30–40 | Standard binary options edge |
| 50+   | Too aggressive               |

---

## License

Private — All rights reserved.
