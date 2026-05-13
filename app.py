import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

# --- Page Configuration ---
st.set_page_config(
    page_title="ThetaTerminal | Market Structure",
    page_icon="📊",
    layout="wide"
)

# --- Custom CSS ---
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 15px; }
    </style>
""", unsafe_allow_html=True)

# --- Data Layer ---
@st.cache_data(ttl=900)
def get_ticker_data(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        current_price = info.get('regularMarketPrice') or info.get('currentPrice')
        if not current_price:
            hist = ticker.history(period="5d")
            if not hist.empty: current_price = hist['Close'].iloc[-1]
        return current_price, ticker.options
    except: return None, None

@st.cache_data(ttl=900)
def get_option_chain(ticker_symbol, expiration):
    try:
        ticker = yf.Ticker(ticker_symbol)
        opts = ticker.option_chain(expiration)
        return opts.calls, opts.puts
    except: return None, None

@st.cache_data(ttl=3600)
def calculate_iv_rank(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        hist = ticker.history(period="1y")
        if hist.empty: return 0, 0
        hist['returns'] = hist['Close'].pct_change()
        hist['vol'] = hist['returns'].rolling(window=20).std() * np.sqrt(252)
        curr = hist['vol'].iloc[-1]
        rank = (curr - hist['vol'].min()) / (hist['vol'].max() - hist['vol'].min()) * 100
        pct = (hist['vol'] < curr).mean() * 100
        return rank, pct
    except: return 0, 0

@st.cache_data(ttl=900)
def get_full_chain_for_surface(ticker_symbol, expirations):
    ticker = yf.Ticker(ticker_symbol)
    all_data = []
    for exp in expirations[:8]:
        try:
            opts = ticker.option_chain(exp)
            c, p = opts.calls, opts.puts
            c['expiration'], c['type'] = exp, 'call'
            p['expiration'], p['type'] = exp, 'put'
            all_data.extend([c, p])
        except: continue
    return pd.concat(all_data) if all_data else pd.DataFrame()

# --- Quant Layer (Market Structure) ---
def calculate_max_pain(calls, puts):
    if calls.empty or puts.empty: return 0
    strikes = sorted(list(set(calls['strike'].unique()) | set(puts['strike'].unique())))
    pains = []
    for s in strikes:
        c_p = calls[calls['strike'] < s].apply(lambda x: (s - x['strike']) * x['openInterest'], axis=1).sum()
        p_p = puts[puts['strike'] > s].apply(lambda x: (x['strike'] - s) * x['openInterest'], axis=1).sum()
        pains.append(c_p + p_p)
    return strikes[np.argmin(pains)]

# --- UI Layout ---
st.sidebar.title("📊 ThetaTerminal")
ticker_input = st.sidebar.text_input("Ticker Symbol", value="TSLA").upper()

if ticker_input:
    current_price, expirations = get_ticker_data(ticker_input)
    
    if current_price and expirations:
        selected_exp = st.sidebar.selectbox("Expiration Date", expirations)
        iv_rank, iv_pct = calculate_iv_rank(ticker_input)
        
        st.title(f"{ticker_input} | Market Dashboard")
        
        # Metrics Row
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Stock Price", f"${current_price:.2f}")
        m2.metric("Volatility Rank", f"{iv_rank:.1f}%")
        m3.metric("Vol Percentile", f"{iv_pct:.1f}%")
        
        # Load and Clean Chains
        calls, puts = get_option_chain(ticker_input, selected_exp)
        if calls is not None and puts is not None:
            # Data Cleaning: Fix None values and ensure numeric types
            for df in [calls, puts]:
                df['strike'] = pd.to_numeric(df['strike'], errors='coerce')
                df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0)
                df['openInterest'] = pd.to_numeric(df['openInterest'], errors='coerce').fillna(0)
                df['impliedVolatility'] = pd.to_numeric(df['impliedVolatility'], errors='coerce').fillna(0)
                df['lastPrice'] = pd.to_numeric(df['lastPrice'], errors='coerce').fillna(0)
                # Remove rows with invalid strike prices
                df.dropna(subset=['strike'], inplace=True)

            max_pain = calculate_max_pain(calls, puts)
            m4.metric("Max Pain Strike", f"${max_pain:.1f}")

            # Tabs
            tab_chain, tab_structure, tab_uoa, tab_surface, tab_builder = st.tabs([
                "📋 Option Chain", "🧠 Market Structure", "🚨 Unusual Activity", "🌊 Vol Surface", "🛠️ Strategy Builder"
            ])

            with tab_chain:
                col_c1, col_c2 = st.columns(2)
                d_cols = ['strike', 'lastPrice', 'volume', 'openInterest', 'impliedVolatility']
                
                with col_c1:
                    st.subheader("Call Options")
                    # Full-table gradient for the deep color effect
                    st.dataframe(
                        calls[d_cols].style.background_gradient(cmap='Greens')
                        .format({'impliedVolatility': '{:.2%}', 'lastPrice': '${:.2f}'}),
                        use_container_width=True
                    )
                with col_c2:
                    st.subheader("Put Options")
                    # Full-table gradient for the deep color effect
                    st.dataframe(
                        puts[d_cols].style.background_gradient(cmap='Reds')
                        .format({'impliedVolatility': '{:.2%}', 'lastPrice': '${:.2f}'}),
                        use_container_width=True
                    )

            with tab_structure:
                st.subheader("Open Interest (OI) Distribution")
                st.info("Institutional 'walls' are often formed at strikes with high Open Interest. Puts are shown as negative values for clarity.")

                # Check if we have valid data to plot
                if not calls.empty and not puts.empty:
                    fig_oi = go.Figure()
                    fig_oi.add_trace(go.Bar(x=calls['strike'], y=calls['openInterest'], name='Calls OI', marker_color='#00ffcc'))
                    fig_oi.add_trace(go.Bar(x=puts['strike'], y=-puts['openInterest'], name='Puts OI', marker_color='#ff4b4b'))

                    fig_oi.add_vline(x=current_price, line_dash="dash", line_color="orange", annotation_text="Spot")
                    fig_oi.add_vline(x=max_pain, line_dash="dot", line_color="white", annotation_text="Max Pain")

                    fig_oi.update_layout(
                        barmode='relative',
                        xaxis_title="Strike",
                        yaxis_title="Contracts",
                        height=500,
                        hovermode='x unified'
                    )
                    fig_oi.update_xaxes(type='linear', range=[current_price * 0.8, current_price * 1.2])
                    st.plotly_chart(fig_oi, use_container_width=True)
                else:
                    st.warning("Insufficient data to display Open Interest distribution.")

            with tab_uoa:
                st.subheader("Unusual Options Activity (Volume > Open Interest)")
                combined = pd.concat([calls.assign(type='Call'), puts.assign(type='Put')])
                uoa = combined[combined['volume'] > combined['openInterest']].sort_values('volume', ascending=False)
                if not uoa.empty:
                    st.dataframe(uoa[['contractSymbol', 'type', 'strike', 'volume', 'openInterest', 'impliedVolatility']], use_container_width=True)
                else:
                    st.info("No unusual activity found for this expiration.")

            with tab_surface:
                with st.spinner("Generating 3D Surface..."):
                    full_chain = get_full_chain_for_surface(ticker_input, expirations)
                    if not full_chain.empty:
                        opt_type_surf = st.selectbox("Surface Type", ["Call", "Put"])
                        surf_df = full_chain[full_chain['type'] == opt_type_surf.lower()].copy()
                        surf_df['days'] = (pd.to_datetime(surf_df['expiration']) - datetime.now()).dt.days
                        surf_df = surf_df[(surf_df['days'] > 0) & (surf_df['impliedVolatility'] > 0.05)]
                        
                        fig_surf = go.Figure(data=[go.Mesh3d(
                            x=surf_df['strike'], y=surf_df['days'], z=surf_df['impliedVolatility'],
                            intensity=surf_df['impliedVolatility'], colorscale='Viridis', opacity=0.8
                        )])
                        fig_surf.update_layout(
                            scene=dict(xaxis_title='Strike', yaxis_title='Days to Expiry', zaxis_title='IV'),
                            height=700, margin=dict(l=0, r=0, b=0, t=40)
                        )
                        st.plotly_chart(fig_surf, use_container_width=True)
                    else:
                        st.warning("Insufficient data for 3D Surface.")

            with tab_builder:
                if 'legs' not in st.session_state: st.session_state.legs = []
                col_b1, col_b2 = st.columns([1, 2])
                with col_b1:
                    with st.form("builder_form"):
                        bt = st.selectbox("Type", ["Call", "Put"])
                        ba = st.selectbox("Action", ["Buy", "Sell"])
                        bs = st.number_input("Strike", value=float(current_price))
                        bp = st.number_input("Premium", value=1.0)
                        if st.form_submit_button("Add Leg"):
                            st.session_state.legs.append({'type': bt, 'action': ba, 'strike': bs, 'premium': bp})
                    if st.button("Clear All"): st.session_state.legs = []
                    st.dataframe(pd.DataFrame(st.session_state.legs))
                
                with col_b2:
                    if st.session_state.legs:
                        spots = np.linspace(current_price*0.8, current_price*1.2, 100)
                        payoff = np.zeros_like(spots)
                        for leg in st.session_state.legs:
                            m = 1 if leg['action'] == 'Buy' else -1
                            p = (np.maximum(spots - leg['strike'], 0) - leg['premium']) if leg['type'] == 'Call' else (np.maximum(leg['strike'] - spots, 0) - leg['premium'])
                            payoff += (p * m * 100)
                        fig_pnl = go.Figure()
                        fig_pnl.add_trace(go.Scatter(x=spots, y=payoff, fill='tozeroy', line=dict(color='#00ffcc')))
                        fig_pnl.add_hline(y=0, line_color="white")
                        fig_pnl.update_layout(title="Payoff at Expiration", xaxis_title="Stock Price", yaxis_title="P&L ($)")
                        st.plotly_chart(fig_pnl, use_container_width=True)
        else:
            st.error("Options chain could not be loaded.")
    else: st.error("No data found for this ticker.")
else: st.info("Enter a ticker symbol to begin.")
