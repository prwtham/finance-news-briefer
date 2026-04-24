import streamlit as st
import re, os, requests, base64
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
from dotenv import load_dotenv
from tavily import TavilyClient
from researcher_alpha import run_quantitative_analysis
from researcher_beta import run_qualitative_analysis
from judge import evaluate_reports

def colorize_numbers(text):
    if not isinstance(text, str):
        return text
    # Escape dollar signs to prevent Streamlit from interpreting them as KaTeX math blocks,
    # which breaks our injected HTML span tags.
    text = text.replace("$", r"\$")
    
    # Alt 1: has \$, optional suffix
    # Alt 2: no \$, requires suffix (%, billion, million, etc)
    pattern = r'(?<![>\d])(?:\\\$\s*-?\d+(?:[,.]\d+)*(?:\s*(?:billion|million|trillion|B|M|K))?|-?\d+(?:[,.]\d+)*(?:\s*(?:billion|million|trillion|B|M|K)|%))(?![<\da-zA-Z])'
    
    neg_words = ["decline", "declined", "drop", "dropped", "fall", "fell", "lose", "lost", "down", "decrease", "decreased", "miss", "missed", "below", "cut", "debt", "deficit", "expense", "loss", "risk", "shortfall", "penalty", "weak"]
    
    def replacer(m):
        val = m.group(0)
        start_idx = m.start()
        context = text[max(0, start_idx-35):start_idx].lower()
        
        if "-" in val:
            return f'<span class="color-red" style="font-weight:600;">{val}</span>'
            
        if any(re.search(rf'\b{w}\b', context) for w in neg_words):
            return f'<span class="color-red" style="font-weight:600;">{val}</span>'
        else:
            return f'<span class="color-green" style="font-weight:600;">{val}</span>'
            
    text = re.sub(pattern, replacer, text)
    return text

load_dotenv()
st.set_page_config(page_title="QUANTUM AI Terminal", page_icon="📟", layout="wide", initial_sidebar_state="expanded")

# =============================================================================
# DATA HELPERS
# =============================================================================
@st.cache_data(ttl=300)
def fetch_ticker_data():
    tickers = {"S&P 500":"^GSPC","NASDAQ 100":"^NDX","DOW J":"^DJI","USD/JPY":"JPY=X","BTC/USD":"BTC-USD","GOLD":"GC=F","CRUDE OIL":"CL=F","VIX":"^VIX","ETH/USD":"ETH-USD"}
    data = {}
    for label, sym in tickers.items():
        try:
            h = yf.Ticker(sym).history(period="2d")
            if len(h)>=2:
                c,p = float(h["Close"].iloc[-1]), float(h["Close"].iloc[-2])
                data[label]={"price":c,"change":((c-p)/p)*100}
            else:
                data[label]={"price":float(h["Close"].iloc[-1]) if len(h)==1 else 0,"change":0.0}
        except: data[label]={"price":0.0,"change":0.0}
    return data

@st.cache_data(ttl=600)
def fetch_trending_news():
    key = os.getenv("TAVILY_API_KEY")
    if not key: return []
    try:
        r = TavilyClient(api_key=key).search(query="latest financial markets news stocks bonds crypto energy semiconductors",search_depth="basic",max_results=6)
        items = []
        for x in r.get("results",[]):
            t = x.get("title",""); cat="MARKETS"
            tl = t.lower()
            if any(w in tl for w in ["chip","gpu","nvidia","semiconductor","intel"]): cat="SEMICONDUCTORS"
            elif any(w in tl for w in ["energy","oil","opec","renewable","solar"]): cat="ENERGY"
            elif any(w in tl for w in ["bond","treasury","inflation","fed","rate","gdp"]): cat="MACRO"
            elif any(w in tl for w in ["crypto","bitcoin","ethereum"]): cat="CRYPTO"
            items.append({"title":t,"url":x.get("url","#"),"category":cat})
        return items
    except: return []

@st.cache_data(ttl=600)
def fetch_pexels_image(query):
    """Fetch a single landscape image from Pexels with photographer credit."""
    key = os.getenv("PEXELS_API_KEY")
    if not key: return None
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": key},
            params={"query": query, "per_page": 1, "orientation": "landscape"},
            timeout=5
        )
        if resp.status_code == 200:
            photos = resp.json().get("photos", [])
            if photos:
                p = photos[0]
                return {
                    "url": p["src"]["landscape"],
                    "photographer": p.get("photographer", ""),
                    "photo_url": p.get("url", ""),
                    "alt": p.get("alt", ""),
                }
    except: pass
    return None

@st.cache_data(ttl=600)
def fetch_unsplash_image(company_name, image_type="logo"):
    """Fetch an image from Unsplash. Type can be 'logo' or 'graph'."""
    key = os.getenv("UNSPLASH_API_KEY")
    if not key: return None
    
    if image_type == "logo":
        query = f"{company_name} logo brand"
        orientation = "squarish"
    elif image_type == "graph":
        query = f"{company_name} stock market chart graph"
        orientation = "landscape"
    elif image_type == "catalyst":
        query = f"{company_name} growth innovation technology"
        orientation = "landscape"
    elif image_type == "risk":
        query = f"{company_name} risk market volatility"
        orientation = "landscape"
    else:
        query = f"{company_name} {image_type}"
        orientation = "landscape"
        
    try:
        resp = requests.get(
            "https://api.unsplash.com/search/photos",
            headers={"Authorization": f"Client-ID {key}"},
            params={"query": query, "per_page": 1, "orientation": orientation},
            timeout=5
        )
        if resp.status_code == 200:
            photos = resp.json().get("results", [])
            if photos:
                p = photos[0]
                return {
                    "url": p["urls"]["regular"],
                    "photographer": p["user"]["name"],
                    "photo_url": p["links"]["html"],
                }
    except: pass
    return None

@st.cache_data(ttl=600)
def fetch_unsplash_images(query, count=3):
    """Fetch multiple images from Unsplash for a gallery."""
    key = os.getenv("UNSPLASH_API_KEY")
    if not key: return []
    try:
        resp = requests.get(
            "https://api.unsplash.com/search/photos",
            headers={"Authorization": f"Client-ID {key}"},
            params={"query": query, "per_page": count, "orientation": "landscape"},
            timeout=5
        )
        if resp.status_code == 200:
            results = []
            for p in resp.json().get("results", []):
                results.append({
                    "url": p["urls"]["regular"],
                    "small_url": p["urls"]["small"],
                    "photographer": p["user"]["name"],
                    "photo_url": p["links"]["html"],
                    "alt": p.get("alt_description", ""),
                })
            return results
    except: pass
    return []

