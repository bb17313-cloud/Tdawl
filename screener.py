"""
Saudi Stock Screener - Telegram Bot (Full Updated)
ساعات التداول: 9:45 – 15:15
المعايير: Change > 0.75% | RVOL > 0.9 | Volume > 100K | Price > 1
عدم التكرار: لا يُعاد التنبيه إلا إذا ارتفع السعر
"""

import requests
import pandas as pd
from datetime import datetime, time
import pytz
import logging
import time as time_module
from typing import List, Dict, Optional

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ====================== الإعدادات ======================
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"      # من @BotFather
CHAT_ID = "YOUR_CHAT_ID"                        # ضع رقم الشات هنا
API_KEY = "YOUR_SAHMK_API_KEY"                  # من https://sahmk.sa/developers

BASE_URL = "https://api.sahmk.sa/api/v1"
HEADERS = {"X-API-Key": API_KEY}

# معايير الفحص
MIN_CHANGE_PERCENT = 0.75
MIN_RVOL = 0.9
MIN_CURRENT_VOLUME = 100_000
MIN_PRICE = 1.0

# كل كم دقيقة يفحص تلقائياً
AUTO_SCAN_INTERVAL_MINUTES = 10

# تخزين آخر سعر تم التنبيه عليه لكل سهم
last_alerted_price: Dict[str, float] = {}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ====================== أدوات الوقت ======================
def is_market_open() -> bool:
    riyadh = pytz.timezone("Asia/Riyadh")
    now = datetime.now(riyadh).time()
    return time(9, 45) <= now <= time(15, 15)


def get_riyadh_time() -> str:
    riyadh = pytz.timezone("Asia/Riyadh")
    return datetime.now(riyadh).strftime("%Y-%m-%d %H:%M:%S")


