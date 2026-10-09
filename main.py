"""
Quotex Trading App — Python + Kivy
يستخدم requests + websocket-client + TLS Spoofing
"""

import json
import re
import ssl
import threading
import time
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

import websocket

from kivy.app import App
from kivy.clock import Clock
from kivy.properties import StringProperty, ListProperty, NumericProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.popup import Popup


# ═══════════════════════════════════════════════════════
#  TLS Spoofing — CipherSuiteAdapter
#  يحاكي بصمة TLS بتاع Chrome
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
        self.ssl_context.set_ecdh_curve("prime256v1")
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
#  Quotex Client
# ═══════════════════════════════════════════════════════
class QuotexClient:
    HOST = "qxbroker.com"
    LANG = "en"
    UA = ("Mozilla/5.0 (Linux; Android 10; K) "
          "AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/124.0.0.0 Mobile Safari/537.36")

    def __init__(self, on_log, on_auth, on_balance, on_tick, on_order):
        self.on_log = on_log
        self.on_auth = on_auth
        self.on_balance = on_balance
        self.on_tick = on_tick
        self.on_order = on_order

        self.session = requests.Session()
        self.session.mount("https://", CipherSuiteAdapter())
        self.session.headers.update({
            "User-Agent": self.UA,
            "Accept-Language": "en-US,en;q=0.9",
        })

        self.ssid = None
        self.cookies = ""
        self.is_demo = True
        self.ws = None
        self.authed = False

    def login(self, email, password, demo=True):
        self.is_demo = demo
        threading.Thread(target=self._login_thread,
                         args=(email, password), daemon=True).start()

    def _login_thread(self, email, password):
        try:
            self.on_log("📡 GET /sign-in/modal/")
            url_modal = f"https://{self.HOST}/{self.LANG}/sign-in/modal/"
            r = self.session.get(url_modal, timeout=30)
            self.on_log(f"   → HTTP {r.status_code}")

            m = re.search(r'name="_token"\s+value="([^"]+)"', r.text)
            if not m:
                self.on_log("❌ CSRF token مش موجود — Cloudflare")
                self.on_auth(False)
                return
            csrf = m.group(1)
            self.on_log(f"✅ CSRF: {csrf[:20]}...")

            self.on_log("📡 POST /sign-in/")
            url_signin = f"https://{self.HOST}/{self.LANG}/sign-in/"
            r = self.session.post(url_signin, data={
                "email": email,
                "password": password,
                "_token": csrf,
            }, timeout=30, allow_redirects=True)
            self.on_log(f"   → HTTP {r.status_code}")

            self.on_log("📡 GET /trade")
            url_trade = f"https://{self.HOST}/{self.LANG}/trade"
            r = self.session.get(url_trade, timeout=30)

            m = re.search(r"window\.settings\s*=\s*(\{.+?\});",
                          r.text, re.DOTALL)
            if not m:
                self.on_log("❌ window.settings مش موجود")
                self.on_auth(False)
                return

            settings = json.loads(m.group(1))
            self.ssid = settings.get("token") or settings.get("ssid")
            if not self.ssid:
                self.on_log("❌ SSID مش موجود")
                self.on_auth(False)
                return

            self.cookies = "; ".join(
                f"{k}={v}" for k, v in self.session.cookies.items())

            self.on_log(f"✅ SSID: {self.ssid[:20]}...")
            self.on_auth(True)
            self._connect_ws()

        except Exception as e:
            self.on_log(f"❌ خطأ: {e}")
            self.on_auth(False)

    def _connect_ws(self):
        url = f"wss://ws2.{self.HOST}/socket.io/?EIO=3&transport=websocket"
        self.on_log("🔌 الاتصال بـ WebSocket...")

        headers = {
            "User-Agent": self.UA,
            "Origin": f"https://{self.HOST}",
            "Cookie": self.cookies,
        }

        sslopt = {
            "cert_reqs": ssl.CERT_NONE,
            "check_hostname": False,
        }

        self.ws = websocket.WebSocketApp(
            url,
            header=[f"{k}: {v}" for k, v in headers.items()],
            on_open=self._on_ws_open,
            on_message=self._on_ws_message,
            on_error=self._on_ws_error,
            on_close=self._on_ws_close,
        )
        threading.Thread(
            target=lambda: self.ws.run_forever(sslopt=sslopt),
            daemon=True).start()

    def _on_ws_open(self, ws):
        self.on_log("✅ WebSocket مفتوح")
        auth = json.dumps({
            "session": self.ssid,
            "isDemo": 1 if self.is_demo else 0,
            "tournamentId": 0,
        }, separators=(",", ":"))
        ws.send(f'42["authorization",{auth}]')
        self.on_log("📤 SSID مرسل")

    def _on_ws_message(self, ws, msg):
        try:
            if msg == "2":
                ws.send("3")
                return
            if msg.startswith("41"):
                self.authed = False
                return
            if "authorization/reject" in msg:
                self.authed = False
                self.on_log("❌ SSID مرفوض")
                return
            if "s_authorization" in msg:
                self.authed = True
                self.on_log("🎉 مصادقة نجحت")
                ws.send('42["tick"]')
                ws.send('42["instruments/list"]')
                ws.send('42["pending/list"]')
                self._subscribe_defaults()
                return
            if msg.startswith("42"):
                payload = msg[2:]
                arr = json.loads(payload)
                event = arr[0]
                data = arr[1] if len(arr) > 1 else None

                if event == "instruments/list":
                    self.on_log("📋 تم استلام الأدوات")
                elif event == "quotes/stream":
                    self.on_tick(data)
                elif event == "orders/open":
                    self.on_order("open", data)
                elif event == "orders/close":
                    self.on_order("close", data)
        except Exception:
            pass

    def _on_ws_error(self, ws, err):
        self.on_log(f"❌ WS error: {err}")

    def _on_ws_close(self, ws, code, msg):
        self.on_log(f"🔌 WS مغلق ({code})")
        self.authed = False

    def _subscribe_defaults(self):
        assets = ["EURUSD_otc", "GBPUSD_otc", "BTCUSD_otc", "ETHUSD_otc"]
        for a in assets:
            payload = json.dumps({"asset": a, "period": 60},
                                 separators=(",", ":"))
            self.ws.send(f'42["instruments/update",{payload}]')
            self.ws.send(f'42["depth/follow","{a}"]')

    def buy(self, asset, amount, direction, duration=60):
        if not self.authed:
            self.on_log("❌ مش متصل")
            return
        request_id = int(time.time() * 1000) % 1_000_000
        option_type = 100 if "_otc" in asset else 1
        expires = int(time.time() / 60) * 60 + 60
        if option_type == 100:
            expires = int(time.time()) + duration

        payload = json.dumps({
            "asset": asset,
            "amount": amount,
            "time": expires,
            "action": direction,
            "isDemo": 1 if self.is_demo else 0,
            "tournamentId": 0,
            "requestId": request_id,
            "optionType": option_type,
        }, separators=(",", ":"))

        self.ws.send('42["tick"]')
        self.ws.send(f'42["orders/open",{payload}]')
        self.on_log(f"📤 صفقة: {direction} {asset} ${amount}")


