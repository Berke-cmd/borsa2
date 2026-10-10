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
ISLENEN_MESAJLAR = set()
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

def calc_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14):
    plus_dm = high.diff()
    minus_dm = low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm > 0] = 0

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.rolling(period).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1/period).mean() / (atr + 1e-9))
    minus_di = 100 * (abs(minus_dm).ewm(alpha=1/period).mean() / (atr + 1e-9))
    dx = (abs(plus_di - minus_di) / (abs(plus_di + minus_di) + 1e-9)) * 100
    adx = dx.rolling(period).mean()
    return adx

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
        adx_series = calc_adx(h, l, c, 14)
        adx = float(adx_series.iloc[-1]) if not adx_series.empty and not np.isnan(adx_series.iloc[-1]) else 25.0

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
        rvol = vol_son / (vol_ort + 1e-9)
        vol_artisi = (rvol > 1.2)
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

        stop_loss = fiyat - (atr * 1.5)
        tp1 = fiyat + (atr * 2.0)
        tp2 = fiyat + (atr * 3.5)
        tepe_hedef = fiyat + (atr * 5.0)

        sl_pct = ((stop_loss - fiyat) / fiyat) * 100
        tp1_pct = ((tp1 - fiyat) / fiyat) * 100
        tp2_pct = ((tp2 - fiyat) / fiyat) * 100
        tepe_pct = ((tepe_hedef - fiyat) / fiyat) * 100

        return {
            "sembol": sembol,
            "fiyat": fiyat,
            "puan": puan,
            "rsi": rsi,
            "roc": roc,
            "atr": atr,
            "atr_pct": atr_pct,
            "cci": cci,
            "adx": adx,
            "rvol": rvol,
            "stop_loss": stop_loss,
            "sl_pct": sl_pct,
            "tp1": tp1,
            "tp1_pct": tp1_pct,
            "tp2": tp2,
            "tp2_pct": tp2_pct,
            "tepe": tepe_hedef,
            "tepe_pct": tepe_pct
        }
    except Exception:
        return None

