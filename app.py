from dotenv import load_dotenv
import os
from flask import Flask, request, jsonify, render_template
from playwright.sync_api import sync_playwright
from jina import Flow, DocumentArray, Client
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

# Define Jina Flow with actual executor URLs
flow = Flow(protocol="http", port=12345).add(
    name="SelectorIdentifier",
    uses="jinahub://ExecutorToIdentifySelectors"  # Replace with your actual executor from Jina Hub
).add(
    name="ReviewProcessor",
    uses="jinahub://ExecutorToProcessReviews"  # Replace with your actual executor from Jina Hub
)

# Start the Flow
with flow:
    flow.block()  # This keeps the Flow running

# Jina client configuration
os.environ["JINA_AUTH_TOKEN"] = api_key  # Set the API key as an environment variable
client = Client(host="http://0.0.0.0:12345")  # Jina Flow runs locally on the specified port

def identify_selectors_with_jina(url):
    try:
        logger.info(f"Sending URL to Jina for selector identification: {url}")
        
        # Create a prompt to instruct Jina to detect the selectors
        prompt = f"""
        Analyze the page at {url} and identify CSS selectors for the following:
        - Review container
        - Review title
        - Review body
        - Review rating
        - Reviewer name
        Return the selectors in the form of a dictionary, for example:
        {{
            "review": "div.review",
            "title": ".review-title",
            "body": ".review-body",
            "rating": ".review-rating",
            "reviewer": ".reviewer-name"
        }}
        """

        result = client.post("/SelectorIdentifier", inputs=DocumentArray([prompt]))
        if not result or not result[0]:
            logger.error("No selectors identified by Jina.")
            return None
        selectors = result[0].tags  # Assuming Jina adds selectors to the tags field
        logger.info(f"Selectors identified by Jina: {selectors}")
        return selectors
    except Exception as e:
        logger.error(f"Error while identifying selectors with Jina: {e}")
        return None

def extract_reviews_with_playwright(url, selectors):
    if not selectors:
        logger.error("Selectors are empty or invalid.")
        return []

    reviews = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            logger.info(f"Navigating to URL: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_load_state('networkidle')

            # Validate and use the review selector
            review_selector = selectors.get('review', 'div.review')
            if not page.query_selector(review_selector):
                logger.warning(f"No elements found for the selector: {review_selector}")
                return []

            # Extract review details
            review_elements = page.query_selector_all(review_selector)
            for review in review_elements:
                title = review.query_selector(selectors.get('title', '.review-title'))
                body = review.query_selector(selectors.get('body', '.review-body'))
                rating = review.query_selector(selectors.get('rating', '.review-rating'))
                reviewer = review.query_selector(selectors.get('reviewer', '.reviewer-name'))

                reviews.append({
                    "title": title.text_content().strip() if title else "No title",
                    "body": body.text_content().strip() if body else "No body",
                    "rating": rating.text_content().strip() if rating else "No rating",
                    "reviewer": reviewer.text_content().strip() if reviewer else "Anonymous"
                })

            logger.info(f"Extracted {len(reviews)} reviews.")
        except Exception as e:
            logger.error(f"Error while extracting reviews: {e}")
        finally:
            browser.close()

    return reviews

def process_reviews_with_jina(reviews):
    try:
        review_texts = [f"{rev['title']} {rev['body']}" for rev in reviews]
        logger.info("Sending reviews to Jina for processing.")
        result = client.post("/ReviewProcessor", inputs=DocumentArray(review_texts))
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
            # Identify selectors using Jina
            selectors = identify_selectors_with_jina(url)
            if not selectors:
                return render_template('index.html', error="Could not identify selectors for the URL!")

            # Extract reviews using Playwright with dynamic selectors
            reviews = extract_reviews_with_playwright(url, selectors)
            if not reviews:
                return render_template('index.html', error="No reviews found!")

            # Process reviews with Jina AI
            processed_reviews = process_reviews_with_jina(reviews)
            if not processed_reviews:
                return render_template('index.html', error="Error processing reviews with Jina.")

            return render_template('index.html', reviews=processed_reviews)
        except Exception as e:
            logger.error(f"Error in processing: {e}")
            return render_template('index.html', error=f"Error: {str(e)}")

    return render_template('index.html')

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