# ═══════════════════════════════════════════════════════
#  Kivy UI
# ═══════════════════════════════════════════════════════
class MainLayout(BoxLayout):
    log_text = StringProperty("")
    balance_text = StringProperty("💰 الرصيد: --")
    status_text = StringProperty("🔌 جاري التحميل...")

    def __init__(self, **kw):
        super().__init__(**kw)
        self.orientation = "vertical"
        self.padding = 20
        self.spacing = 10

        self.client = None

        # Status
        self.add_widget(Label(
            text=self.status_text,
            size_hint_y=None, height=40,
            color=(1, 1, 1, 1)))

        # Balance
        self.balance_label = Label(
            text=self.balance_text,
            size_hint_y=None, height=40,
            color=(0.2, 0.9, 0.5, 1))
        self.add_widget(self.balance_label)

        # Email
        self.email_input = TextInput(
            hint_text="Email",
            size_hint_y=None, height=50,
            multiline=False)
        self.add_widget(self.email_input)

        # Password
        self.pass_input = TextInput(
            hint_text="Password",
            password=True,
            size_hint_y=None, height=50,
            multiline=False)
        self.add_widget(self.pass_input)

        # Login Button
        self.login_btn = Button(
            text="🔐 تسجيل دخول (Demo)",
            size_hint_y=None, height=50,
            background_color=(0.12, 0.44, 0.92, 1))
        self.login_btn.bind(on_press=self.on_login)
        self.add_widget(self.login_btn)

        # Asset Spinner
        self.asset_spinner = Spinner(
            text="EURUSD_otc",
            values=["EURUSD_otc", "GBPUSD_otc", "USDJPY_otc",
                    "BTCUSD_otc", "ETHUSD_otc", "XAUUSD_otc"],
            size_hint_y=None, height=50)
        self.add_widget(self.asset_spinner)

        # Amount
        self.amount_input = TextInput(
            text="1",
            hint_text="Amount",
            input_filter="float",
            size_hint_y=None, height=50,
            multiline=False)
        self.add_widget(self.amount_input)

        # Buy / Sell
        row = BoxLayout(size_hint_y=None, height=60, spacing=10)
        self.buy_btn = Button(
            text="🟢 شراء",
            background_color=(0.18, 0.8, 0.44, 1))
        self.buy_btn.bind(on_press=lambda x: self.do_trade("call"))
        row.add_widget(self.buy_btn)

        self.sell_btn = Button(
            text="🔴 بيع",
            background_color=(0.9, 0.3, 0.24, 1))
        self.sell_btn.bind(on_press=lambda x: self.do_trade("put"))
        row.add_widget(self.sell_btn)
        self.add_widget(row)

        # Log
        scroll = ScrollView()
        self.log_label = Label(
            text="",
            size_hint_y=None,
            text_size=(None, None),
            halign="left",
            valign="top")
        self.log_label.bind(
            texture_size=lambda i, v: setattr(i, "height", v[1]))
        scroll.add_widget(self.log_label)
        self.add_widget(scroll)

    def on_login(self, *args):
        email = self.email_input.text.strip()
        password = self.pass_input.text
        if not email or not password:
            self.append_log("❌ أدخل البريد وكلمة المرور")
            return

        self.client = QuotexClient(
            on_log=self.append_log,
            on_auth=self.on_auth,
            on_balance=self.on_balance,
            on_tick=self.on_tick,
            on_order=self.on_order)
        self.client.login(email, password, demo=True)

    def append_log(self, msg):
        Clock.schedule_once(
            lambda dt: setattr(self.log_label, "text",
                               self.log_label.text + "\n" + msg))

    def on_auth(self, ok):
        Clock.schedule_once(
            lambda dt: setattr(self, "status_text",
                               "✅ متصل" if ok else "❌ فشل"))

    def on_balance(self, data):
        pass

    def on_tick(self, data):
        pass

    def on_order(self, kind, data):
        if kind == "open":
            self.append_log("✅ صفقة مفتوحة")
        elif kind == "close":
            profit = data.get("amount_profit", 0) if data else 0
            self.append_log(f"📊 نتيجة: ${profit}")

    def do_trade(self, direction):
        if not self.client or not self.client.authed:
            self.append_log("❌ سجّل دخول أولاً")
            return
        try:
            amount = float(self.amount_input.text)
        except ValueError:
            amount = 1.0
        asset = self.asset_spinner.text
        self.client.buy(asset, amount, direction, 60)


class QuotexApp(App):
    def build(self):
        self.title = "Quotex Trading"
        return MainLayout()


if __name__ == "__main__":
    QuotexApp().run()
