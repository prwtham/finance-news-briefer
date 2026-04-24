# QUANTUM AI Financial News Briefer 📟

An advanced, multi-agent financial intelligence terminal built with Streamlit. This dashboard provides real-time quantitative and qualitative analysis on a massive database of global equities, private companies, and market sectors.

## 🚀 Features

- **Multi-Agent Architecture**: 
  - **Alpha (Quantitative)**: Pulls hard data, financial metrics, and market caps using `yfinance`.
  - **Beta (Qualitative)**: Conducts deep-dive web research and sentiment analysis using `Tavily` and LLMs.
  - **Judge**: Synthesizes and evaluates the findings from both researchers to produce a cohesive, actionable executive briefing.
- **Massive Ticker Database**: Built-in mapping for thousands of global stocks across the US, Europe, Asia, and India, spanning sectors from aerospace to SaaS and luxury retail.
- **Typo-Tolerant Resolution**: Includes a smart, fuzzy-matching engine (powered by `difflib`) to gracefully handle user typos (e.g., automatically resolving "microsof" to `MSFT`).
- **Private Entity Handling**: Intelligently identifies private companies (SpaceX, Stripe, Klarna, etc.) and gracefully informs the user without breaking the data pipeline.
- **Robust Fallbacks**: Automatically falls back to Tavily web searches or fast `yfinance` endpoints if primary Yahoo Finance data APIs are rate-limited or unavailable.
- **Terminal Aesthetic**: Clean, responsive UI featuring dynamic color-coding for stock performance, interactive news panels, and a premium "hacker/terminal" vibe.

## 🛠️ Tech Stack

- **Frontend**: [Streamlit](https://streamlit.io/)
- **Financial Data**: [yfinance](https://pypi.org/project/yfinance/)
- **Web Search & Research**: [Tavily API](https://tavily.com/)
- **Language Models**: Groq / LangChain
- **Visualization**: Plotly

## ⚙️ Setup & Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/RonnieRobert/finance-news-briefer.git
   cd finance-news-briefer
   ```

2. **Install dependencies**
   Make sure you have Python 3.9+ installed, then run:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**
   Create a `.env` file in the root directory and add your API keys:
   ```env
   TAVILY_API_KEY=your_tavily_api_key
   GROQ_API_KEY=your_groq_api_key
   LOGODEV_API_KEY=your_logodev_api_key
   ```

4. **Run the Application**
   ```bash
   streamlit run app.py
   ```

## 🧠 How it Works

1. **User Query**: You enter a company name (e.g., "Apple", "OpenAI", or a typo like "Nvidida").
2. **Resolution Pipeline**: The system resolves the query to its exact ticker or identifies it as a `PRIVATE` entity using the fuzzy-matching engine.
3. **Agent Dispatch**:
   - The *Quantitative Agent* fetches charts, moving averages, and pricing.
   - The *Qualitative Agent* scrapes recent news and institutional sentiment.
4. **Synthesis**: The *Judge Agent* merges the data, strips out hallucinations, and renders a clean Markdown report directly into the dashboard.

## 📄 License

MIT License - feel free to modify and use for your own research!
