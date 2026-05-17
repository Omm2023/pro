import http.server
import os
import json
import uuid
import pandas as pd
from urllib.parse import urlparse, unquote

PORT = 8000
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
DOWNLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'downloads')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Column mapping
COLUMN_MAPPING = {
    'fsn': 'fsn',
    'dispatch_warehouse_id': 'Warehouse id',
    'product_vertical': 'product_vertical',
    'storage_location_label': 'storage_location_label',
}
FINAL_COLUMNS = ['fsn', 'Warehouse id', 'Location', 'product_vertical', 'storage_location_label']


def filter_excel(input_path, output_path):
    df = pd.read_excel(input_path)

    required = list(COLUMN_MAPPING.keys())
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {', '.join(missing)}")

    filtered_df = df[required].rename(columns=COLUMN_MAPPING)
    filtered_df.insert(2, 'Location', '')
    filtered_df = filtered_df[FINAL_COLUMNS]
    filtered_df.to_excel(output_path, index=False)
    return len(filtered_df)


class Handler(http.server.SimpleHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == '/' or parsed.path == '/index.html':
            self.serve_file('index.html', 'text/html')

        elif parsed.path.startswith('/download/'):
            filename = os.path.basename(unquote(parsed.path.split('/download/')[-1]))
            if not filename:
                self.send_error(404, 'File not found')
                return
            filepath = os.path.join(DOWNLOAD_FOLDER, filename)
            if os.path.exists(filepath):
                self.send_response(200)
                self.send_header('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
                self.end_headers()
                with open(filepath, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404, 'File not found')
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == '/upload':
            content_type = self.headers['Content-Type']
            if 'multipart/form-data' not in content_type:
                self.send_json(400, {'error': 'Invalid content type'})
                return

            # Parse the multipart form data
            boundary = content_type.split('boundary=')[-1].encode()
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)

            # Extract file from multipart data
            file_data, original_filename = self.parse_multipart(body, boundary)

            if not file_data or not original_filename:
                self.send_json(400, {'error': 'No file uploaded'})
                return

            ext = original_filename.rsplit('.', 1)[-1].lower()
            if ext not in ('xlsx', 'xls'):
                self.send_json(400, {'error': 'Invalid file type. Upload .xlsx or .xls'})
                return

            try:
                uid = str(uuid.uuid4())[:8]
                input_path = os.path.join(UPLOAD_FOLDER, f"{uid}_{original_filename}")
                with open(input_path, 'wb') as f:
                    f.write(file_data)

                base_name = original_filename.rsplit('.', 1)[0]
                output_filename = f"{base_name}_filtered.xlsx"
                output_path = os.path.join(DOWNLOAD_FOLDER, f"{uid}_{output_filename}")

                row_count = filter_excel(input_path, output_path)

                # Clean up upload
                os.remove(input_path)

                self.send_json(200, {
                    'success': True,
                    'rows': row_count,
                    'download_url': f"/download/{uid}_{output_filename}",
                    'filename': output_filename
                })

            except ValueError as e:
                self.send_json(400, {'error': str(e)})
            except Exception as e:
                self.send_json(500, {'error': f'Processing error: {str(e)}'})
        else:
            self.send_error(404)

    def parse_multipart(self, body, boundary):
        """Simple multipart parser to extract file data and filename."""
        parts = body.split(b'--' + boundary)
        for part in parts:
            if b'filename="' in part:
                # Extract filename
                header_end = part.find(b'\r\n\r\n')
                header = part[:header_end].decode('utf-8', errors='ignore')
                filename_start = header.find('filename="') + 10
                filename_end = header.find('"', filename_start)
                filename = header[filename_start:filename_end]

                # Extract file data
                file_data = part[header_end + 4:]
                if file_data.endswith(b'\r\n'):
                    file_data = file_data[:-2]

                return file_data, filename
        return None, None

    def serve_file(self, filename, content_type):
        filepath = os.path.join(os.path.dirname(__file__), filename)
        if os.path.exists(filepath):
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.end_headers()
            with open(filepath, 'rb') as f:
                self.wfile.write(f.read())
        else:
            self.send_error(404)

    def send_json(self, status, data):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        print(f"[Server] {args[0]}")


if __name__ == '__main__':
    server = http.server.HTTPServer(('', PORT), Handler)
    print(f"\n  Excel Filter Tool running at: http://localhost:{PORT}\n")
    print(f"  Open the above URL in your browser.")
    print(f"  Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()