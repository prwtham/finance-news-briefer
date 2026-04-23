import streamlit as st
import re
from researcher_alpha import run_quantitative_analysis
from researcher_beta import run_qualitative_analysis
from judge import evaluate_reports

# --- UI Setup ---
st.set_page_config(page_title="Finance News Briefer", page_icon="📈", layout="wide")

# --- Custom CSS ---
custom_css = """
<style>
/* Background and Base Styling */
.stApp {
    background-color: #ffffff;
    background-image: radial-gradient(#e0e0e0 2px, transparent 2px);
    background-size: 30px 30px;
    font-family: 'Inter', sans-serif;
}

/* Animations */
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(-20px); }
    to { opacity: 1; transform: translateY(0); }
}

/* Hero Section */
.hero-container {
    text-align: center;
    padding: 6rem 2rem 2rem 2rem;
    animation: fadeIn 1s ease-out forwards;
}

.hero-title {
    font-size: 4.5rem;
    font-weight: 800;
    color: #1a1a1a;
    margin-bottom: 0.5rem;
    letter-spacing: -0.05em;
    font-family: sans-serif;
}

.hero-subtitle {
    font-size: 1.2rem;
    color: #888888;
    margin-bottom: 3rem;
    font-weight: 300;
}

/* Hide standard Streamlit header elements if necessary */
header {visibility: hidden;}

/* Style the Search Input */
.stTextInput > div > div > input {
    border-radius: 50px;
    padding: 15px 25px;
    border: 1px solid #d0d0d0;
    box-shadow: 0 4px 10px rgba(0,0,0,0.05);
    text-align: center;
    font-size: 1.1rem;
    background-color: #ffffff;
}

/* Style the Button */
.stButton > button {
    border-radius: 50px;
    border: 1px solid #dcdcdc;
    background-color: #ffffff;
    color: #333333;
    padding: 0.5rem 2.5rem;
    font-weight: 500;
    transition: all 0.3s ease;
    display: block;
    margin: 0 auto;
}

.stButton > button:hover {
    border-color: #999999;
    box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    color: #000000;
}

/* Elevated Container for Output */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background-color: rgba(255, 255, 255, 0.95);
    border-radius: 15px;
    padding: 2rem;
    box-shadow: 0 10px 40px rgba(0,0,0,0.08);
    border: 1px solid #f0f0f0;
    backdrop-filter: blur(10px);
}

</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

# --- Hero Content ---
st.markdown("""
<div class="hero-container">
    <h1 class="hero-title">Finance News Briefer</h1>
    <p class="hero-subtitle">AI-Powered Quantitative and Qualitative Market Intelligence</p>
</div>
""", unsafe_allow_html=True)

# --- Input Area (Centered) ---
# Create 3 columns to force the input to the center
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    company = st.text_input("Company", placeholder="Enter Company Name (e.g., Apple, NVIDIA)...", label_visibility="collapsed")
    
    # Nested columns for the button to center it perfectly
    btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 1])
    with btn_col2:
        generate_clicked = st.button("Generate Briefing")

# --- Functional Logic ---
if generate_clicked:
    if company:
        # Create an elevated container for the entire output
        with st.container(border=True):
            with st.status(f"Analyzing {company}...", expanded=True) as status:
                # 1. Run Researchers
                st.write("📊 Researching Market Sentiment (Beta Agent)...")
                beta_data = run_qualitative_analysis(company)

                st.write("🔍 Researching Quant data (Alpha Agent)...")
                alpha_data = run_quantitative_analysis(company)
                
                # 2. Run Judge
                st.write("⚖️ Finalizing report (LLM-as-Judge)...")
                final_report = evaluate_reports(company, alpha_data, beta_data)
                
                status.update(label="Analysis Complete!", state="complete")

            # --- Data Parsing ---
            revenue_match = re.search(r"Revenue:\s*(.*)", alpha_data, re.IGNORECASE)
            stock_match = re.search(r"Stock Price Change:\s*(.*)", alpha_data, re.IGNORECASE)

            revenue_val = revenue_match.group(1).strip() if revenue_match else "N/A"
            stock_val = stock_match.group(1).strip() if stock_match else "N/A"

            # --- Display Results ---
            st.divider()
            
            # Display Metrics at the top
            met_col1, met_col2 = st.columns(2)
            with met_col1:
                st.metric(label="Revenue", value=revenue_val)
            with met_col2:
                st.metric(label="Stock Price Change", value=stock_val)
                
            st.divider()

            # Display Sections in Order: Beta, Alpha, Judge
            st.subheader("Qualitative Insights")
            st.markdown(beta_data)
            
            st.divider()
            st.subheader("Quantitative Analysis")
            st.markdown(alpha_data)
            
            st.divider()
            st.subheader(f"Final Executive Briefing")
            st.markdown(final_report)
            
            st.divider()
            
            # --- Dedicated Visual Section ---
            vis_col1, vis_col2 = st.columns(2)
            
            with vis_col1:
                st.subheader("Company Logo")
                # Create a simple domain guess based on the first word of the company name
                domain_guess = company.split()[0].lower().replace(",", "") + ".com"
                try:
                    st.image(f"https://logo.clearbit.com/{domain_guess}", width=100)
                except Exception:
                    st.write("*(Logo unavailable)*")
                    
            with vis_col2:
                st.subheader("Leadership")
                formatted_name = company.replace(" ", "+")
                try:
                    st.image(f"https://ui-avatars.com/api/?name={formatted_name}&size=128&background=random", width=100)
                except Exception:
                    st.write("*(Leadership avatar unavailable)*")

    else:
        st.warning("Please enter a company name first.")