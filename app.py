import streamlit as st
from researcher_alpha import run_quantitative_analysis
from researcher_beta import run_qualitative_analysis
from judge import evaluate_reports

# --- UI Setup ---
st.set_page_config(page_title="Finance News Briefer", page_icon="📈")
st.title("🚀 Finance News Briefer")
st.markdown("Enter a company name to get a multi-agent verified report.")

# --- Input ---
company = st.text_input("Enter Company Name (e.g., Reliance Industries):")

if st.button("Generate Briefing"):
    if company:
        with st.status(f"Analyzing {company}...", expanded=True) as status:
            # 1. Run Researchers
            st.write("🔍 Researching Quant data (Alpha Agent)...")
            alpha_data = run_quantitative_analysis(company)
            
            st.write("📊 Researching Market Sentiment (Beta Agent)...")
            beta_data = run_qualitative_analysis(company)
            
            # 2. Run Judge
            st.write("⚖️ Finalizing report (LLM-as-Judge)...")
            final_report = evaluate_reports(company, alpha_data, beta_data)
            
            status.update(label="Analysis Complete!", state="complete")

        # --- Display Results ---
        st.divider()
        st.subheader(f"Final Briefing for {company}")
        st.markdown(final_report)
    else:
        st.warning("Please enter a company name first.")