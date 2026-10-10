import os
import sys
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import pandas as pd
import numpy as np
import yfinance as yf

sys.stdout.reconfigure(line_buffering=True)


TELEGRAM_BOT_TOKEN = "8957698110:AAG3lx7jI7mirFy7xdsoy14hE_3ylgzL-eg"

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Bababey Scanner Calisiyor!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        return

def run_server():
    port = int(os.environ.get("PORT", 10000))
    print(f"[HTTP] Web sunucusu port {port} uzerinde baslatiliyor...", flush=True)
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

def telegram_bildir(mesaj: str, chat_id: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": str(chat_id), "text": mesaj}, timeout=10)
        print(f"[Telegram Yanit]: {r.status_code}", flush=True)
    except Exception as e:
        print(f"[Bildirim Hatasi]: {e}", flush=True)

def calc_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def calc_roc(close: pd.Series, period: int = 12) -> pd.Series:
    return ((close - close.shift(period)) / (close.shift(period) + 1e-9)) * 100

def calc_cci(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20) -> pd.Series:
    tp = (high + low + close) / 3
    sma_tp = tp.rolling(period).mean()
    mad = (tp - sma_tp).abs().rolling(period).mean()
    return (tp - sma_tp) / (0.015 * mad + 1e-9)

PORTFOY = [
    "THYAO.IS", "TUPRS.IS", "ASELS.IS", "EREGL.IS", "KCHOL.IS",
    "BIMAS.IS", "FROTO.IS", "PGSUS.IS", "SISE.IS", "SAHOL.IS",
    "AKBNK.IS", "GARAN.IS", "ISCTR.IS", "YKBNK.IS", "MGROS.IS",
    "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD",
    "AVAX-USD", "LINK-USD", "ADA-USD", "DOT-USD", "NEAR-USD",
    "NVDA", "AAPL", "MSFT", "AMZN", "GC=F"
]

def portfoy_metrik_tara():
    sonuclar = []
    print("[Tarama] Metrikler hesaplaniyor...", flush=True)
    for sembol in PORTFOY:
        try:
            df = yf.download(sembol, period="1mo", interval="1h", progress=False)
            if df.empty or len(df) < 30:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            c = df['Close']
            h = df['High']
            l = df['Low']

            fiyat = float(c.iloc[-1])
            atr_val = float(calc_atr(h, l, c, 14).iloc[-1])
            atr_yuzde = (atr_val / fiyat) * 100
            roc_val = float(calc_roc(c, 12).iloc[-1])
            cci_val = float(calc_cci(h, l, c, 20).iloc[-1])

            sonuclar.append({
                "sembol": sembol,
                "fiyat": fiyat,
                "roc": roc_val,
                "atr_pct": atr_yuzde,
                "cci": cci_val
            })
        except Exception:
            continue

    if not sonuclar:
        return "❌ Veri alinamadi."

    df_res = pd.DataFrame(sonuclar)

    max_roc = df_res.loc[df_res['roc'].idxmax()]
    min_roc = df_res.loc[df_res['roc'].idxmin()]

    max_atr = df_res.loc[df_res['atr_pct'].idxmax()]
    min_atr = df_res.loc[df_res['atr_pct'].idxmin()]

    max_cci = df_res.loc[df_res['cci'].idxmax()]
    min_cci = df_res.loc[df_res['cci'].idxmin()]

    rapor = (
        "👑 BABABEY QUANT SCANNER\n"
        "📊 ROC | ATR% | CCI UÇ DEĞER RAPORU\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🚀 EN YÜKSEK DEĞERLER (Momentum Liderleri):\n"
        f"• Max ROC (İvme): {max_roc['sembol']} ➔ %{max_roc['roc']:.2f}\n"
        f"• Max ATR% (Volatilite): {max_atr['sembol']} ➔ %{max_atr['atr_pct']:.2f}\n"
        f"• Max CCI (Kanal Aşımı): {max_cci['sembol']} ➔ {max_cci['cci']:.1f}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🧊 EN DÜŞÜK DEĞERLER (Dip & Sıkışma Adayları):\n"
        f"• Min ROC (Dip/Aşırı Satım): {min_roc['sembol']} ➔ %{min_roc['roc']:.2f}\n"
        f"• Min ATR% (Sıkışma/Squeeze): {min_atr['sembol']} ➔ %{min_atr['atr_pct']:.2f}\n"
        f"• Min CCI (Dip Dönüş Adayı): {min_cci['sembol']} ➔ {min_cci['cci']:.1f}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⚡️ Anlık tarama için: /tara"
    )
    return rapor

def dinleyici():
    print(">>> TELEGRAM LISTENER AKTIF EDILDI <<<", flush=True)
    son_id = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
            res = requests.get(url, params={"offset": son_id + 1, "timeout": 15}, timeout=20).json()
            for u in res.get("result", []):
                son_id = u["update_id"]
                msg = u.get("message") or u.get("edited_message")
                if not msg:
                    continue

                chat_id = str(msg.get("chat", {}).get("id", ""))
                text = msg.get("text", "").strip().lower()

                print(f"[Gelen Mesaj] Chat: {chat_id} | Metin: {text}", flush=True)

                if text in ["/start", "/yardim", "/help"]:
                    telegram_bildir("👑 Bababey Scanner aktif!\n/tara yazarak anlık uç değer raporu alabilirsiniz.", chat_id)
                elif text in ["/tara", "tara"]:
                    telegram_bildir("⏳ Piyasa taranıyor, lütfen bekleyin...", chat_id)
                    rapor = portfoy_metrik_tara()
                    telegram_bildir(rapor, chat_id)
        except Exception as e:
            print(f"[Polling Hatasi]: {e}", flush=True)
        time.sleep(1)


threading.Thread(target=dinleyici, daemon=True).start()


if __name__ == "__main__":
    run_server()
