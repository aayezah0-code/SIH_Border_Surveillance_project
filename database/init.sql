-- Initial Database Schema Skeleton

CREATE TABLE IF NOT EXISTS cameras (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    stream_url VARCHAR(512) NOT NULL,
    location VARCHAR(255),
    status VARCHAR(50) DEFAULT 'offline',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    camera_id INT REFERENCES cameras(id),
    event_type VARCHAR(100) NOT NULL,
    risk_score VARCHAR(50) NOT NULL,
    description TEXT,
    image_path VARCHAR(512),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