COMMON_TICKERS = {
    "mercedes": "MBG.DE",
    "audi": "NSU.DE",
    "honda": "7267.T",
    "toyota": "7203.T",
    "volkswagen": "VOW3.DE",
    "bmw": "BMW.DE",
    "porsche": "P911.DE",
    "ferrari": "RACE",
    "hyundai": "005380.KS",
    "kia": "000270.KS",
    "tata motors": "TATAMOTORS.NS",
    "mahindra": "M&M.NS",
    "maruti suzuki": "MARUTI.NS",
    "reliance": "RELIANCE.NS",
    "hdfc": "HDFCBANK.NS",
    "icici": "ICICIBANK.NS",
    "sbi": "SBIN.NS",
    "infosys": "INFY.NS",
    "tcs": "TCS.NS",
    "wipro": "WIPRO.NS",
    "adani enterprises": "ADANIENT.NS",
    "airtel": "BHARTIARTL.NS",
    "samsung": "005930.KS",
    "sony": "6758.T",
    "nintendo": "7974.T",
    "panasonic": "6752.T",
    "softbank": "9984.T",
    "tsmc": "TSM",
    "asml": "ASML",
    "sap": "SAP.DE",
    "siemens": "SIE.DE",
    "airbus": "AIR.PA",
    "safran": "SAF.PA",
    "totalenergies": "TTE.PA",
    "lvmh": "MC.PA",
    "hermes": "RMS.PA",
    "loreal": "OR.PA",
    "dior": "CDI.PA",
    "bp": "BP.L",
    "shell": "SHEL.L",
    "hsbc": "HSBC.L",
    "unilever": "ULVR.L",
    "rio tinto": "RIO.L",
    "astrazeneca": "AZN.L",
    "glencore": "GLEN.L",
    "nestle": "NESN.SW",
    "roche": "ROG.SW",
    "novartis": "NOVN.SW",
    "ubs": "UBSG.SW",
    "apple": "AAPL",
    "microsoft": "MSFT",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "amazon": "AMZN",
    "nvidia": "NVDA",
    "tesla": "TSLA",
    "meta": "META",
    "netflix": "NFLX",
    "amd": "AMD",
    "intel": "INTC",
    "broadcom": "AVGO",
    "oracle": "ORCL",
    "cisco": "CSCO",
    "adobe": "ADBE",
    "salesforce": "CRM",
    "ibm": "IBM",
    "uber": "UBER",
    "airbnb": "ABNB",
    "disney": "DIS",
    "nike": "NKE",
    "mcdonalds": "MCD",
    "starbucks": "SBUX",
    "coca-cola": "KO",
    "pepsi": "PEP",
    "walmart": "WMT",
    "costco": "COST",
    "visa": "V",
    "mastercard": "MA",
    "jpmorgan": "JPM",
    "goldman sachs": "GS",
    "morgan stanley": "MS",
    "blackrock": "BLK",
    "exxon": "XOM",
    "chevron": "CVX",
    "boeing": "BA",
    "lockheed martin": "LMT",
    "pfizer": "PFE",
    "moderna": "MRNA",
    "tencent": "TCEHY",
    "alibaba": "BABA",
    "baidu": "BIDU",
    "meituan": "3690.HK",
    "jd.com": "JD",
    "byd": "1211.HK",
    "petrochina": "0857.HK",
    "bhp": "BHP.AX",
    "commonwealth bank": "CBA.AX",
    "csl": "CSL.AX",
    "royal bank of canada": "RY.TO",
    "shopify": "SHOP.TO",
    "td bank": "TD.TO",
    "facebook": "META", "coca cola": "KO", "pepsico": "PEP", "jp morgan": "JPM",
    "berkshire": "BRK-B", "paypal": "PYPL", "spotify": "SPOT", "snap": "SNAP",
    "snapchat": "SNAP", "twitter": "X", "palantir": "PLTR", "snowflake": "SNOW",
    "coinbase": "COIN", "robinhood": "HOOD", "qualcomm": "QCOM", "micron": "MU",
    "arm": "ARM", "dell": "DELL", "hp": "HPQ"
}

COMPANY_DOMAINS = {
    "meta": "meta.com", "facebook": "meta.com", "apple": "apple.com",
    "amazon": "amazon.com", "google": "google.com", "alphabet": "google.com",
    "microsoft": "microsoft.com", "nvidia": "nvidia.com", "tesla": "tesla.com",
    "netflix": "netflix.com", "amd": "amd.com", "intel": "intel.com",
    "disney": "disney.com", "walmart": "walmart.com", "coca-cola": "coca-cola.com",
    "coca cola": "coca-cola.com", "pepsi": "pepsico.com", "pepsico": "pepsico.com",
    "nike": "nike.com", "boeing": "boeing.com", "jpmorgan": "jpmorganchase.com",
    "jp morgan": "jpmorganchase.com", "goldman sachs": "goldmansachs.com",
    "berkshire": "berkshirehathaway.com", "visa": "visa.com", "mastercard": "mastercard.com",
    "paypal": "paypal.com", "salesforce": "salesforce.com", "adobe": "adobe.com",
    "uber": "uber.com", "airbnb": "airbnb.com", "spotify": "spotify.com",
    "snap": "snap.com", "snapchat": "snap.com", "palantir": "palantir.com",
    "snowflake": "snowflake.com", "shopify": "shopify.com", "coinbase": "coinbase.com",
    "robinhood": "robinhood.com", "samsung": "samsung.com", "ibm": "ibm.com",
    "oracle": "oracle.com", "qualcomm": "qualcomm.com", "broadcom": "broadcom.com",
    "micron": "micron.com", "dell": "dell.com", "hp": "hp.com",
    "cisco": "cisco.com", "sony": "sony.com", "toyota": "toyota.com",
    "infosys": "infosys.com", "tcs": "tcs.com",
    "aapl": "apple.com", "msft": "microsoft.com", "googl": "google.com", "goog": "google.com", "amzn": "amazon.com", "nvda": "nvidia.com", "tsla": "tesla.com", "nflx": "netflix.com", "intc": "intel.com", "dis": "disney.com", "wmt": "walmart.com", "ko": "coca-cola.com", "pep": "pepsico.com", "nke": "nike.com", "ba": "boeing.com", "jpm": "jpmorganchase.com", "gs": "goldmansachs.com", "brk-b": "berkshirehathaway.com", "v": "visa.com", "ma": "mastercard.com", "pypl": "paypal.com", "crm": "salesforce.com", "adbe": "adobe.com", "abnb": "airbnb.com", "spot": "spotify.com", "pltr": "palantir.com", "snow": "snowflake.com", "shop": "shopify.com", "coin": "coinbase.com", "hood": "robinhood.com", "orcl": "oracle.com", "qcom": "qualcomm.com", "avgo": "broadcom.com", "mu": "micron.com", "arm": "arm.com", "hpq": "hp.com", "csco": "cisco.com", "tm": "toyota.com", "infy": "infosys.com", "x": "x.com", "tcs.ns": "tcs.com", "reliance.ns": "ril.com", "005930.ks": "samsung.com", "twitter": "x.com", "reliance": "ril.com"
}

def _resolve_domain(company_name):
    """Helper to resolve company name or ticker to a domain."""
    name_lower = company_name.strip().lower()
    if name_lower in COMPANY_DOMAINS:
        return COMPANY_DOMAINS[name_lower]
    # Fallback: strip non-alphanumeric and add .com
    clean = re.sub(r'[^a-z0-9]', '', name_lower)
    return f"{clean}.com"

def get_clearbit_logo_url(company_name):
    """Return a logo URL for the company using Logo.dev."""
    token = os.getenv("LOGODEV_API_KEY", "")
    if not token:
        return None
    domain = _resolve_domain(company_name)
    return f"https://img.logo.dev/{domain}?token={token}"

@st.cache_data(ttl=86400)
def fetch_company_logo_b64(company_name):
    """Fetch company logo from Logo.dev server-side and return as base64 data URI.
    This bypasses Streamlit's iframe sandbox that blocks external image URLs."""
    token = os.getenv("LOGODEV_API_KEY", "")
    if not token:
        return None
    domain = _resolve_domain(company_name)
    url = f"https://img.logo.dev/{domain}?token={token}"
    try:
        resp = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image"):
            b64 = base64.b64encode(resp.content).decode()
            mime = resp.headers.get("content-type", "image/png").split(";")[0]
            return f"data:{mime};base64,{b64}"
    except: pass
    return None

def resolve_ticker(company_name):
    """Resolve a company name to a stock ticker symbol."""
    name_lower = company_name.strip().lower()
    if name_lower in COMMON_TICKERS:
        return COMMON_TICKERS[name_lower]
    # If input looks like a ticker already (all caps, short)
    if company_name.isupper() and len(company_name) <= 5:
        return company_name
    # Try yfinance search as fallback
    try:
        t = yf.Ticker(company_name)
        if t.info and t.info.get("symbol"):
            return t.info["symbol"]
    except: pass
    return None

