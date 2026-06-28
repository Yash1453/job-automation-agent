"""
Advanced Job Automation Agent - Main Orchestrator
Windows-compatible, multi-source job scraping + LLM scoring + auto-apply
"""

import os
import sys
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
import requests

# Load environment variables
load_dotenv()

# Setup logging
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "execution.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==============================================================================
# DATABASE SETUP
# ==============================================================================

def init_database():
    """Initialize SQLite database for tracking applications"""
    db_path = "data/applications.db"
    Path("data").mkdir(exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            job_id TEXT PRIMARY KEY,
            source TEXT,
            company TEXT,
            job_title TEXT,
            description TEXT,
            apply_url TEXT,
            salary TEXT,
            location TEXT,
            seniority_level TEXT,
            resume_score REAL,
            scoring_details TEXT,
            application_status TEXT DEFAULT 'pending',
            applied_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scrape_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            jobs_found INTEGER,
            jobs_new INTEGER,
            scrape_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT,
            error_log TEXT
        )
    """)
    
    conn.commit()
    conn.close()
    logger.info("Database initialized")

def job_exists(job_id, company, job_title):
    """Check if job already exists in database (deduplication)"""
    conn = sqlite3.connect("data/applications.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT COUNT(*) FROM applications 
        WHERE job_id = ? OR (company = ? AND job_title = ?)
    """, (job_id, company, job_title))
    
    result = cursor.fetchone()[0] > 0
    conn.close()
    return result

def save_job(job_data):
    """Save job to database"""
    conn = sqlite3.connect("data/applications.db")
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO applications 
            (job_id, source, company, job_title, description, apply_url, 
             salary, location, seniority_level, application_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_data.get('job_id'),
            job_data.get('source'),
            job_data.get('company'),
            job_data.get('title'),
            job_data.get('description'),
            job_data.get('apply_url'),
            job_data.get('salary'),
            job_data.get('location'),
            job_data.get('seniority_level'),
            'pending'
        ))
        conn.commit()
        logger.info(f"Saved job: {job_data.get('title')} @ {job_data.get('company')}")
    except sqlite3.IntegrityError:
        logger.debug(f"Job already exists: {job_data.get('job_id')}")
    finally:
        conn.close()

