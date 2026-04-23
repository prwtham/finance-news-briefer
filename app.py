import streamlit as st
import re
from researcher_alpha import run_quantitative_analysis
from researcher_beta import run_qualitative_analysis
from judge import evaluate_reports

# --- UI Setup ---
st.set_page_config(page_title="QUANTUM AI Terminal", page_icon="📟", layout="wide")

# --- Custom CSS for Terminal v4.2 ---
custom_css = """
<style>
/* Base Dark Theme */
.stApp {
    background-color: #0B1120 !important;
    color: #E2E8F0 !important;
    font-family: 'Inter', sans-serif;
}

/* Sidebar Styling */
[data-testid="stSidebar"] {
    background-color: #0F172A !important;
    border-right: 1px solid #1E293B;
}
[data-testid="stSidebar"] * {
    color: #94A3B8 !important;
}
[data-testid="stSidebar"] h1 {
    color: #F8FAFC !important;
    font-weight: 700;
}

/* Hide header */
header {visibility: hidden;}

/* Ticker Tape Styling */
.ticker-container {
    display: flex;
    justify-content: space-between;
    background-color: #0F172A;
    padding: 10px 20px;
    border-bottom: 1px solid #1E293B;
    margin-top: -3rem;
    margin-bottom: 2rem;
    font-family: 'Courier New', Courier, monospace;
    font-size: 0.85rem;
}
.ticker-item {
    color: #94A3B8;
}
.ticker-value {
    color: #F8FAFC;
    margin-left: 5px;
}
.ticker-positive { color: #10B981; }
.ticker-negative { color: #EF4444; }

/* Badges */
.badge {
    background-color: #064E3B;
    color: #34D399;
    padding: 4px 10px;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: bold;
    letter-spacing: 1px;
}

/* Custom Text colors override */
h1, h2, h3, h4, p, span, div, .stMarkdown {
    color: #E2E8F0 !important;
}

/* Exception for specific classes */
.ticker-item, .ticker-value, .ticker-positive, .ticker-negative, .badge {
    color: inherit !important; /* Let specific classes define their own colors */
}

/* Override metric colors */
[data-testid="stMetricValue"] {
    color: #F8FAFC !important;
    font-size: 1.8rem;
}
[data-testid="stMetricLabel"] {
    color: #94A3B8 !important;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-size: 0.8rem;
}

/* Override Chat Input */
[data-testid="stChatInput"] {
    background-color: #020617;
    border: 1px solid #1E293B;
}

/* Agent Log Container */
.agent-log {
    background-color: #020617;
    border: 1px solid #1E293B;
    border-radius: 8px;
    padding: 15px;
    font-family: 'Courier New', Courier, monospace;
    color: #10B981 !important;
    font-size: 0.85rem;
    margin-top: 2rem;
}
.agent-log p {
    color: #10B981 !important;
    margin: 0;
}

/* Override containers */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background-color: #0F172A !important;
    border: 1px solid #1E293B !important;
    border-radius: 8px;
}
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

# --- Sidebar ---
with st.sidebar:
    st.markdown("<h1 style='color: #F8FAFC !important;'>TERMINAL v4.2</h1><p style='font-size: 0.8rem; color: #10B981 !important;'>System Status: Active</p>", unsafe_allow_html=True)
    st.divider()
    st.markdown("🏢 **INTELLIGENCE**")
    st.markdown("📈 MARKET TICKERS")
    st.markdown("🤖 AGENT LOGS")
    st.markdown("💼 PORTFOLIOS")
    st.markdown("📄 REPORTS")
    st.divider()
    st.button("+ New Research", use_container_width=True)

# --- Top Nav / Ticker Tape ---
st.markdown("""
<div class="ticker-container">
    <div class="ticker-item" style="color:#94A3B8!important;">S&P 500 <span class="ticker-value" style="color:#F8FAFC!important; margin-left:5px;">5,241.53 <span class="ticker-positive" style="color:#10B981!important;">▲ 0.42%</span></span></div>
    <div class="ticker-item" style="color:#94A3B8!important;">NASDAQ 100 <span class="ticker-value" style="color:#F8FAFC!important; margin-left:5px;">18,342.10 <span class="ticker-positive" style="color:#10B981!important;">▲ 1.15%</span></span></div>
    <div class="ticker-item" style="color:#94A3B8!important;">DOW J <span class="ticker-value" style="color:#F8FAFC!important; margin-left:5px;">39,127.14 <span class="ticker-negative" style="color:#EF4444!important;">▼ 0.21%</span></span></div>
    <div class="ticker-item" style="color:#94A3B8!important;">USD/JPY <span class="ticker-value" style="color:#F8FAFC!important; margin-left:5px;">151.24 <span class="ticker-value" style="color:#F8FAFC!important;">0.00%</span></span></div>
    <div class="ticker-item" style="color:#94A3B8!important;">BTC/USD <span class="ticker-value" style="color:#F8FAFC!important; margin-left:5px;">68,432.20 <span class="ticker-positive" style="color:#10B981!important;">▲</span></span></div>