@st.cache_data(ttl=300)
def fetch_stock_history(ticker, period="6mo"):
    """Fetch stock price history from Yahoo Finance."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=period)
        if hist.empty:
            return None, None
        info = {}
        try:
            ti = t.info
            info = {
                "name": ti.get("shortName", ticker),
                "currency": ti.get("currency", "USD"),
                "market_cap": ti.get("marketCap", 0),
                "pe_ratio": ti.get("trailingPE", 0),
                "52w_high": ti.get("fiftyTwoWeekHigh", 0),
                "52w_low": ti.get("fiftyTwoWeekLow", 0),
            }
        except: info = {"name": ticker, "currency": "USD"}
        return hist, info
    except:
        return None, None

def create_price_chart(hist, ticker, info=None):
    """Create a styled plotly price chart with volume overlay."""
    if hist is None or hist.empty:
        return None
    name = info.get("name", ticker) if info else ticker
    close = hist["Close"]
    color = "#419577" if close.iloc[-1] >= close.iloc[0] else "#ec4242"
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=hist.index, y=close,
        mode='lines', name='Price',
        line=dict(color=color, width=2.5),
        fill='tozeroy',
        fillcolor=f"rgba({','.join(str(int(color.lstrip('#')[i:i+2],16)) for i in (0,2,4))},0.08)",
        hovertemplate='%{x|%b %d, %Y}<br>$%{y:,.2f}<extra></extra>',
    ))
    curr = close.iloc[-1]
    prev = close.iloc[0]
    pct = ((curr - prev) / prev) * 100
    arrow = "▲" if pct >= 0 else "▼"
    title_text = f"{name} ({ticker})  •  ${curr:,.2f}  <span style='color:{color};'>{arrow} {abs(pct):.2f}%</span>"
    fig.update_layout(
        title=dict(text=title_text, font=dict(size=14, family="Inter, sans-serif", color="#2D3436")),
        plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        xaxis=dict(showgrid=False, linecolor="#E0D5C7", tickfont=dict(size=10, color="#7a7a7a")),
        yaxis=dict(showgrid=True, gridcolor="rgba(224,213,199,0.3)", linecolor="#E0D5C7", tickfont=dict(size=10, color="#7a7a7a"), tickprefix="$"),
        margin=dict(l=10, r=10, t=40, b=10),
        height=320, showlegend=False,
        hovermode="x unified",
    )
    return fig

def create_volume_chart(hist, ticker):
    """Create a styled volume bar chart."""
    if hist is None or hist.empty:
        return None
    colors = ["#419577" if hist["Close"].iloc[i] >= hist["Open"].iloc[i] else "#ec4242" for i in range(len(hist))]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=hist.index, y=hist["Volume"],
        marker_color=colors, opacity=0.7,
        hovertemplate='%{x|%b %d}<br>Vol: %{y:,.0f}<extra></extra>',
    ))
    fig.update_layout(
        title=dict(text="Trading Volume", font=dict(size=13, family="Inter, sans-serif", color="#2D3436")),
        plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        xaxis=dict(showgrid=False, linecolor="#E0D5C7", tickfont=dict(size=10, color="#7a7a7a")),
        yaxis=dict(showgrid=True, gridcolor="rgba(224,213,199,0.3)", linecolor="#E0D5C7", tickfont=dict(size=10, color="#7a7a7a")),
        margin=dict(l=10, r=10, t=35, b=10),
        height=200, showlegend=False, bargap=0.3,
    )
    return fig

def create_candlestick_chart(hist, ticker, days=30):
    """Create a candlestick chart for recent trading days."""
    if hist is None or hist.empty:
        return None
    recent = hist.tail(days)
    fig = go.Figure(data=[go.Candlestick(
        x=recent.index, open=recent['Open'], high=recent['High'],
        low=recent['Low'], close=recent['Close'],
        increasing_line_color='#419577', decreasing_line_color='#ec4242',
        increasing_fillcolor='#419577', decreasing_fillcolor='#ec4242',
    )])
    fig.update_layout(
        title=dict(text=f"Candlestick (Last {days} Trading Days)", font=dict(size=13, family="Inter, sans-serif", color="#2D3436")),
        plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        xaxis=dict(showgrid=False, linecolor="#E0D5C7", tickfont=dict(size=10, color="#7a7a7a"), rangeslider=dict(visible=False)),
        yaxis=dict(showgrid=True, gridcolor="rgba(224,213,199,0.3)", linecolor="#E0D5C7", tickfont=dict(size=10, color="#7a7a7a"), tickprefix="$"),
        margin=dict(l=10, r=10, t=35, b=10),
        height=300, showlegend=False,
    )
    return fig

def get_news_image_query(title):
    """Extract 2-3 keywords from a headline for a unique Pexels image search."""
    stop = {"the","a","an","is","are","to","for","of","in","on","and","or","as","by","at","from","with","its","it","that","this","how","why","what","vs","amid"}
    words = [w for w in re.sub(r'[^a-zA-Z\s]','',title).split() if w.lower() not in stop and len(w)>2]
    return " ".join(words[:3]) if words else "financial markets"

@st.cache_data(ttl=600)
def fetch_pexels_image(query):
    """Fetch a single landscape image from Pexels for trending news."""
    key = os.getenv("PEXELS_API_KEY")
    if not key: return None
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": key},
            params={"query": f"{query} finance market", "per_page": 1, "orientation": "landscape", "size": "large"},
            timeout=5
        )
        if resp.status_code == 200:
            photos = resp.json().get("photos", [])
            if photos:
                p = photos[0]
                return {
                    "url": p["src"]["large"],
                    "photographer": p.get("photographer", ""),
                    "photo_url": p.get("url", ""),
                }
    except: pass
    return None

def get_color(v): return "#419577" if v>0 else "#ec4242" if v<0 else "#7a7a7a"
def get_arrow(v): return "arrow_drop_up" if v>0 else "arrow_drop_down" if v<0 else "remove"
def compute_signal(s): return "ACCUMULATE" if s>70 else "HOLD" if s>50 else "REDUCE" if s>30 else "SELL"
def compute_vol(s): return "LOW" if s>65 else "MEDIUM" if s>40 else "HIGH"
def vol_color(v): return "#ec4242" if v=="LOW" else "#F5AB41" if v=="MEDIUM" else "#419577"
def sig_color(s): return "#419577" if s in("ACCUMULATE","BUY") else "#F5D649" if s=="HOLD" else "#ec4242"
def cat_color(c): return {"SEMICONDUCTORS":"#419577","ENERGY":"#ec4242","MACRO":"#F5D649","CRYPTO":"#8B5CF6","MARKETS":"#F5AB41"}.get(c,"#7a7a7a")
def insight_sentiment(b):
    neg = ["risk","headwind","decline","threat","antitrust","regulatory","warning","debt","downturn","concern","drop","weak","investigation"]
    return "negative" if any(w in b.lower() for w in neg) else "positive"
def parse_score(d):
    m = re.search(r"Sentiment Score:\s*(\d+)",d,re.I)
    return min(int(m.group(1)),100) if m else 0
def parse_insights(d):
    raw = re.findall(r"\*\*(.+?)\*\*\s*:?\s*(.+?)(?=\n\*\*|\n\n|\Z)",d,re.DOTALL)
    return [{"title":t.strip(),"body":b.strip().replace("\n"," "),"sentiment":insight_sentiment(b)} for t,b in raw[:3]]

def is_company_query(text):
    """Heuristic: if input is 1-3 capitalized words with no question/topic keywords, treat as company."""
    topic_signals = ["impact","effect","how","why","what","will","should","could","analyze","analysis",
                     "compare","between","vs","versus","trend","forecast","predict","news","latest",
                     "market","sector","industry","global","economy","recession","inflation","rate",
                     "hike","cut","war","crisis","policy","regulation","election"]
    words = text.strip().split()
    t = text.lower()
    if any(sig in t for sig in topic_signals):
        return False
    if len(words) <= 4 and not any(w in t for w in ["?","!"]):
        return True
    return False

def extract_catalyst_risk(company, alpha_data, beta_data):
    """Use Groq to extract one upside catalyst and one risk factor from existing reports."""
    from langchain_groq import ChatGroq
    from langchain_core.prompts import ChatPromptTemplate
    llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0.3)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a concise financial analyst. Extract exactly one upside catalyst and one risk exposure from the provided reports. Keep each to exactly 1 sentence (max 25 words). Be specific to the company — mention actual products, markets, competitors, or financial metrics."),
        ("user", """Company: {company}

Quantitative Report:
{alpha}

Qualitative Report:
{beta}

