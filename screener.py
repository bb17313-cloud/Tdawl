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
from tradingview_screener import Query

# ====================== الإعدادات من Secrets ======================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
API_KEY = os.getenv("API_KEY")

BASE_URL = "https://api.sahmk.sa/api/v1"

# ترويسات متصفح كاملة لتجاوز حظر جدار الحماية (WAF / Cloudflare)
HEADERS = {
    "X-API-Key": API_KEY,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.sahmk.sa/",
    "Origin": "https://www.sahmk.sa",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site"
}

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
    retries = 4
    backoff = 3
    
    session = requests.Session()
    session.headers.update(HEADERS)
    
    for attempt in range(retries):
        try:
            r = session.get(url, params=params, timeout=timeout)
            if r.status_code == 429:
                logger.warning(f"Rate limited (429) on {url}. Waiting {backoff}s before retry...")
                time_module.sleep(backoff)
                backoff *= 2
                continue
            return r
        except Exception as e:
            if attempt == retries - 1:
                logger.warning(f"Request failed for {url}: {e}")
                return None
            time_module.sleep(2)
    return None


# ====================== مصدر البيانات: TradingView ======================
_CACHE: Dict[str, Dict] = {}


def _clean(v):
    return None if v is None or (isinstance(v, float) and pd.isna(v)) else v


def get_market_volume_leaders(limit: int = 50) -> List[Dict]:
    try:
        _, df = (
            Query()
            .set_markets("ksa")
            .select("name", "description", "close", "change", "volume",
                    "average_volume_30d_calc", "sector", "industry")
            .order_by("volume", ascending=False)
            .limit(limit)
            .get_scanner_data()
        )
    except Exception as e:
        logger.warning(f"TradingView scanner failed: {e}")
        return []

    leaders = []
    for _, r in df.iterrows():
        symbol = str(r["name"])
        _CACHE[symbol] = {
            "name": _clean(r.get("description")) or symbol,
            "price": _clean(r.get("close")) or 0,
            "change_percent": _clean(r.get("change")) or 0,
            "volume": _clean(r.get("volume")) or 0,
            "avg_volume": _clean(r.get("average_volume_30d_calc")),
            "sector": _clean(r.get("sector")) or "",
            "industry": _clean(r.get("industry")) or "",
        }
        leaders.append({"symbol": symbol})
    return leaders


def get_quote(symbol: str) -> Optional[Dict]:
    d = _CACHE.get(symbol)
    if not d:
        return None
    return {"name": d["name"], "price": d["price"],
            "change_percent": d["change_percent"], "volume": d["volume"]}


def get_company(symbol: str) -> Optional[Dict]:
    d = _CACHE.get(symbol)
    if not d:
        return None
    return {"sector_name": d["sector"], "industry": d["industry"]}


def get_avg_volume(symbol: str, days: int = 20) -> Optional[float]:
    d = _CACHE.get(symbol)
    return d["avg_volume"] if d else None


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

            time_module.sleep(0.4)

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
