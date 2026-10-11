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

# ====================== معايير الفحص ======================
MIN_CHANGE_PERCENT = 0.5    
MIN_RVOL = 0.1              
MIN_CURRENT_VOLUME = 10_000 
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


def safe_get(url: str, params: Optional[Dict] = None, timeout: int = 15) -> Optional[requests.Response]:
    """دالة ذكية للتعامل مع الـ API وتجنب أخطاء الضغط الزائد (429)"""
    retries = 3
    backoff = 2
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=timeout)
            if r.status_code == 429:
                logger.warning(f"Rate limited (429). Waiting {backoff}s before retry...")
                time_module.sleep(backoff)
                backoff *= 2
                continue
            return r
        except Exception as e:
            if attempt == retries - 1:
                logger.warning(f"Request failed for {url}: {e}")
                return None
            time_module.sleep(1)
    return None


def get_market_volume_leaders(limit: int = 50) -> List[Dict]:
    url = f"{BASE_URL}/market/volume/"
    params = {"limit": limit, "index": "TASI"}
    
    r = safe_get(url, params=params)
    if not r or r.status_code != 200:
        logger.warning("Could not fetch market volume leaders.")
        return []
        
    try:
        data = r.json()
        if isinstance(data, dict):
            for key in ["stocks", "results", "data", "items", "list", "content"]:
                if key in data and isinstance(data[key], list):
                    return data[key]
            logger.warning(f"Unexpected API response structure: {list(data.keys())}")
            return []
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning(f"Error parsing market volume leaders: {e}")
        return []


def get_quote(symbol: str) -> Optional[Dict]:
    url = f"{BASE_URL}/quote/{symbol}/"
    r = safe_get(url, timeout=10)
    if r and r.status_code == 200:
        return r.json()
    return None


def get_company(symbol: str) -> Optional[Dict]:
    url = f"{BASE_URL}/company/{symbol}/"
    r = safe_get(url, timeout=10)
    if r and r.status_code == 200:
        return r.json()
    return None


def get_avg_volume(symbol: str, days: int = 20) -> Optional[float]:
    url = f"{BASE_URL}/historical/{symbol}/"
    params = {"interval": "1d", "limit": days + 5}
    r = safe_get(url, params=params, timeout=15)
    if not r or r.status_code != 200:
        return None
    
    try:
        data = r.json()
        bars = []
        if isinstance(data, dict):
            for key in ["data", "results", "items", "candles", "history"]:
                if key in data and isinstance(data[key], list):
                    bars = data[key]
                    break
        elif isinstance(data, list):
            bars = data

        if not bars or len(bars) < 5:
            return None
        volumes = [b.get("volume", 0) for b in bars[-days:] if isinstance(b, dict) and b.get("volume")]
        return sum(volumes) / len(volumes) if volumes else None
    except Exception:
        return None


def run_screener() -> pd.DataFrame:
    results = []
    leaders = get_market_volume_leaders(limit=50)
    
    if not leaders:
        logger.warning("No leaders returned from API or empty list.")
        return pd.DataFrame()

    symbols = [item.get("symbol") or item.get("code") for item in leaders if isinstance(item, dict)]
    symbols = [s for s in symbols if s]

    logger.info(f"Scanning {len(symbols)} active symbols safely...")

    for symbol in symbols:
        try:
            quote = get_quote(symbol)
            if not quote:
                continue

            change_pct = quote.get("change_percent") or quote.get("changePercent") or 0
            volume = quote.get("volume") or 0
            price = quote.get("price") or quote.get("close") or 0
            name = quote.get("name") or quote.get("name_ar") or quote.get("name_en") or symbol

            if price <= MIN_PRICE or volume < MIN_CURRENT_VOLUME or change_pct < MIN_CHANGE_PERCENT:
                continue

            avg_vol = get_avg_volume(symbol)
            rvol = (volume / avg_vol) if avg_vol and avg_vol > 0 else None
            
            if rvol is not None and rvol < MIN_RVOL:
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
                "Change_Pct": change_pct,
                "Volume": volume,
                "RVOL": rvol or 1.0,
            })

            # فاصل زمني أمان لتفادي حظر الطلبات (429)
            time_module.sleep(0.25)

        except Exception as e:
            logger.warning(f"{symbol}: {e}")
            continue

    df = pd.DataFrame(results)
    if not df.empty:
        df = df.sort_values("Change_Pct", ascending=False)
    return df


def format_message(df: pd.DataFrame) -> Optional[str]:
    if df.empty:
        return None

    msg = f"🇸🇦 *تنبيهات السوق السعودي*\n"
    msg += f"⏰ {get_riyadh_time()}\n"
    msg += "━━━━━━━━━━━━━━━━━━━━\n\n"

    for i, row in enumerate(df.itertuples(), 1):
        tv_link = f"https://www.tradingview.com/chart/?symbol=TADAWUL:{row.Symbol}"

        msg += f"🔔 *تنبيه #{i}*\n"
        msg += f"الرمز: `{row.Symbol}`\n"
        msg += f"الاسم: {row.Name}\n"
        msg += f"القطاع: `{row.Sector or '-'}`\n"
        msg += f"الصناعة: `{row.Industry or '-'}`\n"
        msg += f"السعر الحالي: `{row.Price:.2f}`\n"
        msg += f"نسبة التغيير: `{row.Change_Pct:+.2f}%`\n"
        msg += f"الحجم: `{row.Volume:,}`\n"
        msg += f"[شارت TradingView]({tv_link})\n"
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
    logger.info("Message sent to Telegram successfully")


def main():
    if not all([TELEGRAM_TOKEN, CHAT_ID, API_KEY]):
        raise ValueError("Missing secrets: TELEGRAM_TOKEN, CHAT_ID, or API_KEY")

    logger.info(f"Starting scan at {get_riyadh_time()}")
    df = run_screener()
    msg = format_message(df)

    if msg:
        send_telegram(msg)
        logger.info(f"Found {len(df)} stocks and sent to Telegram")
    else:
        logger.info("No stocks matched criteria.")


if __name__ == "__main__":
    main()
