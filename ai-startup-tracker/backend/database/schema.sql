-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Enum types
CREATE TYPE startup_status AS ENUM ('active', 'stealth', 'acquired', 'closed', 'unknown');
CREATE TYPE data_source AS ENUM ('domain_registration', 'product_hunt', 'yc', 'betalist', 'hackernews', 'github', 'linkedin');
CREATE TYPE review_status AS ENUM ('pending', 'approved', 'rejected', 'needs_review');

-- Main startups table
CREATE TABLE IF NOT EXISTS startups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    url VARCHAR(512) UNIQUE NOT NULL,
    domain VARCHAR(255) NOT NULL,
    description TEXT,
    status startup_status DEFAULT 'unknown',
    is_stealth BOOLEAN DEFAULT false,

    -- Location
    country VARCHAR(100),
    city VARCHAR(100),
    region VARCHAR(100),
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),

    -- Categorization
    industry_vertical VARCHAR(100),
    primary_tags TEXT[],
    trend_cluster VARCHAR(100),

    -- Founder info
    founder_names TEXT[],
    founder_backgrounds TEXT,
    has_notable_founders BOOLEAN DEFAULT false,

    -- Metadata
    discovered_date TIMESTAMP NOT NULL DEFAULT NOW(),
    last_updated TIMESTAMP DEFAULT NOW(),
    source data_source NOT NULL,
    source_url VARCHAR(512),

    -- AI Analysis
    relevance_score DECIMAL(3, 2), -- 0.00 to 1.00
    confidence_score DECIMAL(3, 2), -- 0.00 to 1.00
    review_status review_status DEFAULT 'pending',

    -- Embedding
    content_embedding vector(384), -- all-MiniLM-L6-v2 dimension (384)

    -- Full text content
    landing_page_text TEXT,
    extracted_keywords TEXT[],

    -- Indexes
    CONSTRAINT valid_relevance_score CHECK (relevance_score >= 0 AND relevance_score <= 1),
    CONSTRAINT valid_confidence_score CHECK (confidence_score >= 0 AND confidence_score <= 1)
);

-- Scraped URLs tracking (to avoid re-scraping)
CREATE TABLE IF NOT EXISTS scraped_urls (
    id SERIAL PRIMARY KEY,
    url VARCHAR(512) UNIQUE NOT NULL,
    source data_source NOT NULL,
    scraped_at TIMESTAMP DEFAULT NOW(),
    status VARCHAR(50) DEFAULT 'success', -- success, failed, skipped
    error_message TEXT,
    retry_count INTEGER DEFAULT 0
);

-- Weekly scraping jobs tracking
CREATE TABLE IF NOT EXISTS scraping_jobs (
    id SERIAL PRIMARY KEY,
    job_type VARCHAR(50) NOT NULL,
    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    status VARCHAR(50) DEFAULT 'running', -- running, completed, failed
    items_processed INTEGER DEFAULT 0,
    items_added INTEGER DEFAULT 0,
    error_message TEXT,
    metadata JSONB
);

-- Trend clusters (detected by LLM)
CREATE TABLE IF NOT EXISTS trend_clusters (
    id SERIAL PRIMARY KEY,
    cluster_name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    startup_count INTEGER DEFAULT 0,
    centroid_embedding vector(384),
    keywords TEXT[],
    is_emerging BOOLEAN DEFAULT true
);

-- Weekly analytics snapshots
CREATE TABLE IF NOT EXISTS weekly_analytics (
    id SERIAL PRIMARY KEY,
    week_start_date DATE NOT NULL,
    week_end_date DATE NOT NULL,
    total_new_startups INTEGER DEFAULT 0,
    total_stealth_startups INTEGER DEFAULT 0,
    top_vertical VARCHAR(100),
    top_region VARCHAR(100),
    emerging_trends TEXT[],
    metadata JSONB,
    UNIQUE(week_start_date)
);

-- Indexes for performance
CREATE INDEX idx_startups_domain ON startups(domain);
CREATE INDEX idx_startups_status ON startups(status);
CREATE INDEX idx_startups_vertical ON startups(industry_vertical);
CREATE INDEX idx_startups_discovered_date ON startups(discovered_date);
CREATE INDEX idx_startups_source ON startups(source);
CREATE INDEX idx_startups_review_status ON startups(review_status);
CREATE INDEX idx_startups_country ON startups(country);
CREATE INDEX idx_startups_tags ON startups USING GIN(primary_tags);

-- Vector similarity search index (HNSW for better performance)
CREATE INDEX idx_startups_embedding ON startups USING hnsw (content_embedding vector_cosine_ops);

-- Scraped URLs index
CREATE INDEX idx_scraped_urls_source ON scraped_urls(source);
CREATE INDEX idx_scraped_urls_scraped_at ON scraped_urls(scraped_at);

-- Scraping jobs index
CREATE INDEX idx_scraping_jobs_started_at ON scraping_jobs(started_at);
CREATE INDEX idx_scraping_jobs_status ON scraping_jobs(status);

-- Function to update last_updated timestamp
CREATE OR REPLACE FUNCTION update_updated_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_updated = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for startups table
CREATE TRIGGER trigger_update_startups_timestamp
    BEFORE UPDATE ON startups
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_timestamp();

-- Function to calculate similarity
CREATE OR REPLACE FUNCTION find_similar_startups(
    query_embedding vector(384),
    similarity_threshold float DEFAULT 0.7,
    max_results int DEFAULT 10
)
RETURNS TABLE (
    startup_id integer,
    startup_name varchar,
    similarity_score float
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        id,
        name,
        1 - (content_embedding <=> query_embedding) as similarity
    FROM startups
    WHERE content_embedding IS NOT NULL
        AND 1 - (content_embedding <=> query_embedding) >= similarity_threshold
    ORDER BY content_embedding <=> query_embedding
    LIMIT max_results;
END;
$$ LANGUAGE plpgsql;