# ====================== جلب البيانات ======================
def get_market_volume_leaders(limit: int = 80) -> List[Dict]:
    url = f"{BASE_URL}/market/volume/"
    params = {"limit": limit, "index": "TASI"}
    r = requests.get(url, headers=HEADERS, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    return data.get("results", data) if isinstance(data, dict) else data


def get_quote(symbol: str) -> Optional[Dict]:
    url = f"{BASE_URL}/quote/{symbol}/"
    r = requests.get(url, headers=HEADERS, timeout=10)
    return r.json() if r.status_code == 200 else None


def get_company(symbol: str) -> Optional[Dict]:
    url = f"{BASE_URL}/company/{symbol}/"
    r = requests.get(url, headers=HEADERS, timeout=10)
    return r.json() if r.status_code == 200 else None


def get_avg_volume(symbol: str, days: int = 20) -> Optional[float]:
    url = f"{BASE_URL}/historical/{symbol}/"
    params = {"interval": "1d", "limit": days + 5}
    r = requests.get(url, headers=HEADERS, params=params, timeout=15)
    if r.status_code != 200:
        return None
    data = r.json()
    bars = data.get("data") or data.get("results") or data
    if not bars or len(bars) < 5:
        return None
    volumes = [b.get("volume", 0) for b in bars[-days:] if b.get("volume")]
    return sum(volumes) / len(volumes) if volumes else None


# ====================== الفحص الرئيسي ======================
def run_screener() -> pd.DataFrame:
    results = []
    leaders = get_market_volume_leaders(limit=80)
    symbols = [item["symbol"] for item in leaders if "symbol" in item]

    for symbol in symbols:
        try:
            quote = get_quote(symbol)
            if not quote:
                continue

            change_pct = quote.get("change_percent") or 0
            volume = quote.get("volume") or 0
            price = quote.get("price") or 0
            name = quote.get("name") or quote.get("name_en") or ""

            # الفلاتر الأساسية
            if price <= MIN_PRICE:
                continue
            if volume < MIN_CURRENT_VOLUME:
                continue
            if change_pct < MIN_CHANGE_PERCENT:
                continue

            # متوسط الحجم + RVOL
            avg_vol = get_avg_volume(symbol)
            rvol = (volume / avg_vol) if avg_vol and avg_vol > 0 else None
            if rvol is None or rvol < MIN_RVOL:
                continue

            # ========== منطق عدم التكرار ==========
            # لا نرسل التنبيه مرة أخرى إلا إذا ارتفع السعر
            if symbol in last_alerted_price:
                if price <= last_alerted_price[symbol]:
                    continue
            # =====================================

            # بيانات الشركة
            company = get_company(symbol)
            sector = ""
            industry = ""
            float_shares = None

            if company:
                sector = (
                    company.get("sector_name")
                    or company.get("sector_name_ar")
                    or ""
                )
                industry = (
                    company.get("industry")
                    or company.get("industry_name")
                    or company.get("industry_name_ar")
                    or ""
                )
                if company.get("fundamentals"):
                    float_shares = company["fundamentals"].get("float_shares")

            liquidity = quote.get("liquidity") or {}
            net_value = liquidity.get("net_value")

            results.append({
                "Symbol": symbol,
                "Name": name,
                "Sector": sector,
                "Industry": industry,
                "Price": price,
                "Change%": change_pct,
                "Volume": volume,
                "AvgVolume": avg_vol,
                "RVOL": rvol,
                "Value": quote.get("value") or 0,
                "Float": float_shares,
                "NetLiq": net_value,
            })

            # تحديث آخر سعر تم التنبيه عليه
            last_alerted_price[symbol] = price

            time_module.sleep(0.30)

        except Exception as e:
            logger.warning(f"{symbol}: {e}")
            continue

    df = pd.DataFrame(results)
    if not df.empty:
        df = df.sort_values("RVOL", ascending=False)
    return df


def format_message(df: pd.DataFrame) -> Optional[str]:
    if df.empty:
        return None

    msg = f"🇸🇦 *تنبيهات السوق*\n"
    msg += f"⏰ {get_riyadh_time()}\n"
    msg += "━━━━━━━━━━━━━━━━━━━━\n\n"

    for i, row in enumerate(df.itertuples(), 1):
        tv_link = f"https://www.tradingview.com/symbols/TADAWUL-{row.Symbol}/"

        msg += f"🔔 *تنبيه #{i}*\n"
        msg += f"الرمز: `{row.Symbol}`\n"
        msg += f"الاسم: {row.Name}\n"
        msg += f"القطاع: {row.Sector or '-'}\n"
        msg += f"الصناعة: {row.Industry or '-'}\n"
        msg += f"السعر الحالي: `{row.Price:.2f}`\n"
        msg += f"نسبة التغيير من الافتتاح: `{row._5:+.2f}%`\n"  # Change%
        msg += f"Vol: `{row.Volume:,}`\n"
        msg += f"[TradingView]({tv_link})\n"
        msg += "────────────────────\n\n"

    return msg


# ====================== أوامر البوت ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🇸🇦 *بوت فحص أسهم تداول*\n\n"
        "الأوامر المتاحة:\n"
        "/scan - تشغيل الفحص الآن\n"
        "/status - حالة السوق والوقت\n"
        "/help - المساعدة\n\n"
        f"*المعايير الحالية:*\n"
        f"• Change > {MIN_CHANGE_PERCENT}%\n"
        f"• RVOL > {MIN_RVOL}\n"
        f"• Volume > 100,000\n"
        f"• Price > 1\n\n"
        "⚠️ لا يُعاد إرسال نفس السهم إلا إذا ارتفع السعر"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    open_status = "✅ مفتوح" if is_market_open() else "❌ مغلق"
    text = (
        f"⏰ الوقت: `{get_riyadh_time()}`\n"
        f"📈 السوق: {open_status}\n"
        f"🕘 ساعات التداول: 9:45 – 15:15\n"
        f"🔢 عدد الأسهم المخزنة: {len(last_alerted_price)}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 جاري الفحص... انتظر قليلاً")
    try:
        df = run_screener()
        msg = format_message(df)
        if msg:
            await update.message.reply_text(
                msg,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        else:
            await update.message.reply_text("⏳ لا توجد أسهم جديدة تطابق المعايير حالياً.")
    except Exception as e:
        logger.error(f"Scan error: {e}")
        await update.message.reply_text(f"❌ خطأ: {e}")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


# ====================== الفحص التلقائي ======================
async def auto_scan(context: ContextTypes.DEFAULT_TYPE):
    if not is_market_open():
        return

    try:
        df = run_screener()
        msg = format_message(df)
        if msg and CHAT_ID:
            await context.bot.send_message(
                chat_id=CHAT_ID,
                text=msg,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
    except Exception as e:
        logger.error(f"Auto scan error: {e}")


# ====================== التشغيل ======================
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan", scan))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("help", help_cmd))

    # فحص تلقائي كل X دقيقة
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(
            auto_scan,
            interval=AUTO_SCAN_INTERVAL_MINUTES * 60,
            first=15
        )

    print("🤖 البوت يعمل الآن...")
    print(f"⏰ الوقت الحالي: {get_riyadh_time()}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
