import os
import time
import html
import json
import urllib.request
import urllib.parse
from html.parser import HTMLParser
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

STATE_FILE = "saudi_state.json"

SAUDI_NAMES = {
    "1120": "الراجحي", "1150": "الإنماء",
    "2222": "أرامكو", "2380": "بترو رابغ", "2381": "لوبريف", "2382": "أديس",
    "4030": "البحري", "4031": "الخدمات الأرضية", "4200": "الدريس",
    "1201": "تكوين", "1202": "مبكو", "1210": "بي سي آي", "1211": "معادن",
    "1212": "أسترا", "1213": "نسيج", "1214": "شاكر", "1301": "أسلاك",
    "1302": "بوان", "1303": "الصناعات الكهربائية", "1304": "اليمامة للحديد",
    "1320": "أنابيب السعودية", "1321": "أنابيب الشرق", "1322": "أماك",
    "2001": "كيمانول", "2010": "سابك", "2020": "سابك للمغذيات", "2060": "التصنيع",
    "2090": "معدنية", "2150": "زجاج", "2170": "اللجين", "2180": "فيبكو",
    "2200": "أنابيب", "2210": "نماء", "2220": "الوطنية", "2223": "لوبريف",
    "2240": "الزامل", "2250": "المجموعة", "2290": "ينساب", "2300": "صناعة الورق",
    "2310": "سبكيم", "2330": "المتقدمة", "2350": "كيان", "3002": "أسمنت نجران",
    "3003": "أسمنت المدينة", "3004": "أسمنت الشمالية", "3005": "أسمنت أم القرى",
    "3007": "الواحة", "3008": "الكثيري", "3010": "أسمنت العربية", "3020": "أسمنت اليمامة",
    "3030": "أسمنت السعودية", "3040": "أسمنت القصيم", "3050": "أسمنت الجنوب",
    "3060": "أسمنت ينبع", "3080": "أسمنت الشرقية", "3090": "أسمنت تبوك",
    "3091": "أسمنت الجوف", "3092": "أسمنت الرياض",
    "1810": "سيرا", "1820": "مجموعة الحكير", "1830": "وقت اللياقة", "1831": "مهارة",
    "1832": "صدر", "1833": "الموارد", "1834": "سماسكو", "2040": "الخزف",
    "2110": "الكابلات", "2140": "أيان", "2160": "أميانتيت", "2190": "سيسكو",
    "2230": "الكيميائية", "2320": "البابطين", "2360": "الفخارية", "2370": "مسك",
    "4110": "باتك", "4140": "صادرات", "4141": "العمران", "4142": "كابلات الرياض",
    "4143": "تالكو", "4270": "طباعة وتغليف", "6004": "كاتريون",
    "2130": "صدق", "2340": "العبداللطيف", "4011": "لازوردي", "4012": "الأصيل",
    "4040": "سابتكو", "4170": "شمس", "4180": "مجموعة فتيحي", "4210": "الأبحاث والإعلام",
    "4260": "بدجت", "4261": "ذيب", "4262": "لومي", "4263": "سال",
    "4290": "الخليج للتدريب", "4291": "الوطنية للتعليم", "4292": "عطاء", "6002": "هرفي",
    "2050": "صافولا", "2100": "وفرة", "2120": "متطورة", "2270": "سدافكو",
    "2280": "المراعي", "2281": "تنمية", "2282": "نقي", "2283": "المطاحن الأولى",
    "2284": "المطاحن الحديثة", "4001": "أسواق العثيم", "4003": "إكسترا",
    "4006": "أسواق المزرعة", "4008": "ساكو", "4050": "ساسكو", "4051": "باعظيم",
    "4160": "ثمار", "4161": "بن داود", "4162": "المنجم", "4163": "المطاحن الأولى",
    "4164": "المطاحن الحديثة", "4165": "الماجدية", "4190": "جرير",
    "4191": "أبو معطي", "4192": "السيف غاليري", "4240": "سينومي ريتيل",
    "6001": "حلواني", "6010": "نادك", "6012": "ريدان", "6013": "التطويرية الغذائية",
    "6014": "الآمار", "6015": "أمريكانا", "6016": "برغرايززر", "6020": "جاكو",
    "6040": "تبوك الزراعية", "6050": "الأسماك", "6060": "الشرقية للتنمية",
    "6070": "الجوف الزراعية", "6090": "جازادكو",
    "2070": "الدوائية", "4002": "المواساة", "4004": "دلة الصحية", "4005": "رعاية",
    "4007": "الحمادي", "4009": "السعودي الألماني", "4013": "الحبيب",
    "4014": "أفالون", "4015": "جمجوم فارما", "4016": "الدواء", "4017": "فقيه الطبية",
    "1182": "أملاك", "1183": "سهل", "4080": "سناد القابضة", "4081": "النايفات",
    "4082": "مرنة", "4083": "تسهيل", "4130": "الباحة", "4280": "المملكة", "8313": "رسن",
    "8010": "التعاونية", "8012": "جزيرة تكافل", "8020": "ملاذ", "8030": "ميدغلف",
    "8040": "أليانز", "8050": "سلامة", "8060": "ولاء", "8070": "الدرع العربي",
    "8100": "سايكو", "8120": "إتحاد الخليج", "8150": "أسيج", "8160": "التأمين العربية",
    "8170": "الاتحاد", "8180": "الصقر", "8190": "المتحدة", "8200": "الإعادة",
    "8210": "بوبا العربية", "8230": "تكافل الراجحي", "8240": "تشنب",
    "8250": "جي آي جي", "8260": "الخليجية", "8270": "بروج", "8280": "ليفا",
    "8300": "الوطنية", "8310": "أمانة", "8311": "عناية",
    "2080": "الغاز", "2081": "الخريف", "2082": "أكوا باور", "2083": "مرافق",
    "2084": "مياهنا", "5110": "كهرباء السعودية", "7010": "إس تي سي",
    "7020": "اتحاد اتصالات", "7030": "زين السعودية", "7040": "عذيب",
    "7200": "المعمر", "7201": "بحر العرب", "7202": "سلوشنز", "7203": "علم",
    "7204": "توبي", "7211": "أفالون",
    "4020": "العقارية", "4090": "طيبة", "4100": "مكة", "4150": "التعمير",
    "4220": "إعمار", "4230": "البحر الأحمر", "4250": "جبل عمر", "4300": "دار الأركان",
    "4310": "مدينة المعرفة", "4320": "الأندلس", "4321": "سينومي سنترز",
    "4322": "رتال", "4323": "سمو", "4324": "بنان"
}


class GoogleSaudiStockParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_price_div = False
        self.in_pct_div = False
        self.prices = []
        self.pcts = []
        self.full_text = []

    def handle_starttag(self, tag, attrs):
        if tag in ("div", "span"):
            for k, v in attrs:
                if k == "class" and "YMlKec" in v and "fxKbKc" in v:
                    self.in_price_div = True
                elif k == "class" and "JwB6zf" in v:
                    self.in_pct_div = True

    def handle_data(self, data):
        clean_data = html.unescape(data).strip()
        if not clean_data:
            return
        self.full_text.append(clean_data)
        if self.in_price_div:
            self.prices.append(clean_data)
            self.in_price_div = False
        if self.in_pct_div:
            self.pcts.append(clean_data)
            self.in_pct_div = False

    def handle_endtag(self, tag):
        if tag in ("div", "span"):
            self.in_price_div = False
            self.in_pct_div = False


def clean_saudi_price(price_str):
    if not price_str:
        return None
    try:
        cleaned = str(price_str).replace("SAR", "").replace("ر.س", "").replace(",", "").strip()
        return float(cleaned)
    except ValueError:
        return None


def fetch_saudi_stock(ticker):
    url = f"https://google.com{ticker}:TADAWUL?hl=en"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            html_content = response.read().decode("utf-8")

        parser = GoogleSaudiStockParser()
        parser.feed(html_content)

        first_price = next(iter(parser.prices), None)
        if not first_price:
            return None

        price = clean_saudi_price(first_price)
        if not price:
            return None

        pct_change = 0.0
        # البحث أولاً في كلاسات النسبة المئوية المخصصة
        candidates = parser.pcts + parser.full_text
        for word in candidates:
            if "%" in word and any(c.isdigit() for c in word):
                clean_w = word.replace("(", "").replace(")", "").replace("%", "").replace("+", "").strip()
                try:
                    val = float(clean_w)
                    if val > 0:
                        pct_change = val
                        break
                    elif val < 0:
                        return None
                except ValueError:
                    continue

        if pct_change <= 0:
            return None

        return {"ticker": ticker, "name": SAUDI_NAMES.get(ticker, ""), "price": price, "pct": pct_change}
    except Exception:
        return None


def build_saudi_telegram_messages(stocks_list):
    ksa_tz = timezone(timedelta(hours=3))
    current_time = datetime.now(ksa_tz).strftime("%H:%M")

    header = ["🚨 <b>Tadawul Market Movers</b>", f"⏰ <code>{current_time}</code>", ""]
    footer = ["", "📊 المصدر: Google Finance"]

    sorted_stocks = sorted(stocks_list, key=lambda x: x["pct"], reverse=True)
    stock_lines = []

    for idx, item in enumerate(sorted_stocks, start=1):
        t = item["ticker"]
        name = item["name"]
        p = item["price"]
        pct = item["pct"]

        tv_url = f"https://tradingview.com:{t}"
        label = f"{t} {name}".strip()
        p_str = f"{p:.2f} SAR"
        pct_str = f"{pct:.2f}%"

        line = f'{idx}. <a href="{tv_url}"><b><code>{label}</code></b></a>  ·  <code>{p_str}</code>  ·  <code>{pct_str}</code>'
        stock_lines.append(line)

    messages = []
    current_chunk = list(header)
    current_length = sum(len(l) + 1 for l in current_chunk)

    for line in stock_lines:
        if current_length + len(line) + 50 > 3800:
            current_chunk.extend(footer)
            messages.append("\n".join(current_chunk))
            current_chunk = ["🚨 <b>Tadawul Market Movers (تابع)</b>", f"⏰ <code>{current_time}</code>", "", line]
            current_length = sum(len(l) + 1 for l in current_chunk)
        else:
            current_chunk.append(line)
            current_length += len(line) + 1

    if len(current_chunk) > len(header):
        current_chunk.extend(footer)
        messages.append("\n".join(current_chunk))

    return messages


def send_to_telegram(message_text):
    bot_token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("CHAT_ID")
    if not bot_token or not chat_id:
        print("Missing secrets!")
        return
    url = f"https://telegram.org{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message_text, "parse_mode": "HTML", "disable_web_page_preview": True}
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            res = json.loads(response.read().decode("utf-8"))
            print("Telegram Sent:", res.get("ok"))
    except Exception as e:
