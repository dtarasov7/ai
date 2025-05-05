import argparse
import time
import boto3
import http.server
import socketserver
import urllib.parse
from prometheus_client import CollectorRegistry, Gauge, generate_latest, CONTENT_TYPE_LATEST

class S3MetricsHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        if parsed_path.path == "/probe":
            params = urllib.parse.parse_qs(parsed_path.query)
            bucket = params.get('bucket', [None])[0]
            prefix = params.get('prefix', [''])[0]
            delimiter = params.get('delimiter', [''])[0]

            if not bucket:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing 'bucket' parameter")
                return

            output = collect_s3_metrics(bucket, prefix, delimiter)
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(output)
        elif parsed_path.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"""<html>
<head><title>S3 Exporter</title></head>
<body>
<h1>S3 Exporter</h1>
<p><a href='/probe?bucket=mybucket'>Probe mybucket</a></p>
</body>
</html>""")
        else:
            self.send_response(404)
            self.end_headers()


def collect_s3_metrics(bucket, prefix='', delimiter=''):
    s3 = boto3.client('s3')
    registry = CollectorRegistry()

    list_success = Gauge('s3_list_success', 'If the ListObjects operation was a success',
                         ['bucket', 'prefix', 'delimiter'], registry=registry)
    list_duration = Gauge('s3_list_duration_seconds', 'Total duration of the list operation',
                          ['bucket', 'prefix', 'delimiter'], registry=registry)

    last_modified_date = Gauge('s3_last_modified_object_date', 'Last modified date (timestamp)',
                               ['bucket', 'prefix'], registry=registry)
    last_modified_size = Gauge('s3_last_modified_object_size_bytes', 'Size of most recently modified object',
                               ['bucket', 'prefix'], registry=registry)
    object_total = Gauge('s3_objects', 'Total number of objects',
                         ['bucket', 'prefix'], registry=registry)
    size_sum = Gauge('s3_objects_size_sum_bytes', 'Total size of all objects',
                     ['bucket', 'prefix'], registry=registry)
    biggest_object = Gauge('s3_biggest_object_size_bytes', 'Biggest object size',
                           ['bucket', 'prefix'], registry=registry)
    common_prefixes = Gauge('s3_common_prefixes', 'Number of common prefixes',
                            ['bucket', 'prefix', 'delimiter'], registry=registry)

    number_of_objects = 0
    total_size = 0
    biggest_size = 0
    last_modified = 0
    last_size = 0
    prefix_count = 0

    kwargs = {
        'Bucket': bucket,
        'Prefix': prefix,
    }
    if delimiter:
        kwargs['Delimiter'] = delimiter

    start_time = time.time()
    try:
        while True:
            response = s3.list_objects_v2(**kwargs)
            for obj in response.get('Contents', []):
                number_of_objects += 1
                size = obj['Size']
                total_size += size
                if size > biggest_size:
                    biggest_size = size
                if obj['LastModified'].timestamp() > last_modified:
                    last_modified = obj['LastModified'].timestamp()
                    last_size = size
            prefix_count += len(response.get('CommonPrefixes', []))
            if not response.get('IsTruncated'):
                break
            kwargs['ContinuationToken'] = response['NextContinuationToken']

        duration = time.time() - start_time
        list_success.labels(bucket, prefix, delimiter).set(1)
        list_duration.labels(bucket, prefix, delimiter).set(duration)

        if not delimiter:
            last_modified_date.labels(bucket, prefix).set(last_modified)
            last_modified_size.labels(bucket, prefix).set(last_size)
            object_total.labels(bucket, prefix).set(number_of_objects)
            size_sum.labels(bucket, prefix).set(total_size)
            biggest_object.labels(bucket, prefix).set(biggest_size)
        else:
            common_prefixes.labels(bucket, prefix, delimiter).set(prefix_count)

    except Exception as e:
        print(f"Error listing objects: {e}")
        list_success.labels(bucket, prefix, delimiter).set(0)

    return generate_latest(registry)


def main():
    parser = argparse.ArgumentParser(description='S3 Exporter for Prometheus')
    parser.add_argument('--web.listen-address', default='0.0.0.0:9340',
                        help='Address on which to expose metrics and web interface.')
    args = parser.parse_args()

    host, port = args.web_listen_address.split(':')
    port = int(port)

    with socketserver.TCPServer((host, port), S3MetricsHandler) as httpd:
        print(f"Serving on {host}:{port}")
        httpd.serve_forever()


if __name__ == '__main__':
    main()
