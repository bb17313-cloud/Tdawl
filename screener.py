"""
Saudi Stock Screener - للتشغيل مرة واحدة (GitHub Actions)
"""

import os
import requests
import pandas as pd
from datetime import datetime, time
import pytz
import logging
import time as time_module
from typing import List, Dict, Optional

# ====================== الإعدادات من Secrets ======================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
API_KEY = os.getenv("API_KEY")

BASE_URL = "https://api.sahmk.sa/api/v1"
HEADERS = {"X-API-Key": API_KEY}

# معايير الفحص
MIN_CHANGE_PERCENT = 0.75
MIN_RVOL = 0.9
MIN_CURRENT_VOLUME = 100_000
MIN_PRICE = 1.0

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_riyadh_time() -> str:
    riyadh = pytz.timezone("Asia/Riyadh")
    return datetime.now(riyadh).strftime("%Y-%m-%d %H:%M:%S")


def is_market_open() -> bool:
    riyadh = pytz.timezone("Asia/Riyadh")
    now = datetime.now(riyadh).time()
    return time(9, 45) <= now <= time(15, 15)


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


def run_screener() -> pd.DataFrame:
    results = []
    leaders = get_market_volume_leaders(limit=80)
    symbols = [item["symbol"] for item in leaders if "symbol" in item]

    logger.info(f"Scanning {len(symbols)} symbols...")

    for symbol in symbols:
        try:
            quote = get_quote(symbol)
            if not quote:
                continue

            change_pct = quote.get("change_percent") or 0
            volume = quote.get("volume") or 0
            price = quote.get("price") or 0
            name = quote.get("name") or quote.get("name_en") or ""

            if price <= MIN_PRICE or volume < MIN_CURRENT_VOLUME or change_pct < MIN_CHANGE_PERCENT:
                continue

            avg_vol = get_avg_volume(symbol)
            rvol = (volume / avg_vol) if avg_vol and avg_vol > 0 else None
            if rvol is None or rvol < MIN_RVOL:
                continue

            company = get_company(symbol)
            sector = ""
            industry = ""

            if company:
                sector = company.get("sector_name") or company.get("sector_name_ar") or ""
                industry = (
                    company.get("industry")
                    or company.get("industry_name")
                    or company.get("industry_name_ar")
                    or ""
                )

            results.append({
                "Symbol": symbol,
                "Name": name,
                "Sector": sector,
                "Industry": industry,
                "Price": price,
                "Change%": change_pct,
                "Volume": volume,
                "RVOL": rvol,
            })

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
        msg += f"نسبة التغيير من الافتتاح: `{row._5:+.2f}%`\n"
        msg += f"Vol: `{row.Volume:,}`\n"
        msg += f"[TradingView]({tv_link})\n"
        msg += "────────────────────\n\n"

    return msg


def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    r = requests.post(url, json=payload, timeout=15)
    r.raise_for_status()
    logger.info("Message sent to Telegram")


def main():
    if not all([TELEGRAM_TOKEN, CHAT_ID, API_KEY]):
        raise ValueError("Missing secrets: TELEGRAM_TOKEN, CHAT_ID, or API_KEY")

    logger.info(f"Starting scan at {get_riyadh_time()}")
    df = run_screener()
    msg = format_message(df)

    if msg:
        send_telegram(msg)
        logger.info(f"Found {len(df)} stocks")
    else:
        logger.info("No stocks matched the criteria")
        # يمكنك إلغاء التعليق إذا تبي رسالة حتى لو ما فيه أسهم
        # send_telegram(f"⏳ لا توجد أسهم تطابق المعايير\n⏰ {get_riyadh_time()}")


if __name__ == "__main__":
    main()
