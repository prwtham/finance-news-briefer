import os
from dotenv import load_dotenv
from tavily import TavilyClient
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

# Load environment variables from .env
load_dotenv()

def run_qualitative_analysis(company_name: str) -> str:
    """
    Runs a qualitative analysis for a given company.
    Focuses on market sentiment, CEO quotes, and competitive landscape.
    Returns a structured summary with citations.
    """
    print(f"[*] Starting qualitative research for {company_name}...")
    
    # 1. Initialize Tavily Client for searching
    tavily_api_key = os.getenv("TAVILY_API_KEY")
    tavily = TavilyClient(api_key=tavily_api_key)
    
    # 2. Perform the search
    query = f"{company_name} latest news market sentiment, CEO quotes, competitive landscape"
    print(f"[*] Searching Tavily for query: '{query}'")
    try:
        search_result = tavily.search(query=query, search_depth="advanced", max_results=5)
    except Exception as e:
        print(f"[!] Error during Tavily search: {e}")
        return f"Error: Failed to retrieve qualitative data for {company_name} due to Tavily search error: {e}"
    
    # Extract context and URLs for citations
    context = ""
    for idx, result in enumerate(search_result.get("results", [])):
        context += f"Source [{idx+1}]: {result['url']}\n"
        context += f"Content: {result['content']}\n\n"

    # 3. Initialize Groq model for reasoning
    llm = ChatGroq(
        model="llama-3.1-8b-instant",
        temperature=0.5
    )
    
    # 4. Construct Prompt
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert Qualitative Analyst. Your job is to analyze the market sentiment and qualitative data provided and extract key insights."),
        ("user", """
Please analyze the following information for {company_name}. 
Focus specifically on finding and reporting:
1. Market sentiment
2. CEO quotes
3. Competitive landscape news

Provide a highly structured summary of your findings. 
You MUST include inline citations using the Source numbers (e.g., [1], [2]) provided in the context to back up your claims.

Context Information:
{context}

Structured Summary:
""")
    ])
    
    # 5. Generate reasoning/summary
    print(f"[*] Generating reasoning via Groq...")
    chain = prompt | llm
    try:
        response = chain.invoke({
            "company_name": company_name,
            "context": context
        })
        return response.content
    except Exception as e:
        print(f"[!] Error during Groq reasoning: {e}")
        return f"Error: Failed to generate qualitative summary for {company_name} due to Groq reasoning error: {e}"

if __name__ == "__main__":
    # Example usage
    company = "NVIDIA"
    print(f"=== Qualitative Analyst Agent ===")
    summary = run_qualitative_analysis(company)
    print("\n=== Final Report ===")
    print(summary)
