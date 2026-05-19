import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import requests
import requests_cache

# --- Session & Cache Configuration ---
# Use a session with a custom user agent to avoid being blocked
@st.cache_resource
def get_session():
    session = requests_cache.CachedSession('yfinance.cache')
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })
    return session

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
        
        # Try fast_info first for price (more reliable)
        current_price = None
        try:
            current_price = ticker.fast_info.last_price
        except: pass
        
        info = {}
        try:
            info = ticker.info
        except: pass
        
        if not current_price:
            current_price = info.get('regularMarketPrice') or info.get('currentPrice')
            
        if not current_price:
            hist = ticker.history(period="5d")
            if not hist.empty: current_price = hist['Close'].iloc[-1]
        
        # Get Earnings Date
        earnings_date = "N/A"
        try:
            cal = ticker.calendar
            if isinstance(cal, dict) and 'Earnings Date' in cal:
                ed = cal['Earnings Date']
                if isinstance(ed, list) and len(ed) > 0:
                    earnings_date = ed[0].strftime('%Y-%m-%d')
                else:
                    earnings_date = str(ed)
            elif isinstance(cal, pd.DataFrame) and not cal.empty:
                # Some versions return a DataFrame
                if 'Earnings Date' in cal.index:
                    earnings_date = str(cal.loc['Earnings Date'].iloc[0])
                elif 'Earnings Date' in cal.columns:
                    earnings_date = str(cal['Earnings Date'].iloc[0])
        except: pass
        
        # Company Info
        company_info = {
            "name": info.get("longName") or info.get("shortName") or ticker_symbol,
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A"),
            "trailing_pe": info.get("trailingPE", "N/A"),
            "forward_pe": info.get("forwardPE", "N/A"),
            "peg_ratio": info.get("pegRatio", "N/A"),
            "p_b": info.get("priceToBook", "N/A"),
            "ev_ebitda": info.get("enterpriseToEbitda", "N/A")
        }
            
        return current_price, ticker.options, earnings_date, company_info
    except Exception as e:
        st.error(f"Error fetching data for {ticker_symbol}: {e}")
        return None, None, "N/A", {}

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

