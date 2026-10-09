"""
Quotex Python Module — Chaquopy
يستخدم requests + websocket-client + TLS Spoofing
"""

import json
import re
import ssl
import threading
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

import websocket


# ═══════════════════════════════════════════════════════
#  Global State
# ═══════════════════════════════════════════════════════
_callback = None
_session = None
_ws = None
_ssid = None
_cookies = ""
_is_demo = True
_authed = False


def init_callbacks(cb):
    """يُنادى من Kotlin قبل login"""
    global _callback
    _callback = cb


def _log(msg):
    if _callback:
        try:
            _callback.onPythonLog(str(msg))
        except Exception:
            pass


def _on_auth(ok):
    if _callback:
        try:
            _callback.onAuth(bool(ok))
        except Exception:
            pass


def _on_order(kind, id_, profit=0.0):
    if _callback:
        try:
            _callback.onOrder(kind, str(id_), float(profit))
        except Exception:
            pass


# ═══════════════════════════════════════════════════════
#  TLS Spoofing Adapter
# ═══════════════════════════════════════════════════════
class CipherSuiteAdapter(HTTPAdapter):
    def __init__(self, *args, **kwargs):
        self.ssl_context = create_urllib3_context(
            ssl_version=ssl.PROTOCOL_TLS_CLIENT,
            ciphers=(
                "ECDHE-ECDSA-AES128-GCM-SHA256:"
                "ECDHE-RSA-AES128-GCM-SHA256:"
                "ECDHE-ECDSA-AES256-GCM-SHA384:"
                "ECDHE-RSA-AES256-GCM-SHA384:"
                "ECDHE-ECDSA-CHACHA20-POLY1305:"
                "ECDHE-RSA-CHACHA20-POLY1305:"
                "DHE-RSA-AES128-GCM-SHA256:"
                "DHE-RSA-AES256-GCM-SHA384"
            ),
        )
        try:
            self.ssl_context.set_ecdh_curve("prime256v1")
        except Exception:
            pass
        try:
            self.ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
            self.ssl_context.maximum_version = ssl.TLSVersion.TLSv1_3
        except AttributeError:
            pass
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = self.ssl_context
        kwargs["maxsize"] = 10
        return super().init_poolmanager(*args, **kwargs)


# ═══════════════════════════════════════════════════════
#  Login
# ═══════════════════════════════════════════════════════
HOST = "qxbroker.com"
LANG = "en"
UA = ("Mozilla/5.0 (Linux; Android 10; K) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Mobile Safari/537.36")


def login(email, password, demo=True):
    global _session, _ssid, _cookies, _is_demo

    _is_demo = demo
    _log("📡 Login: " + email)

    try:
        _session = requests.Session()
        _session.mount("https://", CipherSuiteAdapter())
        _session.headers.update({
            "User-Agent": UA,
            "Accept-Language": "en-US,en;q=0.9",
        })

        # 1) GET /sign-in/modal/
        _log("GET /sign-in/modal/")
        url_modal = "https://" + HOST + "/" + LANG + "/sign-in/modal/"
        r = _session.get(url_modal, timeout=30)
        _log("  HTTP " + str(r.status_code))

        m = re.search(r'name="_token"\s+value="([^"]+)"', r.text)
        if not m:
            _log("❌ CSRF token not found")
            _on_auth(False)
            return
        csrf = m.group(1)
        _log("✅ CSRF: " + csrf[:15] + "...")

        # 2) POST /sign-in/
        _log("POST /sign-in/")
        url_signin = "https://" + HOST + "/" + LANG + "/sign-in/"
        r = _session.post(url_signin, data={
            "email": email,
            "password": password,
            "_token": csrf,
        }, timeout=30, allow_redirects=True)
        _log("  HTTP " + str(r.status_code))

        # 3) GET /trade
        _log("GET /trade")
        url_trade = "https://" + HOST + "/" + LANG + "/trade"
        r = _session.get(url_trade, timeout=30)

        m = re.search(r"window\.settings\s*=\s*(\{.+?\});",
                      r.text, re.DOTALL)
        if not m:
            _log("❌ window.settings not found")
            _on_auth(False)
            return

        settings = json.loads(m.group(1))
        _ssid = settings.get("token") or settings.get("ssid")
        if not _ssid:
            _log("❌ SSID not found")
            _on_auth(False)
            return

        _cookies = "; ".join(f"{k}={v}" for k, v in _session.cookies.items())
        _log("✅ SSID: " + _ssid[:15] + "...")
        _on_auth(True)
        _connect_ws()

    except Exception as e:
        _log("❌ Login error: " + str(e))
        _on_auth(False)


