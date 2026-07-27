import time
import datetime
import ccxt
import pandas as pd
import requests
import pytz

# إعدادات بوت التلجرام
TELEGRAM_BOT_TOKEN = "8711875284:AAGGERDv9njI0QZ9Fnrc1_tN9xeVLEXtnCc"
TELEGRAM_CHAT_ID = "-1004394911035"

# تهيئة منصة باينانس للفيوتشر
exchange = ccxt.binance({
    'options': {
        'defaultType': 'future',
    },
    'enableRateLimit': True
})

# التوقيت المحلي (السعودية)
ksa_tz = pytz.timezone('Asia/Riyadh')

# الفريمات المطلوبة للمتابعة
TIMEFRAMES = ['15m', '1h', '4h', '1d', '1w']

# ذاكرة لمنع تكرار الإرسال لنفس الشمعة
sent_signals_cache = set()

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Error sending telegram message: {e}")
        return None

def calculate_indicator_logic(df):
    if len(df) < 50:
        return None, 0, "ضعيف"

    close = df['close']
    open_p = df['open']
    high = df['high']
    low = df['low']
    volume = df['volume']

    ma25 = close.ewm(span=25).mean()
    ma50 = close.ewm(span=50).mean()
    
    candle_range = (high - low).replace(0, 0.00001)
    close_pos = (close - low) / candle_range
    
    buy_pct = (volume * close_pos).sum() / max((volume * close_pos).sum() + (volume * (1.0 - close_pos)).sum(), 1.0) * 100.0
    
    bull_score = 0.0
    bear_score = 0.0
    
    last_close = close.iloc[-1]
    last_open = open_p.iloc[-1]
    
    if last_close > last_open:
        bull_score += 35.0
    else:
        bear_score += 35.0
        
    if buy_pct >= 60:
        bull_score += 30.0
    else:
        bear_score += 30.0
        
    if last_close > ma25.iloc[-1]:
        bull_score += 20.0
    else:
        bear_score += 20.0
        
    if ma25.iloc[-1] > ma50.iloc[-1]:
        bull_score += 15.0
    else:
        bear_score += 15.0

    score = max(bull_score, bear_score)
    strength = "قوي" if score >= 75 else ("متوسط" if score >= 55 else "ضعيف")

    if bull_score >= 58 and bull_score > bear_score:
        return "BUY", score, strength
    elif bear_score >= 58 and bear_score > bull_score:
        return "SELL", score, strength
    
    return None, 0, "ضعيف"

def check_markets():
    try:
        markets = exchange.load_markets()
        symbols = [symbol for symbol in markets if symbol.endswith('/USDT:USDT') or symbol.endswith(':USDT')]
        
        for symbol in symbols:
            clean_name = symbol.split('/')[0].replace(':', '')
            hashtag = f"#{clean_name}.P#"
            
            for tf in TIMEFRAMES:
                try:
                    ohlcv = exchange.fetch_ohlcv(symbol, tf, limit=100)
                    if not ohlcv:
                        continue
                    
                    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    
                    # التحقق من توقيت الشمعة الحقيقية بالمللي ثانية
                    candle_timestamp = df['timestamp'].iloc[-1]
                    signal_key = f"{clean_name}_{tf}_{candle_timestamp}"
                    
                    if signal_key in sent_signals_cache:
                        continue
                        
                    current_price = df['close'].iloc[-1]
                    signal_type, score, strength = calculate_indicator_logic(df)
                    
                    if signal_type:
                        # قفل التنبيه لهذه الشمعة فوراً لمنع التكرار
                        sent_signals_cache.add(signal_key)
                        if len(sent_signals_cache) > 4000:
                            sent_signals_cache.clear()
                            
                        current_time_ksa = datetime.datetime.now(ksa_tz).strftime('%Y-%m-%d %H:%M:%S')
                        tv_link = f"https://www.tradingview.com/chart/?symbol=BINANCE:{clean_name}P"
                        binance_link = f"https://www.binance.com/en/futures/{clean_name}USDT"
                        
                        if signal_type == "BUY":
                            message = (
                                f"شارة مبكرة - فرصة شراء جديدة!\n"
                                f"-----------------------------------\n"
                                f"💰 العملة: {hashtag}\n"
                                f"⏰ الفريم: {tf}\n"
                                f"💲 السعر الحالي: {current_price}\n\n"
                                f"🟢 النوع: علامة مبكرة للشراء (Buy Signal)\n"
                                f"⚡️ وقت الظهور: {current_time_ksa} (توقيت السعودية)\n"
                                f"⏳ حالة الشمعة: قيد التكوين ⚠️\n"
                                f"🔥 قوة الإشارة: {strength} ({score:.1f}%)\n\n"
                                f"🔗 [TradingView]({tv_link}) | [Binance Futures]({binance_link})"
                            )
                        else:
                            message = (
                                f"🚨 إشارة مبكرة - فرصة بيع جديدة!\n"
                                f"-----------------------------------\n"
                                f"💰 العملة: {hashtag}\n"
                                f"⏰ الفريم: {tf}\n"
                                f"💲 السعر الحالي: {current_price}\n\n"
                                f"🔴 النوع: علامة مبكرة للبيع (Sell Signal)\n"
                                f"⚡️ وقت الظهور: {current_time_ksa} (توقيت السعودية)\n"
                                f"⏳ حالة الشمعة: قيد التكوين ⚠️\n"
                                f"🔥 قوة الإشارة: {strength} ({score:.1f}%)\n\n"
                                f"🔗 [TradingView]({tv_link}) | [Binance Futures]({binance_link})"
                            )
                        
                        send_telegram_message(message)
                        time.sleep(0.1)
                        
                except Exception as e:
                    continue
                
    except Exception as e:
        print(f"Error loading markets: {e}")

if __name__ == "__main__":
    print("Bot is running with strict synchronization...")
    test_time = datetime.datetime.now(ksa_tz).strftime('%Y-%m-%d %H:%M:%S')
    send_telegram_message(f"✅ تم ضبط دقة توقيت الإشارات ومنع العشوائية بنجاح!\n⚡️ الوقت: {test_time}")
    
    while True:
        check_markets()
        # تقليص وقت الانتظار لجعل الدورة أسرع ومزامنة التوقيت بدقة عالية
        time.sleep(15)
