# main.py
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import feedparser
import tweepy
import os
from datetime import datetime
import logging
from dotenv import load_dotenv

# Load the appropriate .env file
if os.path.exists(".env.development") and os.getenv("ENVIRONMENT") != "production":
    load_dotenv(".env.development")
    print("Loaded development environment variables")
else:
    load_dotenv()
    print("Loaded production environment variables")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Market Watch News Bot")

# Load environment variables
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET")
DEV_MODE = os.getenv("DEV_MODE", "True").lower() == "true"
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "1"))  # Default to 1 minute

# Market Watch RSS feeds
RSS_FEEDS = [
    #"https://www.marketwatch.com/rss/topstories",
    #"https://www.marketwatch.com/rss/marketpulse",
    "https://www.marketwatch.com/rss/breakingnews",
]

# Add more feeds if needed
additional_feeds = os.getenv("ADDITIONAL_RSS_FEEDS")
if additional_feeds:
    RSS_FEEDS.extend(additional_feeds.split(","))

# In-memory storage of last seen article to avoid duplicates
last_seen_articles = {feed: None for feed in RSS_FEEDS}
last_check_time = None
last_post_time = None
post_count = 0

def authenticate_twitter():
    """Authenticate with Twitter API"""
    if not all([TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET]):
        logger.warning("Twitter credentials not fully configured")
        return None
        
    client = tweepy.Client(
        bearer_token=TWITTER_BEARER_TOKEN,
        consumer_key=TWITTER_API_KEY,
        consumer_secret=TWITTER_API_SECRET,
        access_token=TWITTER_ACCESS_TOKEN,
        access_token_secret=TWITTER_ACCESS_SECRET
    )
    return client

def post_to_twitter(headline):
    """Post headline to Twitter"""
    global last_post_time, post_count
    
    try:
        if DEV_MODE:
            # In dev mode, just log what would be posted
            logger.info(f"DEV MODE - Would post to Twitter: {headline}")
            last_post_time = datetime.now()
            post_count += 1
            return {"dev_mode": True, "would_post": headline}
        else:
            # In production mode, actually post
            client = authenticate_twitter()
            if not client:
                logger.error("Cannot post: Twitter client not initialized")
                return None
                
            response = client.create_tweet(text=headline)
            logger.info(f"Posted to Twitter: {headline}")
            last_post_time = datetime.now()
            post_count += 1
            return response
    except Exception as e:
        logger.error(f"Error posting to Twitter: {e}")
        return None

def check_rss_feeds():
    """Check RSS feeds and post new headlines to Twitter"""
    global last_check_time
    last_check_time = datetime.now()
    logger.info(f"Checking RSS feeds (DEV_MODE={DEV_MODE})")
    
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            
            if not feed.entries:
                logger.warning(f"No entries found in feed: {feed_url}")
                continue
                
            # Get the most recent article
            latest_article = feed.entries[0]
            latest_title = latest_article.title
            article_url = latest_article.link  # Get the article URL
            
            # Format headline based on feed type
            if "breakingnews" in feed_url:
                prefix = "Breaking: "
            else:
                prefix = ""
                
            # Combine headline, prefix and URL
            formatted_tweet = f"{prefix}{latest_title}\n\n{article_url}"
            
            # Check if we've seen this article before
            if last_seen_articles[feed_url] != latest_title:
                logger.info(f"New article found: {latest_title}")
                post_to_twitter(formatted_tweet)
                last_seen_articles[feed_url] = latest_title
            else:
                logger.info(f"No new articles in {feed_url}")
                
        except Exception as e:
            logger.error(f"Error processing feed {feed_url}: {e}")

# Set up the scheduler
scheduler = BackgroundScheduler()

@app.on_event("startup")
def start_scheduler():
    """Start the background scheduler when the app starts"""
    trigger = IntervalTrigger(minutes=CHECK_INTERVAL)
    scheduler.add_job(check_rss_feeds, trigger)
    scheduler.start()
    logger.info(f"Scheduler started with {CHECK_INTERVAL}-minute interval")

@app.on_event("shutdown")
def shutdown_scheduler():
    """Shut down the scheduler when the app stops"""
    scheduler.shutdown()
    logger.info("Scheduler shut down")