@st.cache_data(ttl=3600)
def get_analyst_data(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        recs = ticker.recommendations
        ud = ticker.upgrades_downgrades
        news = ticker.news
        return recs, ud, news
    except: return None, None, None

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
    current_price, expirations, earnings_date, company_info = get_ticker_data(ticker_input)
    
    if current_price and expirations:
        selected_exp = st.sidebar.selectbox("Expiration Date", expirations)
        
        # Company Profile Sidebar Section
        if company_info:
            st.sidebar.write("---")
            st.sidebar.subheader("🏢 Company Profile")
            st.sidebar.markdown(f"**Name:** {company_info['name']}")
            st.sidebar.markdown(f"**Sector:** {company_info['sector']}")
            st.sidebar.markdown(f"**Industry:** {company_info['industry']}")
            st.sidebar.write("---")
            st.sidebar.subheader("📊 Financial Multipliers")
            st.sidebar.markdown(f"**Trailing P/E:** {company_info['trailing_pe']}")
            st.sidebar.markdown(f"**Forward P/E:** {company_info['forward_pe']}")
            st.sidebar.markdown(f"**PEG Ratio:** {company_info['peg_ratio']}")
            st.sidebar.markdown(f"**Price/Book:** {company_info['p_b']}")
            st.sidebar.markdown(f"**EV/EBITDA:** {company_info['ev_ebitda']}")

        iv_rank, iv_pct = calculate_iv_rank(ticker_input)
        
        st.title(f"{ticker_input} | Market Dashboard")
        
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
                df.dropna(subset=['strike'], inplace=True)

            # --- Calculate Metrics ---
            max_pain = calculate_max_pain(calls, puts)
            
            # Expected Move Calculation
            days_to_expiry = (datetime.strptime(selected_exp, '%Y-%m-%d') - datetime.now()).days
            atm_call = calls.iloc[(calls['strike'] - current_price).abs().argsort()[:1]]
            atm_iv = atm_call['impliedVolatility'].iloc[0] if not atm_call.empty else 0
            expected_move = current_price * atm_iv * np.sqrt(max(days_to_expiry, 1) / 365)
            
            # Put/Call Ratios
            total_call_vol = calls['volume'].sum()
            total_put_vol = puts['volume'].sum()
            total_call_oi = calls['openInterest'].sum()
            total_put_oi = puts['openInterest'].sum()
            pc_vol_ratio = total_put_vol / total_call_vol if total_call_vol > 0 else 0
            pc_oi_ratio = total_put_oi / total_call_oi if total_call_oi > 0 else 0

            # --- Metrics Display ---
            row1_col1, row1_col2, row1_col3, row1_col4 = st.columns(4)
            row1_col1.metric("Stock Price", f"${current_price:.2f}")
            row1_col2.metric("Expected Move", f"±${expected_move:.2f}")
            row1_col3.metric("Max Pain Strike", f"${max_pain:.1f}")
            row1_col4.metric("Next Earnings", earnings_date)

            st.write("---")
            
            row2_col1, row2_col2, row2_col3, row2_col4 = st.columns(4)
            row2_col1.metric("Volatility Rank", f"{iv_rank:.1f}%")
            row2_col2.metric("Vol Percentile", f"{iv_pct:.1f}%")
            row2_col3.metric("P/C Vol Ratio", f"{pc_vol_ratio:.2f}")
            row2_col4.metric("P/C OI Ratio", f"{pc_oi_ratio:.2f}")

            # Visual Bars
            def create_ratio_bar(put_val, call_val):
                total = put_val + call_val
                if total == 0: return ""
                put_pct = (put_val / total) * 100
                call_pct = (call_val / total) * 100
                return f"""
                    <div style="width: 100%; background-color: #22262B; border-radius: 4px; height: 8px; display: flex; overflow: hidden; margin-top: 10px;">
                        <div style="width: {put_pct}%; background-color: #E53935; height: 100%;"></div>
                        <div style="width: {call_pct}%; background-color: #43A047; height: 100%;"></div>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 10px; margin-top: 4px; color: #8b949e;">
                        <span>P: {put_pct:.0f}%</span>
                        <span>C: {call_pct:.0f}%</span>
                    </div>
                """

            with row2_col3:
                st.markdown(create_ratio_bar(total_put_vol, total_call_vol), unsafe_allow_html=True)
            with row2_col4:
                st.markdown(create_ratio_bar(total_put_oi, total_call_oi), unsafe_allow_html=True)

            # Tabs
            tab_chain, tab_structure, tab_uoa, tab_surface, tab_analyst, tab_builder = st.tabs([
                "📋 Option Chain", "🧠 Market Structure", "🚨 Unusual Activity", "🌊 Vol Surface", "🔭 Analyst Insights", "🛠️ Strategy Builder"
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
                    
                    # Expected Move Bounds
                    fig_oi.add_vline(x=current_price + expected_move, line_dash="dot", line_color="#ff4b4b", annotation_text="+EM")
                    fig_oi.add_vline(x=current_price - expected_move, line_dash="dot", line_color="#00ffcc", annotation_text="-EM")

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

            with tab_analyst:
                recs, ud, news = get_analyst_data(ticker_input)
                
                col_a1, col_a2 = st.columns([1, 2])
                
                with col_a1:
                    st.subheader("Consensus Ratings")
                    if recs is not None and not recs.empty:
                        # Display latest recommendation (period '0m')
                        latest_rec = recs.iloc[0]
                        fig_rec = go.Figure(data=[go.Pie(
                            labels=['Strong Buy', 'Buy', 'Hold', 'Sell', 'Strong Sell'],
                            values=[latest_rec['strongBuy'], latest_rec['buy'], latest_rec['hold'], latest_rec['sell'], latest_rec['strongSell']],
                            hole=.3,
                            marker_colors=['#00c853', '#64dd17', '#ffeb3b', '#ff9800', '#f44336']
                        )])
                        fig_rec.update_layout(showlegend=True, height=350, margin=dict(l=0, r=0, b=0, t=0))
                        st.plotly_chart(fig_rec, use_container_width=True)
                    else:
                        st.info("No recommendation data available.")

                with col_a2:
                    st.subheader("Recent Upgrades/Downgrades")
                    if ud is not None and not ud.empty:
                        # Sort by date (index) and show top 10
                        st.dataframe(ud.sort_index(ascending=False).head(10), use_container_width=True)
                    else:
                        st.info("No upgrades/downgrades data available.")

                st.write("---")
                st.subheader("Latest Market News")
                if news:
                    for item in news[:5]:
                        content = item.get('content', {})
                        title = content.get('title', 'No Title')
                        summary = content.get('summary', '')
                        # URL is often at the top level of the item or within canonicalUrl sibling
                        url = item.get('canonicalUrl', {}).get('url') or item.get('clickThroughUrl', {}).get('url') or "#"
                        pub_date = content.get('pubDate', '')
                        
                        st.markdown(f"### [{title}]({url})")
                        st.caption(f"Published: {pub_date}")
                        st.write(summary)
                        st.write("---")
                else:
                    st.info("No news available for this ticker.")

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