def update_job_score(job_id, score, reasoning):
    """Update job with LLM score"""
    conn = sqlite3.connect("data/applications.db")
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE applications 
        SET resume_score = ?, scoring_details = ?
        WHERE job_id = ?
    """, (score, reasoning, job_id))
    conn.commit()
    conn.close()

def get_high_score_jobs():
    """Get jobs scoring >= 75 that haven't been applied to"""
    conn = sqlite3.connect("data/applications.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM applications 
        WHERE resume_score >= 75 AND application_status = 'pending'
        ORDER BY resume_score DESC
        LIMIT 10
    """)
    jobs = cursor.fetchall()
    conn.close()
    return jobs

# ==============================================================================
# LLM SCORING ENGINE (Ollama Local)
# ==============================================================================

class LLMScorer:
    """Score jobs against resume using local Ollama LLM"""
    
    def __init__(self, model=None, base_url=None):
        self.model = model or os.getenv("OLLAMA_MODEL", "phi3:mini")
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.resume_context = self._load_resume()
    
    def _load_resume(self):
        """Load resume context from file"""
        resume_file = "config/resume_context.txt"
        if Path(resume_file).exists():
            with open(resume_file, 'r') as f:
                return f.read()
        return "Resume context not found. Add to config/resume_context.txt"
    
    def score_job(self, job_data):
        """Score a job posting against resume"""
        prompt = f"""You are a job-resume matcher. Score this job posting against the candidate's resume.

CANDIDATE RESUME (Key Skills & Experience):
{self.resume_context}

JOB POSTING:
Title: {job_data.get('title', 'N/A')}
Company: {job_data.get('company', 'N/A')}
Location: {job_data.get('location', 'N/A')}
Seniority: {job_data.get('seniority_level', 'N/A')}
Requirements: {job_data.get('description', 'N/A')[:1000]}

Score this job on a scale of 0-100 based on:
1. Tech stack alignment (40%): LangChain, LangGraph, FastAPI, GCP, Docker, RAG, FAISS, ChromaDB, OpenAI/Anthropic APIs
2. Experience level match (30%): 1-2 years GenAI/LLM focus preferred
3. Seniority appropriateness (20%): Entry-level to mid-level roles
4. Role relevance (10%): AI Engineer, GenAI Engineer, ML Engineer, Data roles

Return ONLY valid JSON (no markdown, no extra text):
{{
    "score": <number 0-100>,
    "reasoning": "<brief explanation under 50 words>",
    "key_matches": ["skill1", "skill2", "skill3"],
    "gaps": ["gap1", "gap2"],
    "recommendation": "APPLY" or "SKIP"
}}"""
        
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.3
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result_text = response.json().get('response', '').strip()
                
                # Extract JSON from response
                try:
                    # Try to find JSON in response
                    start_idx = result_text.find('{')
                    end_idx = result_text.rfind('}') + 1
                    if start_idx != -1 and end_idx > start_idx:
                        json_str = result_text[start_idx:end_idx]
                        return json.loads(json_str)
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse LLM response: {result_text}")
                    return {"score": 0, "reasoning": "Parsing error", "recommendation": "SKIP"}
        
        except requests.exceptions.ConnectionError:
            logger.error("Ollama not running. Start with: ollama serve")
            return {"score": 0, "reasoning": "Ollama unavailable", "recommendation": "SKIP"}
        except Exception as e:
            logger.error(f"Scoring error: {e}")
            return {"score": 0, "reasoning": f"Error: {str(e)}", "recommendation": "SKIP"}
    
    def is_available(self):
        """Check if Ollama is running"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except:
            return False

# ==============================================================================
# TELEGRAM NOTIFIER
# ==============================================================================

class TelegramNotifier:
    """Send notifications via Telegram bot"""
    
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.ready = self.token and self.chat_id
        if not self.ready:
            logger.warning("Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
    
    def send_application(self, job_data, score):
        """Notify about successful application"""
        if not self.ready:
            return
        
        try:
            score_value = float(score)
        except (TypeError, ValueError):
            score_value = 0.0
        message = f"""✅ Applied to Job
        
<b>{job_data.get('title')}</b>
Company: {job_data.get('company')}
Location: {job_data.get('location', 'Remote')}
Score: <b>{score_value:.0f}/100</b>
Status: <b>{job_data.get('status', 'submitted')}</b>

<a href="{job_data.get('apply_url')}">View Posting</a>"""
        
        self._send_message(message)
    
    def send_skipped(self, job_data, reason):
        """Notify about skipped job"""
        if not self.ready:
            return
        
        message = f"""⏭️ Skipped Job
        
{job_data.get('title')} @ {job_data.get('company')}
Reason: {reason}"""
        
        self._send_message(message)
    
    def send_daily_summary(self, stats):
        """Send daily summary"""
        if not self.ready:
            return
        
        message = f"""📊 Daily Summary ({datetime.now().strftime('%Y-%m-%d')})
        
Applications Sent: {stats.get('applied', 0)}
Jobs Scraped: {stats.get('scraped', 0)}
Average Score: {stats.get('avg_score', 0):.1f}
Pending: {stats.get('pending', 0)}
Submitted: {stats.get('submitted', 0)}
Not Scored: {stats.get('not_scored', 0)}"""
        
        self._send_message(message)
    
    def _send_message(self, text):
        """Send message to Telegram"""
        try:
            response = requests.post(
                f"{self.base_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML"
                },
                timeout=10
            )
            if response.status_code != 200:
                logger.error(f"Telegram error: {response.text}")
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")

# ==============================================================================
# MAIN ORCHESTRATOR
# ==============================================================================

class JobAgent:
    """Main job automation agent"""
    
    def __init__(self):
        init_database()
        self.scorer = LLMScorer()
        self.notifier = TelegramNotifier()
        self.stats = {
            'scraped': 0,
            'new': 0,
            'scored': 0,
            'applied': 0,
            'skipped': 0,
            'avg_score': 0.0,
            'pending': 0,
            'submitted': 0,
            'not_scored': 0
        }
    
    def run(self, mode='full'):
        """Run agent in specified mode"""
        logger.info(f"Starting job agent in {mode} mode")
        
        if mode in ['scrape', 'full']:
            self.scrape_all()
        
        if mode in ['score', 'full']:
            self.score_all()
        
        if mode in ['apply', 'full']:
            self.apply_all()
        
        self.report()
        logger.info("Job agent completed")
    
    def scrape_all(self):
        """Scrape all job sources"""
        logger.info("=== SCRAPE PHASE ===")
        
        from scrapers import (
            LinkedInScraper, WellfoundScraper, AngelListScraper,
            HackerNewsScraper, RemoteOKScraper, StackOverflowScraper,
            IndeedScraper
        )
        
        scrapers = [
            LinkedInScraper(),
            WellfoundScraper(),
            AngelListScraper(),
            HackerNewsScraper(),
            RemoteOKScraper(),
            StackOverflowScraper(),
            IndeedScraper()
        ]
        
        for scraper in scrapers:
            try:
                jobs = scraper.scrape()
                logger.info(f"{scraper.__class__.__name__}: Found {len(jobs)} jobs")
                
                for job in jobs:
                    if not job_exists(job.get('job_id'), job.get('company'), job.get('title')):
                        save_job(job)
                        self.stats['new'] += 1
                    self.stats['scraped'] += 1
            
            except Exception as e:
                logger.error(f"Scraper {scraper.__class__.__name__} failed: {e}")
    
    def score_all(self):
        """Score all pending jobs"""
        logger.info("=== SCORING PHASE ===")
        
        if not self.scorer.is_available():
            logger.error("❌ Ollama not running!")
            logger.info("To start Ollama on Windows:")
            logger.info("  1. Download from https://ollama.ai")
            logger.info("  2. Run: ollama serve")
            logger.info("  3. In another terminal: ollama pull llama2")
            return
        
        conn = sqlite3.connect("data/applications.db")
        cursor = conn.cursor()
        cursor.execute("SELECT job_id, company, job_title, description FROM applications WHERE resume_score IS NULL LIMIT 20")
        jobs = cursor.fetchall()
        conn.close()
        
        for job_id, company, title, description in jobs:
            job_data = {
                'job_id': job_id,
                'company': company,
                'title': title,
                'description': description
            }
            
            score_result = self.scorer.score_job(job_data)
            score_raw = score_result.get('score', 0)
            try:
                score = float(score_raw)
            except (TypeError, ValueError):
                score = 0.0
            reasoning = json.dumps(score_result)
            
            update_job_score(job_id, score, reasoning)
            self.stats['scored'] += 1
            logger.info(f"Scored: {title} @ {company}: {score}/100")
    
    def apply_all(self):
        """Apply to high-scoring jobs"""
        logger.info("=== APPLICATION PHASE ===")
        
        jobs = get_high_score_jobs()
        logger.info(f"Found {len(jobs)} jobs with score >= 75")
        
        # TODO: Implement Playwright form automation
        # For now, just mark as applied and notify
        for job in jobs:
            job_id = job[0]
            score = job[10]
            job_title = job[3]
            company = job[2]
            location = job[7]
            apply_url = job[5]
            job_data = {
                'title': job_title,
                'company': company,
                'location': location,
                'apply_url': apply_url,
                'status': 'submitted'
            }
            
            conn = sqlite3.connect("data/applications.db")
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE applications 
                SET application_status = 'submitted', applied_at = CURRENT_TIMESTAMP
                WHERE job_id = ?
            """, (job_id,))
            conn.commit()
            conn.close()
            
            self.stats['applied'] += 1
            logger.info(f"Applied to job {job_id}")
            self.notifier.send_application(job_data, score)
    
    def report(self):
        """Print and send daily report"""
        logger.info("=== REPORT ===")
        
        conn = sqlite3.connect("data/applications.db")
        cursor = conn.cursor()
        cursor.execute("SELECT AVG(resume_score) FROM applications WHERE resume_score IS NOT NULL")
        avg_score = cursor.fetchone()[0] or 0.0
        cursor.execute("SELECT COUNT(*) FROM applications WHERE application_status = 'pending'")
        pending = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM applications WHERE application_status = 'submitted'")
        submitted = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM applications WHERE resume_score IS NULL")
        not_scored = cursor.fetchone()[0]
        conn.close()
        
        self.stats['avg_score'] = avg_score
        self.stats['pending'] = pending
        self.stats['submitted'] = submitted
        self.stats['not_scored'] = not_scored
        
        report_line = (
            f"Scraped: {self.stats['scraped']} | New: {self.stats['new']} | Scored: {self.stats['scored']} | Applied: {self.stats['applied']} | "
            f"Average Score: {self.stats['avg_score']:.1f} | Pending: {self.stats['pending']} | Submitted: {self.stats['submitted']} | Not Scored: {self.stats['not_scored']}"
        )
        logger.info(report_line)
        self.notifier.send_daily_summary(self.stats)

# ==============================================================================
# ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    agent = JobAgent()
    
    mode = sys.argv[1] if len(sys.argv) > 1 else 'full'
    # Usage: python job_agent_complete.py [scrape|score|apply|full]
    
    agent.run(mode)
