"""
Network Logger Web Application
A Flask-based web UI for the network logger
"""

from flask import Flask, render_template, jsonify, send_file, request
from flask_socketio import SocketIO, emit
import asyncio
import json
import csv
import time
import re
import os
import glob
from datetime import datetime
from typing import List, Dict
from playwright.async_api import async_playwright, Request, Response
import threading

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

class NetworkLoggerWeb:
    def __init__(self):
        self.requests: List[Dict] = []
        self.web_vitals: List[Dict] = []  # Store Web Vitals metrics
        self.is_logging = False
        self.request_start_times: Dict[str, float] = {}
        self.browser = None
        self.page = None
        self.playwright = None
        self.context = None
        self.is_running = False  # Track if a session is already running

    def _extract_request_data(self, request: Request, response: Response = None, duration: float = 0, size: int = 0) -> Dict:
        """Extract relevant data from request and response"""
        timestamp = datetime.now().isoformat()

        headers = request.headers
        status = response.status if response else None
        status_text = response.status_text if response else None
        response_headers = response.headers if response else {}

        # Extract GraphQL operation name and query ID
        graphql_operation = ''
        graphql_query_id = ''

        # Check if this looks like a GraphQL request
        if 'graphql' in request.url.lower() or request.resource_type in ['fetch', 'xhr']:
            # Try to parse GraphQL operation from POST data
            if request.post_data:
                try:
                    post_json = json.loads(request.post_data)

                    # Extract query ID from 'id' field (persisted queries)
                    graphql_query_id = post_json.get('id') or post_json.get('queryId') or post_json.get('query_id') or ''

                    # Extract operation name
                    # Priority 1: Use the id field if available
                    graphql_operation = graphql_query_id

                    # Priority 2: If no id, extract operation name from query string
                    if not graphql_operation and 'query' in post_json:
                        query_string = post_json.get('query', '')
                        # Match pattern: query/mutation/subscription OperationName
                        match = re.search(r'(?:query|mutation|subscription)\s+(\w+)', query_string)
                        if match:
                            graphql_operation = match.group(1)

                except (json.JSONDecodeError, AttributeError):
                    pass

        data = {
            'timestamp': timestamp,
            'method': request.method,
            'url': request.url,
            'resource_type': request.resource_type,
            'status': status,
            'status_text': status_text,
            'duration': duration,
            'size': size,
            'graphql_query_id': graphql_query_id,
            'graphql_operation': graphql_operation,
            'request_headers': json.dumps(headers),
            'response_headers': json.dumps(response_headers),
            'post_data': request.post_data if request.post_data else '',
        }

        return data

    async def start_logging(self):
        """Start browser session and begin logging network activity"""
        if self.is_running:
            socketio.emit('status', {'message': 'Error: A logging session is already running!'})
            return

        self.is_running = True
        self.is_logging = True

        try:
            # Start playwright - keep it alive
            socketio.emit('status', {'message': 'Starting Playwright...'})
            self.playwright = await async_playwright().start()

            socketio.emit('status', {'message': 'Launching browser...'})
            self.browser = await self.playwright.chromium.launch(
                headless=False,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-first-run',
                    '--no-default-browser-check',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-renderer-backgrounding'
                ]
            )
            self.context = await self.browser.new_context()
            self.page = await self.context.new_page()

            # Give browser time to stabilize
            await asyncio.sleep(1)

            # Expose function to receive Web Vitals from the browser
            async def log_web_vital(metric):
                """Receive Web Vitals metrics from browser JavaScript"""
                try:
                    vital_data = {
                        'timestamp': datetime.now().isoformat(),
                        'url': self.page.url,
                        'metric_name': metric.get('name'),
                        'value': round(metric.get('value', 0), 2),
                        'rating': metric.get('rating', 'unknown')
                    }
                    self.web_vitals.append(vital_data)

                    # Emit to web UI
                    socketio.emit('web_vital', {
                        'name': metric.get('name'),
                        'value': round(metric.get('value', 0), 2),
                        'rating': metric.get('rating', 'unknown'),
                        'url': self.page.url
                    })
                    print(f"Web Vital captured: {metric.get('name')} = {metric.get('value')}")
                except Exception as e:
                    print(f"Error logging web vital: {e}")

            await self.page.expose_function('logWebVital', log_web_vital)

            # Inject Web Vitals collection script into every page
            await self.page.add_init_script("""
                // Web Vitals measurement script
                (function() {
                    function sendMetric(metric) {
                        if (window.logWebVital) {
                            window.logWebVital({
                                name: metric.name,
                                value: metric.value,
                                rating: metric.rating || 'unknown'
                            });
                        }
                    }

                    // LCP - Largest Contentful Paint
                    new PerformanceObserver((list) => {
                        const entries = list.getEntries();
                        const lastEntry = entries[entries.length - 1];
                        const rating = lastEntry.renderTime < 2500 ? 'good' : lastEntry.renderTime < 4000 ? 'needs-improvement' : 'poor';
                        sendMetric({
                            name: 'LCP',
                            value: lastEntry.renderTime || lastEntry.loadTime,
                            rating: rating
                        });
                    }).observe({ type: 'largest-contentful-paint', buffered: true });

                    // CLS - Cumulative Layout Shift
                    let clsValue = 0;
                    let clsEntries = [];
                    new PerformanceObserver((list) => {
                        for (const entry of list.getEntries()) {
                            if (!entry.hadRecentInput) {
                                clsValue += entry.value;
                                clsEntries.push(entry);
                            }
                        }
                        const rating = clsValue < 0.1 ? 'good' : clsValue < 0.25 ? 'needs-improvement' : 'poor';
                        sendMetric({
                            name: 'CLS',
                            value: clsValue,
                            rating: rating
                        });
                    }).observe({ type: 'layout-shift', buffered: true });

                    // INP - Interaction to Next Paint (using First Input Delay as fallback for older browsers)
                    new PerformanceObserver((list) => {
                        const entries = list.getEntries();
                        entries.forEach(entry => {
                            const duration = entry.processingStart - entry.startTime;
                            const rating = duration < 200 ? 'good' : duration < 500 ? 'needs-improvement' : 'poor';
                            sendMetric({
                                name: 'INP',
                                value: duration,
                                rating: rating
                            });
                        });
                    }).observe({ type: 'event', buffered: true, durationThreshold: 16 });

                    // FID - First Input Delay (fallback for INP)
                    new PerformanceObserver((list) => {
                        const firstInput = list.getEntries()[0];
                        if (firstInput) {
                            const fid = firstInput.processingStart - firstInput.startTime;
                            const rating = fid < 100 ? 'good' : fid < 300 ? 'needs-improvement' : 'poor';
                            sendMetric({
                                name: 'FID',
                                value: fid,
                                rating: rating
                            });
                        }
                    }).observe({ type: 'first-input', buffered: true });

                    // Report metrics on page unload
                    window.addEventListener('beforeunload', () => {
                        if (clsValue > 0) {
                            const rating = clsValue < 0.1 ? 'good' : clsValue < 0.25 ? 'needs-improvement' : 'poor';
                            sendMetric({
                                name: 'CLS',
                                value: clsValue,
                                rating: rating
                            });
                        }
                    });
                })();
            """)

            async def handle_request(request: Request):
                if self.is_logging:
                    if request.resource_type in ['fetch', 'xhr', 'script', 'document']:
                        self.request_start_times[request.url] = time.time()
                        socketio.emit('request', {
                            'type': request.resource_type.upper(),
                            'method': request.method,
                            'url': request.url
                        })

            async def handle_response(response: Response):
                if self.is_logging:
                    request = response.request
                    if request.resource_type in ['fetch', 'xhr', 'script', 'document']:
                        duration = 0
                        if request.url in self.request_start_times:
                            duration = time.time() - self.request_start_times[request.url]
                            del self.request_start_times[request.url]

                        size = 0
                        try:
                            body = await response.body()
                            size = len(body)
                        except Exception:
                            pass

                        data = self._extract_request_data(request, response, duration, size)
                        self.requests.append(data)

                        # Emit to web UI (convert duration to milliseconds)
                        socketio.emit('response', {
                            'duration': f"{duration * 1000:.2f}",
                            'size': size,
                            'url': request.url,
                            'status': response.status
                        })

            self.page.on('request', handle_request)
            self.page.on('response', handle_response)

            # Don't navigate - just keep browser open
            socketio.emit('status', {'message': 'Browser opened! Navigate and perform actions. Click "Save Logs" to save current session. Close browser when done.'})

            # Stay open until user closes or clicks Stop
            while self.is_logging:
                try:
                    # Check if browser/context is still alive
                    if not self.browser or not self.browser.is_connected():
                        socketio.emit('status', {'message': 'Browser closed by user.'})
                        break
                    await asyncio.sleep(1)
                except Exception as e:
                    # Only break on actual connection errors
                    error_msg = str(e).lower()
                    if 'close' in error_msg or 'disconnect' in error_msg or 'target' in error_msg:
                        socketio.emit('status', {'message': 'Browser closed by user.'})
                        break
                    # Log other errors but don't close
                    print(f"Non-fatal error in keep-alive loop: {e}")

        except Exception as e:
            socketio.emit('status', {'message': f'Error: {str(e)[:200]}'})
        finally:
            # Clean up
            try:
                if self.browser:
                    await self.browser.close()
            except Exception:
                pass

            try:
                if self.playwright:
                    await self.playwright.stop()
            except Exception:
                pass

            self.browser = None
            self.playwright = None
            self.context = None
            self.page = None
            self.is_logging = False
            self.is_running = False
            socketio.emit('status', {'message': f'Logging stopped. Captured {len(self.requests)} requests.'})

    def export_to_csv(self, filename: str = None, prefix: str = None):
        """Export captured network logs to CSV file

        Args:
            filename: Optional full filename (overrides prefix)
            prefix: Optional prefix to add before NL_ (e.g., 'mytest' -> 'mytest_NL_...')
        """
        if not self.requests:
            return None

        if filename is None:
            # Format: [PREFIX_]NL_DDMMYY_HH:MM:SSAM/PM.csv
            timestamp = datetime.now().strftime("%d%m%y_%I:%M:%S%p")
            if prefix:
                filename = f"{prefix}_NL_{timestamp}.csv"
            else:
                filename = f"NL_{timestamp}.csv"

        if not filename.endswith('.csv'):
            filename += '.csv'

        # Save to reports/network_logs directory
        filepath = os.path.join('reports', 'network_logs', filename)

        fieldnames = [
            'timestamp', 'method', 'url', 'resource_type',
            'status', 'status_text', 'duration_ms', 'size_kb',
            'graphql_query_id', 'graphql_endpoint', 'post_data'
        ]

        # Convert data to CSV format with proper units
        csv_data = []
        for req in self.requests:
            csv_row = req.copy()
            # Convert duration from seconds to milliseconds
            csv_row['duration_ms'] = round(req['duration'] * 1000, 2)
            # Convert size from bytes to KB
            csv_row['size_kb'] = round(req['size'] / 1024, 2)
            # Rename graphql_operation to graphql_endpoint for CSV export
            csv_row['graphql_endpoint'] = csv_row.pop('graphql_operation', '')
            # graphql_query_id stays as is
            # Remove old keys
            csv_row.pop('duration', None)
            csv_row.pop('size', None)
            # Remove verbose fields
            csv_row.pop('request_headers', None)
            csv_row.pop('response_headers', None)
            csv_data.append(csv_row)

        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_data)

        return filepath

    def clear_logs(self):
        """Clear all captured requests and web vitals"""
        self.requests.clear()
        self.web_vitals.clear()

    def export_web_vitals_to_csv(self, filename: str = None, prefix: str = None):
        """Export Web Vitals to separate CSV file

        Args:
            filename: Optional full filename (overrides prefix)
            prefix: Optional prefix to add before WV_ (e.g., 'mytest' -> 'mytest_WV_...')
        """
        if not self.web_vitals:
            return None

        if filename is None:
            # Format: [PREFIX_]WV_DDMMYY_HH:MM:SSAM/PM.csv
            timestamp = datetime.now().strftime("%d%m%y_%I:%M:%S%p")
            if prefix:
                filename = f"{prefix}_WV_{timestamp}.csv"
            else:
                filename = f"WV_{timestamp}.csv"

        if not filename.endswith('.csv'):
            filename += '.csv'

        # Save to reports/web_vitals directory
        filepath = os.path.join('reports', 'web_vitals', filename)

        fieldnames = ['timestamp', 'url', 'metric_name', 'value_ms_or_score', 'rating', 'unit']

        # Add unit information to each row
        csv_data = []
        for vital in self.web_vitals:
            row = vital.copy()
            metric_name = vital.get('metric_name', '')

            # Determine unit based on metric
            if metric_name in ['LCP', 'INP', 'FID']:
                row['unit'] = 'ms'
            elif metric_name == 'CLS':
                row['unit'] = 'score (unitless)'
            else:
                row['unit'] = ''

            # Rename value key
            row['value_ms_or_score'] = row.pop('value')
            csv_data.append(row)

        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_data)

        return filepath

