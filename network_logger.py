"""
Network Logger - Captures fetch/XHR/JS network calls and exports to CSV

This script uses Playwright to monitor network activity in a browser session,
capturing all fetch/XHR/script requests and responses, then exports them to CSV format.
"""

import asyncio
import json
import csv
import time
from datetime import datetime
from typing import List, Dict
from playwright.async_api import async_playwright, Request, Response  # type: ignore


class NetworkLogger:
    def __init__(self):
        self.requests: List[Dict] = []
        self.is_logging = False
        self.request_start_times: Dict[str, float] = {}  # Track request start times

    def _extract_request_data(self, request: Request, response: Response = None, duration: float = 0, size: int = 0) -> Dict:
        """Extract relevant data from request and response"""
        timestamp = datetime.now().isoformat()

        # Get request headers
        headers = request.headers

        # Get response data if available
        status = response.status if response else None
        status_text = response.status_text if response else None
        response_headers = response.headers if response else {}

        # Calculate timing
        timing = request.timing if hasattr(request, 'timing') else {}

        data = {
            'timestamp': timestamp,
            'method': request.method,
            'url': request.url,
            'resource_type': request.resource_type,
            'status': status,
            'status_text': status_text,
            'duration': duration,
            'size': size,
            'request_headers': json.dumps(headers),
            'response_headers': json.dumps(response_headers),
            'post_data': request.post_data if request.post_data else '',
        }

        return data

    async def start_logging(self, url: str, headless: bool = False):
        """
        Start browser session and begin logging network activity

        Args:
            url: The URL to navigate to (e.g., your login page)
            headless: Whether to run browser in headless mode
        """
        self.is_logging = True

        async with async_playwright() as p:
            # Launch browser
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context()
            page = await context.new_page()

            # Set up network listeners
            async def handle_request(request: Request):
                if self.is_logging:
                    # Capture fetch/XHR/script requests
                    if request.resource_type in ['fetch', 'xhr', 'script']:
                        self.request_start_times[request.url] = time.time()
                        print(f"[REQUEST] {request.resource_type.upper()} {request.method} {request.url}")

            async def handle_response(response: Response):
                if self.is_logging:
                    request = response.request
                    # Capture fetch/XHR/script requests
                    if request.resource_type in ['fetch', 'xhr', 'script']:
                        # Calculate duration
                        duration = 0
                        if request.url in self.request_start_times:
                            duration = time.time() - self.request_start_times[request.url]
                            del self.request_start_times[request.url]

                        # Get response size
                        size = 0
                        try:
                            body = await response.body()
                            size = len(body)
                        except Exception:
                            pass

                        data = self._extract_request_data(request, response, duration, size)
                        self.requests.append(data)
                        print(f"{duration:.6f}, {size}")

            # Attach listeners
            page.on('request', handle_request)
            page.on('response', handle_response)

            # Navigate to the URL
            await page.goto(url)

            print(f"\n{'='*60}")
            print("Network Logger Started")
            print(f"{'='*60}")
            print("Browser is now open. Perform your actions.")
            print("\nTo stop logging and export to CSV:")
            print("  - Close the browser window")
            print(f"{'='*60}\n")

            # Wait for the page to close (user closes browser)
            await page.wait_for_event('close', timeout=0)

            await browser.close()

        self.is_logging = False
        print(f"\nLogging stopped. Captured {len(self.requests)} requests.")

    def export_to_csv(self, filename: str = None):
        """
        Export captured network logs to CSV file

        Args:
            filename: Output CSV filename (default: network_log_TIMESTAMP.csv)
        """
        if not self.requests:
            print("No requests to export.")
            return

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"network_log_{timestamp}.csv"

        # Ensure .csv extension
        if not filename.endswith('.csv'):
            filename += '.csv'

        # Write to CSV
        fieldnames = [
            'timestamp', 'method', 'url', 'resource_type',
            'status', 'status_text', 'duration', 'size',
            'request_headers', 'response_headers', 'post_data'
        ]

        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.requests)

        print(f"\nExported {len(self.requests)} requests to: {filename}")
        return filename

    def clear_logs(self):
        """Clear all captured requests"""
        self.requests.clear()
        print("Logs cleared.")


async def main():
    """Example usage"""
    # Create logger instance
    logger = NetworkLogger()

    # Start logging - replace with your application URL
    url = input("Enter your application URL (e.g., https://example.com/login): ").strip()

    if not url:
        url = "https://example.com"  # Default

    # Start browser and logging (headless=False to see the browser)
    try:
        await logger.start_logging(url, headless=False)
    except Exception as e:
        print(f"Error during logging: {e}")

    # Export to CSV
    logger.export_to_csv()


if __name__ == "__main__":
    asyncio.run(main())