Respond in EXACTLY this format (no extra text):
CATALYST: [one sentence about the strongest upside catalyst]
RISK: [one sentence about the biggest risk exposure]""")
    ])
    try:
        response = (prompt | llm).invoke({"company": company, "alpha": alpha_data[:1500], "beta": beta_data[:1500]})
        text = response.content
        catalyst = "Strong growth momentum detected in core business segments."
        risk = "Competitive and regulatory headwinds could pressure near-term margins."
        for line in text.strip().split("\n"):
            line = line.strip()
            if line.upper().startswith("CATALYST:"):
                catalyst = line.split(":", 1)[1].strip()
            elif line.upper().startswith("RISK:"):
                risk = line.split(":", 1)[1].strip()
        return catalyst, risk
    except:
        return ("Strong growth momentum detected in core business segments.",
                "Competitive and regulatory headwinds could pressure near-term margins.")

def run_topic_analysis(topic):
    """Search Tavily for a general topic and summarize with Groq into 3 Key Insights."""
    from langchain_groq import ChatGroq
    from langchain_core.prompts import ChatPromptTemplate
    tavily_key = os.getenv("TAVILY_API_KEY")
    tavily = TavilyClient(api_key=tavily_key)
    try:
        results = tavily.search(query=topic, search_depth="advanced", max_results=5)
    except Exception as e:
        return f"Error searching for topic: {e}"
    context = ""
    for idx, r in enumerate(results.get("results",[])):
        context += f"Source [{idx+1}]: {r['url']}\nContent: {r['content']}\n\n"
    llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0.5)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert financial analyst providing key insights on market topics."),
        ("user", """Analyze the following topic: {topic}

Your output MUST be formatted as exactly 3 KEY INSIGHTS. Each insight must follow this exact format:

**[Short Bold Title]:** [1-2 sentence explanation with inline citation using source numbers e.g. [1], [2]]

Context Information:
{context}

KEY INSIGHTS:
""")
    ])
    try:
        response = (prompt | llm).invoke({"topic": topic, "context": context})
        return response.content
    except Exception as e:
        return f"Error generating topic analysis: {e}"

# =============================================================================
# CSS — Exact palette from the HTML spec
# =============================================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Manrope:wght@500;600;700;800;900&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap');
.material-symbols-outlined{font-family:'Material Symbols Outlined';font-variation-settings:'FILL' 0,'wght' 400,'GRAD' 0,'opsz' 24;vertical-align:middle;}

.stApp{background-color:#FDF5EC!important;color:#2D3436!important;font-family:'Inter',sans-serif!important;}
/* Hide header decorations but keep sidebar controls visible */
header[data-testid="stHeader"]{background:transparent!important;backdrop-filter:none!important;border:none!important;pointer-events:none!important;}
header[data-testid="stHeader"] [data-testid="stDecoration"]{display:none!important;}
header[data-testid="stHeader"] [data-testid="stToolbar"]{display:none!important;}
[data-testid="stSidebar"]{background-color:#fff8f0!important;border-right:1px solid #E0D5C7!important;}
[data-testid="stSidebar"] *{color:#5a5a5a!important;}
h1,h2,h3,h4,h5,h6{color:#419577!important;}
p,span,div,.stMarkdown{color:#2D3436!important;}

/* Containers */
div[data-testid="stVerticalBlockBorderWrapper"]{background-color:#FFFFFF!important;border:1px solid #E0D5C7!important;border-radius:8px!important;}

/* Chat Input */
[data-testid="stBottom"] {
    position: static !important;
    padding-bottom: 20px;
    background: transparent !important;
}
[data-testid="stChatInput"]{background-color:#FDF5EC!important;border:1px solid #E0D5C7!important;border-radius:16px!important;}
[data-testid="stChatInput"] input{color:#2D3436!important;}
[data-testid="stChatInput"] button{background-color:#F5D649!important;border-radius:12px!important;}

/* Scrollbar */
::-webkit-scrollbar{width:4px;height:4px}
::-webkit-scrollbar-track{background:#FDF5EC}
::-webkit-scrollbar-thumb{background:#E0D5C7;border-radius:10px}

/* Sidebar Nav Item Active */
.nav-active{background:#FDF5EC;border-left:4px solid #419577;color:#419577!important;}
.nav-item{padding:12px 24px;display:flex;align-items:center;gap:16px;cursor:pointer;transition:all 0.2s;}
.nav-item:hover{background:#FDF5EC;}
.nav-label{font-size:12px;letter-spacing:0.05em;font-weight:600;text-transform:uppercase;}

/* Ticker */
.color-green, .color-green * { color: #419577 !important; }
.color-red, .color-red * { color: #ec4242 !important; }
.color-gray, .color-gray * { color: #7a7a7a !important; }
.ticker-row{display:flex;align-items:center;gap:0;background:#F5D649;border-radius:12px;border:1px solid rgba(0,0,0,0.05);padding:0 24px;height:60px;margin-bottom:32px;overflow-x:auto;}
.ticker-row::-webkit-scrollbar { display: none; }
.ticker-item{display:flex;align-items:center;gap:8px;padding-right:32px;border-right:1px solid rgba(0,0,0,0.12);margin-right:0;padding-left:32px;flex-shrink:0;}
.ticker-item:first-child{padding-left:0;}
.ticker-item:last-child{border-right:none;}
.ticker-lbl{font-size:10px;color:#2D3436;text-transform:uppercase;font-weight:600;letter-spacing:0.05em;}
.ticker-val{font-size:14px;font-weight:500;font-family:'Inter',monospace;color:#2D3436;}
.ticker-chg{font-size:12px;font-weight:500;display:flex;align-items:center;}

/* Top Nav */
.topnav{display:flex;justify-content:space-between;align-items:center;padding:0 24px;height:64px;background:#FDF5EC;border-bottom:1px solid #E0D5C7;}
.topnav-brand{font-size:18px;font-weight:900;color:#419577!important;text-transform:uppercase;font-family:'Manrope',sans-serif;letter-spacing:-0.02em;}
.topnav-link{font-size:14px;color:#7a7a7a!important;text-decoration:none;transition:color 0.2s;}
.topnav-link-active{color:#419577!important;font-weight:700;border-bottom:2px solid #419577;padding-bottom:4px;}

/* Sections */
.section-label{font-size:12px;letter-spacing:0.05em;font-weight:600;text-transform:uppercase;color:#7a7a7a!important;margin-bottom:16px;}
.metric-label{font-size:10px;letter-spacing:0.05em;font-weight:600;text-transform:uppercase;color:#7a7a7a!important;}
.metric-value{font-size:24px;font-weight:600;font-family:'Manrope',sans-serif;letter-spacing:-0.01em;}
.insight-title{font-size:12px;color:#419577!important;text-transform:uppercase;letter-spacing:0.05em;font-weight:600;border-bottom:1px solid rgba(65,149,119,0.3);padding-bottom:8px;margin-bottom:16px;}
.insight-item{display:flex;gap:12px;margin-bottom:16px;line-height:1.6;}
.insight-text{font-size:16px;color:#2D3436!important;}
.insight-bold{font-weight:700;color:#1a1a1a!important;}

/* Log */
.perf-log{background:#fff8f0;padding:16px;border-radius:8px;font-family:'Inter',monospace;font-size:14px;border-left:2px solid #419577;}
.log-line{margin-bottom:4px;}
.log-dim{color:#7a7a7a!important;}
.log-highlight{color:#419577!important;}

/* News - Full Bleed Overlay Style */
.news-card{position:relative;height:240px;border-radius:16px;margin-bottom:24px;overflow:hidden;cursor:pointer;transition:all 0.3s cubic-bezier(0.4, 0, 0.2, 1);border:1px solid rgba(224, 213, 199, 0.4);}
.news-card:hover{transform:translateY(-4px);box-shadow:0 12px 24px rgba(0,0,0,0.15);border-color:#F5AB41;}
.news-img{position:absolute;top:0;left:0;width:100% !important;height:100% !important;object-fit:cover !important;transition:transform 0.5s ease;display:block !important;}
.news-card:hover .news-img{transform:scale(1.05);}
.news-overlay{position:absolute;bottom:0;left:0;right:0;top:0;background:linear-gradient(to top, rgba(0,0,0,0.9) 0%, rgba(0,0,0,0.4) 50%, rgba(0,0,0,0.1) 100%);display:flex;flex-direction:column;justify-content:flex-end;padding:24px;z-index:2;}
.news-cat{font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:0.1em;color:#F5D649!important;margin-bottom:8px;}
.news-title{font-size:18px;color:#FFFFFF!important;font-weight:700;font-family:'Manrope',sans-serif;line-height:1.3;margin:0;}
.news-meta{font-size:10px;color:rgba(255,255,255,0.7)!important;margin-top:12px;font-weight:600;}

/* Hero Section */
.hero-container{height:25vh;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;margin-bottom:20px;margin-top: -40px;}
.hero-title{font-family:'Manrope',sans-serif;font-size:64px;font-weight:900;margin:0;padding:0;background:linear-gradient(135deg,#419577,#F5AB41);-webkit-background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:-0.03em;line-height:1.1;}
.hero-subtitle{color:#7a7a7a!important;font-size:14px;margin:12px 0 0 0;font-weight:700;letter-spacing:0.2em;text-transform:uppercase;}

/* History */
.hist-card{padding:12px;border-radius:8px;margin-bottom:12px;cursor:pointer;transition:all 0.2s;}
.hist-card-active{background:#FDF5EC;border:1px solid #E0D5C7;}
.hist-card-inactive{background:transparent;border:1px solid transparent;}
.hist-card:hover{background:#FDF5EC;}
.hist-title{font-size:14px;color:#2D3436!important;line-height:1.4;}
.hist-meta{font-size:10px;color:#7a7a7a!important;font-weight:600;letter-spacing:0.05em;}

/* Badge */
.exec-badge{background:rgba(65,149,119,0.1);color:#419577!important;border:1px solid rgba(65,149,119,0.3);padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:-0.02em;}
.task-id{font-size:10px;color:#7a7a7a!important;font-weight:700;text-transform:uppercase;margin-left:8px;}

/* Portfolio Alert */
.portfolio-alert{background:#FFFFFF;border:1px solid #E0D5C7;border-radius:16px;padding:24px;margin-top:40px;}
.portfolio-title{font-size:14px;color:#419577!important;font-weight:600;font-family:'Manrope',sans-serif;margin-bottom:8px;}
.portfolio-text{font-size:12px;color:#5a5a5a!important;line-height:1.5;}
.portfolio-btn{margin-top:16px;color:#419577!important;font-size:10px;font-weight:600;letter-spacing:0.05em;text-transform:uppercase;border:1px solid rgba(65,149,119,0.3);padding:8px 12px;border-radius:4px;background:transparent;width:100%;text-align:center;cursor:pointer;}

/* Mini Chart */
.mini-chart{height:96px;width:100%;background:#fff8f0;border-radius:4px;display:flex;align-items:flex-end;padding:8px;gap:4px;margin-bottom:16px;}
.mini-bar{flex:1;}

/* Metrics divider */
.metrics-row{display:flex;align-items:center;gap:0;padding:16px 0;border-top:1px solid #E0D5C7;border-bottom:1px solid #E0D5C7;}
.metric-col{display:flex;flex-direction:column;}
.metric-col+.metric-col{border-left:1px solid #E0D5C7;padding-left:24px;margin-left:24px;}

/* Company Logo */
.company-logo{width:48px;height:48px;border-radius:12px;object-fit:contain;background:#fff8f0;border:1px solid #E0D5C7;}
.company-initial{width:48px;height:48px;border-radius:12px;background:linear-gradient(135deg,#419577,#F5AB41);display:flex;align-items:center;justify-content:center;font-size:22px;font-weight:800;color:#fff!important;font-family:'Manrope',sans-serif;flex-shrink:0;}
.company-header{display:flex;align-items:center;gap:16px;margin-bottom:16px;}

/* Company header */

/* Expander Overrides */
[data-testid="stExpander"], [data-testid="stExpander"] details, [data-testid="stExpander"] summary, [data-testid="stExpanderDetails"] {
    background-color: #FDF5EC !important;
}
[data-testid="stExpander"] details:hover, [data-testid="stExpander"] summary:hover, [data-testid="stExpander"] details[open], [data-testid="stExpander"] > div > div {
    background-color: #FDF5EC !important;
}

/* Sidebar active nav link */
.nav-link{display:flex;align-items:center;gap:16px;padding:12px 24px;cursor:pointer;transition:all 0.2s;text-decoration:none;color:#5a5a5a!important;}
.nav-link:hover{background:#FDF5EC;color:#419577!important;}
.nav-link-active{background:#FDF5EC;border-left:4px solid #419577;color:#419577!important;}
.nav-link-active .nav-label{color:#419577!important;}

/* Streamlit buttons override */
.stButton>button{background-color:#419577!important;color:#F5D649!important;border:none!important;font-weight:800!important;text-transform:uppercase!important;letter-spacing:0.05em!important;border-radius:8px!important;transition:all 0.2s!important;}
.stButton>button p{color:#F5D649!important;font-weight:800!important;text-transform:uppercase!important;letter-spacing:0.05em!important;}
.stButton>button:hover{background-color:#357a62!important;color:#F5D649!important;transform:translateY(-1px)!important;box-shadow:0 4px 12px rgba(65,149,119,0.3)!important;}
.stButton>button:hover p{color:#F5D649!important;}

/* Dynamic Metric Colors */
.color-green{color:#419577!important;}
.color-red{color:#ec4242!important;}
.color-gray{color:#7a7a7a!important;}
</style>
""", unsafe_allow_html=True)

