"""
Web scraper for OpenML dataset statistics.

This module provides Selenium-based web scraping for OpenML dataset stats
that are not available via the API (likes, downloads, issues, status).
"""

from __future__ import annotations

import re
import time
import random
import logging
from typing import Dict, Optional
from threading import Lock

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException


logger = logging.getLogger(__name__)


class BrowserPool:
    """Thread-safe browser pool for reusing browser instances"""

    def __init__(self, max_browsers: int = 4, timeout: int = 30):
        self.max_browsers = max_browsers
        self.timeout = timeout
        self.available_browsers = []
        self.in_use_browsers = set()
        self.lock = Lock()
        self.browser_creation_lock = Lock()

    def _create_browser(self):
        """Create a new browser instance with optimized settings"""
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins")
        chrome_options.add_argument("--disable-images")
        chrome_options.add_argument("--disable-javascript")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--allow-running-insecure-content")
        chrome_options.add_argument("--disable-features=VizDisplayCompositor")
        chrome_options.add_argument("--memory-pressure-off")
        chrome_options.add_argument("--max_old_space_size=4096")

        # Randomize user agent
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]
        chrome_options.add_argument(f"--user-agent={random.choice(user_agents)}")

        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(self.timeout)
            driver.implicitly_wait(10)
            return driver
        except Exception as e:
            raise WebDriverException(f"Failed to create browser: {str(e)}")

    def get_browser(self):
        """Get an available browser from the pool"""
        with self.lock:
            if self.available_browsers:
                browser = self.available_browsers.pop()
                self.in_use_browsers.add(browser)
                return browser

            if len(self.in_use_browsers) < self.max_browsers:
                with self.browser_creation_lock:
                    try:
                        browser = self._create_browser()
                        self.in_use_browsers.add(browser)
                        return browser
                    except Exception:
                        return None

            return None

    def return_browser(self, browser):
        """Return a browser to the pool"""
        with self.lock:
            if browser in self.in_use_browsers:
                self.in_use_browsers.remove(browser)
                try:
                    # Clear cookies and cache
                    browser.delete_all_cookies()
                    browser.execute_script("window.localStorage.clear();")
                    browser.execute_script("window.sessionStorage.clear();")
                    self.available_browsers.append(browser)
                except Exception:
                    # If cleanup fails, quit the browser
                    try:
                        browser.quit()
                    except:
                        pass

    def close_all(self):
        """Close all browsers in the pool"""
        with self.lock:
            all_browsers = list(self.available_browsers) + list(self.in_use_browsers)
            for browser in all_browsers:
                try:
                    browser.quit()
                except:
                    pass
            self.available_browsers.clear()
            self.in_use_browsers.clear()