# Global logger instance
logger = NetworkLoggerWeb()

@app.route('/')
def index():
    """Render main page"""
    return render_template('index.html')

@app.route('/start', methods=['POST'])
def start_logging():
    """Start logging endpoint"""
    if logger.is_running:
        return jsonify({'status': 'error', 'message': 'A logging session is already running'}), 400

    # Run async function in a thread
    def run_async():
        asyncio.run(logger.start_logging())

    thread = threading.Thread(target=run_async)
    thread.daemon = True
    thread.start()

    return jsonify({'status': 'started'})

@app.route('/stop', methods=['POST'])
def stop_logging():
    """Stop logging endpoint"""
    logger.is_logging = False
    return jsonify({'status': 'stopped', 'total_requests': len(logger.requests)})

@app.route('/status', methods=['GET'])
def get_status():
    """Get current logging status"""
    return jsonify({
        'is_running': logger.is_running,
        'is_logging': logger.is_logging,
        'total_requests': len(logger.requests),
        'total_vitals': len(logger.web_vitals)
    })

@app.route('/export', methods=['GET'])
def export_logs():
    """Export logs to CSV"""
    prefix = request.args.get('prefix', None)
    filename = logger.export_to_csv(prefix=prefix)
    if filename:
        return send_file(filename, as_attachment=True)
    return jsonify({'error': 'No logs to export'}), 400

