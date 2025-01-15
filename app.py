from dotenv import load_dotenv
import os
import json
from flask import Flask, request, jsonify, render_template
import cohere
import logging
import requests
from scrapy.http import HtmlResponse
from zyte_api import ZyteAPI
import time

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
        response = cohere_client.generate(
            model="command",
            prompt=f"""
                Analyze the webpage at {url} and provide CSS selectors for extracting the following elements:
                - Review container
                - Review title
                - Review body
                - Review rating
                - Reviewer name

                The output should be a JSON-like dictionary. Only return structured JSON format and no other text in output. Example:
                {{
                    "review": ".col-12.col-sm-12.product-review",
                    "title": ".review-title",
                    "body": ".review-body",
                    "rating": ".review-rating",
                    "reviewer": ".reviewer"
                }}
            """,
            max_tokens=300
        )

        # Log full response for debugging
        logger.info(f"Cohere API response: {response}")

        # Validate response structure
        if not response or not hasattr(response, "text") or not response.text:
            raise ValueError("Cohere response does not contain valid text.")

        # Extract and parse the response
        selectors = response.text.strip()
        logger.info(f"Selectors identified by Cohere: {selectors}")

        # Convert the string response into a dictionary
        selectors_dict = json.loads(selectors)

        # Ensure it's a valid dictionary
        if not isinstance(selectors_dict, dict):
            raise ValueError("Selectors response is not a valid dictionary.")

        return selectors_dict
    except Exception as e:
        logger.error(f"Error identifying selectors with Cohere: {e}")
        return None

def extract_reviews_with_zyte(url, selectors):
    try:
        if not isinstance(selectors, dict):
            raise ValueError("Selectors should be a valid dictionary.")

        reviews = []
        page_number = 1
        retry_limit = 5

        for _ in range(retry_limit):
            logger.info(f"Fetching page {page_number} with Zyte: {url}?page={page_number}")
            response = requests.post(
                "https://api.zyte.com/v1/extract",
                auth=(zyte_api_key, ""),
                json={
                    "url": f"{url}?page={page_number}",
                    "httpResponseBody": True,
                    "browserHtml": True,
                    "renderJS": True,
                },
            )

            if response.status_code != 200:
                logger.error(f"Failed to fetch the page with Zyte. Status: {response.status_code}")
                break

            response_json = response.json()
            browser_html = response_json.get("browserHtml")

            if not browser_html:
                logger.warning(f"No browser HTML found on page {page_number}. Retrying...")
                time.sleep(2)
                continue

            with open(f"page_{page_number}_browser_html.html", "w", encoding="utf-8") as fp:
                fp.write(browser_html)

            scrapy_response = HtmlResponse(url=f"{url}?page={page_number}", body=browser_html, encoding='utf-8')
            review_elements = scrapy_response.css(selectors.get('review'))

            if not review_elements:
                logger.info("No more reviews found, stopping pagination.")
                break

            for review in review_elements:
                title = review.css(selectors.get('title')).get(default='').strip()
                body = review.css(selectors.get('body')).get(default='').strip()
                rating = review.css(selectors.get('rating')).get(default='').strip()
                reviewer = review.css(selectors.get('reviewer')).get(default='').strip()

                reviews.append({
                    "title": title,
                    "body": body,
                    "rating": rating,
                    "reviewer": reviewer
                })

            page_number += 1
            time.sleep(2)

        logger.info(f"Extracted {len(reviews)} reviews across {page_number - 1} pages.")
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
    reviews = []
    error_message = None

    if request.method == 'POST':
        url = request.form.get('url')
        if not url:
            error_message = "URL is required!"
            return render_template('index.html', reviews=reviews, error=error_message)

        try:
            selectors = identify_selectors_with_cohere(url)
            if not selectors:
                error_message = "Could not identify selectors for the URL!"
                return render_template('index.html', reviews=reviews, error=error_message)

            logger.info(f"Selectors passed to Zyte: {selectors}")

            reviews = extract_reviews_with_zyte(url, selectors)
            if not reviews:
                error_message = "No reviews found!"
                return render_template('index.html', reviews=reviews, error=error_message)

            reviews = process_reviews_with_cohere(reviews)
            if not reviews:
                error_message = "Error processing reviews with Cohere."
                return render_template('index.html', reviews=reviews, error=error_message)

            return render_template('index.html', reviews=reviews)
        except Exception as e:
            logger.error(f"Error processing: {e}")
            error_message = f"Error: {str(e)}"
            return render_template('index.html', reviews=reviews, error=error_message)

    return render_template('index.html', reviews=reviews)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=True)

