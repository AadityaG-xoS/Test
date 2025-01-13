from dotenv import load_dotenv
import os
import json
from flask import Flask, request, jsonify, render_template
import cohere
import logging
import requests
from scrapy.http import HtmlResponse

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

# Initialize Cohere Client
cohere_client = cohere.Client(cohere_api_key)

# Define ZyteAPI class
class ZyteAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.zyte.com/v1"

    def get(self, url):
        headers = {"Authorization": f"Apikey {self.api_key}"}
        payload = {"url": url}
        response = requests.post(f"{self.base_url}/extract", json=payload, headers=headers)
        response.raise_for_status()
        return response

# Initialize Zyte Client
zyte_client = ZyteAPI(zyte_api_key)

app = Flask(__name__)

def identify_selectors_with_cohere(url):
    try:
        logger.info(f"Sending URL to Cohere for selector identification: {url}")

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

        response = cohere_client.generate(
            model='command-xlarge',
            prompt=prompt,
            max_tokens=150,
            temperature=0.5
        )

        if response.generations and response.generations[0].text:
            selectors = json.loads(response.generations[0].text.strip())
            logger.info(f"Selectors identified by Cohere: {selectors}")
            return selectors
        else:
            logger.error("Cohere did not return any selectors.")
            return None
    except Exception as e:
        logger.error(f"Error while identifying selectors with Cohere: {e}")
        return None

def extract_reviews_with_zyte(url, selectors):
    try:
        logger.info(f"Sending request to Zyte for URL: {url}")
        response = zyte_client.get(url)
        reviews = []

        if response.status_code != 200:
            logger.error(f"Failed to fetch the page with Zyte. Status: {response.status_code}")
            return reviews

        scrapy_response = HtmlResponse(url=url, body=response.content, encoding='utf-8')

        review_elements = scrapy_response.css(selectors.get('review', 'div.review'))
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
        logger.error(f"Error while scraping with Zyte: {e}")
        return []

def process_reviews_with_cohere(reviews):
    try:
        review_texts = [f"{rev['title']} {rev['body']}" for rev in reviews]
        logger.info("Sending reviews to Cohere for processing.")

        response = cohere_client.generate(
            model='command-xlarge',
            prompt="Process these reviews and provide a sentiment analysis summary:\n" + "\n".join(review_texts),
            max_tokens=200,
            temperature=0.5
        )

        if response.generations and response.generations[0].text:
            processed_reviews = response.generations[0].text.strip()
            logger.info("Reviews processed successfully with Cohere.")
            return processed_reviews
        else:
            logger.error("Cohere did not return a valid response.")
            return "Error processing reviews."
    except Exception as e:
        logger.error(f"Error while processing reviews with Cohere: {e}")
        return "Error processing reviews."

@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        url = request.form.get('url')
        if not url:
            return render_template('index.html', error="URL is required!")

        try:
            selectors = identify_selectors_with_cohere(url)
            if not selectors:
                return render_template('index.html', error="Could not identify selectors for the URL!")

            reviews = extract_reviews_with_zyte(url, selectors)
            if not reviews:
                return render_template('index.html', error="No reviews found!")

            processed_reviews = process_reviews_with_cohere(reviews)
            if not processed_reviews:
                return render_template('index.html', error="Error processing reviews with Cohere.")

            return render_template('index.html', reviews=processed_reviews)
        except Exception as e:
            logger.error(f"Error in processing: {e}")
            return render_template('index.html', error=f"Error: {str(e)}")

    return render_template('index.html')

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
