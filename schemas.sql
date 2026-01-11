-- Users table
CREATE TABLE IF NOT EXISTS users (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    interests JSON,
    verified BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- CV Uploads table
CREATE TABLE IF NOT EXISTS cv_uploads (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    file_path VARCHAR(255) NOT NULL,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

-- CV Analyses table: store extracted text and AI analysis results
CREATE TABLE IF NOT EXISTS cv_analyses (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    file_path VARCHAR(255) NOT NULL,
    parsed_text LONGTEXT,
    analysis_json JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

-- Interview sessions table
CREATE TABLE IF NOT EXISTS interview_sessions (
    id VARCHAR(36) PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    topic VARCHAR(255) DEFAULT 'General',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP NULL,
    metadata JSON NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

-- Interview messages table
CREATE TABLE IF NOT EXISTS interview_messages (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL,
    role ENUM('user','ai') NOT NULL,
    content TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES interview_sessions(id) ON DELETE CASCADE,
    INDEX (session_id),
    INDEX (created_at)
) ENGINE=InnoDB;
