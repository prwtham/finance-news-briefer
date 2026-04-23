import sys
import time
import concurrent.futures
from dotenv import load_dotenv

from researcher_alpha import run_quantitative_analysis
from researcher_beta import run_qualitative_analysis
from judge import evaluate_reports

# Load environment variables
load_dotenv()

def main():
    if len(sys.argv) > 1:
        company_name = sys.argv[1]
    else:
        company_name = input("Enter the Company Name for the Finance News Briefer: ").strip()

    if not company_name:
        print("Company name cannot be empty. Exiting.")
        return

    print(f"==================================================")
    print(f"  Finance News Briefer initialized for: {company_name}")
    print(f"==================================================")

    # Run researchers in parallel with a slight stagger to avoid Rate Limits (429)
    print("\n[*] Dispatching Alpha (Quantitative) and Beta (Qualitative) agents...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        # Submit the first agent
        future_alpha = executor.submit(run_quantitative_analysis, company_name)
        
        # Wait 2 seconds before submitting the second agent to the API
        time.sleep(2) 
    
        # Submit the second agent
        future_beta = executor.submit(run_qualitative_analysis, company_name)

        # Wait for both to complete
        report_alpha = future_alpha.result()
        report_beta = future_beta.result()

    print("\n--- Alpha Report ---")
    print(report_alpha)
    print("\n--- Beta Report ---")
    print(report_beta)

    # Pass outputs to the Judge
    print("\n==================================================")
    print(f"[*] Passing reports to the Judge agent...")
    final_briefing = evaluate_reports(company_name, report_alpha, report_beta)

    print("\n================ FINAL BRIEFING ================")
    print(final_briefing)
    print("==================================================")

if __name__ == "__main__":
    main()