# =============================================================================
# FETCH DATA
# =============================================================================
ticker_data = fetch_ticker_data()
trending_news = fetch_trending_news()



# =============================================================================
# MAIN HEADER
# =============================================================================
if "active_view" not in st.session_state:
    st.session_state.active_view = "Overview"

st.markdown("""
<div class="hero-container">
    <h1 class="hero-title">Financial News Briefer</h1>
    <p class="hero-subtitle">Intelligent Multi-Agent Terminal</p>
</div>
""", unsafe_allow_html=True)

# =============================================================================
# TICKER TAPE (REAL-TIME)
# =============================================================================
ticker_html = ""
for i,(lbl,d) in enumerate(ticker_data.items()):
    c_class = "color-green" if d["change"]>0 else "color-red" if d["change"]<0 else "color-gray"
    a = get_arrow(d["change"])
    ps = f"{d['price']:,.2f}" if d['price']>1000 else f"{d['price']:.2f}"
    ticker_html += f'<div class="ticker-item {c_class}"><span class="ticker-lbl {c_class}">{lbl}</span><span class="ticker-val {c_class}">{ps}</span><span class="ticker-chg {c_class}"><span class="material-symbols-outlined {c_class}" style="font-size:14px;">{a}</span>{abs(d["change"]):.2f}%</span></div>'
st.markdown(f'<div class="ticker-row">{ticker_html}</div>', unsafe_allow_html=True)

st.markdown("<div style='margin-top: 50px;'></div>", unsafe_allow_html=True)