class OpenMLWebScraper:
    """
    Web scraper for OpenML dataset statistics not available via API.

    Scrapes status, downloads, likes, and issues counts from OpenML web interface.
    Uses a browser pool for efficient parallel scraping.
    """

    def __init__(self, max_browsers: int = 4, max_retries: int = 3):
        """
        Initialize the web scraper.

        Args:
            max_browsers: Maximum number of concurrent browser instances
            max_retries: Maximum number of retry attempts per dataset
        """
        self.browser_pool = BrowserPool(max_browsers=max_browsers)
        self.max_retries = max_retries
        self.request_delays = [1, 2, 3, 5, 8]  # Exponential backoff delays
        self.scraping_enabled = True

    def scrape_dataset_stats(self, dataset_id: int) -> Dict:
        """
        Scrape statistics for a single dataset with retry logic.

        Args:
            dataset_id: The OpenML dataset ID

        Returns:
            Dict with keys: status, downloads, likes, issues
        """
        if not self.scraping_enabled:
            return {"status": "N/A", "downloads": 0, "likes": 0, "issues": 0}

        for attempt in range(self.max_retries + 1):
            try:
                return self._scrape_dataset_stats_once(dataset_id)
            except Exception as e:
                logger.warning(
                    f"Attempt {attempt + 1} failed for dataset {dataset_id}: {str(e)}"
                )
                if attempt < self.max_retries:
                    # Exponential backoff with jitter
                    delay = self.request_delays[
                        min(attempt, len(self.request_delays) - 1)
                    ]
                    jitter = random.uniform(0.5, 1.5)
                    time.sleep(delay * jitter)
                else:
                    logger.error(
                        f"All {self.max_retries + 1} attempts failed for dataset {dataset_id}"
                    )
                    # Disable scraping if too many connection failures
                    if "ERR_CONNECTION_CLOSED" in str(e):
                        self.scraping_enabled = False
                        logger.error("Disabling scraping due to connection issues")

        return {"status": "N/A", "downloads": 0, "likes": 0, "issues": 0}

    def _scrape_dataset_stats_once(self, dataset_id: int) -> Dict:
        """
        Single attempt to scrape dataset statistics.

        Args:
            dataset_id: The OpenML dataset ID

        Returns:
            Dict with keys: status, downloads, likes, issues
        """
        browser = self.browser_pool.get_browser()
        if not browser:
            raise Exception("No browser available from pool")

        try:
            url = f"https://www.openml.org/search?type=data&id={dataset_id}"
            logger.info(f"Scraping dataset ID {dataset_id}: {url}")

            # Add random delay to avoid rate limiting
            time.sleep(random.uniform(1, 3))

            browser.get(url)
            wait = WebDriverWait(browser, 15)

            # Wait for page to load
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

            stats = {}

            # Robust selectors with multiple fallbacks
            selector_mappings = {
                "status": [
                    'span[aria-label="status"]',
                    'span[title="status"]',
                    ".status-indicator",
                    '[data-testid="status"]',
                ],
                "downloads": [
                    'span[aria-label="downloads"]',
                    'span[title="downloads"]',
                    ".download-count",
                    '[data-testid="downloads"]',
                ],
                "likes": [
                    'span[aria-label="likes"]',
                    'span[title="likes"]',
                    ".like-count",
                    '[data-testid="likes"]',
                ],
                "issues": [
                    'span[aria-label="issues"]',
                    'span[title="issues"]',
                    ".issue-count",
                    '[data-testid="issues"]',
                ],
            }

            for stat in ["status", "downloads", "likes", "issues"]:
                stats[stat] = "N/A"

                for selector in selector_mappings[stat]:
                    try:
                        element = wait.until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                        if element and element.text.strip():
                            stats[stat] = element.text.strip()
                            logger.debug(
                                f"Extracted {stat} using selector '{selector}': {stats[stat]}"
                            )
                            break
                    except TimeoutException:
                        continue
                    except Exception as e:
                        logger.debug(
                            f"Error with selector '{selector}' for {stat}: {str(e)}"
                        )
                        continue

                if stats[stat] == "N/A":
                    logger.warning(f"Could not extract '{stat}' for dataset {dataset_id}")

            # Extract numbers from text
            stats["downloads"] = self._extract_number(stats["downloads"])
            stats["likes"] = self._extract_number(stats["likes"])
            stats["issues"] = self._extract_number(stats["issues"])

            logger.info(f"Completed scraping for dataset {dataset_id}: {stats}")
            return stats

        except Exception as e:
            logger.error(f"Error scraping dataset {dataset_id}: {str(e)}")
            raise

        finally:
            if browser:
                self.browser_pool.return_browser(browser)

    def _extract_number(self, stat_string: str) -> int:
        """
        Extract numeric value from stat string (handles K, M, B suffixes).

        Args:
            stat_string: String like "1.5K", "2M", "500", or "N/A"

        Returns:
            Integer value
        """
        if stat_string == "N/A":
            return 0

        # Handle various number formats (1K, 1M, 1.5K, etc.)
        number_match = re.search(r"(\d+(?:\.\d+)?)\s*([KMB]?)", stat_string.upper())
        if number_match:
            num = float(number_match.group(1))
            multiplier = number_match.group(2)
            if multiplier == "K":
                return int(num * 1000)
            elif multiplier == "M":
                return int(num * 1000000)
            elif multiplier == "B":
                return int(num * 1000000000)
            else:
                return int(num)
        return 0

    def close(self):
        """Clean up browser pool"""
        self.browser_pool.close_all()

    def __del__(self):
        """Cleanup on object destruction"""
        if hasattr(self, "browser_pool") and self.browser_pool:
            self.browser_pool.close_all()


