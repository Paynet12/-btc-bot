import time
import requests
import pandas as pd
import pandas_ta as ta
import telebot

# --- SIZNING TO'LIQ TAYYOR MA'LUMOTLARINGIZ ---
TELEGRAM_TOKEN = "8018566176:AAEmPV70inx5Cj1M9Bcc6Nj05piWWgV4BuY"
CHAT_ID = "876547542"

bot = telebot.TeleBot(TELEGRAM_TOKEN)

def get_binance_data(interval, limit=100):
    url = "https://binance.com"
    params = {"symbol": "BTCUSDT", "interval": interval, "limit": limit}
    response = requests.get(url, params=params).json()
    
    df = pd.DataFrame(response, columns=[
        'time', 'open', 'high', 'low', 'close', 'volume', 
        'close_time', 'q_volume', 'trades', 'taker_base', 'taker_quote', 'ignore'
    ])
    df['open'] = df['open'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['close'] = df['close'].astype(float)
    return df

def analyze_smc():
    try:
        # 1. Turli vaqt oraliqlaridan (MTF) ma'lumotlarni yuklash
        df_15m = get_binance_data("15m")
        df_1h = get_binance_data("1h")
        df_4h = get_binance_data("4h")
        
        current_price = df_15m.iloc[-1]['close']
        
        # --- 4H VA 1H SMART MONEY VA LIKVIDLIK TAHLILI ---
        # Katta taymfreymdagi asosiy likvidlik zonalari (BSL / SSL)
        highs_4h = df_4h['high'].tail(30).max()
        lows_4h = df_4h['low'].tail(30).min()
        
        highs_1h = df_1h['high'].tail(30).max()
        lows_1h = df_1h['low'].tail(30).min()
        
        # Indikatorlar (Trendni aniqlash uchun)
        df_15m['EMA_200'] = ta.ema(df_15m['close'], length=200)
        df_1h['EMA_50'] = ta.ema(df_1h['close'], length=50)
        df_15m['RSI'] = ta.rsi(df_15m['close'], length=14)
        
        last_15m = df_15m.iloc[-1]
        last_1h = df_1h.iloc[-1]
        rsi_val = round(last_15m['RSI'], 2)
        
        # --- FOIZLARNI HISOBLASH ALGORITMI (SCORING) ---
        bay_score = 0
        sell_score = 0
        
        # A. 4H va 1H Global Trend yo'nalishi
        if current_price > last_1h['EMA_50']:
            bay_score += 25  # 1H da trend o'suvchi
        else:
            sell_score += 25
            
        if current_price > last_15m['EMA_200']:
            bay_score += 20  # 15m da narx uzoq muddatli trend ustida
        else:
            sell_score += 20
            
        # B. 4H/1H Likvidlik Hovuzlari (Liquidity Pools) va Re-test
        # Agar narx 1H/4H pastki stoplariga (SSL) yaqinlashsa - xarid kuchayadi
        if abs(current_price - lows_4h) < (current_price * 0.005) or abs(current_price - lows_1h) < (current_price * 0.003):
            bay_score += 35  # Smart Money xarid zonasi (SSL Sweep)
        
        # Agar narx yuqori stoplarga (BSL) yaqinlashsa - sotuv kuchayadi
        if abs(current_price - highs_4h) < (current_price * 0.005) or abs(current_price - highs_1h) < (current_price * 0.003):
            sell_score += 35  # Smart Money sotish zonasi (BSL Sweep)
            
        # C. 15m Lokal Momentum (RSI)
        if rsi_val < 35:
            bay_score += 20  # Haddan tashqari sotilgan (Oversold)
        elif rsi_val > 65:
            sell_score += 20  # Haddan tashqari sotib olingan (Overbought)
        else:
            bay_score += 10
            sell_score += 10
            
        # D. Asosiy Order Block (OB) aniqlash (1H bo'yicha)
        # Oxirgi sham yutib yuborish (Engulfing) bo'lsa
        if df_1h.iloc[-2]['close'] > df_1h.iloc[-2]['open'] and current_price > df_1h.iloc[-2]['high']:
            bay_score += 15  # Demand Order Block kuchli
        elif df_1h.iloc[-2]['close'] < df_1h.iloc[-2]['open'] and current_price < df_1h.iloc[-2]['low']:
            sell_score += 15  # Supply Order Block kuchli

        # Yakuniy foiz ko'rsatkichini chiqarish
        total_score = bay_score + sell_score
        bay_percent = round((bay_score / total_score) * 100)
        sell_percent = 100 - bay_percent
        
        # Bozor yo'nalishi signali
        if bay_percent > 55:
            signal = "🟢 KUCHLI BAY (Long)"
        elif sell_percent > 55:
            signal = "🔴 KUCHLI SELL (Short)"
        else:
            signal = "🟡 NEUTRAL (Kanal ichida savdo)"
            
        # Telegram xabari matni formatting
        message = (
            f"📊 *BTC/USDT SMART MONEY HISOBOTI (15M)*\n\n"
            f"💰 *Hozirgi narx:* `${current_price:.2f}`\n"
            f"📈 *15m RSI:* `{rsi_val}`\n\n"
            f"🔍 *KATTA TAYMFREYM LIKVIDLIKLARI:* \n"
            f"🛑 *4H/1H SSL (Pastki stoplar):* `${min(lows_4h, lows_1h):.2f}`\n"
            f"🎯 *4H/1H BSL (Yuqori stoplar):* `${max(highs_4h, highs_1h):.2f}`\n\n"
            f"⚡ *SMART MONEY TAHLILI:* {signal}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🟢 *Xarid Ehtimoli (BAY):* `{bay_percent}%`\n"
            f"🔴 *Sotish Ehtimoli (SELL):* `{sell_percent}%`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🕒 _Keyingi tahlil 15 daqiqadan so'ng yuboriladi._"
        )
        
        bot.send_message(CHAT_ID, message, parse_mode="Markdown")
        print("Tahlil Telegramga yuborildi!")
        
    except Exception as e:
        print(f"Xatolik yuz berdi: {e}")

# Ishga tushirish tsikli (Har 15 daqiqada bir marta)
if __name__ == "__main__":
    print("SMC Bot muvaffaqiyatli ishga tushdi...")
    while True:
        analyze_smc()
        time.sleep(900)  # 900 soniya = 15 minut