@app.get("/")
def read_root():
    """Root endpoint that confirms the service is running"""
    return {
        "status": "running", 
        "dev_mode": DEV_MODE,
        "check_interval": f"{CHECK_INTERVAL} minutes",
        "last_check": last_check_time.isoformat() if last_check_time else None,
        "last_post": last_post_time.isoformat() if last_post_time else None,
        "post_count": post_count,
        "feeds_monitored": len(RSS_FEEDS)
    }

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

@app.post("/check-now")
def manual_check():
    """Manually trigger an RSS check"""
    check_rss_feeds()
    return {
        "status": "completed", 
        "timestamp": datetime.now().isoformat(),
        "last_check": last_check_time.isoformat() if last_check_time else None,
        "post_count": post_count
    }

@app.get("/test-auth")
def test_auth():
    """Test Twitter authentication without posting"""
    client = authenticate_twitter()
    return {
        "authenticated": client is not None,
        "dev_mode": DEV_MODE,
        "credentials_configured": {
            "api_key": bool(TWITTER_API_KEY),
            "api_secret": bool(TWITTER_API_SECRET),
            "bearer_token": bool(TWITTER_BEARER_TOKEN),
            "access_token": bool(TWITTER_ACCESS_TOKEN),
            "access_secret": bool(TWITTER_ACCESS_SECRET)
        }
    }

