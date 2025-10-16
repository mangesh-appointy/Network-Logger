# Network Logger

A Python tool that captures fetch/XHR network calls from your web application and exports them to CSV format.

## Features

- Captures all fetch/XHR network requests in real-time
- Records request/response details (URL, method, headers, status, etc.)
- Exports logs to CSV format
- Interactive browser session - perform actions manually
- Progressive logging - captures calls as they happen

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Install Playwright browsers:
```bash
playwright install chromium
```

## Usage

### Basic Usage

Run the script:
```bash
python network_logger.py
```

The script will:
1. Prompt you for your application URL
2. Open a browser window
3. Start logging all fetch/XHR requests
4. Wait for you to perform your actions (login, navigation, etc.)
5. When you close the browser, it exports logs to CSV

### Programmatic Usage

You can also use the NetworkLogger class in your own scripts:

```python
import asyncio
from network_logger import NetworkLogger

async def custom_logging():
    logger = NetworkLogger()

    # Start logging
    await logger.start_logging("https://your-app.com/login", headless=False)

    # Export to CSV
    logger.export_to_csv("my_network_log.csv")

    # Clear logs if needed
    logger.clear_logs()

asyncio.run(custom_logging())
```

## Workflow

1. **Start the logger**: Run `python network_logger.py`
2. **Enter your application URL**: When prompted, enter your login page URL
3. **Browser opens**: A Chromium browser window opens
4. **Perform your actions**:
   - Login to your application
   - Navigate through pages
   - Perform any actions that trigger network calls
5. **Stop logging**: Close the browser window when done
6. **CSV is generated**: File `network_log_TIMESTAMP.csv` is created

## CSV Output Format

The exported CSV contains the following columns:

| Column | Description |
|--------|-------------|
| timestamp | ISO format timestamp of the request |
| method | HTTP method (GET, POST, PUT, etc.) |
| url | Full request URL |
| resource_type | Type of resource (fetch, xhr) |
| status | HTTP status code |
| status_text | HTTP status text |
| request_headers | JSON string of request headers |
| response_headers | JSON string of response headers |
| post_data | POST request body (if applicable) |

## Example Output

```csv
timestamp,method,url,resource_type,status,status_text,request_headers,response_headers,post_data
2025-10-15T10:30:45.123,GET,https://api.example.com/users,fetch,200,OK,"{""accept"":""application/json""}","{""content-type"":""application/json""}",
2025-10-15T10:30:46.456,POST,https://api.example.com/login,fetch,201,Created,"{""content-type"":""application/json""}","{""content-type"":""application/json""}","{""username"":""user"",""password"":""***""}"
```

## Advanced Options

### Headless Mode

Run without showing the browser (useful for automation):

```python
await logger.start_logging("https://example.com", headless=True)
```

Note: In headless mode, you'll need to automate the interactions using Playwright's page API.

### Custom CSV Filename

```python
logger.export_to_csv("custom_name.csv")
```

## Troubleshooting

**Browser doesn't open**:
- Make sure you ran `playwright install chromium`

**No requests captured**:
- The logger only captures fetch/XHR requests, not regular page loads or static resources
- Check that your application actually makes fetch/XHR calls

**Permission errors**:
- Make sure you have write permissions in the current directory

## Notes

- Only fetch and XHR requests are logged (not images, CSS, scripts, etc.)
- Logs are stored in memory until exported
- Closing the browser triggers the CSV export
