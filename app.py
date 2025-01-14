from dotenv import load_dotenv
import os
import json
from flask import Flask, request, jsonify, render_template
import cohere
import logging
import requests
from scrapy.http import HtmlResponse
from zyte_api import ZyteAPI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
cohere_api_key = os.getenv("COHERE_API_KEY")
zyte_api_key = os.getenv("ZYTE_API_KEY")

if not cohere_api_key:
    raise EnvironmentError("COHERE_API_KEY environment variable is not set.")
if not zyte_api_key:
    raise EnvironmentError("ZYTE_API_KEY environment variable is not set.")

# Initialize Cohere client
cohere_client = cohere.Client(cohere_api_key)

# Initialize Zyte client
zyte_client = ZyteAPI(api_key=zyte_api_key)

app = Flask(__name__)

def identify_selectors_with_cohere(url):
    try:
        logger.info(f"Sending URL to Cohere for selector identification: {url}")
        
        response = cohere_client.chat(
            model="command-r-plus",
            message=f"""
            Analyze the webpage at {url} and provide CSS selectors for extracting the following elements:
            - Review container
            - Review title
            - Review body
            - Review rating
            - Reviewer name

            The output should be a JSON-like dictionary. Example:
            {{
                "review": "review",
                "title": ".review-title",
                "body": ".review-body",
                "rating": ".review-rating",
                "reviewer": ".reviewer-name"
            }}
            """,
            preamble="You are an AI-assistant chatbot. You are trained to assist users by providing thorough and helpful responses to their queries.",
        )

        # Extract the response text and evaluate it
        selectors = response.text.strip()
        logger.info(f"Selectors identified by Cohere: {selectors}")

        # Convert the string response into a dictionary (handle the case of single quotes)
        selectors_dict = json.loads(selectors.replace("'", '"'))  # Convert single quotes to double quotes for valid JSON
        logger.info(f"Selectors as a dictionary: {selectors_dict}")

        # Check if it's a valid dictionary
        if not isinstance(selectors_dict, dict):
            raise ValueError("Selectors response is not a valid dictionary.")

        return selectors_dict
    except Exception as e:
        logger.error(f"Error identifying selectors with Cohere: {e}")
        return None

def extract_reviews_with_zyte(url, selectors):
    try:
        # Ensure selectors are a dictionary
        if not isinstance(selectors, dict):
            raise ValueError("Selectors should be a valid dictionary.")

        logger.info(f"Fetching URL with Zyte: {url}")
        # Use Zyte API to fetch browser-rendered HTML
        response = requests.post(
            "https://api.zyte.com/v1/extract",
            auth=(zyte_api_key, ""),  # Use your Zyte API key
            json={
                "url": url,
                "browserHtml": True,
            },
        )
        if response.status_code != 200:
            logger.error(f"Failed to fetch the page with Zyte. Status: {response.status_code}")
            return []

        # Save the browser-rendered HTML for debugging
        browser_html = response.json().get("browserHtml", "")
        with open("browser_html.html", "w", encoding="utf-8") as fp:
            fp.write(browser_html)
        logger.info("Saved browser-rendered HTML to browser_html.html for debugging.")

        # Use Scrapy's HtmlResponse for extraction
        scrapy_response = HtmlResponse(url=url, body=browser_html, encoding='utf-8')

        reviews = []
        review_elements = scrapy_response.css(selectors.get('review', 'div.review'))
        logger.debug(f"Review elements found: {review_elements}")

        for review in review_elements:
            title = review.css(selectors.get('title', '.review-title::text')).get(default="No title").strip()
            body = review.css(selectors.get('body', '.review-body::text')).get(default="No body").strip()
            rating = review.css(selectors.get('rating', '.review-rating::text')).get(default="No rating").strip()
            reviewer = review.css(selectors.get('reviewer', '.reviewer-name::text')).get(default="Anonymous").strip()

            reviews.append({
                "title": title,
                "body": body,
                "rating": rating,
                "reviewer": reviewer
            })

        logger.info(f"Extracted {len(reviews)} reviews.")
        return reviews
    except Exception as e:
        logger.error(f"Error extracting reviews with Zyte: {e}")
        return []

def process_reviews_with_cohere(reviews):
    try:
        if not reviews:
            raise ValueError("No reviews to process.")
        
        processed_reviews = []
        for review in reviews:
            # Example processing: Add a prefix to each review title (customize as per your need)
            processed_review = {
                "title": f"Processed: {review['title']}",
                "body": review['body'],
                "rating": review['rating'],
                "reviewer": review['reviewer']
            }
            processed_reviews.append(processed_review)
        
        logger.info(f"Processed {len(processed_reviews)} reviews.")
        return processed_reviews
    except Exception as e:
        logger.error(f"Error processing reviews with Cohere: {e}")
        return []

@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        url = request.form.get('url')
        if not url:
            return render_template('index.html', error="URL is required!")

        try:
            # Identify selectors using Cohere
            selectors = identify_selectors_with_cohere(url)
            if not selectors:
                return render_template('index.html', error="Could not identify selectors for the URL!")

            logger.info(f"Selectors passed to Zyte: {selectors}")

            # Extract reviews using Zyte
            reviews = extract_reviews_with_zyte(url, selectors)
            if not reviews:
                return render_template('index.html', error="No reviews found!")

            # Process reviews with Cohere AI
            processed_reviews = process_reviews_with_cohere(reviews)
            if not processed_reviews:
                return render_template('index.html', error="Error processing reviews with Cohere.")

            return render_template('index.html', reviews=processed_reviews)
        except Exception as e:
            logger.error(f"Error processing: {e}")
            return render_template('index.html', error=f"Error: {str(e)}")
    
    # Render the home page on GET request
    return render_template('index.html', reviews=None)

if __name__ == '__main__':
     app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=True)
