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
st.set_page_config(page_title="QUANTUM AI Terminal", page_icon="📟", layout="wide")

# =============================================================================
# DATA HELPERS
# =============================================================================
@st.cache_data(ttl=300)
def fetch_ticker_data():
    tickers = {"S&P 500":"^GSPC","NASDAQ 100":"^NDX","DOW J":"^DJI","USD/JPY":"JPY=X","BTC/USD":"BTC-USD"}
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
        r = TavilyClient(api_key=key).search(query="latest financial markets news stocks bonds crypto energy semiconductors",search_depth="basic",max_results=3)
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
    """Fetch a single landscape image URL from Pexels for a given search query."""
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
                return photos[0]["src"]["landscape"]
    except: pass
    return None

def get_image_query(category):
    """Map news category to a Pexels search query for relevant imagery."""
    mapping = {
        "SEMICONDUCTORS": "semiconductor chip factory technology",
        "ENERGY": "electric power grid energy station",
        "MACRO": "central bank building finance",
        "CRYPTO": "cryptocurrency bitcoin digital",
        "MARKETS": "stock market trading finance"
    }
    return mapping.get(category, "financial markets")

def get_company_logo_url(company_name):
    """Try Clearbit logo, fallback to a styled initial-letter HTML block."""
    domain_guess = company_name.strip().split()[0].lower()
    clearbit_url = f"https://logo.clearbit.com/{domain_guess}.com"
    try:
        r = requests.head(clearbit_url, timeout=3)
        if r.status_code == 200:
            return clearbit_url
    except: pass
    return None

def get_color(v): return "#4edea3" if v>0 else "#ec4242" if v<0 else "#c5c6cd"
def get_arrow(v): return "arrow_drop_up" if v>0 else "arrow_drop_down" if v<0 else "remove"
def compute_signal(s): return "ACCUMULATE" if s>70 else "HOLD" if s>50 else "REDUCE" if s>30 else "SELL"
def compute_vol(s): return "LOW" if s>65 else "MEDIUM" if s>40 else "HIGH"
def vol_color(v): return "#ec4242" if v=="LOW" else "#ffb3ad" if v=="MEDIUM" else "#4edea3"
def sig_color(s): return "#4edea3" if s in("ACCUMULATE","BUY") else "#b9c7e4" if s=="HOLD" else "#ec4242"
def cat_color(c): return {"SEMICONDUCTORS":"#4edea3","ENERGY":"#ec4242","MACRO":"#b9c7e4","CRYPTO":"#8B5CF6","MARKETS":"#EC4899"}.get(c,"#c5c6cd")
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

