from dotenv import load_dotenv
import os
from flask import Flask, request, jsonify, render_template
from playwright.sync_api import sync_playwright
from jina import Client
import subprocess
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
api_key = os.getenv("JINA_API_KEY")
if not api_key:
    raise EnvironmentError("JINA_API_KEY environment variable is not set.")

def install_playwright_browsers():
    try:
        logger.info("Installing Playwright browsers...")
        subprocess.run(["playwright", "install"], check=True)
        logger.info("Playwright browsers installed successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error installing Playwright browsers: {e}")
        raise RuntimeError("Playwright browser installation failed.")

try:
    install_playwright_browsers()
except RuntimeError as e:
    logger.error(f"Setup failed: {e}")

app = Flask(__name__)

# Jina client configuration
os.environ["JINA_AUTH_TOKEN"] = api_key  # Set the API key as an environment variable
client = Client(host="https://test-d2se.onrender.com")  # Do not pass `api_key` directly


def extract_reviews_with_playwright(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        reviews = []
        try:
            logger.info(f"Navigating to URL: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_load_state('networkidle')

            # Wait for reviews to load
            page.wait_for_selector('div.review', timeout=60000)

            # Extract reviews from the page
            review_elements = page.query_selector_all('div.review')
            for review in review_elements:
                title = review.query_selector('.review-title').text_content().strip() if review.query_selector('.review-title') else "No title"
                body = review.query_selector('.review-body').text_content().strip() if review.query_selector('.review-body') else "No body"
                rating = review.query_selector('.review-rating').text_content().strip() if review.query_selector('.review-rating') else "No rating"
                reviewer = review.query_selector('.reviewer-name').text_content().strip() if review.query_selector('.reviewer-name') else "Anonymous"

                reviews.append({
                    "title": title,
                    "body": body,
                    "rating": rating,
                    "reviewer": reviewer
                })
        except Exception as e:
            logger.error(f"Error while fetching reviews: {e}")
        finally:
            browser.close()

        return reviews

def process_reviews_with_jina(reviews):
    try:
        review_texts = [f"{rev['title']} {rev['body']}" for rev in reviews]
        result = client.post('/reviews', inputs=review_texts)
        logger.info("Reviews processed successfully with Jina.")
        return result
    except Exception as e:
        logger.error(f"Error while processing reviews with Jina: {e}")
        return []

@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        url = request.form.get('url')
        if not url:
            return render_template('index.html', error="URL is required!")

        try:
            # Extract reviews using Playwright
            reviews = extract_reviews_with_playwright(url)

            # Process reviews with Jina AI
            result = process_reviews_with_jina(reviews)

            return render_template('index.html', reviews=result)
        except Exception as e:
            return render_template('index.html', error=f"Error: {str(e)}")

    return render_template('index.html')

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