@app.route('/clear', methods=['POST'])
def clear_logs():
    """Clear all logs"""
    logger.clear_logs()
    return jsonify({'status': 'cleared'})

@app.route('/logs', methods=['GET'])
def get_logs():
    """Get all captured logs"""
    return jsonify({'logs': logger.requests, 'total': len(logger.requests)})

@app.route('/export-vitals', methods=['GET'])
def export_vitals():
    """Export Web Vitals to CSV"""
    prefix = request.args.get('prefix', None)
    filename = logger.export_web_vitals_to_csv(prefix=prefix)
    if filename:
        return send_file(filename, as_attachment=True)
    return jsonify({'error': 'No web vitals to export'}), 400

@app.route('/vitals', methods=['GET'])
def get_vitals():
    """Get all captured web vitals"""
    return jsonify({'vitals': logger.web_vitals, 'total': len(logger.web_vitals)})

@app.route('/reports')
def reports():
    """View all available CSV reports"""
    reports_data = {
        'network_logs': [],
        'web_vitals': []
    }

    # Get network log files
    network_logs_path = os.path.join('reports', 'network_logs', '*.csv')
    for file in glob.glob(network_logs_path):
        file_stat = os.stat(file)
        # Get just the filename for display, but keep relative path for operations
        filename = os.path.basename(file)
        relative_path = os.path.join('network_logs', filename)

        file_info = {
            'filename': filename,
            'path': relative_path,  # For file operations
            'size': round(file_stat.st_size / 1024, 2),  # KB
            'modified': datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        }

        # Count rows
        try:
            with open(file, 'r', encoding='utf-8') as f:
                row_count = sum(1 for _ in f) - 1  # Exclude header
                file_info['rows'] = row_count
        except:
            file_info['rows'] = 0

        reports_data['network_logs'].append(file_info)

    # Get web vitals files
    web_vitals_path = os.path.join('reports', 'web_vitals', '*.csv')
    for file in glob.glob(web_vitals_path):
        file_stat = os.stat(file)
        filename = os.path.basename(file)
        relative_path = os.path.join('web_vitals', filename)

        file_info = {
            'filename': filename,
            'path': relative_path,
            'size': round(file_stat.st_size / 1024, 2),  # KB
            'modified': datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        }

        # Count rows
        try:
            with open(file, 'r', encoding='utf-8') as f:
                row_count = sum(1 for _ in f) - 1  # Exclude header
                file_info['rows'] = row_count
        except:
            file_info['rows'] = 0

        reports_data['web_vitals'].append(file_info)

    # Sort by modified date (newest first)
    reports_data['network_logs'].sort(key=lambda x: x['modified'], reverse=True)
    reports_data['web_vitals'].sort(key=lambda x: x['modified'], reverse=True)

    return render_template('reports.html', reports=reports_data)

