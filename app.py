import streamlit as st
import re
from researcher_alpha import run_quantitative_analysis
from researcher_beta import run_qualitative_analysis
from judge import evaluate_reports

# --- UI Setup ---
st.set_page_config(page_title="Finance News Briefer", page_icon="📈", layout="wide")
st.title("🚀 Finance News Briefer")
st.markdown("Enter a company name to get a multi-agent verified report.")

# --- Input ---
company = st.text_input("Enter Company Name (e.g., Reliance Industries):")

if st.button("Generate Briefing"):
    if company:
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
        col1, col2 = st.columns(2)
        with col1:
            st.metric(label="Revenue", value=revenue_val)
        with col2:
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