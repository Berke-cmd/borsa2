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

TAKIP_LISTESI = [
    "THYAO.IS", "TUPRS.IS", "ASELS.IS", "EREGL.IS", "KCHOL.IS",
    "BIMAS.IS", "FROTO.IS", "PGSUS.IS", "SISE.IS", "SAHOL.IS",
    "AKBNK.IS", "GARAN.IS", "ISCTR.IS", "YKBNK.IS", "MGROS.IS",
    "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD",
    "AVAX-USD", "LINK-USD", "ADA-USD", "DOT-USD", "NEAR-USD",
    "NVDA", "AAPL", "MSFT", "AMZN", "GC=F"
]

KAYITLI_CHATLER = set()
SON_SINYALLER = {}
is_manual_scanning = False

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
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

def telegram_bildir(mesaj: str, chat_id: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": str(chat_id), "text": mesaj}, timeout=10)
    except Exception as e:
        print(f"[Bildirim Hatasi]: {e}", flush=True)

def herkese_bildir(mesaj: str):
    for cid in list(KAYITLI_CHATLER):
        telegram_bildir(mesaj, cid)

def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def calc_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def calc_roc(close: pd.Series, period: int = 12) -> pd.Series:
    return ((close - close.shift(period)) / (close.shift(period) + 1e-9)) * 100

def calc_cci(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20) -> pd.Series:
    tp = (high + low + close) / 3
    sma_tp = tp.rolling(period).mean()
    mad = (tp - sma_tp).abs().rolling(period).mean()
    return (tp - sma_tp) / (0.015 * mad + 1e-9)

def calc_stoch(high: pd.Series, low: pd.Series, close: pd.Series, k_period: int = 14, d_period: int = 3):
    lowest_low = low.rolling(k_period).min()
    highest_high = high.rolling(k_period).max()
    k = 100 * ((close - lowest_low) / (highest_high - lowest_low + 1e-9))
    d = k.rolling(d_period).mean()
    return k, d

def calc_bollinger(close: pd.Series, period: int = 20, std_dev: int = 2):
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    return sma + (std * std_dev), sma, sma - (std * std_dev)

def calc_macd(close: pd.Series):
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    return macd_line, signal_line

def sembol_detayli_analiz(sembol: str):
    try:
        df = yf.download(sembol, period="3mo", interval="1h", progress=False)
        if df.empty or len(df) < 50:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        c = df['Close']
        h = df['High']
        l = df['Low']
        v = df['Volume']

        fiyat = float(c.iloc[-1])

        ema9 = float(c.ewm(span=9).mean().iloc[-1])
        ema21 = float(c.ewm(span=21).mean().iloc[-1])
        ema50 = float(c.ewm(span=50).mean().iloc[-1])
        sma200 = float(c.rolling(min(len(c), 200)).mean().iloc[-1])

        rsi = float(calc_rsi(c, 14).iloc[-1])
        roc = float(calc_roc(c, 12).iloc[-1])
        cci = float(calc_cci(h, l, c, 20).iloc[-1])
        stoch_k, stoch_d = calc_stoch(h, l, c)
        sk, sd = float(stoch_k.iloc[-1]), float(stoch_d.iloc[-1])

        atr = float(calc_atr(h, l, c, 14).iloc[-1])
        atr_pct = (atr / fiyat) * 100
        bb_upper, bb_mid, bb_lower = calc_bollinger(c)
        b_up, b_low = float(bb_upper.iloc[-1]), float(bb_lower.iloc[-1])

        macd, macd_sig = calc_macd(c)
        m_val, m_sig = float(macd.iloc[-1]), float(macd_sig.iloc[-1])

        vol_ort = float(v.rolling(20).mean().iloc[-1])
        vol_son = float(v.iloc[-1])
        vol_artisi = (vol_son > vol_ort * 1.2)
        fiyat_hh = (h.iloc[-1] > h.iloc[-2])
        fiyat_hl = (l.iloc[-1] > l.iloc[-2])
        dip_mesafe = ((fiyat - b_low) / fiyat) * 100

        puan = 0
        if fiyat > ema9: puan += 1
        if ema9 > ema21: puan += 1
        if fiyat > ema50: puan += 1
        if fiyat > sma200: puan += 1
        if 40 <= rsi <= 65: puan += 1
        if roc > 0: puan += 1
        if -100 <= cci <= 100: puan += 1
        if sk > sd: puan += 1
        if sk < 80: puan += 1
        if fiyat > b_low and fiyat < b_up: puan += 1
        if m_val > m_sig: puan += 1
        if m_val > 0: puan += 1
        if vol_artisi: puan += 1
        if fiyat_hh: puan += 1
        if fiyat_hl: puan += 1
        if atr_pct > 0.5: puan += 1
        if c.iloc[-1] > c.iloc[-2]: puan += 1
        if dip_mesafe > 0.5: puan += 1

        return {
            "sembol": sembol,
            "fiyat": fiyat,
            "puan": puan,
            "rsi": rsi,
            "roc": roc,
            "atr_pct": atr_pct,
            "cci": cci
        }
    except Exception:
        return None

def tum_piyasayi_tara():
    veriler = []
    for s in TAKIP_LISTESI:
        res = sembol_detayli_analiz(s)
        if res:
            veriler.append(res)

    if not veriler:
        return "❌ Piyasa verisi alinamadi."

    df = pd.DataFrame(veriler)

    elitler = df[df['puan'] >= 14].sort_values(by="puan", ascending=False)

    max_roc = df.loc[df['roc'].idxmax()]
    min_roc = df.loc[df['roc'].idxmin()]
    max_atr = df.loc[df['atr_pct'].idxmax()]
    min_atr = df.loc[df['atr_pct'].idxmin()]
    max_cci = df.loc[df['cci'].idxmax()]
    min_cci = df.loc[df['cci'].idxmin()]

    rapor = "👑 BABABEY QUANT SCANNER | 18 KRİTERLİ A++ RAPOR\n"
    rapor += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"

    if elitler.empty:
        rapor += "ℹ️ Şu an 18 kriterli A++ şartını (≥14 puan) sağlayan elit sinyal yok.\n\n"
    else:
        rapor += "🚀 A++ KRİTERLERİNİ SAĞLAYAN ELİT VARLIKLAR:\n"
        for _, row in elitler.iterrows():
            rapor += f"• {row['sembol']} | Fiyat: {row['fiyat']:.2f} | Puan: {row['puan']}/18 | RSI: {row['rsi']:.0f} | ROC: %{row['roc']:.1f}\n"
        rapor += "\n"

    rapor += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    rapor += "⚡️ GÜNÜN UÇ NOKTALARI (EKSTRA GÖSTERGELER):\n"
    rapor += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    rapor += f"🚀 Max ROC (Güçlü İvme): {max_roc['sembol']} ➔ %{max_roc['roc']:.2f}\n"
    rapor += f"🚀 Max ATR% (Yüksek Volatilite): {max_atr['sembol']} ➔ %{max_atr['atr_pct']:.2f}\n"
    rapor += f"🚀 Max CCI (Aşırı Alım Zirve): {max_cci['sembol']} ➔ {max_cci['cci']:.1f}\n\n"
    rapor += f"🧊 Min ROC (Dip/Aşırı Satım): {min_roc['sembol']} ➔ %{min_roc['roc']:.2f}\n"
    rapor += f"🧊 Min ATR% (Sıkışma/Squeeze): {min_atr['sembol']} ➔ %{min_atr['atr_pct']:.2f}\n"
    rapor += f"🧊 Min CCI (Dip Dönüş Adayı): {min_cci['sembol']} ➔ {min_cci['cci']:.1f}\n"
    rapor += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    rapor += "⚡️ Anlık: /tara | Detay: /analiz SEMBOL"

    return rapor

def otomatik_tarayici():
    time.sleep(30)
    while True:
        try:
            if KAYITLI_CHATLER:
                for sembol in TAKIP_LISTESI:
                    res = sembol_detayli_analiz(sembol)
                    if res and res["puan"] >= 14:
                        suan = time.time()
                        if sembol in SON_SINYALLER and (suan - SON_SINYALLER[sembol]) < 7200:
                            continue

                        SON_SINYALLER[sembol] = suan
                        otomatik_mesaj = (
                            "🚨 [OTOMATİK SİNYAL ALARMI]\n"
                            f"💎 A++ ELİT FIRSAT YAKALANDI: {res['sembol']}\n"
                            "━━━━━━━━━━━━━━━━━━━━\n"
                            f"• Kalite Puanı: {res['puan']}/18 🔥\n"
                            f"• Güncel Fiyat: {res['fiyat']:.2f}\n"
                            f"• RSI: {res['rsi']:.1f}\n"
                            f"• ROC%: %{res['roc']:.2f}\n"
                            f"• ATR%: %{res['atr_pct']:.2f}\n"
                            f"• CCI: {res['cci']:.1f}\n"
                            "━━━━━━━━━━━━━━━━━━━━\n"
                            "Detaylı inceleme: /analiz " + res['sembol']
                        )
                        herkese_bildir(otomatik_mesaj)
        except Exception as e:
            print(f"[Otopilot Hatasi]: {e}", flush=True)

        time.sleep(900)

def dinleyici():
    global is_manual_scanning
    print(">>> TELEGRAM LISTENER AKTIF EDILDI <<<", flush=True)
    son_id = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
            res = requests.get(url, params={"offset": son_id + 1, "timeout": 20}, timeout=25).json()

            if "result" in res and res["result"]:
                for u in res["result"]:
                    son_id = u["update_id"]
                    msg = u.get("message") or u.get("edited_message")
                    if not msg:
                        continue

                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    if chat_id:
                        KAYITLI_CHATLER.add(chat_id)

                    text = msg.get("text", "").strip()
                    parts = text.split()
                    komut = parts[0].lower() if parts else ""

                    print(f"--> [MESAJ GELDI] Chat: {chat_id} | Icerik: {text}", flush=True)

                    if komut in ["/start", "/help", "/yardim"]:
                        yardim = (
                            "👑 Bababey Scanner Otopilot Aktif!\n"
                            "━━━━━━━━━━━━━━━━━━━━\n"
                            "• Bot arka planda 15 dakikada bir 18 parametreli A++ tarama yapar.\n"
                            "• Elit bir fırsat yakaladığında otomatik olarak bildirim atar.\n\n"
                            "Komutlar:\n"
                            "• /tara ➔ Anlık A++ ve uç değer raporu üretir\n"
                            "• /analiz SEMBOL ➔ Varlığı 18 parametreyle analiz eder\n"
                            "• /ekle SEMBOL ➔ Takip listesine ekler\n"
                            "• /sil SEMBOL ➔ Takip listesinden çıkarır\n"
                            "• /liste ➔ Takip listesini listeler"
                        )
                        telegram_bildir(yardim, chat_id)

                    elif komut in ["/tara", "tara"]:
                        if is_manual_scanning:
                            telegram_bildir("⚠️ Zaten bir tarama devam ediyor, lütfen bekleyin...", chat_id)
                            continue

                        is_manual_scanning = True
                        telegram_bildir("🚀 18 parametreli A++ kalite tarama başlatıldı (ekstra uç noktalar dahil)...", chat_id)
                        try:
                            sonuc = tum_piyasayi_tara()
                            telegram_bildir(sonuc, chat_id)
                        finally:
                            is_manual_scanning = False

                    elif komut == "/analiz" and len(parts) > 1:
                        target = parts[1].upper()
                        telegram_bildir(f"🔍 {target} için 18 parametreli analiz yapılıyor...", chat_id)
                        res = sembol_detayli_analiz(target)
                        if res:
                            rapor = (
                                f"📊 {target} DETAYLI ANALİZ\n"
                                f"━━━━━━━━━━━━━━━━━━━━\n"
                                f"• Fiyat: {res['fiyat']:.2f}\n"
                                f"• Kalite Skoru: {res['puan']}/18\n"
                                f"• RSI: {res['rsi']:.1f}\n"
                                f"• ROC%: %{res['roc']:.2f}\n"
                                f"• ATR%: %{res['atr_pct']:.2f}\n"
                                f"• CCI: {res['cci']:.1f}\n"
                                f"• Sinyal: {'A++ Güçlü Alım' if res['puan'] >= 14 else 'Nötr / İzlemede'}"
                            )
                            telegram_bildir(rapor, chat_id)
                        else:
                            telegram_bildir(f"❌ {target} için veri bulunamadı.", chat_id)

                    elif komut == "/ekle" and len(parts) > 1:
                        target = parts[1].upper()
                        if target not in TAKIP_LISTESI:
                            TAKIP_LISTESI.append(target)
                            telegram_bildir(f"✅ {target} takip listesine eklendi.", chat_id)
                        else:
                            telegram_bildir(f"ℹ️ {target} zaten listede.", chat_id)

                    elif komut == "/sil" and len(parts) > 1:
                        target = parts[1].upper()
                        if target in TAKIP_LISTESI:
                            TAKIP_LISTESI.remove(target)
                            telegram_bildir(f"🗑 {target} listeden çıkarıldı.", chat_id)
                        else:
                            telegram_bildir(f"❌ {target} listede bulunamadı.", chat_id)

                    elif komut == "/liste":
                        txt = "📋 TAKİP EDİLEN VARLIKLAR:\n" + ", ".join(TAKIP_LISTESI)
                        telegram_bildir(txt, chat_id)

        except Exception as e:
            print(f"[Hata Polling]: {e}", flush=True)
        time.sleep(1)

threading.Thread(target=dinleyici, daemon=True).start()
threading.Thread(target=otomatik_tarayici, daemon=True).start()

if __name__ == "__main__":
    run_server()
