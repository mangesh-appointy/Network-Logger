# Network Logger - Deployment Guide

## Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
playwright install chromium
```

2. Run the application:
```bash
python3 app.py
```

3. Open your browser and navigate to:
```
http://localhost:5000
```

## Deployment Options

### Option 1: Heroku

1. Install Heroku CLI and login:
```bash
heroku login
```

2. Create a new Heroku app:
```bash
heroku create your-app-name
```

3. Add Playwright buildpack:
```bash
heroku buildpacks:add --index 1 heroku/python
heroku buildpacks:add --index 2 https://github.com/mxschmitt/heroku-playwright-buildpack.git
```

4. Deploy:
```bash
git init
git add .
git commit -m "Initial commit"
git push heroku main
```

### Option 2: Render

1. Create a new Web Service on Render.com
2. Connect your GitHub repository
3. Set build command: `pip install -r requirements.txt && playwright install chromium`
4. Set start command: `gunicorn --worker-class eventlet -w 1 app:app`
5. Deploy

### Option 3: Railway

1. Create a new project on Railway.app
2. Connect your GitHub repository
3. Railway will auto-detect the Python app
4. Add this to railway.json (create if needed):
```json
{
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "playwright install chromium && gunicorn --worker-class eventlet -w 1 app:app",
    "restartPolicyType": "ON_FAILURE"
  }
}
```

### Option 4: DigitalOcean App Platform

1. Create a new app on DigitalOcean
2. Connect your GitHub repository
3. Set run command: `gunicorn --worker-class eventlet -w 1 app:app`
4. Add build command: `pip install -r requirements.txt && playwright install chromium`

### Option 5: Docker (for any platform)

Create a Dockerfile:
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium
RUN playwright install-deps

COPY . .

EXPOSE 5000

CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "--bind", "0.0.0.0:5000", "app:app"]
```

Build and run:
```bash
docker build -t network-logger .
docker run -p 5000:5000 network-logger
```

## Environment Variables

Set these if needed:
- `PORT`: Port number (default: 5000)
- `SECRET_KEY`: Flask secret key for sessions

## Usage

1. Enter a URL in the input field
2. Click "Start" to begin logging
3. The browser will run and capture all network requests
4. Click "Stop" when done
5. Click "Export CSV" to download the logs
6. Click "Clear" to reset all logs

## Features

- Real-time network request monitoring
- WebSocket-based live updates
- Duration and size tracking for each request
- CSV export functionality
- Beautiful, responsive UI
- Support for fetch/XHR/script requests

## Notes

- Headless mode is enabled by default for deployment
- The logger runs for 60 seconds by default (adjustable in app.py)
- All timestamps are in ISO format
- Request/response headers are stored as JSON strings