@app.route('/view-csv/<path:filepath>')
def view_csv(filepath):
    """View a CSV file in browser"""
    # Security: only allow CSV files in reports directory
    if not filepath.endswith('.csv'):
        return jsonify({'error': 'Invalid filename'}), 400

    # Ensure path is within reports directory
    if not filepath.startswith(('network_logs/', 'web_vitals/')):
        return jsonify({'error': 'Invalid path'}), 400

    full_path = os.path.join('reports', filepath)
    if not os.path.exists(full_path):
        return jsonify({'error': 'File not found'}), 404

    return render_template('csv_viewer.html', filepath=filepath, filename=os.path.basename(filepath))

@app.route('/api/csv-data/<path:filepath>')
def get_csv_data(filepath):
    """Get CSV data as JSON"""
    # Security: only allow CSV files in reports directory
    if not filepath.endswith('.csv'):
        return jsonify({'error': 'Invalid filename'}), 400

    # Ensure path is within reports directory
    if not filepath.startswith(('network_logs/', 'web_vitals/')):
        return jsonify({'error': 'Invalid path'}), 400

    full_path = os.path.join('reports', filepath)
    if not os.path.exists(full_path):
        return jsonify({'error': 'File not found'}), 404

    try:
        data = []
        with open(full_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)

        return jsonify({'data': data, 'total': len(data)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/delete-report/<path:filepath>', methods=['POST'])
def delete_report(filepath):
    """Delete a CSV report file"""
    # Security: only allow CSV files in reports directory
    if not filepath.endswith('.csv'):
        return jsonify({'error': 'Invalid filename'}), 400

    # Ensure path is within reports directory
    if not filepath.startswith(('network_logs/', 'web_vitals/')):
        return jsonify({'error': 'Invalid path'}), 400

    full_path = os.path.join('reports', filepath)
    if not os.path.exists(full_path):
        return jsonify({'error': 'File not found'}), 404

    try:
        os.remove(full_path)
        filename = os.path.basename(filepath)
        return jsonify({'status': 'success', 'message': f'{filename} deleted successfully'})
    except Exception as e:
        return jsonify({'error': f'Failed to delete file: {str(e)}'}), 500

@app.route('/rename-report', methods=['POST'])
def rename_report():
    """Rename a CSV report file"""
    data = request.get_json()
    old_filepath = data.get('old_filepath')
    new_filename = data.get('new_filename')

    if not old_filepath or not new_filename:
        return jsonify({'error': 'Both old filepath and new filename are required'}), 400

    # Ensure new filename ends with .csv
    if not new_filename.endswith('.csv'):
        new_filename += '.csv'

    # Security: only allow CSV files in reports directory
    if not old_filepath.endswith('.csv'):
        return jsonify({'error': 'Invalid old filename'}), 400

    # Ensure path is within reports directory
    if not old_filepath.startswith(('network_logs/', 'web_vitals/')):
        return jsonify({'error': 'Invalid path'}), 400

    # Security: no path characters in new filename
    if '/' in new_filename or '\\' in new_filename:
        return jsonify({'error': 'Invalid new filename - no path characters allowed'}), 400

    old_full_path = os.path.join('reports', old_filepath)

    # Get the directory from old filepath to keep file in same category
    directory = os.path.dirname(old_filepath)
    new_filepath = os.path.join(directory, new_filename)
    new_full_path = os.path.join('reports', new_filepath)

    # Check old file exists
    if not os.path.exists(old_full_path):
        return jsonify({'error': 'Original file not found'}), 404

    # Check new filename doesn't already exist
    if os.path.exists(new_full_path):
        return jsonify({'error': f'File {new_filename} already exists'}), 400

    try:
        os.rename(old_full_path, new_full_path)
        return jsonify({
            'status': 'success',
            'message': f'Renamed to {new_filename}',
            'new_filename': new_filename,
            'new_filepath': new_filepath
        })
    except Exception as e:
        return jsonify({'error': f'Failed to rename file: {str(e)}'}), 500

@app.route('/download/<path:filepath>')
def download_file(filepath):
    """Download a CSV file"""
    # Security: only allow CSV files in reports directory
    if not filepath.endswith('.csv'):
        return jsonify({'error': 'Invalid filename'}), 400

    # Ensure path is within reports directory
    if not filepath.startswith(('network_logs/', 'web_vitals/')):
        return jsonify({'error': 'Invalid path'}), 400

    full_path = os.path.join('reports', filepath)
    if not os.path.exists(full_path):
        return jsonify({'error': 'File not found'}), 404

    try:
        filename = os.path.basename(filepath)
        return send_file(full_path, as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({'error': f'Failed to download file: {str(e)}'}), 500

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    emit('status', {'message': 'Connected to Network Logger'})

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5001, debug=True, allow_unsafe_werkzeug=True)