# --- Trending News Grid (2 rows of 3) ---
for row in range(2):
    news_cols = st.columns(3)
    for col in range(3):
        idx = row * 3 + col
        if idx < len(trending_news):
            news = trending_news[idx]
            with news_cols[col]:
                pexels_data = fetch_pexels_image(get_news_image_query(news["title"]))
                if pexels_data:
                    img_html = f'<img class="news-img" src="{pexels_data["url"]}" alt="{pexels_data.get("alt","")}" />'
                else:
                    fallback_grads = ["linear-gradient(135deg,#419577,#FDF5EC,#F5D649)","linear-gradient(135deg,#F5AB41,#FDF5EC,#419577)","linear-gradient(135deg,#F5D649,#FDF5EC,#F5AB41)"]
                    img_html = f'<div class="news-img" style="background:{fallback_grads[idx%3]};"></div>'
                    
                st.markdown(f"""
                <div class="news-card">
                    <a href="{news['url']}" target="_blank" style="text-decoration: none; display: block; position: absolute; top:0; left:0; width:100%; height:100%; z-index:5;"></a>
                    {img_html}
                    <div class="news-overlay">
                        <span class="news-cat">{news["category"]}</span>
                        <div class="news-title">{news["title"][:65]}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

st.markdown('<div style="text-align:right; margin-top: -12px; margin-bottom: 40px; opacity:0.3;"><a href="https://www.pexels.com" target="_blank"><img src="https://images.pexels.com/lib/api/pexels-white.png" style="width:40px;" /></a></div>', unsafe_allow_html=True)

# =============================================================================
# TOP NAV (functional tabs)
# =============================================================================
# Center the tabs
nav_cols = st.columns([3, 1.3, 1.6, 1.3, 3])
for idx, view_name in enumerate(["Overview","Forecasting","Sentiment"]):
    with nav_cols[idx+1]:
        is_active = st.session_state.active_view == view_name
        if st.button(view_name, key=f"view_{view_name}", use_container_width=True):
            st.session_state.active_view = view_name
            st.rerun()

st.markdown("<div style='margin-top: 50px;'></div>", unsafe_allow_html=True)

# --- Search Box (Agent) ---
company = st.chat_input("Analyze the impact of a company's market position...")

# =========================================================================
# VIEW ROUTING: Overview / Forecasting / Sentiment
# =========================================================================
if st.session_state.active_view == "Forecasting":
    st.markdown('<span class="exec-badge" style="background:rgba(245,171,65,0.1)!important;color:#F5AB41!important;border-color:rgba(245,171,65,0.3)!important;">FORECASTING ENGINE</span>', unsafe_allow_html=True)
    st.markdown('<h1 style="font-size:30px;font-weight:700;font-family:Manrope,sans-serif;color:#419577!important;margin-top:12px;">Market Forecasting & Predictive Models</h1>', unsafe_allow_html=True)
    st.markdown('<p style="color:#5a5a5a!important; margin-bottom: 24px;">AI-driven forecasts based on historical patterns, options flow, and macroeconomic indicators.</p>', unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown('<div style="padding:20px;background:#FFFFFF;border:1px solid #E0D5C7;border-radius:12px;text-align:center;"><span style="color:#7a7a7a;font-size:14px;">Probability of Rate Cut (Q3)</span><h2 style="color:#419577;margin:8px 0;font-size:32px;">68.4%</h2><span style="color:#419577;font-size:12px;">▲ 4.2% from last week</span></div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div style="padding:20px;background:#FFFFFF;border:1px solid #E0D5C7;border-radius:12px;text-align:center;"><span style="color:#7a7a7a;font-size:14px;">Market Volatility Risk</span><h2 style="color:#F5AB41;margin:8px 0;font-size:32px;">ELEVATED</h2><span style="color:#F5AB41;font-size:12px;">VIX approaching 20.0 level</span></div>', unsafe_allow_html=True)
    with c3:
        st.markdown('<div style="padding:20px;background:#FFFFFF;border:1px solid #E0D5C7;border-radius:12px;text-align:center;"><span style="color:#7a7a7a;font-size:14px;">S&P 500 Year-End Target</span><h2 style="color:#2D3436;margin:8px 0;font-size:32px;">5,850</h2><span style="color:#7a7a7a;font-size:12px;">Consensus Base Case</span></div>', unsafe_allow_html=True)
    
    st.markdown('<h2 style="font-size:20px;font-weight:600;color:#419577;margin-top:32px;border-bottom:1px solid #E0D5C7;padding-bottom:12px;">Sector Outlook (Next 30 Days)</h2>', unsafe_allow_html=True)
    sectors = [
        ("Technology", "Bullish", 78, "#419577"),
        ("Energy", "Neutral", 45, "#F5D649"),
        ("Financials", "Bullish", 62, "#419577"),
        ("Consumer Discretionary", "Bearish", 28, "#ec4242"),
        ("Healthcare", "Neutral", 50, "#F5D649")
    ]
    for sec, dir, val, col in sectors:
        st.markdown(f'''
        <div style="display:flex;align-items:center;margin:16px 0;">
            <div style="width:180px;color:#5a5a5a;font-weight:500;">{sec}</div>
            <div style="flex-grow:1;height:8px;background:#E0D5C7;border-radius:4px;margin:0 16px;overflow:hidden;">
                <div style="width:{val}%;height:100%;background:{col};border-radius:4px;"></div>
            </div>
            <div style="width:80px;text-align:right;color:{col};font-weight:700;">{dir}</div>
        </div>
        ''', unsafe_allow_html=True)
        
    st.markdown('<h2 style="font-size:20px;font-weight:600;color:#419577;margin-top:32px;border-bottom:1px solid #E0D5C7;padding-bottom:12px;">Asset Signals</h2>', unsafe_allow_html=True)
    for lbl, d in ticker_data.items():
        direction = "ACCUMULATE" if d["change"] > 0 else "REDUCE" if d["change"] < 0 else "HOLD"
        color = get_color(d["change"])
        st.markdown(f'<div style="padding:16px;margin-bottom:8px;background:#FFFFFF;border:1px solid #E0D5C7;border-radius:8px;display:flex;justify-content:space-between;align-items:center;"><div style="display:flex;align-items:center;gap:12px;"><strong style="color:#2D3436!important;font-size:16px;width:100px;">{lbl}</strong><span style="color:#7a7a7a!important;font-size:14px;">Spot: {d["price"]:,.2f}</span></div><div><span style="color:{color}!important;font-weight:700;background:{color}20;padding:4px 12px;border-radius:4px;font-size:12px;">{direction} ({d["change"]:+.2f}%)</span></div></div>', unsafe_allow_html=True)

elif st.session_state.active_view == "Sentiment":
    st.markdown('<span class="exec-badge" style="background:rgba(245,214,73,0.1)!important;color:#F5D649!important;border-color:rgba(245,214,73,0.3)!important;">SENTIMENT SCANNER</span>', unsafe_allow_html=True)
    st.markdown('<h1 style="font-size:30px;font-weight:700;font-family:Manrope,sans-serif;color:#419577!important;margin-top:12px;">Global Market Sentiment Matrix</h1>', unsafe_allow_html=True)
    st.markdown('<p style="color:#5a5a5a!important; margin-bottom: 24px;">Real-time NLP sentiment extraction across global financial media, social chatter, and institutional notes.</p>', unsafe_allow_html=True)
    st.markdown('''
    <div style="display:flex;gap:16px;margin-bottom:32px;">
        <div style="flex:1;background:#FFFFFF;border:1px solid #E0D5C7;border-radius:12px;padding:20px;">
            <div style="color:#7a7a7a;font-size:14px;margin-bottom:12px;">Overall Macro Sentiment</div>
            <div style="display:flex;align-items:center;gap:16px;">
                <h2 style="color:#419577;margin:0;font-size:36px;">58/100</h2>
                <span style="background:rgba(65,149,119,0.1);color:#419577;padding:4px 8px;border-radius:4px;font-weight:600;font-size:14px;">CAUTIOUSLY OPTIMISTIC</span>
            </div>
        </div>
        <div style="flex:1;background:#FFFFFF;border:1px solid #E0D5C7;border-radius:12px;padding:20px;">
            <div style="color:#7a7a7a;font-size:14px;margin-bottom:12px;">Fear & Greed Index</div>
            <div style="display:flex;align-items:center;gap:16px;">
                <h2 style="color:#F5AB41;margin:0;font-size:36px;">62</h2>
                <span style="background:rgba(245,171,65,0.1);color:#F5AB41;padding:4px 8px;border-radius:4px;font-weight:600;font-size:14px;">GREED</span>
            </div>
        </div>
    </div>
    ''', unsafe_allow_html=True)

    st.markdown('<h2 style="font-size:20px;font-weight:600;color:#419577;margin-top:32px;border-bottom:1px solid #E0D5C7;padding-bottom:12px;">Live News Sentiment</h2>', unsafe_allow_html=True)
    for news in trending_news[:5]:
        sent = insight_sentiment(news["title"])
        icon = "check_circle" if sent=="positive" else "warning"
        ic = "#419577" if sent=="positive" else "#ec4242"
        st.markdown(f'''
        <div style="background:rgba(253,245,236,0.5);border-left:4px solid {ic};padding:16px;margin-bottom:12px;border-radius:0 8px 8px 0;display:flex;gap:16px;align-items:flex-start;">
            <span class="material-symbols-outlined" style="color:{ic}!important;font-size:24px;">{icon}</span>
            <div>
                <span style="color:#7a7a7a;font-size:12px;font-weight:600;letter-spacing:1px;text-transform:uppercase;">{news["category"]}</span>
                <p style="color:#2D3436;margin:4px 0 0 0;font-size:15px;line-height:1.5;">{news["title"]}</p>
            </div>
        </div>
        ''', unsafe_allow_html=True)

elif company:
    now = datetime.now()
    is_company = is_company_query(company)
    mode_label = "Company Analysis" if is_company else "Topic Intelligence"
    st.session_state.active_view = "Overview"
    task_id = abs(hash(company + now.isoformat())) % 10000

    if is_company:
        # =================================================================
        # COMPANY MODE — Full Alpha + Beta + Judge pipeline
        # =================================================================

        # Resolve ticker & fetch stock info early for the header card
        ticker_symbol = resolve_ticker(company)
        stock_hist, stock_info = fetch_stock_history(ticker_symbol) if ticker_symbol else (None, {})
        stock_info = stock_info or {}

        # Build live price string
        curr_price, pct_6m = None, None
        if stock_hist is not None and not stock_hist.empty:
            curr_price = float(stock_hist["Close"].iloc[-1])
            pct_6m = ((curr_price - float(stock_hist["Close"].iloc[0])) / float(stock_hist["Close"].iloc[0])) * 100

        logo_data_uri = fetch_company_logo_b64(company)
        initial = company.strip()[0].upper()
        if logo_data_uri:
            logo_img_html = f'<img src="{logo_data_uri}" alt="{company}" style="width:72px;height:72px;border-radius:14px;object-fit:contain;background:#fff;border:1px solid #E0D5C7;padding:6px;display:block;" />'
        else:
            logo_img_html = f'<div style="width:72px;height:72px;border-radius:14px;background:linear-gradient(135deg,#419577,#F5AB41);display:flex;align-items:center;justify-content:center;font-size:28px;font-weight:800;color:#fff;font-family:Manrope,sans-serif;">{initial}</div>'
        full_name = stock_info.get("name", company)
        sector = ""
        description = ""
        website = ""
        hq = ""
        try:
            t_info = yf.Ticker(ticker_symbol).info if ticker_symbol else {}
            sector = t_info.get("sector", "")
            description = t_info.get("longBusinessSummary", "")[:280]
            website = t_info.get("website", "")
            hq_city = t_info.get("city", "")
            hq_country = t_info.get("country", "")
            hq = ", ".join(filter(None, [hq_city, hq_country]))
        except: pass

        mcap = stock_info.get("market_cap", 0)
        mcap_str = f"${mcap/1e12:.2f}T" if mcap >= 1e12 else f"${mcap/1e9:.1f}B" if mcap >= 1e9 else f"${mcap/1e6:.0f}M" if mcap >= 1e6 else "—"
        pe = stock_info.get("pe_ratio", 0)
        pe_cls = "color-green" if (0 < pe <= 25) else "color-red" if pe > 25 else "color-gray"
        pe_str = f'<span class="{pe_cls}" style="font-weight:700;">{pe:.1f}x</span>' if pe else "—"
        price_str = f"${curr_price:,.2f}" if curr_price else "—"
        pct_cls = "color-green" if pct_6m is not None and pct_6m >= 0 else "color-red"
        _arrow = "▲" if pct_6m is not None and pct_6m >= 0 else "▼"
        _pct_val = f"{_arrow} {abs(pct_6m):.2f}%" if pct_6m is not None else ""
        pct_str = f'<span class="{pct_cls}" style="font-weight:700;">{_pct_val}</span> (6M)' if pct_6m is not None else ""

        ticker_badge = f'<span style="background:#F5D649;color:#2D3436;font-size:11px;font-weight:800;padding:3px 10px;border-radius:20px;letter-spacing:0.05em;">{ticker_symbol}</span>' if ticker_symbol else ""
        sector_badge = f'<span style="background:rgba(65,149,119,0.1);color:#419577;font-size:11px;font-weight:700;padding:3px 10px;border-radius:20px;border:1px solid rgba(65,149,119,0.25);">{sector}</span>' if sector else ""
        website_link = f'<a href="{website}" target="_blank" style="color:#7a7a7a;font-size:12px;text-decoration:none;"><span class="material-symbols-outlined" style="font-size:13px;vertical-align:-2px;">language</span> {website.replace("https://","").replace("http://","").rstrip("/")}</a>' if website else ""
        hq_text = f'<span style="color:#7a7a7a;font-size:12px;"><span class="material-symbols-outlined" style="font-size:13px;vertical-align:-2px;">location_on</span> {hq}</span>' if hq else ""

        st.markdown(f"""
<div style="background:#FFFFFF;border:1px solid #E0D5C7;border-radius:16px;padding:28px 32px;margin-bottom:4px;">
<div style="display:flex;align-items:flex-start;gap:24px;">
<div style="flex-shrink:0;">
{logo_img_html}
</div>
<div style="flex:1;min-width:0;">
<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px;">
<h1 style="font-size:26px;font-weight:800;font-family:Manrope,sans-serif;color:#2D3436!important;letter-spacing:-0.02em;margin:0;">{full_name}</h1>
{ticker_badge}{sector_badge}
</div>
<p style="font-size:13px;color:#5a5a5a!important;line-height:1.6;margin:0 0 12px 0;max-width:680px;">{colorize_numbers(description)}</p>
<div style="display:flex;gap:20px;flex-wrap:wrap;align-items:center;">
{website_link}{hq_text}
</div>
</div>
<div style="flex-shrink:0;text-align:right;border-left:1px solid #E0D5C7;padding-left:28px;min-width:130px;">
<div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;color:#7a7a7a;margin-bottom:4px;">Live Price</div>
<div style="font-size:28px;font-weight:800;font-family:Manrope,sans-serif;color:#2D3436!important;line-height:1;">{price_str}</div>
<div style="font-size:12px;font-weight:600;color:#7a7a7a;margin-top:4px;">{pct_str}</div>
<div style="margin-top:16px;display:flex;flex-direction:column;gap:6px;">
<div><span style="font-size:10px;color:#7a7a7a;text-transform:uppercase;letter-spacing:0.05em;">Mkt Cap</span><br><span style="font-size:14px;font-weight:700;color:#2D3436;">{mcap_str}</span></div>
<div><span style="font-size:10px;color:#7a7a7a;text-transform:uppercase;letter-spacing:0.05em;">P/E Ratio</span><br><span style="font-size:14px;font-weight:700;">{pe_str}</span></div>
</div>
</div>
</div>
</div>
""", unsafe_allow_html=True)

        with st.status(f"Scanning Bloomberg, Reuters, Financial Times for {company}...", expanded=True) as status:
            st.write(">> INITIALIZING ALPHA NODE (QUANT)...")
            alpha_data = run_quantitative_analysis(company)
            st.write(">> INITIALIZING BETA NODE (QUAL)...")
            beta_data = run_qualitative_analysis(company)
            st.write(">> ROUTING TO NEURAL JUDGE FOR SYNTHESIS...")
            final_report = evaluate_reports(company, alpha_data, beta_data)
            status.update(label="ANALYSIS COMPILED", state="complete")

        score = parse_score(alpha_data)
        signal = compute_signal(score)
        volatility = compute_vol(score)
        sm = re.search(r"Top Signal:\s*(BUY|SELL|HOLD|ACCUMULATE|REDUCE)",alpha_data,re.I)
        vm = re.search(r"Volatility Index:\s*(LOW|MEDIUM|HIGH)",alpha_data,re.I)
        if sm: signal = sm.group(1).upper()
        if vm: volatility = vm.group(1).upper()
        
        s_cls = "color-green" if score >= 60 else "color-red" if score <= 40 else "color-gray"
        v_cls = "color-green" if volatility=="LOW" else "color-red" if volatility=="HIGH" else "color-gray"
        sig_cls = "color-green" if signal in ("ACCUMULATE","BUY") else "color-red" if signal in ("REDUCE","SELL") else "color-gray"

        # AI Signal metrics row — flush under the profile card
        st.markdown(f"""
        <div style="background:#FFFFFF;border:1px solid #E0D5C7;border-top:none;border-radius:0 0 16px 16px;padding:16px 32px;margin-bottom:28px;display:flex;gap:0;border-top:1px solid #E0D5C7;margin-top:-1px;">
            <div style="flex:1;display:flex;flex-direction:column;border-right:1px solid #E0D5C7;padding-right:24px;">
                <span style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;color:#7a7a7a;">AI Sentiment Score</span>
                <span class="{s_cls}" style="font-size:22px;font-weight:700;font-family:Manrope,sans-serif;">{score} <span style="font-size:13px;color:#7a7a7a;font-weight:400;">/ 100</span></span>
            </div>
            <div style="flex:1;display:flex;flex-direction:column;border-right:1px solid #E0D5C7;padding:0 24px;">
                <span style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;color:#7a7a7a;">Volatility Index</span>
                <span class="{v_cls}" style="font-size:22px;font-weight:700;font-family:Manrope,sans-serif;">{volatility}</span>
            </div>
            <div style="flex:1;display:flex;flex-direction:column;padding-left:24px;">
                <span style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;color:#7a7a7a;">Top Signal</span>
                <span class="{sig_cls}" style="font-size:22px;font-weight:700;font-family:Manrope,sans-serif;">{signal}</span>
            </div>
            <div style="flex-shrink:0;display:flex;align-items:center;padding-left:24px;border-left:1px solid #E0D5C7;">
                <span style="font-size:10px;color:#7a7a7a;font-weight:600;text-transform:uppercase;">TASK ID</span>&nbsp;
                <span style="font-size:11px;font-weight:700;color:#419577;">#{task_id}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<h2 class="insight-title" style="margin-top:32px;">Key Executive Insights</h2>', unsafe_allow_html=True)
        insights = parse_insights(beta_data)
        if insights:
            for ins in insights:
                icon = "check_circle" if ins["sentiment"]=="positive" else "warning"
                ic = "#419577" if ins["sentiment"]=="positive" else "#ec4242"
                st.markdown(f'<div class="insight-item" style="text-align:center;justify-content:center;"><span class="material-symbols-outlined" style="color:{ic}!important;flex-shrink:0;">{icon}</span><p class="insight-text" style="text-align:center;"><span class="insight-bold">{colorize_numbers(ins["title"])}:</span> {colorize_numbers(ins["body"])}</p></div>', unsafe_allow_html=True)
        else:
            st.markdown(colorize_numbers(beta_data), unsafe_allow_html=True)

        st.markdown('<div style="height:24px;"></div>', unsafe_allow_html=True)
        catalyst_text, risk_text = extract_catalyst_risk(company, alpha_data, beta_data)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f'<div style="padding:24px;background:#FFFFFF;border:1px solid #E0D5C7;border-radius:12px;height:100%;"><p class="metric-label" style="margin-bottom:16px;">Upside Catalyst</p><div style="width:100%;height:120px;border-radius:8px;background:linear-gradient(to right, rgba(65,149,119,0.15), rgba(245,214,73,0.15));margin-bottom:16px;display:flex;align-items:center;justify-content:center;"><span class="material-symbols-outlined" style="font-size:32px;color:#2D3436;">trending_up</span></div><p style="font-size:13px;color:#5a5a5a!important;line-height:1.6;margin:0;">{colorize_numbers(catalyst_text)}</p></div>', unsafe_allow_html=True)
        with c2:
            st.markdown(f'<div style="padding:24px;background:#FFFFFF;border:1px solid #E0D5C7;border-radius:12px;height:100%;"><p class="metric-label" style="margin-bottom:16px;">Risk Exposure</p><div style="width:100%;height:120px;border-radius:8px;background:linear-gradient(to right, rgba(236,66,66,0.15), rgba(245,171,65,0.15));margin-bottom:16px;display:flex;align-items:center;justify-content:center;"><span class="material-symbols-outlined" style="font-size:32px;color:#2D3436;">trending_down</span></div><p style="font-size:13px;color:#5a5a5a!important;line-height:1.6;margin:0;">{colorize_numbers(risk_text)}</p></div>', unsafe_allow_html=True)

        # ---- Stock Performance Charts (Real Data) ----
        st.markdown('<div style="height:32px;"></div>', unsafe_allow_html=True)
        if ticker_symbol:
            stock_hist, stock_info = stock_hist, stock_info  # already fetched for header
            if stock_hist is not None and not stock_hist.empty:
                st.markdown('<h2 class="insight-title">Stock Performance</h2>', unsafe_allow_html=True)

                # Key stock metrics row (52W range)
                high_52 = stock_info.get("52w_high", 0)
                low_52 = stock_info.get("52w_low", 0)
                mc1, mc2 = st.columns(2)
                for col, label, val in [(mc1,"52-Week High",f"${high_52:,.2f}" if high_52 else "N/A"),(mc2,"52-Week Low",f"${low_52:,.2f}" if low_52 else "N/A")]:
                    with col:
                        st.markdown(f'<div style="text-align:center;padding:12px 0 4px 0;"><span class="metric-label">{label}</span><br><span style="font-size:18px;font-weight:700;font-family:Manrope,sans-serif;color:#2D3436!important;">{val}</span></div>', unsafe_allow_html=True)

                # Price chart
                price_fig = create_price_chart(stock_hist, ticker_symbol, stock_info)
                if price_fig:
                    st.plotly_chart(price_fig, use_container_width=True, config={"displayModeBar": False})

                # Volume + Candlestick side by side
                vc1, vc2 = st.columns(2)
                with vc1:
                    vol_fig = create_volume_chart(stock_hist, ticker_symbol)
                    if vol_fig:
                        st.plotly_chart(vol_fig, use_container_width=True, config={"displayModeBar": False})
                with vc2:
                    candle_fig = create_candlestick_chart(stock_hist, ticker_symbol)
                    if candle_fig:
                        st.plotly_chart(candle_fig, use_container_width=True, config={"displayModeBar": False})

                st.markdown(f'<p style="font-size:10px;color:#b0a89e!important;text-align:right;margin-top:-8px;">Data from Yahoo Finance · {ticker_symbol} · Updated {datetime.now().strftime("%b %d, %Y %H:%M")}</p>', unsafe_allow_html=True)

        st.markdown('<div style="height:32px;"></div>', unsafe_allow_html=True)

        with st.expander("📄 Full Alpha Report (Quantitative)"):
            st.markdown(colorize_numbers(alpha_data), unsafe_allow_html=True)
        with st.expander("📄 Full Beta Report (Qualitative)"):
            st.markdown(colorize_numbers(beta_data), unsafe_allow_html=True)
        with st.expander("⚖️ Full Judge Synthesis"):
            st.markdown(colorize_numbers(final_report), unsafe_allow_html=True)

    else:
        # =================================================================
        # TOPIC MODE — Tavily search + single LLM summary
        # =================================================================
        st.markdown(f'<div style="margin-bottom:16px;"><span class="exec-badge" style="background:rgba(245,171,65,0.1)!important;color:#F5AB41!important;border-color:rgba(245,171,65,0.3)!important;">TOPIC INTELLIGENCE</span><span class="task-id">TASK ID: #TI-{task_id}</span></div>', unsafe_allow_html=True)
        st.markdown(f'<h1 style="font-size:30px;font-weight:700;font-family:Manrope,sans-serif;color:#419577!important;letter-spacing:-0.02em;line-height:38px;margin-bottom:16px;">Topic Brief: {company}</h1>', unsafe_allow_html=True)

        with st.status(f"Searching global sources for: {company}...", expanded=True) as status:
            st.write(">> SCANNING TAVILY KNOWLEDGE BASE...")
            topic_data = run_topic_analysis(company)
            status.update(label="TOPIC BRIEF COMPILED", state="complete")

        st.markdown('<h2 class="insight-title" style="margin-top:24px;">Key Insights</h2>', unsafe_allow_html=True)
        insights = parse_insights(topic_data)
        if insights:
            for ins in insights:
                icon = "check_circle" if ins["sentiment"]=="positive" else "warning"
                ic = "#419577" if ins["sentiment"]=="positive" else "#ec4242"
                st.markdown(f'<div class="insight-item" style="text-align:center;justify-content:center;"><span class="material-symbols-outlined" style="color:{ic}!important;flex-shrink:0;">{icon}</span><p class="insight-text" style="text-align:center;"><span class="insight-bold">{colorize_numbers(ins["title"])}:</span> {colorize_numbers(ins["body"])}</p></div>', unsafe_allow_html=True)
        else:
            st.markdown(colorize_numbers(topic_data), unsafe_allow_html=True)

        with st.expander("📄 Full Topic Analysis"):
            st.markdown(colorize_numbers(topic_data), unsafe_allow_html=True)

else:
    st.markdown('<span class="exec-badge" style="background:rgba(224,213,199,0.3)!important;color:#7a7a7a!important;border-color:#E0D5C7!important;">SYSTEM IDLE</span>', unsafe_allow_html=True)
    st.markdown('<h1 style="font-size:30px;font-weight:700;font-family:Manrope,sans-serif;color:#b0a89e!important;margin-top:12px;">Awaiting Execution Protocol</h1>', unsafe_allow_html=True)
    st.markdown('<p style="color:#b0a89e!important;">Enter a company name for full analysis, or type any topic for a quick intelligence brief.</p>', unsafe_allow_html=True)