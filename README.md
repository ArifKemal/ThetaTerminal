# ThetaTerminal | Advanced Quant Suite

ThetaTerminal is a professional-grade interactive terminal for stock options research, volatility analysis, and market structure visualization. It focuses on detecting options pricing anomalies and institutional positioning.

## Project Overview

*   **Purpose:** Provide deep-dive options analytics beyond standard data viewers.
*   **Main Technologies:** 
    *   **Framework:** [Streamlit](https://streamlit.io/) (Data Apps)
    *   **Data Source:** `yfinance` (US Equity Options Chains)
    *   **Quant Math:** `py_vollib_vectorized` (Black-Scholes Greeks), `numpy`, `pandas`
    *   **Visualization:** `plotly` (3D Volatility Surfaces, GEX Bar Charts, Payoff Diagrams)

## Key Features

*   **Option Chain Analysis:** Real-time fetching and heat-mapped display of Call/Put chains with Delta, Gamma, Theta, and Vega.
*   **Quant Insights:**
    *   **Gamma Exposure (GEX):** Visualizes market maker hedging requirements to identify volatility buffers or acceleration zones.
    *   **Max Pain:** Calculates the strike price where the most options value expires worthless.
    *   **IV Rank & Percentile:** Contextualizes current Implied Volatility against 1-year historical data.
*   **Strategy Builder:** Interactive modeling of multi-leg strategies with real-time P&L payoff diagrams.
*   **Unusual Options Activity (UOA):** Detects contracts where daily volume exceeds open interest.
*   **Volatility Surface:** 3D visualization of IV across various strikes and expiration dates.

## Building and Running

### Prerequisites
Ensure you have Python installed. It is recommended to use a virtual environment.

### Installation
```bash
pip install -r requirements.txt
```

### Running the Application
```bash
streamlit run app.py
```

## Technical Architecture

*   **Data Flow:** `yfinance` fetches raw data -> `Pandas` for transformation -> `Quant Layer` for analytics (IV Rank, Max Pain) -> `Plotly` for visualization.
*   **Performance:** Extensive use of `@st.cache_data` with tiered TTLs:
    *   `900s` (15m) for price and option chain data.
    *   `3600s` (1h) for historical volatility and IV Rank.
*   **State Management:** `st.session_state` is used to persist complex user inputs, such as the multi-leg strategy builder.
*   **Calculation Logic:** Max Pain is determined by iterating through all strikes to find the point of minimum dollar-value expiration for contract holders.
