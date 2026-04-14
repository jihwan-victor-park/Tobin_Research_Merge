"""
AI Startup Tracker - Professional Dashboard
Demonstrates Groq API + Vector Embeddings in action
"""




import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import numpy as np
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.database.models import Startup
from backend.database.connection import get_db_session
from backend.intelligence.embeddings import get_embedding_generator
from backend.intelligence.llm_analyzer import get_llm_analyzer
from backend.config import get_settings

# Page config
st.set_page_config(
    page_title="AI Startup Tracker",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main {
        background-color: #0e1117;
    }
    .stMetric {
        background-color: #1e2130;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #2e3446;
    }
    .startup-card {
        background-color: #1e2130;
        padding: 20px;
        border-radius: 10px;
        border-left: 4px solid #4CAF50;
        margin-bottom: 15px;
    }
    .vertical-tag {
        background-color: #2e3446;
        padding: 5px 15px;
        border-radius: 15px;
        display: inline-block;
        margin: 5px;
        font-size: 12px;
    }
    h1 {
        color: #4CAF50;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=300)
def load_startups():
    """Load startups from database"""
    with get_db_session() as session:
        startups = session.query(Startup).filter(
            Startup.relevance_score >= 0.75
        ).order_by(
            Startup.relevance_score.desc()
        ).all()

        data = []
        for s in startups:
            data.append({
                'id': s.id,
                'name': s.name,
                'url': s.url,
                'description': s.description,
                'vertical': s.industry_vertical or 'Other AI',
                'relevance_score': float(s.relevance_score) if s.relevance_score is not None else 0.0,
                'confidence_score': float(s.confidence_score) if s.confidence_score is not None else 0.0,
                'emergence_score': float(s.emergence_score) if getattr(s, 'emergence_score', None) is not None else 0.0,
                'country': s.country,
                'city': s.city,
                'latitude': float(s.latitude) if s.latitude is not None else None,
                'longitude': float(s.longitude) if s.longitude is not None else None,
                'extra_metadata': s.extra_metadata,
                'is_stealth': s.is_stealth or False,
                'has_notable_founders': s.has_notable_founders or False,
                'founder_backgrounds': s.founder_backgrounds or '',
                'created_at': s.discovered_date,
                'source': s.source
            })

        return pd.DataFrame(data)


@st.cache_resource
def get_ai_resources():
    """Get AI resources (cached)"""
    settings = get_settings()
    embedding_gen = get_embedding_generator()
    llm_analyzer = get_llm_analyzer()
    return settings, embedding_gen, llm_analyzer


def demonstrate_vector_similarity(embedding_gen, df):
    """Demonstrate vector embedding similarity calculation"""
    st.subheader("Live Vector Similarity Demo")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Enter a query:**")
        query = st.text_input(
            "Search for startups",
            value="AI healthcare diagnostics",
            key="similarity_search"
        )

    with col2:
        st.markdown("**Similarity Threshold:**")
        threshold = st.slider(
            "Minimum similarity",
            0.0, 1.0, 0.7,
            key="similarity_threshold"
        )

    if query:
        with st.spinner("Calculating vector embeddings..."):
            # Generate query embedding
            query_embedding = embedding_gen.generate_embedding(query)

            # Show embedding info
            st.info(f"Generated {len(query_embedding)}-dimensional embedding vector")
            st.code(f"First 5 dimensions: {query_embedding[:5]}", language="python")

            # Calculate similarities
            results = []
            with get_db_session() as session:
                startups = session.query(Startup).filter(
                    Startup.content_embedding.isnot(None)
                ).limit(50).all()

                for startup in startups:
                    if startup.content_embedding is not None:
                        startup_embedding = np.array(startup.content_embedding)
                        similarity = embedding_gen.calculate_similarity(
                            query_embedding,
                            startup_embedding
                        )

                        if similarity >= threshold:
                            results.append({
                                'name': startup.name,
                                'similarity': similarity,
                                'vertical': startup.industry_vertical or 'Other',
                                'url': startup.url
                            })

            # Sort by similarity
            results = sorted(results, key=lambda x: x['similarity'], reverse=True)

            # Display results
            if results:
                st.success(f"Found {len(results)} matches using cosine similarity")

                for i, result in enumerate(results[:5], 1):
                    with st.container():
                        col1, col2, col3 = st.columns([3, 2, 1])
                        with col1:
                            st.markdown(f"**{i}. [{result['name']}]({result['url']})**")
                        with col2:
                            st.markdown(f"`{result['vertical']}`")
                        with col3:
                            st.metric("Similarity", f"{result['similarity']:.1%}")
            else:
                st.warning("No matches found. Try lowering the threshold.")


def demonstrate_llm_analysis(llm_analyzer):
    """Demonstrate Groq LLM analysis"""
    st.subheader("Live Groq LLM Analysis Demo")

    st.markdown(f"**Model:** `{llm_analyzer.model}` (Groq API)")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Startup Information:**")
        test_name = st.text_input("Company Name", value="HealthAI Corp", key="llm_name")
        test_desc = st.text_area(
            "Description",
            value="AI-powered medical diagnosis platform using deep learning for radiology",
            key="llm_desc"
        )

    with col2:
        st.markdown("**Analysis Tasks:**")
        analyze_vertical = st.checkbox("Categorize Vertical", value=True)
        analyze_stealth = st.checkbox("Detect Stealth Status", value=True)

    if st.button("Run LLM Analysis", type="primary"):
        startup_data = {
            'name': test_name,
            'description': test_desc,
            'landing_page_text': test_desc,
            'url': 'https://example.com',
            'founder_names': []
        }

        with st.spinner("Groq LLM analyzing..."):
            if analyze_vertical:
                vertical, confidence = llm_analyzer.categorize_vertical(startup_data)
                st.success(f"**Vertical:** {vertical} (Confidence: {confidence:.1%})")
                st.code(f"""
Prompt sent to Groq:
- Model: {llm_analyzer.model}
- Task: Categorize into 13 AI verticals
- Response: {vertical} ({confidence:.0%} confidence)
                """, language="text")

            if analyze_stealth:
                is_stealth, stealth_conf, reasoning = llm_analyzer.detect_stealth_status(startup_data)
                status = "Stealth Mode" if is_stealth else "Public"
                st.success(f"**Status:** {status} (Confidence: {stealth_conf:.1%})")
                st.info(f"**Reasoning:** {reasoning}")


def create_geographic_map(df):
    """Create geographic distribution map"""
    # Real coordinates mapping
    coords = {
        'USA': (37.0902, -95.7129), 'United States': (37.0902, -95.7129), 'US': (37.0902, -95.7129),
        'San Francisco': (37.7749, -122.4194), 'SF': (37.7749, -122.4194),
        'New York': (40.7128, -74.0060), 'NY': (40.7128, -74.0060),
        'London': (51.5074, -0.1278), 'UK': (55.3781, -3.4360), 'United Kingdom': (55.3781, -3.4360),
        'Berlin': (52.5200, 13.4050), 'Germany': (51.1657, 10.4515),
        'Paris': (48.8566, 2.3522), 'France': (46.2276, 2.2137),
        'Toronto': (43.6532, -79.3832), 'Canada': (56.1304, -106.3468),
        'Tel Aviv': (32.0853, 34.7818), 'Israel': (31.0461, 34.8516),
        'Singapore': (1.3521, 103.8198),
        'Beijing': (39.9042, 116.4074), 'China': (35.8617, 104.1954),
        'Bangalore': (12.9716, 77.5946), 'India': (20.5937, 78.9629),
        'Tokyo': (35.6762, 139.6503), 'Japan': (36.2048, 138.2529),
        'Sydney': (-33.8688, 151.2093), 'Australia': (-25.2744, 133.7751),
    }

    map_data = []
    for idx, row in df.iterrows():
        # Get city and country
        city = row.get('city')
        country = row.get('country')

        # First try to use database coordinates
        lat = row.get('latitude')
        lon = row.get('longitude')

        # Fallback to dictionary lookup if no database coordinates
        if lat is None or lon is None:
            if city and city in coords:
                lat, lon = coords[city]
            elif country and country in coords:
                lat, lon = coords[country]

        if lat is None or lon is None:
            continue  # Skip if no location found

        # Add larger jitter for visibility when many startups in same location
        lat += np.random.uniform(-2.0, 2.0)
        lon += np.random.uniform(-2.0, 2.0)

        map_data.append({
            'name': row['name'],
            'lat': lat,
            'lon': lon,
            'location': city or country or 'Unknown',
            'vertical': row['vertical'],
            'relevance': row['relevance_score']
        })

    map_df = pd.DataFrame(map_data)

    # Create map
    fig = px.scatter_mapbox(
        map_df,
        lat='lat',
        lon='lon',
        hover_name='name',
        hover_data=['vertical', 'location', 'relevance'],
        color='vertical',
        size='relevance',
        size_max=20,
        zoom=1,
        height=600,
        title="Global AI Startup Emergence Map"
    )

    fig.update_layout(
        mapbox_accesstoken=None,
        mapbox_style="carto-darkmatter",
        showlegend=True,
        legend=dict(
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01,
            bgcolor="rgba(0,0,0,0.5)"
        )
    )

    return fig


def create_weekly_trend(df):
    """Create weekly trend analysis"""
    # Generate weekly data
    today = datetime.now()
    weeks = []

    for i in range(12, -1, -1):
        week_start = today - timedelta(weeks=i)
        week_data = df[df['created_at'] >= week_start - timedelta(weeks=1)]
        week_data = week_data[week_data['created_at'] < week_start]

        vertical_counts = week_data['vertical'].value_counts()

        weeks.append({
            'week': week_start.strftime('%Y-%m-%d'),
            'total': len(week_data),
            'verticals': vertical_counts.to_dict()
        })

    # Create stacked area chart
    verticals = df['vertical'].unique()

    trend_data = []
    for week in weeks:
        row = {'week': week['week'], 'total': week['total']}
        for vertical in verticals:
            row[vertical] = week['verticals'].get(vertical, 0)
        trend_data.append(row)

    trend_df = pd.DataFrame(trend_data)

    fig = go.Figure()

    for vertical in verticals:
        if vertical in trend_df.columns:
            # Get color from Plotly palette and convert to rgba
            color_idx = hash(vertical) % len(px.colors.qualitative.Plotly)
            hex_color = px.colors.qualitative.Plotly[color_idx]
            r = int(hex_color[1:3], 16)
            g = int(hex_color[3:5], 16)
            b = int(hex_color[5:7], 16)

            fig.add_trace(go.Scatter(
                x=trend_df['week'],
                y=trend_df[vertical],
                mode='lines',
                name=vertical,
                stackgroup='one',
                fillcolor=f'rgba({r},{g},{b},0.5)'
            ))

    fig.update_layout(
        title="Weekly AI Startup Emergence Trend",
        xaxis_title="Week",
        yaxis_title="Number of Startups",
        hovermode='x unified',
        height=400,
        template="plotly_dark"
    )

    return fig


def create_emergence_heatmap(df):
    """Create emergence score heatmap by vertical"""
    if 'emergence_score' not in df.columns or df['emergence_score'].isna().all():
        return None

    # Group by vertical and calculate avg emergence score
    vertical_emergence = df.groupby('vertical')['emergence_score'].agg(['mean', 'count']).reset_index()
    vertical_emergence = vertical_emergence.sort_values('mean', ascending=False)

    fig = px.bar(
        vertical_emergence,
        x='vertical',
        y='mean',
        color='mean',
        title="Emergence Score by Vertical (0-100)",
        labels={'mean': 'Avg Emergence Score', 'vertical': 'Industry Vertical'},
        color_continuous_scale='Reds',
        height=400
    )

    fig.update_layout(
        template="plotly_dark",
        showlegend=False,
        xaxis_tickangle=-45
    )

    return fig


def create_source_distribution(df):
    """Create pie chart of data sources"""
    if 'extra_metadata' not in df.columns:
        return None

    # Extract original_source from extra_metadata
    sources = []
    for meta in df['extra_metadata']:
        if isinstance(meta, dict) and 'original_source' in meta:
            sources.append(meta['original_source'])
        else:
            sources.append('Unknown')

    source_counts = pd.Series(sources).value_counts()

    fig = px.pie(
        values=source_counts.values,
        names=source_counts.index,
        title="Data Sources Distribution",
        hole=0.4,
        color_discrete_sequence=px.colors.qualitative.Set3
    )

    fig.update_layout(
        template="plotly_dark",
        height=400
    )

    return fig


def create_global_flow_map(df):
    """Create advanced geographic map showing global AI flow"""
    if 'country' not in df.columns and 'city' not in df.columns:
        # Fallback to mock data
        return create_geographic_map(df)

    # Country coordinates (major AI hubs)
    country_coords = {
        'USA': (37.0902, -95.7129),
        'United States': (37.0902, -95.7129), 'US': (37.0902, -95.7129),
        'UK': (55.3781, -3.4360),
        'United Kingdom': (55.3781, -3.4360), 'England': (52.3555, -1.1743), 'London': (51.5074, -0.1278),
        'China': (35.8617, 104.1954), 'Hong Kong': (22.3193, 114.1694), 'Beijing': (39.9042, 116.4074),
        'Singapore': (1.3521, 103.8198),
        'Germany': (51.1657, 10.4515), 'Berlin': (52.5200, 13.4050),
        'Israel': (31.0461, 34.8516), 'Tel Aviv': (32.0853, 34.7818),
        'Canada': (56.1304, -106.3468), 'Toronto': (43.6532, -79.3832),
        'France': (46.2276, 2.2137), 'Paris': (48.8566, 2.3522),
        'India': (20.5937, 78.9629), 'Bangalore': (12.9716, 77.5946),
        'Japan': (36.2048, 138.2529), 'Tokyo': (35.6762, 139.6503),
        'South Korea': (35.9078, 127.7669), 'Seoul': (37.5665, 126.9780),
        'Australia': (-25.2744, 133.7751), 'Sydney': (-33.8688, 151.2093),
        'Brazil': (-14.2350, -51.9253),
        'Netherlands': (52.1326, 5.2913), 'Amsterdam': (52.3676, 4.9041),
        'Sweden': (60.1282, 18.6435), 'Stockholm': (59.3293, 18.0686),
        'Switzerland': (46.8182, 8.2275), 'Zurich': (47.3769, 8.5417),
        'Spain': (40.4637, -3.7492), 'Madrid': (40.4168, -3.7038),
        'Italy': (41.8719, 12.5674), 'Milan': (45.4642, 9.1900),
        'Ireland': (53.1424, -7.6921), 'Dublin': (53.3498, -6.2603),
        'UAE': (23.4241, 53.8478), 'Dubai': (25.2048, 55.2708),
        'Estonia': (58.5953, 25.0136),
        'Unknown': (0, 0)
    }

    map_data = []
    for idx, row in df.iterrows():
        country = row.get('country', 'Unknown') or 'Unknown'
        city = row.get('city', '')

        # Get coordinates
        if country in country_coords:
            lat, lon = country_coords[country]
        elif city in country_coords:
            lat, lon = country_coords[city]
        else:
            # Default to random location
            lat, lon = country_coords['Unknown']

        # Add small random offset for visualization
        lat += np.random.uniform(-5, 5)
        lon += np.random.uniform(-5, 5)

        map_data.append({
            'name': row['name'],
            'lat': lat,
            'lon': lon,
            'country': country,
            'vertical': row.get('vertical', 'Other'),
            'emergence': row.get('emergence_score', 50) if 'emergence_score' in df.columns else 50
        })

    map_df = pd.DataFrame(map_data)

    # Filter out unknown locations
    map_df = map_df[map_df['country'] != 'Unknown']

    if len(map_df) == 0:
        return None

    fig = px.scatter_mapbox(
        map_df,
        lat='lat',
        lon='lon',
        hover_name='name',
        hover_data=['vertical', 'country', 'emergence'],
        color='emergence',
        size='emergence',
        size_max=30,
        zoom=1,
        height=600,
        title="Global AI Flow Map (by Emergence Score)",
        color_continuous_scale='YlOrRd'
    )

    fig.update_layout(
        mapbox_style="carto-darkmatter",
        showlegend=False
    )

    return fig


def main():
    """Main dashboard"""
    st.title("Tobin Research - AI Startup Tracker Dashboard")
    st.markdown("**Real-time tracking of AI startup emergence using Vector Embeddings & Groq LLM**")

    # Load data
    with st.spinner("Loading data..."):
        df = load_startups()
        settings, embedding_gen, llm_analyzer = get_ai_resources()

    if len(df) == 0:
        st.warning("No data found. Run the trend analysis script:")
        st.code("python scripts/run_trend_analysis.py", language="bash")
        return

    # Sidebar - Tech Stack Info
    with st.sidebar:
        st.header("Technology Stack")
        st.markdown(f"""
        **Embedding Model:**
        `{settings.EMBEDDING_MODEL}`
        ({settings.EMBEDDING_DIMENSION} dimensions)

        **LLM Model:**
        `{settings.LLM_MODEL}`
        (Groq API)

        **Database:**
        PostgreSQL + pgvector

        **Cost:**
        **$0.00/month** (Exlcuded other ones)
        """)

        st.markdown("---")

        # Statistics
        st.header("Statistics")
        st.metric("Total Startups", len(df))
        st.metric("AI-Relevant", len(df[df['relevance_score'] >= 0.75]))
        st.metric("Analyzed", len(df[df['vertical'] != 'Other AI']))
        st.metric("Stealth Mode", len(df[df['is_stealth'] == True]))
        st.metric("Notable Founders", len(df[df['has_notable_founders'] == True]))

    # Main content tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "Geographic View",
        "Startup Directory",
        "Live AI Demo",
        "Trend Intelligence"
    ])

    with tab1:
        # Two-column layout
        col1, col2 = st.columns([6, 4])

        with col1:
            # Geographic Map (LEFT)
            st.markdown("### Geographic Distribution")
            map_fig = create_geographic_map(df)
            st.plotly_chart(map_fig, use_container_width=True)

        with col2:
            # Top Verticals (RIGHT)
            st.markdown("### Top Verticals")
            vertical_counts = df['vertical'].value_counts().head(10)

            fig = px.bar(
                x=vertical_counts.values,
                y=vertical_counts.index,
                orientation='h',
                title="Startups by Category",
                labels={'x': 'Count', 'y': 'Vertical'},
                color=vertical_counts.values,
                color_continuous_scale='Viridis'
            )
            fig.update_layout(
                showlegend=False,
                height=500,
                template="plotly_dark"
            )
            st.plotly_chart(fig, use_container_width=True)

        # Weekly Trend (BOTTOM)
        st.markdown("### Weekly Emergence Trend")
        trend_fig = create_weekly_trend(df)
        st.plotly_chart(trend_fig, use_container_width=True)

        # Key Insights
        st.markdown("### Key Insights")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            avg_relevance = df['relevance_score'].mean()
            st.metric("Avg AI Relevance", f"{avg_relevance:.1%}")

        with col2:
            top_vertical = df['vertical'].value_counts().index[0]
            st.metric("Top Vertical", top_vertical)

        with col3:
            stealth_pct = len(df[df['is_stealth'] == True]) / len(df) * 100
            st.metric("Stealth Mode %", f"{stealth_pct:.1f}%")

        with col4:
            notable_pct = len(df[df['has_notable_founders'] == True]) / len(df) * 100
            st.metric("Notable Founders %", f"{notable_pct:.1f}%")

    with tab2:
        # Startup Directory
        st.markdown("### AI Startup Directory")

        # Filters
        col1, col2, col3 = st.columns(3)

        with col1:
            selected_vertical = st.selectbox(
                "Filter by Vertical",
                options=['All'] + sorted(df['vertical'].unique().tolist())
            )

        with col2:
            min_relevance = st.slider(
                "Minimum AI Relevance",
                0.0, 1.0, 0.75
            )

        with col3:
            show_stealth = st.checkbox("Show Stealth Only", value=False)

        # Apply filters
        filtered_df = df.copy()
        if selected_vertical != 'All':
            filtered_df = filtered_df[filtered_df['vertical'] == selected_vertical]
        filtered_df = filtered_df[filtered_df['relevance_score'] >= min_relevance]
        if show_stealth:
            filtered_df = filtered_df[filtered_df['is_stealth'] == True]

        st.markdown(f"**Showing {len(filtered_df)} startups**")

        # Group by vertical
        for vertical in sorted(filtered_df['vertical'].unique()):
            with st.expander(f"**{vertical}** ({len(filtered_df[filtered_df['vertical'] == vertical])} startups)", expanded=True):
                vertical_startups = filtered_df[filtered_df['vertical'] == vertical]

                for _, startup in vertical_startups.iterrows():
                    st.markdown(f"""
                    <div class="startup-card">
                        <h3>{startup['name']}</h3>
                        <p><a href="{startup['url']}" target="_blank">{startup['url']}</a></p>
                        <p>{startup['description'][:200]}...</p>
                        <span class="vertical-tag">{startup['vertical']}</span>
                        <span class="vertical-tag">AI Relevance: {startup['relevance_score']:.0%}</span>
                        <span class="vertical-tag">Confidence: {startup['confidence_score']:.0%}</span>
                        {'<span class="vertical-tag">Stealth Mode</span>' if startup['is_stealth'] else ''}
                        {'<span class="vertical-tag">Notable Founders</span>' if startup['has_notable_founders'] else ''}
                    </div>
                    """, unsafe_allow_html=True)

    with tab3:
        # Live AI Demonstrations
        st.markdown("### Live AI Technology Demonstrations")
        st.markdown("**Prove that Groq API and Vector Embeddings are actually working!**")

        # Vector Similarity Demo
        demonstrate_vector_similarity(embedding_gen, df)

        st.markdown("---")

        # LLM Analysis Demo
        demonstrate_llm_analysis(llm_analyzer)

    with tab4:
        # Trend Intelligence Dashboard
        st.markdown("### Global AI Trend Intelligence")
        st.markdown("**Visualize the global flow of AI innovation across verticals and regions**")

        # Check if we have emergence scores
        has_emergence = 'emergence_score' in df.columns and not df['emergence_score'].isna().all()

        if not has_emergence:
            st.warning("Emergence scores not available. Run `python scripts/run_trend_analysis.py` to generate trend data.")
            st.info("This tab shows advanced trend analysis including emergence scores, geographic flow, and source distribution.")
        else:
            # Row 1: Global Flow Map (full width)
            st.markdown("#### Global AI Innovation Flow")
            flow_map = create_global_flow_map(df)
            if flow_map:
                st.plotly_chart(flow_map, use_container_width=True)
            else:
                st.info("Geographic data not available for trend map")

            st.markdown("---")

            # Row 2: Two columns
            col1, col2 = st.columns(2)

            with col1:
                # Emergence Heatmap
                st.markdown("#### Emergence by Vertical")
                emergence_fig = create_emergence_heatmap(df)
                if emergence_fig:
                    st.plotly_chart(emergence_fig, use_container_width=True)

                    # Top emerging verticals
                    st.markdown("**Top 3 Emerging Verticals:**")
                    top_emerging = df.groupby('vertical')['emergence_score'].mean().sort_values(ascending=False).head(3)
                    for idx, (vertical, score) in enumerate(top_emerging.items(), 1):
                        st.metric(f"{idx}. {vertical}", f"{score:.1f}/100", delta=None)

            with col2:
                # Source Distribution
                st.markdown("#### Data Sources")
                source_fig = create_source_distribution(df)
                if source_fig:
                    st.plotly_chart(source_fig, use_container_width=True)
                else:
                    st.info("Source distribution not available")

                # Source stats
                if 'extra_metadata' in df.columns:
                    st.markdown("**Source Breakdown:**")
                    sources = []
                    for meta in df['extra_metadata']:
                        if isinstance(meta, dict) and 'original_source' in meta:
                            sources.append(meta['original_source'])
                    source_counts = pd.Series(sources).value_counts()
                    for source, count in source_counts.items():
                        st.write(f"- {source}: {count} projects")

            st.markdown("---")

            # Row 3: Key Insights
            st.markdown("#### Key Trend Insights")

            cols = st.columns(4)

            with cols[0]:
                avg_emergence = df['emergence_score'].mean()
                st.metric("Avg Emergence", f"{avg_emergence:.1f}/100")

            with cols[1]:
                high_emergence = len(df[df['emergence_score'] >= 80])
                st.metric("High Emergence", f"{high_emergence} projects", delta=f"{high_emergence/len(df)*100:.1f}%")

            with cols[2]:
                unique_countries = df['country'].nunique() if 'country' in df.columns else 0
                st.metric("Countries", unique_countries)

            with cols[3]:
                unique_verticals = df['vertical'].nunique()
                st.metric("Active Verticals", unique_verticals)

            # Row 4: Emergence Score Details
            st.markdown("---")
            st.markdown("#### Emergence Score Details")

            st.info("""
            **What is Emergence Score?**
            - Range: 0-100 (higher = more emerging/trending)
            - Factors:
              - **Recency**: Newer projects score higher
              - **Source**: Product Hunt > Y Combinator > GitHub
              - **Quality**: Description completeness
            - Use this to identify which AI projects are gaining momentum
            """)

            # Show top 10 most emerging projects
            with st.expander("Top 10 Most Emerging Projects"):
                top_projects = df.nlargest(10, 'emergence_score')[['name', 'vertical', 'emergence_score', 'url']]
                for idx, row in top_projects.iterrows():
                    st.markdown(f"**{row['name']}** ({row['vertical']}) - {row['emergence_score']:.1f}/100")
                    st.markdown(f"[Visit]({row['url']})")
                    st.markdown("---")


if __name__ == "__main__":
    main()