# ═══════════════════════════════════════════════════════
#  WebSocket
# ═══════════════════════════════════════════════════════
def _connect_ws():
    global _ws
    url = "wss://ws2." + HOST + "/socket.io/?EIO=3&transport=websocket"
    _log("🔌 Connecting WebSocket...")

    headers = [
        "User-Agent: " + UA,
        "Origin: https://" + HOST,
        "Cookie: " + _cookies,
    ]

    sslopt = {
        "cert_reqs": ssl.CERT_NONE,
        "check_hostname": False,
    }

    _ws = websocket.WebSocketApp(
        url,
        header=headers,
        on_open=_on_ws_open,
        on_message=_on_ws_message,
        on_error=_on_ws_error,
        on_close=_on_ws_close,
    )
    threading.Thread(
        target=lambda: _ws.run_forever(sslopt=sslopt),
        daemon=True).start()


def _on_ws_open(ws):
    _log("✅ WS open")
    auth = json.dumps({
        "session": _ssid,
        "isDemo": 1 if _is_demo else 0,
        "tournamentId": 0,
    }, separators=(",", ":"))
    ws.send('42["authorization",' + auth + ']')
    _log("📤 SSID sent")


def _on_ws_message(ws, msg):
    global _authed
    try:
        if msg == "2":
            ws.send("3")
            return
        if msg.startswith("41"):
            _authed = False
            return
        if "authorization/reject" in msg:
            _authed = False
            _log("❌ SSID rejected")
            _on_auth(False)
            return
        if "s_authorization" in msg:
            _authed = True
            _log("🎉 Authenticated")
            ws.send('42["tick"]')
            ws.send('42["instruments/list"]')
            ws.send('42["pending/list"]')
            _subscribe_defaults()
            return
        if msg.startswith("42"):
            arr = json.loads(msg[2:])
            event = arr[0] if isinstance(arr, list) and arr else ""
            data = arr[1] if isinstance(arr, list) and len(arr) > 1 else None

            if event == "orders/open" and isinstance(data, dict):
                id_ = data.get("deal_idt") or data.get("id") or ""
                _on_order("open", id_, 0.0)
            elif event == "orders/close" and isinstance(data, dict):
                id_ = data.get("deal_idt") or ""
                profit = float(data.get("amount_profit", 0))
                _on_order("close", id_, profit)
            elif event == "orders/error":
                _on_order("error", str(data)[:50], 0.0)
    except Exception:
        pass


def _on_ws_error(ws, err):
    _log("❌ WS error: " + str(err))


def _on_ws_close(ws, code, msg):
    global _authed
    _log("🔌 WS closed (" + str(code) + ")")
    _authed = False


def _subscribe_defaults():
    assets = ["EURUSD_otc", "GBPUSD_otc", "BTCUSD_otc", "ETHUSD_otc"]
    for a in assets:
        payload = json.dumps({"asset": a, "period": 60},
                             separators=(",", ":"))
        _ws.send('42["instruments/update",' + payload + ']')
        _ws.send('42["depth/follow","' + a + '"]')


# ═══════════════════════════════════════════════════════
#  Trade
# ═══════════════════════════════════════════════════════
def buy(asset, amount, direction, duration=60):
    global _authed
    if not _authed or not _ws:
        _log("❌ Not authenticated")
        return
    rid = int(time.time() * 1000) % 1000000
    opt = 100 if "_otc" in asset else 1
    expires = int(time.time()) + duration

    payload = json.dumps({
        "asset": asset,
        "amount": float(amount),
        "time": expires,
        "action": direction,
        "isDemo": 1 if _is_demo else 0,
        "tournamentId": 0,
        "requestId": rid,
        "optionType": opt,
    }, separators=(",", ":"))

    _ws.send('42["tick"]')
    _ws.send('42["orders/open",' + payload + ']')
    _log("📤 Trade: " + direction + " " + asset + " $" + str(amount))
