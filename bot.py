import os
import time
import requests
import pandas as pd
import numpy as np
from flask import Flask, jsonify
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

TELEGRAM_TOKEN = "8711875284:AAGGERDv9njI0QZ9Fnrc1_tN9xeVLEXtnCc"
CHAT_ID = "-1004394911035"

# جلب جميع عملات الفيوتشر النشطة من باينانس
def get_binance_futures_symbols():
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        symbols = [s['symbol'] for s in data['symbols'] if s['contractType'] == 'PERPETUAL' and s['status'] == 'TRADING']
        return symbols
    except Exception as e:
        print(f"Error fetching symbols: {e}")
    return []

# جلب الشموع التاريخية (Klines)
def get_historical_klines(symbol, interval, limit=100):
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        if isinstance(data, list):
            df = pd.DataFrame(data, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])
            df['close'] = df['close'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            df['open'] = df['open'].astype(float)
            return df
    except Exception as e:
        pass
    return None

# حساب مؤشر RSI وتكتيك الدايفرجنس المخفي (Hidden Divergence)
def calculate_rsi_and_divergence(df, period=14):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # فحص القمم والقيعان للدايفرجنس المخفي بآخر شمعة مغلقة
    if len(df) < 30:
        return None, None
        
    # قاع مخفي صاعد: السعر صنع قاع أعلى، بينما RSI صنع قاع أقل
    lows = df['low'].values
    rsis = df['rsi'].values
    
    # ابسط كشف للدايفرجنس المخفي على آخر قيعان محددة
    # (يمكن توسيع الشروط لتطابق دقة مؤشرك تماماً)
    curr_low = lows[-2]
    prev_low = lows[-15]
    curr_rsi = rsis[-2]
    prev_rsi = rsis[-15]
    
    hidden_bull = (curr_low > prev_low) and (curr_rsi < prev_rsi) and (rsis[-1] > rsis[-2])
    
    curr_high = highs = df['high'].values[-2]
    prev_high = df['high'].values[-15]
    hidden_bear = (curr_high < prev_high) and (curr_rsi > prev_rsi) and (rsis[-1] < rsis[-2])
    
    return hidden_bull, hidden_bear

# إرسال التنبيه إلى تيليجرام بالتنسيق المطلوب
def send_telegram_alert(symbol, interval_str, div_type, price):
    text = f"""🚨 تنبيه دايفرجنس جديد

🪙 العملة: {symbol}#
⏱️ الفريم: {interval_str}
📊 نوع التنبيه: {div_type}
💵 السعر الحالي: {price:.4f}
⏰ الوقت: {time.strftime('%Y-%m-%d %H:%M:%S')}"""

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Telegram error: {e}")

# مهمة الفحص الدورية للعملات
def scan_market():
    symbols = get_binance_futures_symbols()
    intervals = {"15m": "15", "1h": "60"}
    
    for symbol in symbols:
        for binance_tf, label_tf in intervals.items():
            df = get_historical_klines(symbol, binance_tf, limit=50)
            if df is not None and not df.empty:
                h_bull, h_bear = calculate_rsi_and_divergence(df)
                current_price = df['close'].iloc[-2] # شمعة مغلقة لتجنب الإشارات الوهمية
                
                if h_bull:
                    send_telegram_alert(symbol, label_tf, "Hidden Bullish Divergence", current_price)
                if h_bear:
                    send_telegram_alert(symbol, label_tf, "Hidden Bearish Divergence", current_price)
            time.sleep(0.1) # لمنع حظر الطلبات من باينانس

@app.route("/")
def home():
    return "Bot is running successfully!"

if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    # يتم فحص السوق كل دقيقتين لضمان رصد الإغلاق اللحظي للفريمات
    scheduler.add_job(func=scan_market, trigger="interval", minutes=2)
    scheduler.start()
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
