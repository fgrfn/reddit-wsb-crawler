"""Rate limiting utilities for API calls.

Implements simple rate limiting to avoid hitting API limits:
- Reddit: 60 requests/minute
- Yahoo Finance: ~2000 requests/hour (unofficial)
- NewsAPI: 100 requests/day (free tier)
"""
import time
import threading
from collections import defaultdict
from datetime import datetime, timedelta

class RateLimiter:
    """Thread-safe rate limiter."""
    
    def __init__(self, max_calls: int, period: float):
        """Initialize rate limiter.
        
        Args:
            max_calls: Maximum number of calls allowed
            period: Time period in seconds
        """
        self.max_calls = max_calls
        self.period = period
        self.calls = []
        self.lock = threading.Lock()
    
    def __call__(self, func):
        """Decorator for rate limiting."""
        def wrapper(*args, **kwargs):
            self.wait_if_needed()
            return func(*args, **kwargs)
        return wrapper
    
    def wait_if_needed(self):
        """Wait if rate limit would be exceeded."""
        with self.lock:
            now = time.time()
            
            # Remove old calls
            self.calls = [call_time for call_time in self.calls 
                         if now - call_time < self.period]
            
            # Check if we need to wait
            if len(self.calls) >= self.max_calls:
                sleep_time = self.period - (now - self.calls[0])
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    # Refresh after sleep
                    now = time.time()
                    self.calls = [call_time for call_time in self.calls 
                                 if now - call_time < self.period]
            
            # Record this call
            self.calls.append(now)

class APIRateLimits:
    """Centralized rate limiters for different APIs."""
    
    # Reddit: 60 requests/minute (conservative: 50)
    reddit = RateLimiter(max_calls=50, period=60)
    
    # Yahoo Finance: ~2000/hour (conservative: 1500/hour = 25/min)
    yahoo = RateLimiter(max_calls=25, period=60)
    
    # NewsAPI: 100/day free tier (conservative: 90/day = ~1/960s)
    newsapi = RateLimiter(max_calls=1, period=960)
    
    @staticmethod
    def reddit_call(func):
        """Decorator for Reddit API calls."""
        return APIRateLimits.reddit(func)
    
    @staticmethod
    def yahoo_call(func):
        """Decorator for Yahoo Finance calls."""
        return APIRateLimits.yahoo(func)
    
    @staticmethod
    def newsapi_call(func):
        """Decorator for NewsAPI calls."""
        return APIRateLimits.newsapi(func)

# Convenience decorators
rate_limit_reddit = APIRateLimits.reddit_call
rate_limit_yahoo = APIRateLimits.yahoo_call
rate_limit_newsapi = APIRateLimits.newsapi_call

# Example usage:
# @rate_limit_yahoo
# def get_stock_price(ticker):
#     return yf.Ticker(ticker).info
