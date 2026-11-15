class GoogleSaudiStockParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_price_div = False
        self.prices = []
        self.pcts = []
        self.full_text = []

    def handle_starttag(self, tag, attrs):
        if tag in ("div", "span"):
            for k, v in attrs:
                if k == "class" and "N6SYTe" in v:
                    self.in_price_div = True

    def handle_data(self, data):
        clean_data = html.unescape(data).strip()
        if not clean_data:
            return
        self.full_text.append(clean_data)
        if self.in_price_div:
            self.prices.append(clean_data)
            self.in_price_div = False

    def handle_endtag(self, tag):
        if tag in ("div", "span"):
            self.in_price_div = False


def fetch_saudi_stock(ticker):
    for exch in ("TADAWUL", "TDWL"):
        url = f"https://www.google.com/finance/quote/{ticker}:{exch}?hl=en"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Cookie": "CONSENT=YES+cb.20210720-07-p0.en+FX+410; SOCS=CAISHAgBEhJnd3NfMjAyMzA4MTAtMF9SQzIaAmVuIAEaBgiAo_CmBg"
        }
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as response:
                html_content = response.read().decode("utf-8")
            
            parser = GoogleSaudiStockParser()
            parser.feed(html_content)
            
            first_price = next(iter(parser.prices), None)
            if not first_price:
                continue
            
            cleaned = str(first_price).replace("SAR", "").replace("ر.س", "").replace(",", "").strip()
            try:
                price = float(cleaned)
            except:
                continue
            
            pct_change = 0.0
            # نبحث عن النسبة في كل النصوص
            for word in parser.full_text:
                if "%" in word and any(c.isdigit() for c in word):
                    clean_w = word.replace("(", "").replace(")", "").replace("%", "").replace("+", "").replace("−", "-").replace("–", "-").strip()
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
            
            return {
                "ticker": ticker,
                "name": SAUDI_NAMES.get(ticker, ""),
                "price": price,
                "pct": pct_change
            }
        except Exception:
            continue
    return None