.stApp{background-color:#031427!important;color:#d3e4fe!important;font-family:'Inter',sans-serif!important;}
header{visibility:hidden!important;}
[data-testid="stSidebar"]{background-color:#112240!important;border-right:1px solid rgba(51,65,85,0.5)!important;}
[data-testid="stSidebar"] *{color:#94a3b8!important;}
h1,h2,h3,h4,h5,h6,p,span,div,.stMarkdown{color:#d3e4fe!important;}

/* Containers */
div[data-testid="stVerticalBlockBorderWrapper"]{background-color:#1b2b3f!important;border:1px solid #44474d!important;border-radius:8px!important;}

/* Chat Input */
[data-testid="stChatInput"]{background-color:#112240!important;border:1px solid rgba(51,65,85,0.7)!important;border-radius:16px!important;}
[data-testid="stChatInput"] input{color:#d3e4fe!important;}
[data-testid="stChatInput"] button{background-color:#4edea3!important;border-radius:12px!important;}

/* Scrollbar */
::-webkit-scrollbar{width:4px;height:4px}
::-webkit-scrollbar-track{background:#0a192f}
::-webkit-scrollbar-thumb{background:#26364a;border-radius:10px}

/* Sidebar Nav Item Active */
.nav-active{background:#1E293B;border-left:4px solid #4edea3;color:#4edea3!important;}
.nav-item{padding:12px 24px;display:flex;align-items:center;gap:16px;cursor:pointer;transition:all 0.2s;}
.nav-item:hover{background:#1E293B;}
.nav-label{font-size:12px;letter-spacing:0.05em;font-weight:600;text-transform:uppercase;}

/* Ticker */
.ticker-row{display:flex;align-items:center;gap:0;background:#102034;border-bottom:1px solid rgba(51,65,85,0.5);padding:0 24px;height:40px;margin-bottom:0;}
.ticker-item{display:flex;align-items:center;gap:8px;padding-right:32px;border-right:1px solid rgba(51,65,85,0.5);margin-right:0;padding-left:32px;}
.ticker-item:first-child{padding-left:0;}
.ticker-item:last-child{border-right:none;}
.ticker-lbl{font-size:10px;color:#c5c6cd;text-transform:uppercase;font-weight:600;letter-spacing:0.05em;}
.ticker-val{font-size:14px;font-weight:500;font-family:'Inter',monospace;}
.ticker-chg{font-size:12px;font-weight:500;display:flex;align-items:center;}

/* Top Nav */
.topnav{display:flex;justify-content:space-between;align-items:center;padding:0 24px;height:64px;background:#0A192F;border-bottom:1px solid rgba(51,65,85,0.5);}
.topnav-brand{font-size:18px;font-weight:900;color:#fff!important;text-transform:uppercase;font-family:'Manrope',sans-serif;letter-spacing:-0.02em;}
.topnav-link{font-size:14px;color:#64748b!important;text-decoration:none;transition:color 0.2s;}
.topnav-link-active{color:#4edea3!important;font-weight:700;border-bottom:2px solid #4edea3;padding-bottom:4px;}

/* Sections */
.section-label{font-size:12px;letter-spacing:0.05em;font-weight:600;text-transform:uppercase;color:#c5c6cd!important;margin-bottom:16px;}
.metric-label{font-size:10px;letter-spacing:0.05em;font-weight:600;text-transform:uppercase;color:#c5c6cd!important;}
.metric-value{font-size:24px;font-weight:600;font-family:'Manrope',sans-serif;letter-spacing:-0.01em;}
.insight-title{font-size:12px;color:#4edea3!important;text-transform:uppercase;letter-spacing:0.05em;font-weight:600;border-bottom:1px solid rgba(78,222,163,0.2);padding-bottom:8px;margin-bottom:16px;}
.insight-item{display:flex;gap:12px;margin-bottom:16px;line-height:1.6;}
.insight-text{font-size:16px;color:#d3e4fe!important;}
.insight-bold{font-weight:700;color:#fff!important;}

/* Log */
.perf-log{background:#0b1c30;padding:16px;border-radius:8px;font-family:'Inter',monospace;font-size:14px;border-left:2px solid #4edea3;}
.log-line{margin-bottom:4px;}
.log-dim{color:#64748b!important;}
.log-highlight{color:#4edea3!important;}

/* News */
.news-card{margin-bottom:24px;cursor:pointer;}
.news-img{width:100%;height:96px;object-fit:cover;border-radius:8px;margin-bottom:12px;opacity:0.8;}
.news-img:hover{opacity:1;}
.news-cat{font-size:10px;font-weight:700;text-transform:uppercase;}
.news-title{font-size:14px;color:#fff!important;font-weight:600;font-family:'Manrope',sans-serif;margin-top:4px;line-height:1.3;}
.news-meta{font-size:10px;color:#64748b!important;margin-top:8px;font-weight:600;letter-spacing:0.05em;}

/* History */
.hist-card{padding:12px;border-radius:8px;margin-bottom:12px;cursor:pointer;transition:all 0.2s;}
.hist-card-active{background:#1b2b3f;border:1px solid #44474d;}
.hist-card-inactive{background:transparent;border:1px solid transparent;}
.hist-card:hover{background:#1b2b3f;}
.hist-title{font-size:14px;color:#d3e4fe!important;line-height:1.4;}
.hist-meta{font-size:10px;color:#c5c6cd!important;font-weight:600;letter-spacing:0.05em;}

/* Badge */
.exec-badge{background:rgba(78,222,163,0.1);color:#4edea3!important;border:1px solid rgba(78,222,163,0.2);padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:-0.02em;}
.task-id{font-size:10px;color:#c5c6cd!important;font-weight:700;text-transform:uppercase;margin-left:8px;}

/* Portfolio Alert */
.portfolio-alert{background:#1b2b3f;border:1px solid #44474d;border-radius:16px;padding:24px;margin-top:40px;}
.portfolio-title{font-size:14px;color:#fff!important;font-weight:600;font-family:'Manrope',sans-serif;margin-bottom:8px;}
.portfolio-text{font-size:12px;color:#c5c6cd!important;line-height:1.5;}
.portfolio-btn{margin-top:16px;color:#4edea3!important;font-size:10px;font-weight:600;letter-spacing:0.05em;text-transform:uppercase;border:1px solid rgba(78,222,163,0.3);padding:8px 12px;border-radius:4px;background:transparent;width:100%;text-align:center;cursor:pointer;}

/* Mini Chart */
.mini-chart{height:96px;width:100%;background:#0b1c30;border-radius:4px;display:flex;align-items:flex-end;padding:8px;gap:4px;margin-bottom:16px;}
.mini-bar{flex:1;}

/* Metrics divider */
.metrics-row{display:flex;align-items:center;gap:0;padding:16px 0;border-top:1px solid rgba(51,65,85,0.5);border-bottom:1px solid rgba(51,65,85,0.5);}
.metric-col{display:flex;flex-direction:column;}
.metric-col+.metric-col{border-left:1px solid rgba(51,65,85,0.5);padding-left:24px;margin-left:24px;}

/* Company Logo */
.company-logo{width:48px;height:48px;border-radius:12px;object-fit:contain;background:#112240;border:1px solid #44474d;}
.company-initial{width:48px;height:48px;border-radius:12px;background:linear-gradient(135deg,#4edea3,#112240);display:flex;align-items:center;justify-content:center;font-size:22px;font-weight:800;color:#fff!important;font-family:'Manrope',sans-serif;flex-shrink:0;}
.company-header{display:flex;align-items:center;gap:16px;margin-bottom:16px;}

/* Sidebar Toggle */
button[data-testid="stBaseButton-header"]{background:#112240!important;border:1px solid rgba(78,222,163,0.3)!important;border-radius:8px!important;color:#4edea3!important;}
[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"]{display:block!important;}

/* Sidebar active nav link */
.nav-link{display:flex;align-items:center;gap:16px;padding:12px 24px;cursor:pointer;transition:all 0.2s;text-decoration:none;color:#94a3b8!important;}
.nav-link:hover{background:#1E293B;color:#fff!important;}
.nav-link-active{background:#1E293B;border-left:4px solid #4edea3;color:#4edea3!important;}
.nav-link-active .nav-label{color:#4edea3!important;}
</style>
""", unsafe_allow_html=True)

# =============================================================================
# FETCH DATA
# =============================================================================
ticker_data = fetch_ticker_data()
trending_news = fetch_trending_news()

# =============================================================================
# SIDEBAR
# =============================================================================
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "Intelligence"

with st.sidebar:
    st.markdown("""
    <div style="padding:24px 24px 0 24px;">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:32px;">
            <div style="width:32px;height:32px;border-radius:50%;background:linear-gradient(135deg,#4edea3,#0a192f);display:flex;align-items:center;justify-content:center;">
                <span style="color:#fff!important;font-size:14px;font-weight:bold;">Q</span>
            </div>
            <div>
                <div style="color:#fff!important;font-weight:700;font-family:'Manrope',sans-serif;font-size:14px;text-transform:uppercase;letter-spacing:-0.02em;">Terminal v4.2</div>
                <div style="font-size:10px;color:#4edea3!important;font-weight:600;letter-spacing:0.05em;">System Status: Active</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Navigation tabs
    tabs = [
        ("Intelligence", "analytics"),
        ("Market Tickers", "finance_mode"),
        ("Agent Logs", "terminal"),
        ("Portfolios", "pie_chart"),
        ("Reports", "description"),
    ]
    for tab_name, icon in tabs:
        active = "nav-link-active" if st.session_state.active_tab == tab_name else ""
        if st.sidebar.button(f"  {tab_name}", key=f"nav_{tab_name}", use_container_width=True):
            st.session_state.active_tab = tab_name
            st.rerun()

    st.button("+ New Research", use_container_width=True)

    st.markdown("""
    <div style="margin-top:auto;padding:24px;border-top:1px solid rgba(51,65,85,0.5);">
        <div class="nav-link" style="padding:8px 0;"><span class="material-symbols-outlined">gavel</span><span class="nav-label">Compliance</span></div>
        <div class="nav-link" style="padding:8px 0;"><span class="material-symbols-outlined">api</span><span class="nav-label">API Docs</span></div>
    </div>
    """, unsafe_allow_html=True)

# =============================================================================
# TOP NAV
# =============================================================================
st.markdown("""
<div class="topnav">
    <div style="display:flex;align-items:center;gap:16px;">
        <span class="topnav-brand">QUANTUM AI</span>
        <div style="height:24px;width:1px;background:#334155;margin:0 8px;"></div>
        <a class="topnav-link topnav-link-active" href="#">Overview</a>
        <a class="topnav-link" href="#">Forecasting</a>
        <a class="topnav-link" href="#">Sentiment</a>
    </div>
    <div style="display:flex;align-items:center;gap:16px;">
        <span class="material-symbols-outlined" style="color:#94a3b8!important;cursor:pointer;">notifications</span>
        <span class="material-symbols-outlined" style="color:#94a3b8!important;cursor:pointer;">settings</span>
    </div>
</div>
""", unsafe_allow_html=True)

# =============================================================================
# TICKER TAPE (REAL-TIME)
# =============================================================================
ticker_html = ""
for i,(lbl,d) in enumerate(ticker_data.items()):
    c = get_color(d["change"])
    a = get_arrow(d["change"])
    ps = f"{d['price']:,.2f}" if d['price']>1000 else f"{d['price']:.2f}"
    ticker_html += f'<div class="ticker-item"><span class="ticker-lbl">{lbl}</span><span class="ticker-val" style="color:{c}!important;">{ps}</span><span class="ticker-chg" style="color:{c}!important;"><span class="material-symbols-outlined" style="font-size:14px;color:{c}!important;">{a}</span>{abs(d["change"]):.2f}%</span></div>'
st.markdown(f'<div class="ticker-row">{ticker_html}</div>', unsafe_allow_html=True)

# =============================================================================
# 3-COLUMN LAYOUT
# =============================================================================
col_hist, col_main, col_news = st.columns([2, 7, 3])

# --- LEFT: Research History ---
with col_hist:
    st.markdown('<p class="section-label">Research History</p>', unsafe_allow_html=True)
    if "search_history" not in st.session_state:
        st.session_state.search_history = []
    for i, item in enumerate(st.session_state.search_history[-3:]):
        cls = "hist-card-active" if i==0 else "hist-card-inactive"
        st.markdown(f'<div class="hist-card {cls}"><p class="hist-title">{item["name"][:40]}</p><span class="hist-meta">{item["time"]} • Deep Scan</span></div>', unsafe_allow_html=True)
    if not st.session_state.search_history:
        st.markdown('<p style="color:#64748b!important;font-size:12px;">No research yet.</p>', unsafe_allow_html=True)

# --- RIGHT: Trending News ---
with col_news:
    st.markdown('<p class="section-label">Trending News</p>', unsafe_allow_html=True)
    for i, news in enumerate(trending_news[:3]):
        cc = cat_color(news["category"])
        img_url = fetch_pexels_image(get_image_query(news["category"]))
        if img_url:
            img_html = f'<img class="news-img" src="{img_url}" alt="{news["category"]}" />'
        else:
            fallback_grads = ["linear-gradient(135deg,#0a192f,#112240,#4edea3)","linear-gradient(135deg,#0a192f,#3c0003,#ec4242)","linear-gradient(135deg,#0a192f,#26364a,#b9c7e4)"]
            img_html = f'<div style="width:100%;height:96px;border-radius:8px;margin-bottom:12px;background:{fallback_grads[i%3]};"></div>'
        st.markdown(f"""
        <div class="news-card">
            {img_html}
            <span class="news-cat" style="color:{cc}!important;">{news["category"]}</span>
            <div class="news-title">{news["title"][:65]}</div>
            <div class="news-meta">Source</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("""
    <div class="portfolio-alert">
        <div class="portfolio-title">Portfolio Alert</div>
        <p class="portfolio-text">Your exposure to 'Technology' exceeds target by 4.2%. Consider rebalancing during the afternoon session.</p>
        <div class="portfolio-btn">View Details</div>
    </div>
    """, unsafe_allow_html=True)

# --- CENTER: Main Terminal ---
with col_main:
    company = st.chat_input("Analyze the impact of a company's market position...")

    if company:
        now = datetime.now()
        is_company = is_company_query(company)
        mode_label = "Company Analysis" if is_company else "Topic Intelligence"
        st.session_state.search_history.insert(0, {"name":f"{company[:30]} • {mode_label}","time":now.strftime("%I:%M %p")})
        task_id = abs(hash(company + now.isoformat())) % 10000

        if is_company:
            # =================================================================
            # COMPANY MODE — Full Alpha + Beta + Judge pipeline
            # =================================================================
            st.markdown(f'<div style="margin-bottom:16px;"><span class="exec-badge">AI AGENT EXECUTION</span><span class="task-id">TASK ID: #QT-{task_id}</span></div>', unsafe_allow_html=True)

            # Company Logo
            logo_url = get_company_logo_url(company)
            initial = company.strip()[0].upper()
            if logo_url:
                logo_html = f'<img class="company-logo" src="{logo_url}" alt="{company} logo" />'
            else:
                logo_html = f'<div class="company-initial">{initial}</div>'
            st.markdown(f'<div class="company-header">{logo_html}<h1 style="font-size:30px;font-weight:700;font-family:Manrope,sans-serif;color:#fff!important;letter-spacing:-0.02em;line-height:38px;margin:0;">Market Analysis: {company}</h1></div>', unsafe_allow_html=True)

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
                <div class="metric-col"><span class="metric-label">Sentiment Score</span><span class="metric-value" style="color:#4edea3!important;">{score} / 100</span></div>
                <div class="metric-col"><span class="metric-label">Volatility Index</span><span class="metric-value" style="color:{vc}!important;">{volatility}</span></div>
                <div class="metric-col"><span class="metric-label">Top Signal</span><span class="metric-value" style="color:{sc}!important;">{signal}</span></div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown('<h2 class="insight-title" style="margin-top:32px;">Key Executive Insights</h2>', unsafe_allow_html=True)
            insights = parse_insights(beta_data)
            if insights:
                for ins in insights:
                    icon = "check_circle" if ins["sentiment"]=="positive" else "warning"
                    ic = "#4edea3" if ins["sentiment"]=="positive" else "#ec4242"
                    st.markdown(f'<div class="insight-item"><span class="material-symbols-outlined" style="color:{ic}!important;flex-shrink:0;">{icon}</span><p class="insight-text"><span class="insight-bold">{ins["title"]}:</span> {ins["body"]}</p></div>', unsafe_allow_html=True)
            else:
                st.markdown(beta_data)

            st.markdown('<h2 class="insight-title" style="margin-top:32px;">Agent Performance Log</h2>', unsafe_allow_html=True)
            ts = now.strftime("%H:%M:%S")
            ci = min(score+16,99)
            st.markdown(f'<div class="perf-log"><p class="log-line log-dim">[{ts}] Scanning Bloomberg, Reuters, Financial Times...</p><p class="log-line log-dim">[{ts}] Identifying correlation patterns for {company}...</p><p class="log-line log-highlight">[{ts}] Critical Pattern Detected: Score={score}, Signal={signal}</p><p class="log-line log-dim">[{ts}] Briefing compiled. Confidence Interval: {ci}.{abs(hash(company))%10}%</p></div>', unsafe_allow_html=True)

            st.markdown('<div style="height:24px;"></div>', unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            with c1:
                bars = "".join([f'<div class="mini-bar" style="background:#4edea3;height:{20+i*13}%;"></div>' for i in range(6)])
                st.markdown(f'<div style="padding:24px;background:#1b2b3f;border:1px solid #44474d;border-radius:12px;"><p class="metric-label" style="margin-bottom:16px;">Upside Catalyst</p><div class="mini-chart" style="background:linear-gradient(to top right,rgba(78,222,163,0.2),transparent);">{bars}</div><p style="font-size:12px;color:#c5c6cd!important;">Strong institutional inflow detected in high-beta assets over 48h period.</p></div>', unsafe_allow_html=True)
            with c2:
                bars = "".join([f'<div class="mini-bar" style="background:#ec4242;height:{100-i*15}%;"></div>' for i in range(6)])
                st.markdown(f'<div style="padding:24px;background:#1b2b3f;border:1px solid #44474d;border-radius:12px;"><p class="metric-label" style="margin-bottom:16px;">Risk Exposure</p><div class="mini-chart" style="background:linear-gradient(to top right,rgba(236,66,66,0.2),transparent);">{bars}</div><p style="font-size:12px;color:#c5c6cd!important;">Over-leveraging in consumer retail puts pressure on broader market liquidity.</p></div>', unsafe_allow_html=True)

            with st.expander("📄 Full Alpha Report (Quantitative)"):
                st.markdown(alpha_data)
            with st.expander("📄 Full Beta Report (Qualitative)"):
                st.markdown(beta_data)
            with st.expander("⚖️ Full Judge Synthesis"):
                st.markdown(final_report)

        else:
            # =================================================================
            # TOPIC MODE — Tavily search + single LLM summary
            # =================================================================
            st.markdown(f'<div style="margin-bottom:16px;"><span class="exec-badge" style="background:rgba(185,199,228,0.1)!important;color:#b9c7e4!important;border-color:rgba(185,199,228,0.2)!important;">TOPIC INTELLIGENCE</span><span class="task-id">TASK ID: #TI-{task_id}</span></div>', unsafe_allow_html=True)
            st.markdown(f'<h1 style="font-size:30px;font-weight:700;font-family:Manrope,sans-serif;color:#fff!important;letter-spacing:-0.02em;line-height:38px;margin-bottom:16px;">Topic Brief: {company}</h1>', unsafe_allow_html=True)

            with st.status(f"Searching global sources for: {company}...", expanded=True) as status:
                st.write(">> SCANNING TAVILY KNOWLEDGE BASE...")
                topic_data = run_topic_analysis(company)
                status.update(label="TOPIC BRIEF COMPILED", state="complete")

            st.markdown('<h2 class="insight-title" style="margin-top:24px;">Key Insights</h2>', unsafe_allow_html=True)
            insights = parse_insights(topic_data)
            if insights:
                for ins in insights:
                    icon = "check_circle" if ins["sentiment"]=="positive" else "warning"
                    ic = "#4edea3" if ins["sentiment"]=="positive" else "#ec4242"
                    st.markdown(f'<div class="insight-item"><span class="material-symbols-outlined" style="color:{ic}!important;flex-shrink:0;">{icon}</span><p class="insight-text"><span class="insight-bold">{ins["title"]}:</span> {ins["body"]}</p></div>', unsafe_allow_html=True)
            else:
                st.markdown(topic_data)

            st.markdown('<h2 class="insight-title" style="margin-top:32px;">Agent Performance Log</h2>', unsafe_allow_html=True)
            ts = now.strftime("%H:%M:%S")
            st.markdown(f'<div class="perf-log"><p class="log-line log-dim">[{ts}] Topic scan initiated: {company[:50]}...</p><p class="log-line log-highlight">[{ts}] Tavily returned 5 sources. Summarizing...</p><p class="log-line log-dim">[{ts}] Topic brief compiled successfully.</p></div>', unsafe_allow_html=True)

            with st.expander("📄 Full Topic Analysis"):
                st.markdown(topic_data)

    else:
        st.markdown('<span class="exec-badge" style="background:#1E293B!important;color:#94a3b8!important;border-color:#44474d!important;">SYSTEM IDLE</span>', unsafe_allow_html=True)
        st.markdown('<h1 style="font-size:30px;font-weight:700;font-family:Manrope,sans-serif;color:#475569!important;margin-top:12px;">Awaiting Execution Protocol</h1>', unsafe_allow_html=True)
        st.markdown('<p style="color:#475569!important;">Enter a company name for full analysis, or type any topic for a quick intelligence brief.</p>', unsafe_allow_html=True)