@app.post("/test-post")
def test_post(message: str = "TEST - This is a test headline from Market Watch RSS Bot"):
    """Test endpoint that posts a test message to Twitter"""
    result = post_to_twitter(message)
    return {
        "status": "test_completed",
        "dev_mode": DEV_MODE,
        "result": result,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Simple dashboard for testing"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Market Watch RSS Bot - Test Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
            .container { max-width: 800px; margin: 0 auto; }
            .card { background: #f9f9f9; border-radius: 5px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            button { background: #4CAF50; color: white; border: none; padding: 10px 15px; cursor: pointer; border-radius: 4px; margin-right: 10px; }
            button:hover { background: #45a049; }
            .dev-mode { color: #ff6600; font-weight: bold; }
            .response { background: #f0f0f0; padding: 10px; margin-top: 10px; border-radius: 4px; overflow-x: auto; }
            h1, h2 { color: #333; }
            .stats { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 15px; }
            .stat-box { background: #e9e9e9; padding: 10px; border-radius: 4px; flex: 1; min-width: 120px; text-align: center; }
            .stat-value { font-size: 24px; font-weight: bold; margin: 5px 0; }
            .stat-label { font-size: 14px; color: #666; }
            input[type="text"] { padding: 8px; width: 100%; margin-bottom: 10px; box-sizing: border-box; border: 1px solid #ddd; border-radius: 4px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Market Watch RSS Bot - Test Dashboard</h1>
            
            <div class="card">
                <h2>Status</h2>
                <div class="stats" id="stats">Loading...</div>
            </div>
            
            <div class="card">
                <h2>RSS Feed Check</h2>
                <button onclick="checkNow()">Check RSS Feeds Now</button>
                <div id="checkResponse" class="response"></div>
            </div>
            
            <div class="card">
                <h2>Twitter Tests</h2>
                <button onclick="testAuth()">Test Twitter Auth</button>
                <button onclick="testPost()">Test Post with Default Message</button>
                <div style="margin-top: 15px;">
                    <input type="text" id="customMessage" placeholder="Enter a custom test message" />
                    <button onclick="testCustomPost()">Post Custom Message</button>
                </div>
                <div id="testResponse" class="response"></div>
            </div>
            
            <div class="card">
                <h2>Feeds Monitored</h2>
                <div id="feedsList">Loading...</div>
            </div>
        </div>
        
        <script>
            // Fetch status on page load
            document.addEventListener('DOMContentLoaded', function() {
                fetchStatus();
                setInterval(fetchStatus, 30000); // Refresh every 30 seconds
            });
            
            // Fetch the current status
            async function fetchStatus() {
                try {
                    const response = await fetch('/');
                    const data = await response.json();
                    
                    // Format timestamps
                    const lastCheck = data.last_check ? new Date(data.last_check).toLocaleString() : 'Never';
                    const lastPost = data.last_post ? new Date(data.last_post).toLocaleString() : 'Never';
                    
                    // Build stats section
                    let statsHtml = `
                        <div class="stat-box">
                            <div class="stat-value">${data.dev_mode ? 'DEV' : 'PROD'}</div>
                            <div class="stat-label">Mode</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-value">${data.check_interval}</div>
                            <div class="stat-label">Check Interval</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-value">${data.post_count}</div>
                            <div class="stat-label">Posts</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-value">${data.feeds_monitored}</div>
                            <div class="stat-label">Feeds</div>
                        </div>
                    `;
                    
                    // Additional info
                    statsHtml += `
                        <div style="width: 100%; margin-top: 10px;">
                            <p><strong>Last Check:</strong> ${lastCheck}</p>
                            <p><strong>Last Post:</strong> ${lastPost}</p>
                        </div>
                    `;
                    
                    document.getElementById('stats').innerHTML = statsHtml;
                    
                    // Build feeds list
                    let feedsListHtml = '<ul>';
                    for (let i = 0; i < data.feeds_monitored; i++) {
                        feedsListHtml += `<li>Loading feed ${i+1}...</li>`;
                    }
                    feedsListHtml += '</ul>';
                    
                    document.getElementById('feedsList').innerHTML = feedsListHtml;
                    
                    // Fetch feeds list
                    fetchFeeds();
                    
                } catch (error) {
                    console.error('Error fetching status:', error);
                    document.getElementById('stats').innerHTML = '<p>Error loading status</p>';
                }
            }
            
            // Fetch feeds list
            async function fetchFeeds() {
                try {
                    const response = await fetch('/feeds');
                    const data = await response.json();
                    
                    let feedsListHtml = '<ul>';
                    data.feeds.forEach((feed, index) => {
                        const headline = data.last_seen_headlines[feed] || 'No headlines yet';
                        feedsListHtml += `<li><strong>Feed ${index+1}:</strong> ${feed}<br>
                                         <small>Last headline: ${headline}</small></li>`;
                    });
                    feedsListHtml += '</ul>';
                    
                    document.getElementById('feedsList').innerHTML = feedsListHtml;
                } catch (error) {
                    console.error('Error fetching feeds:', error);
                }
            }
            
            // Manually trigger an RSS check
            async function checkNow() {
                try {
                    const response = await fetch('/check-now', { method: 'POST' });
                    const data = await response.json();
                    document.getElementById('checkResponse').innerHTML = JSON.stringify(data, null, 2);
                    fetchStatus();
                } catch (error) {
                    console.error('Error checking feeds:', error);
                    document.getElementById('checkResponse').innerHTML = 'Error: ' + error.message;
                }
            }
            
            // Test Twitter authentication
            async function testAuth() {
                try {
                    const response = await fetch('/test-auth');
                    const data = await response.json();
                    document.getElementById('testResponse').innerHTML = JSON.stringify(data, null, 2);
                } catch (error) {
                    console.error('Error testing auth:', error);
                    document.getElementById('testResponse').innerHTML = 'Error: ' + error.message;
                }
            }
            
            // Test Twitter posting with default message
            async function testPost() {
                try {
                    const testMessage = "TEST - This is a test headline from Market Watch RSS Bot at " + new Date().toLocaleString();
                    const response = await fetch('/test-post?message=' + encodeURIComponent(testMessage), { method: 'POST' });
                    const data = await response.json();
                    document.getElementById('testResponse').innerHTML = JSON.stringify(data, null, 2);
                    fetchStatus();
                } catch (error) {
                    console.error('Error testing post:', error);
                    document.getElementById('testResponse').innerHTML = 'Error: ' + error.message;
                }
            }
            
            // Test Twitter posting with custom message
            async function testCustomPost() {
                try {
                    const customMessage = document.getElementById('customMessage').value;
                    if (!customMessage) {
                        alert('Please enter a custom message');
                        return;
                    }
                    
                    const response = await fetch('/test-post?message=' + encodeURIComponent(customMessage), { method: 'POST' });
                    const data = await response.json();
                    document.getElementById('testResponse').innerHTML = JSON.stringify(data, null, 2);
                    fetchStatus();
                } catch (error) {
                    console.error('Error posting custom message:', error);
                    document.getElementById('testResponse').innerHTML = 'Error: ' + error.message;
                }
            }
        </script>
    </body>
    </html>
    """

@app.get("/feeds")
def list_feeds():
    """List all RSS feeds being monitored"""
    return {
        "feeds": RSS_FEEDS,
        "count": len(RSS_FEEDS),
        "last_seen_headlines": last_seen_articles
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))