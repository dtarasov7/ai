#!/usr/bin/env python
"""Запустить на отдельной ВМ с Istio-agent: python vm-server.py.

Остановить Ctrl+C. Не запускать вместо ВМ внутри Pod: это изменит смысл проверки.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Уникальный ответ отличает наш процесс от случайного HTTP-сервера на порту.
        body = b"pmi-istio-20-real-vm\n"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# Приложение запускается обычным пользователем, НЕ istio-proxy: иначе обход iptables.
# Агент должен перехватывать входящие соединения на этот порт.
ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
