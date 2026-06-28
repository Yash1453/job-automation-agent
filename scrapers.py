"""
Multi-source job scrapers for:
- LinkedIn
- Wellfound
- AngelList
- HackerNews Who's Hiring
- RemoteOK
- Stack Overflow Jobs
- Indeed
"""

import requests
import logging
from datetime import datetime
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup
import json
import hashlib
import time
from fake_useragent import UserAgent

logger = logging.getLogger(__name__)

# ==============================================================================
# BASE SCRAPER CLASS
# ==============================================================================

class BaseScraper(ABC):
    """Base class for all scrapers"""
    
    def __init__(self):
        self.ua = UserAgent()
        self.session = requests.Session()
        self.jobs = []
    
    def get_headers(self):
        """Get randomized headers to avoid detection"""
        return {
            'User-Agent': self.ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://google.com',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
    
    def generate_job_id(self, company, title, url):
        """Generate unique job ID"""
        return hashlib.md5(f"{company}{title}{url}".encode()).hexdigest()[:12]
    
    @abstractmethod
    def scrape(self):
        """Scrape jobs from source"""
        pass

# ==============================================================================
# LINKEDIN SCRAPER
# ==============================================================================

class LinkedInScraper(BaseScraper):
    """Scrape LinkedIn job postings"""
    
    def scrape(self):
        """Scrape LinkedIn using keyword search"""
        try:
            keywords = [
                "GenAI Engineer",
                "AI Engineer",
                "LLM Engineer",
                "Machine Learning Engineer",
                "Data Engineer",
                "AI Systems Engineer"
            ]
            
            for keyword in keywords:
                # LinkedIn API approach (requires authentication in production)
                # For MVP, using public job search URL
                url = f"https://www.linkedin.com/jobs/search/?keywords={keyword}&location=India&f_T=1,2,3&f_WRA=true"
                
                try:
                    response = self.session.get(url, headers=self.get_headers(), timeout=10)
                    
                    # Note: LinkedIn heavily blocks scrapers
                    # Production should use LinkedIn API or proxy service
                    if response.status_code == 200:
                        jobs = self._parse_linkedin(response.text)
                        self.jobs.extend(jobs)
                    
                    time.sleep(2)  # Rate limiting
                except Exception as e:
                    logger.error(f"LinkedIn scrape error: {e}")
            
            return self.jobs
        except Exception as e:
            logger.error(f"LinkedIn scraper failed: {e}")
            return []
    
    def _parse_linkedin(self, html):
        """Parse LinkedIn job listings"""
        jobs = []
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # LinkedIn structure varies; this is a fallback
            job_cards = soup.find_all('div', {'class': 'base-card'})
            
            for card in job_cards[:10]:  # Limit to first 10
                try:
                    title = card.find('h3', {'class': 'base-search-card__title'})
                    company = card.find('h4', {'class': 'base-search-card__subtitle'})
                    location = card.find('span', {'class': 'job-search-card__location'})
                    link = card.find('a', {'class': 'base-card__full-link'})
                    
                    if all([title, company, link]):
                        job = {
                            'job_id': self.generate_job_id(
                                company.text.strip() if company else 'LinkedIn',
                                title.text.strip(),
                                link.get('href', '')
                            ),
                            'source': 'LinkedIn',
                            'title': title.text.strip(),
                            'company': company.text.strip() if company else 'LinkedIn',
                            'location': location.text.strip() if location else 'Not specified',
                            'apply_url': link.get('href', ''),
                            'description': card.text[:500],
                            'seniority_level': 'Mid-Level'
                        }
                        jobs.append(job)
                except Exception as e:
                    logger.debug(f"Error parsing LinkedIn job card: {e}")
        
        except Exception as e:
            logger.error(f"LinkedIn parse error: {e}")
        
        return jobs

# ==============================================================================
# WELLFOUND SCRAPER
# ==============================================================================

class WellfoundScraper(BaseScraper):
    """Scrape Wellfound (formerly AngelList) startup jobs"""
    
    def scrape(self):
        """Scrape Wellfound jobs via their API"""
        try:
            # Wellfound has a public API
            url = "https://api.wellfound.com/jobs"
            
            params = {
                'role_types': ['engineer'],
                'skills': ['machine-learning', 'ai', 'python', 'langchain'],
                'job_type': ['full-time'],
                'locations': ['remote', 'in-person', 'india'],
                'per_page': 100
            }
            
            response = self.session.get(
                url,
                params=params,
                headers=self.get_headers(),
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                jobs = data.get('jobs', [])
                
                for job in jobs:
                    parsed_job = {
                        'job_id': self.generate_job_id(
                            job.get('company_name', 'Unknown'),
                            job.get('title', ''),
                            job.get('id', '')
                        ),
                        'source': 'Wellfound',
                        'title': job.get('title', ''),
                        'company': job.get('company_name', ''),
                        'location': ', '.join(job.get('locations', [])) if job.get('locations') else 'Remote',
                        'description': job.get('description', '')[:1000],
                        'apply_url': f"https://wellfound.com/jobs/{job.get('id')}",
                        'salary': f"${job.get('min_salary', 'N/A')} - ${job.get('max_salary', 'N/A')}",
                        'seniority_level': job.get('seniority', 'Mid-Level')
                    }
                    self.jobs.append(parsed_job)
            
            logger.info(f"Wellfound: Found {len(self.jobs)} jobs")
            return self.jobs
        
        except Exception as e:
            logger.error(f"Wellfound scraper failed: {e}")
            return []

# ==============================================================================
# ANGELLIST SCRAPER
# ==============================================================================

class AngelListScraper(BaseScraper):
    """Scrape AngelList (now Wellfound) startup jobs"""
    
    def scrape(self):
        """Scrape AngelList via Wellfound API"""
        # AngelList merged with Wellfound, so we reuse Wellfound
        return WellfoundScraper().scrape()

# ==============================================================================
# HACKERNEWS SCRAPER
# ==============================================================================

class HackerNewsScraper(BaseScraper):
    """Scrape HackerNews Who's Hiring monthly thread"""
    
    def scrape(self):
        """Scrape HackerNews Who's Hiring"""
        try:
            # HackerNews API for "Who is Hiring" posts
            url = "https://hacker-news.firebaseio.com/v0/user/whoishiring/jobs.json"
            
            response = self.session.get(url, headers=self.get_headers(), timeout=10)
            
            if response.status_code == 200:
                job_ids = response.json()
                
                # Fetch latest 50 jobs
                for job_id in job_ids[-50:]:
                    try:
                        job_url = f"https://hacker-news.firebaseio.com/v0/item/{job_id}.json"
                        job_response = self.session.get(job_url, headers=self.get_headers(), timeout=5)
                        
                        if job_response.status_code == 200:
                            job_data = job_response.json()
                            
                            # Parse HN job format
                            text = job_data.get('text', '')
                            title = self._extract_title(text)
                            company = self._extract_company(text)
                            location = self._extract_location(text)
                            
                            job = {
                                'job_id': self.generate_job_id(company, title, str(job_id)),
                                'source': 'HackerNews',
                                'title': title,
                                'company': company,
                                'location': location,
                                'description': text[:500],
                                'apply_url': f"https://news.ycombinator.com/item?id={job_id}",
                                'seniority_level': 'Not specified'
                            }
                            self.jobs.append(job)
                        
                        time.sleep(0.5)  # Rate limiting
                    except Exception as e:
                        logger.debug(f"Error parsing HN job {job_id}: {e}")
            
            logger.info(f"HackerNews: Found {len(self.jobs)} jobs")
            return self.jobs
        
        except Exception as e:
            logger.error(f"HackerNews scraper failed: {e}")
            return []
    
    def _extract_title(self, text):
        """Extract job title from HN post"""
        lines = text.split('\n')
        return lines[0][:100] if lines else "HackerNews Job"
    
    def _extract_company(self, text):
        """Extract company name from HN post"""
        if '|' in text:
            return text.split('|')[0].strip()[:50]
        return "HackerNews"
    
    def _extract_location(self, text):
        """Extract location from HN post"""
        if 'remote' in text.lower():
            return 'Remote'
        if 'india' in text.lower():
            return 'India'
        return 'Not specified'

# ==============================================================================
# REMOTEOK SCRAPER
# ==============================================================================

class RemoteOKScraper(BaseScraper):
    """Scrape RemoteOK remote jobs"""
    
    def scrape(self):
        """Scrape RemoteOK jobs"""
        try:
            url = "https://remoteok.io/api"
            
            response = self.session.get(url, headers=self.get_headers(), timeout=15)
            
            if response.status_code == 200:
                jobs_data = response.json()
                
                for job in jobs_data[1:51]:  # Skip header, get first 50
                    if job.get('job_type') in ['full-time', 'flexible']:
                        # Filter for tech/AI roles
                        title = job.get('title', '')
                        if any(keyword in title.lower() for keyword in ['engineer', 'ai', 'python', 'data', 'ml']):
                            parsed_job = {
                                'job_id': self.generate_job_id(
                                    job.get('company_name', ''),
                                    title,
                                    job.get('id', '')
                                ),
                                'source': 'RemoteOK',
                                'title': title,
                                'company': job.get('company_name', 'Remote Company'),
                                'location': 'Remote',
                                'description': job.get('description', '')[:1000],
                                'apply_url': job.get('url', ''),
                                'salary': job.get('salary', 'Not disclosed'),
                                'seniority_level': 'Not specified'
                            }
                            self.jobs.append(parsed_job)
            
            logger.info(f"RemoteOK: Found {len(self.jobs)} jobs")
            return self.jobs
        
        except Exception as e:
            logger.error(f"RemoteOK scraper failed: {e}")
            return []

# ==============================================================================
# STACK OVERFLOW SCRAPER
# ==============================================================================

class StackOverflowScraper(BaseScraper):
    """Scrape Stack Overflow jobs"""
    
    def scrape(self):
        """Scrape Stack Overflow jobs"""
        try:
            url = "https://stackoverflow.com/jobs"
            
            params = {
                'q': 'machine learning OR python OR ai',
                'l': 'India',
                't': 'permanent',
                'r': 'true'  # remote
            }
            
            response = self.session.get(
                url,
                params=params,
                headers=self.get_headers(),
                timeout=15
            )
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                job_cards = soup.find_all('div', {'class': 's-job-card'})
                
                for card in job_cards[:20]:
                    try:
                        title_elem = card.find('a', {'class': 's-link'})
                        company_elem = card.find('a', {'class': 'fc-black-500'})
                        
                        if title_elem and company_elem:
                            job = {
                                'job_id': self.generate_job_id(
                                    company_elem.text.strip(),
                                    title_elem.text.strip(),
                                    title_elem.get('href', '')
                                ),
                                'source': 'Stack Overflow',
                                'title': title_elem.text.strip(),
                                'company': company_elem.text.strip(),
                                'location': 'Remote',
                                'description': card.text[:500],
                                'apply_url': f"https://stackoverflow.com{title_elem.get('href', '')}",
                                'seniority_level': 'Not specified'
                            }
                            self.jobs.append(job)
                    except Exception as e:
                        logger.debug(f"Error parsing SO job: {e}")
            
            logger.info(f"Stack Overflow: Found {len(self.jobs)} jobs")
            return self.jobs
        
        except Exception as e:
            logger.error(f"Stack Overflow scraper failed: {e}")
            return []

# ==============================================================================
# INDEED SCRAPER
# ==============================================================================

class IndeedScraper(BaseScraper):
    """Scrape Indeed jobs"""
    
    def scrape(self):
        """Scrape Indeed jobs"""
        try:
            url = "https://in.indeed.com/jobs"
            
            params = {
                'q': 'AI Engineer OR GenAI OR LLM',
                'l': 'India'
            }
            
            response = self.session.get(
                url,
                params=params,
                headers=self.get_headers(),
                timeout=15
            )
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                job_cards = soup.find_all('div', {'class': 'resultContent'})
                
                for card in job_cards[:20]:
                    try:
                        title_elem = card.find('h2', {'class': 'jobTitle'})
                        company_elem = card.find('span', {'class': 'companyName'})
                        location_elem = card.find('div', {'class': 'companyLocation'})
                        
                        if title_elem and company_elem:
                            link_elem = title_elem.find('a')
                            job = {
                                'job_id': self.generate_job_id(
                                    company_elem.text.strip(),
                                    title_elem.text.strip(),
                                    link_elem.get('href', '') if link_elem else ''
                                ),
                                'source': 'Indeed',
                                'title': title_elem.text.strip(),
                                'company': company_elem.text.strip(),
                                'location': location_elem.text.strip() if location_elem else 'Not specified',
                                'description': card.text[:500],
                                'apply_url': f"https://in.indeed.com{link_elem.get('href', '')}" if link_elem else '',
                                'seniority_level': 'Not specified'
                            }
                            self.jobs.append(job)
                    except Exception as e:
                        logger.debug(f"Error parsing Indeed job: {e}")
            
            logger.info(f"Indeed: Found {len(self.jobs)} jobs")
            return self.jobs
        
        except Exception as e:
            logger.error(f"Indeed scraper failed: {e}")
            return []

# ==============================================================================
# EXPORT ALL SCRAPERS
# ==============================================================================

__all__ = [
    'LinkedInScraper',
    'WellfoundScraper',
    'AngelListScraper',
    'HackerNewsScraper',
    'RemoteOKScraper',
    'StackOverflowScraper',
    'IndeedScraper'
]