def uc_nokta_tarama():
    veriler = []
    for s in TAKIP_LISTESI:
        try:
            df = yf.download(s, period="1mo", interval="1h", progress=False)
            if df.empty or len(df) < 30:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            c = df['Close']
            h = df['High']
            l = df['Low']

            fiyat = float(c.iloc[-1])
            atr_val = float(calc_atr(h, l, c, 14).iloc[-1])
            atr_pct = (atr_val / fiyat) * 100
            roc_val = float(calc_roc(c, 12).iloc[-1])
            cci_val = float(calc_cci(h, l, c, 20).iloc[-1])

            veriler.append({
                "sembol": s,
                "fiyat": fiyat,
                "roc": roc_val,
                "atr_pct": atr_pct,
                "cci": cci_val
            })
        except Exception:
            continue

    if not veriler:
        return "❌ Veri alinamadi."

    df = pd.DataFrame(veriler)

    max_roc = df.loc[df['roc'].idxmax()]
    min_roc = df.loc[df['roc'].idxmin()]
    max_atr = df.loc[df['atr_pct'].idxmax()]
    min_atr = df.loc[df['atr_pct'].idxmin()]
    max_cci = df.loc[df['cci'].idxmax()]
    min_cci = df.loc[df['cci'].idxmin()]

    rapor = (
        "👑 BABABEY QUANT SCANNER\n"
        "📊 ROC | ATR% | CCI UÇ DEĞER FİLTRESİ\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🚀 EN YÜKSEK DEĞERLER (Momentum & Volatilite):\n"
        f"• Max ROC (İvme): {max_roc['sembol']} ➔ %{max_roc['roc']:.2f}\n"
        f"• Max ATR% (Volatilite): {max_atr['sembol']} ➔ %{max_atr['atr_pct']:.2f}\n"
        f"• Max CCI (Kanal Aşımı): {max_cci['sembol']} ➔ {max_cci['cci']:.1f}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🧊 EN DÜŞÜK DEĞERLER (Dip & Sıkışma Adayları):\n"
        f"• Min ROC (Dip/Aşırı Satım): {min_roc['sembol']} ➔ %{min_roc['roc']:.2f}\n"
        f"• Min ATR% (Sıkışma/Squeeze): {min_atr['sembol']} ➔ %{min_atr['atr_pct']:.2f}\n"
        f"• Min CCI (Dip Dönüş Adayı): {min_cci['sembol']} ➔ {min_cci['cci']:.1f}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⚡️ Tekrar taramak için: /uc"
    )
    return rapor

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
    rapor += "⚡️ GÜNÜN UÇ NOKTALARI (ROC / ATR / CCI):\n"
    rapor += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    rapor += f"🚀 Max ROC (Güçlü İvme): {max_roc['sembol']} ➔ %{max_roc['roc']:.2f}\n"
    rapor += f"🚀 Max ATR% (Yüksek Volatilite): {max_atr['sembol']} ➔ %{max_atr['atr_pct']:.2f}\n"
    rapor += f"🚀 Max CCI (Aşırı Alım Zirve): {max_cci['sembol']} ➔ {max_cci['cci']:.1f}\n\n"
    rapor += f"🧊 Min ROC (Dip/Aşırı Satım): {min_roc['sembol']} ➔ %{min_roc['roc']:.2f}\n"
    rapor += f"🧊 Min ATR% (Sıkışma/Squeeze): {min_atr['sembol']} ➔ %{min_atr['atr_pct']:.2f}\n"
    rapor += f"🧊 Min CCI (Dip Dönüş Adayı): {min_cci['sembol']} ➔ {min_cci['cci']:.1f}\n"
    rapor += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    rapor += "⚡️ Anlık: /tara | Sadece Uç Değerler: /uc | Detay: /analiz SEMBOL"

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
            res = requests.get(url, params={"offset": son_id, "timeout": 20}, timeout=25).json()

            if "result" in res and res["result"]:
                for u in res["result"]:
                    son_id = u["update_id"] + 1

                    msg = u.get("message") or u.get("edited_message")
                    if not msg:
                        continue

                    msg_id = msg.get("message_id")
                    if msg_id in ISLENEN_MESAJLAR:
                        continue
                    ISLENEN_MESAJLAR.add(msg_id)

                    if len(ISLENEN_MESAJLAR) > 1000:
                        ISLENEN_MESAJLAR.clear()

                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    if chat_id:
                        KAYITLI_CHATLER.add(chat_id)

                    text = msg.get("text", "").strip()
                    parts = text.split()
                    komut = parts[0].lower() if parts else ""

                    print(f"--> [MESAJ GELDI] Chat: {chat_id} | Icerik: {text}", flush=True)

                    if komut in ["/start", "/help", "/yardim"]:
                        yardim = (
                            "👑 Bababey Scanner Komutları:\n"
                            "━━━━━━━━━━━━━━━━━━━━\n"
                            "• /tara ➔ 18 parametreli A++ tarama ve uç değerleri listeler\n"
                            "• /uc ➔ Sadece listedeki ROC, ATR% ve CCI uç değerlerini tarar\n"
                            "• /analiz SEMBOL ➔ Kademeli detaylı teknik rapor üretir\n"
                            "• /ekle SEMBOL ➔ Takip listesine ekler\n"
                            "• /sil SEMBOL ➔ Takip listesinden çıkarır\n"
                            "• /liste ➔ Takip listesini döker"
                        )
                        telegram_bildir(yardim, chat_id)

                    elif komut in ["/tara", "tara"]:
                        if is_manual_scanning:
                            telegram_bildir("⚠️ Zaten bir tarama devam ediyor, lütfen bekleyin...", chat_id)
                            continue

                        is_manual_scanning = True
                        telegram_bildir("🚀 18 parametreli A++ kalite tarama başlatıldı...", chat_id)
                        try:
                            sonuc = tum_piyasayi_tara()
                            telegram_bildir(sonuc, chat_id)
                        finally:
                            is_manual_scanning = False

                    elif komut in ["/uc", "uc"]:
                        telegram_bildir("⏳ Listedeki ROC, ATR ve CCI uç değerleri taranıyor...", chat_id)
                        sonuc = uc_nokta_tarama()
                        telegram_bildir(sonuc, chat_id)

                    elif komut in ["/analiz", "/analizi"] and len(parts) > 1:
                        target = parts[1].upper()
                        telegram_bildir(f"🔍 {target} için analiz hazırlanıyor...", chat_id)
                        res = sembol_detayli_analiz(target)
                        if res:
                            trend_metin = "Güçlü Trend" if res['adx'] >= 25 else "Zayıf / Yatay"
                            hacim_metin = "Yüksek Kurumsal Hacim" if res['rvol'] >= 1.2 else "Normal Hacim"
                            sinyal_durum = "🔥 A++ Güçlü Alım" if res['puan'] >= 14 else "⏳ Beklemede"

                            roc_filtre = "Zirve Aşırı İvme" if res['roc'] > 5 else ("Dip/Aşırı Satım" if res['roc'] < -5 else "Normal")
                            atr_filtre = "Yüksek Volatilite" if res['atr_pct'] > 1.5 else ("Sıkışma/Squeeze" if res['atr_pct'] < 0.3 else "Dengeli")
                            cci_filtre = "Kanal Dışı Aşırı Alım" if res['cci'] > 100 else ("Dip Bölgesi" if res['cci'] < -100 else "Nötr")

                            rapor = (
                                f"📊 18 PARAMETRELİ ANALİZ RAPORU: {target}\n"
                                "━━━━━━━━━━━━━━━\n"
                                "📊 TEKNİK ANALİZ VERİLERİ:\n"
                                f"• Uygunluk Skoru: {res['puan']} / 18\n"
                                f"• Trend Gücü (ADX): {res['adx']:.1f} ({trend_metin})\n"
                                f"• Momentum (RSI): {res['rsi']:.1f}\n"
                                f"• Hacim Patlaması (RVOL): {res['rvol']:.2f}x ({hacim_metin})\n"
                                f"• Sinyal Durumu: {sinyal_durum}\n"
                                "━━━━━━━━━━━━━━━\n"
                                "⚡️ ROC | ATR | CCI UÇ DEĞER FİLTRESİ:\n"
                                f"• ROC (İvme): %{res['roc']:.2f} ➔ {roc_filtre}\n"
                                f"• ATR% (Volatilite): %{res['atr_pct']:.2f} ➔ {atr_filtre}\n"
                                f"• CCI (Kanal): {res['cci']:.1f} ➔ {cci_filtre}\n"
                                "━━━━━━━━━━━━━━━\n"
                                "📍 İŞLEM & FİYAT KADEMELERİ:\n"
                                f"💵 Giriş Fiyatı: {res['fiyat']:.4f}\n"
                                f"🛑 Stop-Loss: {res['stop_loss']:.4f} ({res['sl_pct']:.2f}%)\n"
                                f"🥇 1. Hedef (TP1): {res['tp1']:.4f} (+%{res['tp1_pct']:.2f})\n"
                                f"🥈 2. Aralık (TP2): {res['tp2']:.4f} (+%{res['tp2_pct']:.2f})\n"
                                f"🏁 Yükseliş Bitiş Noktası (Tepe Projeksiyonu): {res['tepe']:.4f} (+%{res['tepe_pct']:.2f})\n"
                                "⚙️ Tür: 3x İzole"
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
