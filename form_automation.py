"""
Playwright-based form automation for auto-applying to jobs
Handles various form types, CAPTCHA detection, and human-like behavior
"""

import asyncio
import logging
import time
import random
from pathlib import Path
from playwright.async_api import async_playwright, Page
from typing import Dict, List, Optional
import json

logger = logging.getLogger(__name__)

class FormAutomation:
    """Automate job application form filling"""
    
    def __init__(self, headless=True, slow_mo=100):
        self.headless = headless
        self.slow_mo = slow_mo  # milliseconds
        self.page: Optional[Page] = None
        self.browser = None
    
    async def init_browser(self):
        """Initialize Playwright browser"""
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--disable-dev-shm-usage',  # Fix memory issues on Windows
                '--no-sandbox',
            ]
        )
        self.page = await self.browser.new_page()
    
    async def close(self):
        """Close browser safely"""
        if self.page:
            await self.page.close()
        if self.browser:
            await self.browser.close()
    
    async def apply_to_job(self, job_data: Dict) -> bool:
        """Attempt to apply to a job posting"""
        try:
            apply_url = job_data.get('apply_url')
            if not apply_url:
                logger.warning("No apply URL provided")
                return False
            
            logger.info(f"Navigating to {apply_url}")
            await self.page.goto(apply_url, wait_until="networkidle", timeout=30000)
            
            # Wait for page to fully load
            await asyncio.sleep(random.uniform(2, 4))
            
            # Detect and handle different form types
            if await self._detect_capcha():
                logger.warning("CAPTCHA detected, skipping")
                return False
            
            # Try to find and fill application form
            if await self._fill_application_form(job_data):
                logger.info(f"Successfully applied to {job_data.get('title')}")
                return True
            else:
                logger.warning(f"Could not fill form for {job_data.get('title')}")
                return False
        
        except Exception as e:
            logger.error(f"Application failed: {e}")
            return False
    
    async def _detect_capcha(self) -> bool:
        """Detect if CAPTCHA is present"""
        captcha_indicators = [
            'g-recaptcha',
            'hcaptcha',
            'captcha',
            'verify you are human',
        ]
        
        page_content = await self.page.content()
        
        for indicator in captcha_indicators:
            if indicator.lower() in page_content.lower():
                logger.warning(f"CAPTCHA detected: {indicator}")
                return True
        
        return False
    
    async def _fill_application_form(self, job_data: Dict) -> bool:
        """Fill out job application form"""
        try:
            # Find all input fields
            inputs = await self.page.query_selector_all('input, textarea, select')
            
            if not inputs:
                logger.warning("No form fields found on page")
                return False
            
            for input_elem in inputs:
                try:
                    input_type = await input_elem.get_attribute('type')
                    input_name = await input_elem.get_attribute('name')
                    placeholder = await input_elem.get_attribute('placeholder')
                    label_text = await self._get_associated_label(input_elem)
                    
                    field_context = f"{input_name or ''} {placeholder or ''} {label_text or ''}".lower()
                    
                    # Map field to resume data
                    value = await self._determine_field_value(field_context, job_data)
                    
                    if value:
                        await self._fill_field(input_elem, input_type, value)
                        logger.debug(f"Filled field: {field_context} = {value[:30]}...")
                    
                    # Human-like delay
                    await asyncio.sleep(random.uniform(0.5, 2))
                
                except Exception as e:
                    logger.debug(f"Could not fill field: {e}")
                    continue
            
            # Try to find and click submit button
            submit_button = await self._find_submit_button()
            if submit_button:
                logger.info("Found submit button, clicking...")
                await asyncio.sleep(random.uniform(1, 3))
                await submit_button.click()
                await asyncio.sleep(3)  # Wait for submission
                return True
            
            return False
        
        except Exception as e:
            logger.error(f"Form filling error: {e}")
            return False
    
    async def _get_associated_label(self, elem) -> str:
        """Get label text associated with input"""
        try:
            # Try to find associated label
            label = await elem.evaluate("""
                (el) => {
                    if (el.labels && el.labels.length > 0) {
                        return el.labels[0].textContent;
                    }
                    return '';
                }
            """)
            return label or ""
        except:
            return ""
    
    async def _determine_field_value(self, field_context: str, job_data: Dict) -> Optional[str]:
        """Determine what value to fill based on field context"""
        
        # Mapping of field keywords to resume values
        field_mappings = {
            'name': 'Yash',  # TODO: Make configurable
            'email': 'your-email@domain.com',  # TODO: Make configurable
            'phone': '+91-XXXXXXXXXX',  # TODO: Make configurable
            'location': 'India',
            'city': 'Aurangabad',
            'country': 'India',
            'position': job_data.get('title', ''),
            'company': job_data.get('company', ''),
            'experience': '1.5 years',
            'skills': 'Python, LangChain, FastAPI, LLM',
            'resume': 'resume.pdf',  # TODO: Add resume path
            'cover': 'Do you want to provide a cover letter?',
            'notice': 'Can start immediately',
            'relocation': 'Open to relocation',
            'visa': 'Visa sponsorship available',
            'remote': 'Yes, I can work remotely',
            'india': 'Yes, India based',
        }
        
        for keyword, value in field_mappings.items():
            if keyword in field_context:
                return value
        
        return None
    
    async def _fill_field(self, elem, field_type: str, value: str):
        """Fill form field with value"""
        if field_type == 'file':
            # For file upload
            resume_path = Path("config/resume.pdf")
            if resume_path.exists():
                await elem.set_input_files(str(resume_path))
                logger.info("Resume uploaded")
        
        elif field_type == 'checkbox':
            # For checkboxes
            if value.lower() in ['yes', 'true', '1']:
                await elem.check()
        
        elif field_type == 'radio':
            # For radio buttons
            await elem.click()
        
        else:
            # Text input or textarea
            await elem.clear()
            
            # Type with human-like speed
            for char in value:
                await elem.type(char, delay=random.uniform(10, 50))
            
            # Occasionally add typo and correct it
            if random.random() < 0.1:  # 10% chance
                await elem.type('x', delay=20)
                await asyncio.sleep(0.5)
                await elem.press('Backspace')
    
    async def _find_submit_button(self) -> Optional:
        """Find submit button on form"""
        
        # Common submit button selectors
        selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Submit")',
            'button:has-text("Apply")',
            'button:has-text("Send")',
            'a[href*="apply"]',
        ]
        
        for selector in selectors:
            try:
                button = await self.page.query_selector(selector)
                if button:
                    return button
            except:
                continue
        
        return None

