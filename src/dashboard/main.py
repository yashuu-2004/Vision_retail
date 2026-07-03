"""
VisionRetail AI - Streamlit Dashboard
Real-time store intelligence visualization
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
import os

# Configure Streamlit
st.set_page_config(
    page_title="VisionRetail AI",
    page_icon="VR",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Styling
st.markdown("""
    <style>
    .main {
        padding-top: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1.5rem;
        border-radius: 0.5rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    </style>
""", unsafe_allow_html=True)

# API Configuration
API_URL = os.getenv("API_URL", "http://localhost:8000")
STORE_ID = os.getenv("STORE_ID", "ST1008")


@st.cache_data(ttl=30)
def fetch_api(path, params=None):
    """Fetch a JSON API payload for the selected store."""
    try:
        response = requests.get(f"{API_URL}{path}", params=params or {}, timeout=10)
        if response.status_code == 200:
            return response.json()
        st.warning(f"API returned {response.status_code} for {path}")
    except Exception as e:
        st.error(f"Error fetching {path}: {e}")
    return None


def fetch_metrics(lookback_minutes):
    return fetch_api(f"/stores/{STORE_ID}/metrics", {"lookback_minutes": lookback_minutes})


def fetch_funnel(lookback_minutes):
    return fetch_api(f"/stores/{STORE_ID}/funnel", {"lookback_minutes": lookback_minutes})


def fetch_heatmap(metric, lookback_minutes):
    return fetch_api(f"/stores/{STORE_ID}/heatmap", {"metric": metric, "lookback_minutes": lookback_minutes})


def main():
    """Main dashboard"""
    
    # Header
    st.title("VisionRetail AI - Store Intelligence")
    st.subheader("Brigade Road conversion, journey, queue, and POS attribution")
    
    # Sidebar
    with st.sidebar:
        st.markdown("### Dashboard Controls")
        lookback_minutes = st.slider("Lookback Period", 15, 1440, 60, step=15)
        refresh_rate = st.selectbox("Refresh Rate", ["5s", "10s", "30s", "1m"])
        
        st.markdown("---")
        st.markdown("### Store Info")
        st.markdown(f"**Store**: Brigade Road - Bangalore  \n**Region**: Karnataka, India")
    
    # Main tabs
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "Overview",
        "Conversion",
        "Heatmap",
        "Queue",
        "Journeys",
        "Predictions",
        "Anomalies"
    ])
    
    # TAB 1: Overview
    with tab1:
        metrics = fetch_metrics(lookback_minutes)
        
        if metrics:
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    "Total Visitors",
                    f"{metrics['total_visitors']:,}",
                    delta=f"{metrics['total_visitors'] - 50}" if metrics['total_visitors'] > 50 else None
                )
            
            with col2:
                st.metric(
                    "Unique Visitors",
                    f"{metrics['unique_visitors']:,}",
                    delta=f"{((metrics['unique_visitors'] / metrics['total_visitors'] * 100) if metrics['total_visitors'] > 0 else 0):.1f}%"
                )
            
            with col3:
                st.metric(
                    "Conversion Rate",
                    f"{metrics['conversion_rate']:.1f}%",
                    delta="+2.3%" if metrics['conversion_rate'] > 20 else None
                )
            
            with col4:
                st.metric(
                    "Revenue",
                    f"INR {float(metrics['total_revenue']):,.0f}",
                    delta=f"INR {int(float(metrics['total_revenue']) * 0.1):,.0f}"
                )

            with st.expander("Metric Traceability"):
                st.json(metrics.get("evidence", {}))
            
            st.markdown("---")
            
            # Charts
            col_chart1, col_chart2 = st.columns(2)
            
            with col_chart1:
                # Zone performance
                zone_data = pd.DataFrame(metrics.get('zones', []))
                if not zone_data.empty:
                    fig_zones = px.bar(
                        zone_data,
                        x='zone_name',
                        y='visitor_count',
                        title='Visitors by Zone',
                        color='conversion_rate',
                        color_continuous_scale='RdYlGn'
                    )
                    st.plotly_chart(fig_zones, use_container_width=True)
            
            with col_chart2:
                queue = fetch_api(f"/stores/{STORE_ID}/queue-analytics", {"lookback_minutes": lookback_minutes}) or {}
                queue_data = pd.DataFrame([
                    {"metric": "Current Depth", "value": queue.get("current_depth", 0)},
                    {"metric": "Max Depth", "value": queue.get("max_depth", 0)},
                    {"metric": "Avg Depth", "value": queue.get("avg_depth", 0)},
                    {"metric": "Abandoned", "value": queue.get("abandonment_count", 0)},
                ])
                fig_queue = px.bar(queue_data, x="metric", y="value", title="Billing Queue From Camera Events")
                st.plotly_chart(fig_queue, use_container_width=True)
    
    # TAB 2: Funnel
    with tab2:
        funnel = fetch_funnel(lookback_minutes)
        
        if funnel:
            st.markdown("### Conversion Funnel")
            st.markdown(f"**Overall Conversion Rate**: {funnel.get('overall_conversion_rate', 0):.1f}%")
            
            stages = funnel.get('stages', [])
            funnel_data = pd.DataFrame(stages)
            
            fig_funnel = go.Figure(data=[go.Funnel(
                y=[s['stage'].title() for s in stages],
                x=[s['count'] for s in stages],
                textposition="inside",
                textinfo="value+percent previous"
            )])
            fig_funnel.update_layout(title="Customer Journey Funnel")
            st.plotly_chart(fig_funnel, use_container_width=True)

            with st.expander("Funnel Traceability"):
                st.json(funnel.get("evidence", {}))
            
            # Details
            if len(stages) >= 4:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Entry to Zone", f"{stages[1]['drop_off_percent']:.1f}% drop")
                with col2:
                    st.metric("Zone to Queue", f"{stages[2]['drop_off_percent']:.1f}% drop")
                with col3:
                    st.metric("Queue to Purchase", f"{stages[3]['drop_off_percent']:.1f}% drop")
    
    # TAB 3: Heatmap
    with tab3:
        heat_metric = st.radio("Metric", ["visitor_count", "dwell_time", "conversion_rate"], horizontal=True)
        heatmap = fetch_heatmap(heat_metric, lookback_minutes)
        
        if heatmap:
            zones = heatmap.get('zones', [])
            heatmap_data = pd.DataFrame(zones)
            
            fig_heatmap = px.bar(
                heatmap_data,
                x='zone_name',
                y='value',
                color='value',
                color_continuous_scale='YlOrRd',
                title='Zone Intensity Heatmap'
            )
            st.plotly_chart(fig_heatmap, use_container_width=True)
            with st.expander("Heatmap Traceability"):
                st.json(heatmap.get("evidence", {}))
    
    # TAB 4: Queue
    with tab4:
        queue = fetch_api(f"/stores/{STORE_ID}/queue-analytics", {"lookback_minutes": lookback_minutes}) or {}
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Current Depth", queue.get("current_depth", 0))
        col2.metric("Max Depth", queue.get("max_depth", 0))
        col3.metric("Avg Wait", f"{int(queue.get('avg_wait_time_ms', 0) / 1000)}s")
        col4.metric("Abandonment", f"{queue.get('abandonment_rate', 0):.1f}%")
        st.dataframe(pd.DataFrame([queue]), use_container_width=True)
        with st.expander("Queue Traceability"):
            st.json(queue.get("evidence", {}))
    
    # TAB 5: Journeys
    with tab5:
        st.markdown("### Top Customer Journeys")
        journeys = fetch_api(f"/stores/{STORE_ID}/journeys", {"limit": 10, "min_visitors": 1}) or []
        journey_rows = [
            {
                "Path": " -> ".join(row.get("journey_path", [])),
                "Frequency": row.get("occurrence_count", 0),
                "Purchases": row.get("purchase_count", 0),
                "Conversion": f"{row.get('conversion_rate', 0):.1f}%",
                "Avg Time": f"{int(row.get('avg_duration_ms', 0) / 1000)}s",
            }
            for row in journeys
        ]
        st.dataframe(pd.DataFrame(journey_rows), use_container_width=True)
    
    # TAB 6: Predictions
    with tab6:
        st.markdown("### Purchase Probability Predictions")
        predictions = fetch_api(f"/stores/{STORE_ID}/predictions", {"lookback_minutes": lookback_minutes}) or []
        prediction_rows = [
            {
                "Visitor": row.get("visitor_id"),
                "Purchase Prob": f"{row.get('prediction_score', 0) * 100:.0f}%",
                "Abandon Prob": f"{row.get('abandonment_probability', 0) * 100:.0f}%",
                "Basket Prob": f"{row.get('basket_size_probability', 0) * 100:.0f}%",
                "Confidence": f"{row.get('confidence', 0) * 100:.0f}%",
                "Features": ", ".join(row.get("features_used", [])),
                "Reasoning": row.get("reasoning"),
            }
            for row in predictions
        ]
        st.dataframe(pd.DataFrame(prediction_rows), use_container_width=True)
    
    # TAB 7: Anomalies
    with tab7:
        st.markdown("### Real-time Alerts")
        anomalies = fetch_api(f"/stores/{STORE_ID}/anomalies", {"severity": "low"}) or []
        opportunities = fetch_api(f"/stores/{STORE_ID}/opportunities") or []
        if anomalies:
            st.dataframe(pd.DataFrame(anomalies), use_container_width=True)
        else:
            st.success("No active anomalies for the selected threshold.")
        if opportunities:
            st.markdown("### Opportunities")
            st.dataframe(pd.DataFrame(opportunities), use_container_width=True)
    
    # Footer
    st.markdown("---")
    st.markdown(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Data refresh: {refresh_rate}")


if __name__ == "__main__":
    main()
