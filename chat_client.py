# -*- coding: utf-8 -*-
import threading
import socket
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.parse
import os
import html
import uuid

TCP_HOST = '147.185.221.19'
TCP_PORT = 42439
WEB_PORT = 803
TIMEOUT_SECONDS = 180

sessions = {}
sessions_lock = threading.Lock()


def start_tcp_session(session_id):
    s = sessions[session_id]
    try:
        s['sock'] = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s['sock'].connect((TCP_HOST, TCP_PORT))
        s['sock'].settimeout(0.5)
        print(f"[{session_id[:8]}] Подключено к TCP-серверу.")

        def ping_loop():
            while s['sock']:
                try:
                    s['sock'].sendall(b"/\r\n")
                except:
                    break
                time.sleep(5)

        threading.Thread(target=ping_loop, daemon=True).start()

        while True:
            if time.time() - s['last_activity'] > TIMEOUT_SECONDS:
                print(f"[{session_id[:8]}] Неактивен - соединение закрыто.")
                break

            try:
                data = s['sock'].recv(1024)
                if not data:
                    raise ConnectionError
                text = data.decode('utf-8', errors='ignore')
                for line in text.splitlines():
                    clean = line.strip()
                    if not clean or clean in ("*Ping!*", "Unknown command."):
                        continue

                    if ':' in clean:
                        raw_name, raw_msg = clean.split(':', 1)
                        raw_name = raw_name.strip()
                        raw_msg = raw_msg.strip()
                        safe_name = html.escape(raw_name)
                        safe_msg = html.escape(raw_msg)
                        if ' ' not in raw_name and raw_name != "Usage":
                            safe_name = f"<b>{safe_name}</b>"
                        clean_text = f"{safe_name}: {safe_msg}"
                    else:
                        clean_text = html.escape(clean)

                    entry = (
                        '<font color="#808080">[%s]</font> '
                        '<font color="#000000">%s</font>'
                    ) % (time.strftime("%H:%M"), clean_text)

                    with s['lock']:
                        s['messages'].append(entry)
                        if len(s['messages']) > 200:
                            s['messages'].pop(0)
            except socket.timeout:
                continue

    except Exception as e:
        print(f"[{session_id[:8]}] Ошибка TCP: {e}.")
    finally:
        try:
            if s['sock']:
                s['sock'].close()
        except:
            pass
        s['sock'] = None
        print(f"[{session_id[:8]}] Соединение закрыто.")


class ChatHandler(BaseHTTPRequestHandler):
    def get_session(self):
        cookie = self.headers.get('Cookie', '')
        sid = None
        if 'session=' in cookie:
            sid = cookie.split('session=')[-1].split(';')[0]

        with sessions_lock:
            if sid not in sessions:
                sid = str(uuid.uuid4())
                sessions[sid] = {
                    'messages': [],
                    'lock': threading.Lock(),
                    'sock': None,
                    'last_activity': time.time()
                }
                threading.Thread(target=start_tcp_session, args=(sid,), daemon=True).start()

        self.session_id = sid
        return sessions[sid]

    def do_GET(self):
        if self.path in ('/', '/index'):
            self.send_html('templates/index.html')
        elif self.path == '/chat':
            self.show_chat()
        elif self.path == '/send_input':
            self.send_html('templates/send_input.html')
        elif self.path == '/disconnect':
            self.disconnect_user()
        else:
            self.send_error(404)


    def disconnect_user(self):
        cookie = self.headers.get('Cookie', '')
        sid = None
        if 'session=' in cookie:
            sid = cookie.split('session=')[-1].split(';')[0]

        if sid:
            with sessions_lock:
                session = sessions.pop(sid, None)
            if session and session.get('sock'):
                try:
                    session['sock'].close()
                except:
                    pass

        self.send_response(303)
        self.send_header('Location', '/send')
        self.send_header('Connection', 'close')
        self.send_header('Set-Cookie', 'session=deleted; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT')
        self.end_headers()


    def do_POST(self):
        if self.path == '/send':
            session = self.get_session()
            length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(length).decode('utf-8', errors='ignore')
            fields = urllib.parse.parse_qs(post_data)
            msg = fields.get('msg', [''])[0].strip()
            if msg:
                try:
                    if session['sock']:
                        session['sock'].sendall((msg + "\r\n").encode('utf-8'))
                except Exception as e:
                    print(f"⚠️ [{self.session_id[:8]}] Ошибка при отправке: {e}")
            self.send_response(303)
            self.send_header('Location', '/send')
            self.send_header('Connection', 'close')
            self.send_header('Set-Cookie', f'session={self.session_id}; Path=/')
            self.end_headers()
        else:
            self.send_error(404)

    def send_html(self, path):
        if not os.path.exists(path):
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Connection', 'close')
        self.send_header('Set-Cookie', f'session={self.get_session_id()}; Path=/')
        self.end_headers()
        with open(path, 'rb') as f:
            self.wfile.write(f.read())

    def get_session_id(self):
        if not hasattr(self, 'session_id'):
            self.get_session()
        return self.session_id

    def show_chat(self):
        session = self.get_session()
        session['last_activity'] = time.time()

        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Connection', 'close')
        self.send_header('Set-Cookie', f'session={self.session_id}; Path=/')
        self.end_headers()

        html_page = (
            '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">'
            '<html>'
            '<head>'
            '<meta http-equiv="Content-Type" content="text/html; charset=utf-8">'
            '<meta http-equiv="refresh" content="3">'
            '<title>DMconnect.</title>'
            '<script type="text/javascript">'
            'function scrollToBottom() {'
            '  window.scrollTo(0, document.body.scrollHeight);'
            '}'
            '</script>'
            '</head>'
            '<body bgcolor="#F7F7F7" text="#000000" link="#0000FF" vlink="#800080" '
            'style="margin:0; padding:0;" onload="scrollToBottom();">'
            '<table border="0" width="100%" cellspacing="0" cellpadding="0">'
            '<tr><td>'
            '<div style="font-family:Tahoma, monospace; font-size:12px; '
            'white-space: pre-wrap; word-wrap: break-word; margin:0; padding:0 0 0 10px;">'
        )

        with session['lock']:
            if session['messages']:
                html_page += '<br>' + "<br>".join(session['messages'][-100:])
            else:
                html_page += '<br>'

        html_page += '</div></td></tr></table></body></html>'
        self.wfile.write(html_page.encode('utf-8'))

if __name__ == '__main__':
    print(f"Сервер запущен: http://localhost:{WEB_PORT}/index.")
    server = HTTPServer(('0.0.0.0', WEB_PORT), ChatHandler)
    server.serve_forever()