class ApplicationBatch:
    """Handle batch application processing"""
    
    def __init__(self, headless=True):
        self.automation = FormAutomation(headless=headless)
        self.results = {
            'succeeded': [],
            'failed': [],
            'skipped': []
        }
    
    async def apply_to_batch(self, jobs: List[Dict]) -> Dict:
        """Apply to multiple jobs"""
        try:
            await self.automation.init_browser()
            
            for job in jobs:
                try:
                    success = await self.automation.apply_to_job(job)
                    
                    if success:
                        self.results['succeeded'].append(job)
                        logger.info(f"✅ Applied: {job.get('title')} @ {job.get('company')}")
                    else:
                        self.results['failed'].append(job)
                        logger.warning(f"❌ Failed: {job.get('title')} @ {job.get('company')}")
                    
                    # Delay between applications
                    await asyncio.sleep(random.uniform(5, 15))
                
                except Exception as e:
                    logger.error(f"Error applying to {job.get('title')}: {e}")
                    self.results['failed'].append(job)
        
        finally:
            await self.automation.close()
        
        return self.results

# ==============================================================================
# ASYNC RUNNER FOR SYNC CODE
# ==============================================================================

def apply_to_jobs_sync(jobs: List[Dict], headless=True) -> Dict:
    """Synchronous wrapper for batch applications"""
    batch = ApplicationBatch(headless=headless)
    return asyncio.run(batch.apply_to_batch(jobs))

# ==============================================================================
# TESTING
# ==============================================================================

if __name__ == "__main__":
    # Test script
    logging.basicConfig(level=logging.INFO)
    
    test_job = {
        'title': 'AI Engineer',
        'company': 'TestCorp',
        'apply_url': 'https://example.com/apply',
        'description': 'Looking for AI engineer'
    }
    
    # Uncomment to test
    # result = apply_to_jobs_sync([test_job], headless=False)
    # print(json.dumps(result, indent=2))