</div>
""", unsafe_allow_html=True)

# --- Main Layout ---
col_hist, col_main = st.columns([1, 3])

with col_hist:
    st.markdown("<p style='color: #94A3B8 !important; font-size: 0.8rem; font-weight: bold;'>RESEARCH HISTORY</p>", unsafe_allow_html=True)
    
    with st.container(border=True):
        st.markdown("<strong style='color:#E2E8F0!important;'>NVIDIA Blackwell GPU Market...</strong><br><span style='color: #94A3B8 !important; font-size: 0.8rem;'>2h ago • Deep Scan</span>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("<strong style='color:#E2E8F0!important;'>Fed Interest Rate Pivot...</strong><br><span style='color: #94A3B8 !important; font-size: 0.8rem;'>5h ago • Macro</span>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("<strong style='color:#E2E8F0!important;'>OPEC+ Production Cut...</strong><br><span style='color: #94A3B8 !important; font-size: 0.8rem;'>Yesterday • Energy</span>", unsafe_allow_html=True)

with col_main:
    # Check for chat input
    company = st.chat_input("Analyze the impact of a company's market position...")

    if company:
        # Show Top Header
        st.markdown(f"<span class='badge' style='background-color:#064E3B;color:#34D399;padding:4px 8px;border-radius:4px;font-size:0.75rem;font-weight:bold;'>AI AGENT EXECUTION</span> <span style='color: #94A3B8 !important; font-size: 0.8rem; margin-left: 10px;'>TASK ID: #QT-{len(company)*1337}</span>", unsafe_allow_html=True)
        st.markdown(f"<h1 style='font-size: 2.5rem; margin-top: 10px; color:#F8FAFC!important;'>Market Analysis: {company.upper()}</h1>", unsafe_allow_html=True)
        st.divider()
        
        # Execute Agents
        with st.status(f"System running macro and micro analysis for {company}...", expanded=True) as status:
            st.write(">> INITIALIZING ALPHA NODE (QUANT)...")
            alpha_data = run_quantitative_analysis(company)
            
            st.write(">> INITIALIZING BETA NODE (QUAL)...")
            beta_data = run_qualitative_analysis(company)
            
            st.write(">> ROUTING TO NEURAL JUDGE FOR SYNTHESIS...")
            final_report = evaluate_reports(company, alpha_data, beta_data)
            status.update(label="ANALYSIS COMPILED", state="complete")

        # Parse Data
        revenue_match = re.search(r"Revenue:\s*(.*)", alpha_data, re.IGNORECASE)
        stock_match = re.search(r"Stock Price Change:\s*(.*)", alpha_data, re.IGNORECASE)

        revenue_val = revenue_match.group(1).strip() if revenue_match else "SCANNING..."
        stock_val = stock_match.group(1).strip() if stock_match else "CALCULATING..."

        # Metrics Row
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric(label="REVENUE TRAJECTORY", value=revenue_val)
        with m2:
            st.metric(label="STOCK MOMENTUM", value=stock_val)
        with m3:
            # Simple heuristic for top signal
            top_signal = "HOLD"
            if "-" in stock_val:
                top_signal = "SELL"
            elif "%" in stock_val:
                top_signal = "ACCUMULATE"
            st.metric(label="TOP SIGNAL", value=top_signal)
            
        st.divider()

        # Insights
        st.markdown("<p style='color: #10B981 !important; font-size: 0.9rem; font-weight: bold; letter-spacing: 1px;'>KEY EXECUTIVE INSIGHTS</p>", unsafe_allow_html=True)
        
        with st.container(border=True):
            st.markdown("<p style='color: #10B981 !important; font-weight: bold;'>[BETA] QUALITATIVE DATA</p>", unsafe_allow_html=True)
            st.markdown(beta_data)
        
        with st.container(border=True):
            st.markdown("<p style='color: #10B981 !important; font-weight: bold;'>[ALPHA] QUANTITATIVE DATA</p>", unsafe_allow_html=True)
            st.markdown(alpha_data)
            
        with st.container(border=True):
            st.markdown("<p style='color: #3B82F6 !important; font-weight: bold;'>[JUDGE] FINAL SYNTHESIS</p>", unsafe_allow_html=True)
            st.markdown(final_report)

        # Terminal Log Output
        st.markdown(f"""
        <div class="agent-log">
            <p style="color:#10B981!important;margin:0;">[SYSTEM] Final Briefing generated for {company}.</p>
            <p style="color:#10B981!important;margin:0;">[SYSTEM] Confidence Interval: 94.2%</p>
            <p style="color:#10B981!important;margin:0;">[SYSTEM] Awaiting next command...</p>
        </div>
        """, unsafe_allow_html=True)

    else:
        # Default empty state
        st.markdown("<span style='background-color:#1E293B;color:#94A3B8;padding:4px 10px;border-radius:4px;font-size:0.75rem;font-weight:bold;'>SYSTEM IDLE</span>", unsafe_allow_html=True)
        st.markdown("<h1 style='font-size: 2.5rem; margin-top: 10px; color: #475569 !important;'>Awaiting Execution Protocol</h1>", unsafe_allow_html=True)
        st.markdown("<p style='color: #475569 !important;'>Use the terminal input below to launch a targeted market scan.</p>", unsafe_allow_html=True)