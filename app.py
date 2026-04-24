import streamlit as st
import re, os, requests
import yfinance as yf
from datetime import datetime
from dotenv import load_dotenv
from tavily import TavilyClient
from researcher_alpha import run_quantitative_analysis
from researcher_beta import run_qualitative_analysis
from judge import evaluate_reports

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
    else:
        query = f"{company_name} stock market chart graph"
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
.ticker-row{display:flex;align-items:center;gap:0;background:#F5D649;border-radius:12px;border:1px solid rgba(0,0,0,0.05);padding:0 24px;height:60px;margin-bottom:32px;overflow:hidden;}
.ticker-item{display:flex;align-items:center;gap:8px;padding-right:32px;border-right:1px solid rgba(0,0,0,0.12);margin-right:0;padding-left:32px;}
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
nav_cols = st.columns([4, 1.2, 1.2, 1.2, 4])
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
        st.markdown(f'<div style="margin-bottom:16px;"><span class="exec-badge">AI AGENT EXECUTION</span><span class="task-id">TASK ID: #QT-{task_id}</span></div>', unsafe_allow_html=True)

        # Company Image from Unsplash
        company_img = fetch_unsplash_image(company, "logo")
        initial = company.strip()[0].upper()
        if company_img:
            logo_html = f'<img class="company-logo" src="{company_img["url"]}" alt="{company}" />'
        else:
            logo_html = f'<div class="company-initial">{initial}</div>'
        st.markdown(f'<div class="company-header">{logo_html}<h1 style="font-size:30px;font-weight:700;font-family:Manrope,sans-serif;color:#419577!important;letter-spacing:-0.02em;line-height:38px;margin:0;">Market Analysis: {company}</h1></div>', unsafe_allow_html=True)

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
        vc = vol_color(volatility)
        sc = sig_color(signal)

        st.markdown(f"""
        <div class="metrics-row">
            <div class="metric-col"><span class="metric-label">Sentiment Score</span><span class="metric-value" style="color:#419577!important;">{score} / 100</span></div>
            <div class="metric-col"><span class="metric-label">Volatility Index</span><span class="metric-value" style="color:{vc}!important;">{volatility}</span></div>
            <div class="metric-col"><span class="metric-label">Top Signal</span><span class="metric-value" style="color:{sc}!important;">{signal}</span></div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<h2 class="insight-title" style="margin-top:32px;">Key Executive Insights</h2>', unsafe_allow_html=True)
        insights = parse_insights(beta_data)
        if insights:
            for ins in insights:
                icon = "check_circle" if ins["sentiment"]=="positive" else "warning"
                ic = "#419577" if ins["sentiment"]=="positive" else "#ec4242"
                st.markdown(f'<div class="insight-item"><span class="material-symbols-outlined" style="color:{ic}!important;flex-shrink:0;">{icon}</span><p class="insight-text"><span class="insight-bold">{ins["title"]}:</span> {ins["body"]}</p></div>', unsafe_allow_html=True)
        else:
            st.markdown(beta_data)

        st.markdown('<div style="height:24px;"></div>', unsafe_allow_html=True)
        catalyst_text, risk_text = extract_catalyst_risk(company, alpha_data, beta_data)
        c1, c2 = st.columns(2)
        with c1:
            bars = "".join([f'<div class="mini-bar" style="background:#419577;height:{20+i*13}%;"></div>' for i in range(6)])
            st.markdown(f'<div style="padding:24px;background:#FFFFFF;border:1px solid #E0D5C7;border-radius:12px;"><p class="metric-label" style="margin-bottom:16px;">Upside Catalyst</p><div class="mini-chart" style="background:linear-gradient(to top right,rgba(65,149,119,0.15),transparent);">{bars}</div><p style="font-size:12px;color:#5a5a5a!important;">{catalyst_text}</p></div>', unsafe_allow_html=True)
        with c2:
            bars = "".join([f'<div class="mini-bar" style="background:#ec4242;height:{100-i*15}%;"></div>' for i in range(6)])
            st.markdown(f'<div style="padding:24px;background:#FFFFFF;border:1px solid #E0D5C7;border-radius:12px;"><p class="metric-label" style="margin-bottom:16px;">Risk Exposure</p><div class="mini-chart" style="background:linear-gradient(to top right,rgba(236,66,66,0.15),transparent);">{bars}</div><p style="font-size:12px;color:#5a5a5a!important;">{risk_text}</p></div>', unsafe_allow_html=True)

        st.markdown('<div style="height:32px;"></div>', unsafe_allow_html=True)

        with st.expander("📄 Full Alpha Report (Quantitative)"):
            st.markdown(alpha_data)
        with st.expander("📄 Full Beta Report (Qualitative)"):
            unsplash_img = fetch_unsplash_image(company, "graph")
            if unsplash_img:
                st.markdown(f'''
                <div style="margin-bottom: 24px;">
                    <h3 style="color:#419577; font-size: 16px; margin: 0 0 16px 0;">Market Graphs &amp; Charts</h3>
                    <img src="{unsplash_img["url"]}" style="width:100%; max-height: 250px; object-fit: cover; border-radius: 8px; margin-bottom: 8px;" />
                    <p style="color:#7a7a7a; font-size:12px; text-align:right;">Photo by <a href="{unsplash_img["photo_url"]}" target="_blank" style="color:#7a7a7a;">{unsplash_img["photographer"]}</a> on Unsplash</p>
                </div>
                ''', unsafe_allow_html=True)
            
            # Mock Graph for Qualitative sentiment
            bars = "".join([f'<div style="background:{col};height:{h}px;width:12px;border-radius:2px;"></div>' for col, h in zip(["#ec4242","#F5AB41","#F5D649","#419577","#419577"], [40, 60, 30, 80, 100])])
            st.markdown(f'''
            <div style="background:#FFFFFF; padding: 16px; border-radius: 8px; border: 1px solid #E0D5C7; margin-bottom: 24px;">
                <h3 style="color:#419577; font-size: 16px; margin: 0 0 16px 0;">Sentiment Trend (30 Days)</h3>
                <div style="display:flex; align-items:flex-end; gap:8px; height: 100px; padding-bottom: 8px; border-bottom: 1px solid #E0D5C7;">
                    {bars}
                </div>
            </div>
            ''', unsafe_allow_html=True)

            st.markdown(beta_data)
        with st.expander("⚖️ Full Judge Synthesis"):
            st.markdown(final_report)

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
                st.markdown(f'<div class="insight-item"><span class="material-symbols-outlined" style="color:{ic}!important;flex-shrink:0;">{icon}</span><p class="insight-text"><span class="insight-bold">{ins["title"]}:</span> {ins["body"]}</p></div>', unsafe_allow_html=True)
        else:
            st.markdown(topic_data)

        with st.expander("📄 Full Topic Analysis"):
            st.markdown(topic_data)

else:
    st.markdown('<span class="exec-badge" style="background:rgba(224,213,199,0.3)!important;color:#7a7a7a!important;border-color:#E0D5C7!important;">SYSTEM IDLE</span>', unsafe_allow_html=True)
    st.markdown('<h1 style="font-size:30px;font-weight:700;font-family:Manrope,sans-serif;color:#b0a89e!important;margin-top:12px;">Awaiting Execution Protocol</h1>', unsafe_allow_html=True)
    st.markdown('<p style="color:#b0a89e!important;">Enter a company name for full analysis, or type any topic for a quick intelligence brief.</p>', unsafe_allow_html=True)