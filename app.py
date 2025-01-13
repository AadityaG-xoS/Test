from dotenv import load_dotenv
import os
from flask import Flask, request, jsonify, render_template
import cohere
import logging
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

# Initialize Cohere and Zyte Clients
cohere_client = cohere.Client(cohere_api_key)
zyte_client = ZyteAPI(zyte_api_key)

app = Flask(__name__)

def identify_selectors_with_cohere(url):
    try:
        logger.info(f"Sending URL to Cohere for selector identification: {url}")

        prompt = f"""
        You are an expert in HTML and CSS. Analyze the webpage at the URL: {url} and identify CSS selectors for the following elements:
        - Review container
        - Review title
        - Review body
        - Review rating
        - Reviewer name
        Return the CSS selectors as a JSON object in the format below:
        {
            "review": "div.review-container",
            "title": ".review-title",
            "body": ".review-body",
            "rating": ".review-rating",
            "reviewer": ".reviewer-name"
        }
        Ensure the JSON object is valid and properly formatted.
        """

        response = cohere_client.generate(
            model='command-xlarge',
            prompt=prompt,
            max_tokens=200,
            temperature=0.5
        )

        logger.info(f"Cohere API Response: {response}")

        if not response or not response.generations:
            logger.error("No valid generations received from Cohere API.")
            return None

        selectors = response.generations[0].text.strip()
        logger.info(f"Selectors identified by Cohere: {selectors}")

        try:
            return eval(selectors)
        except Exception as e:
            logger.error(f"Error parsing selectors JSON: {e}")
            return None

    except cohere.error.CohereError as e:
        logger.error(f"Cohere API Error: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return None

def extract_reviews_with_zyte(url, selectors):
    try:
        logger.info(f"Sending request to Zyte for URL: {url}")
        response = zyte_client.get(url)
        reviews = []

        if response.status != 200:
            logger.error(f"Failed to fetch the page with Zyte. Status: {response.status}")
            return reviews

        # Parse the HTML response
        from scrapy.http import HtmlResponse
        scrapy_response = HtmlResponse(url=url, body=response.content, encoding='utf-8')

        # Extract reviews based on selectors
        review_elements = scrapy_response.css(selectors.get('review', 'div.review-container'))
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

        prompt = """
        Analyze the following reviews and provide a sentiment analysis summary, including the count of positive, negative, and neutral reviews:
        """
        prompt += "\n".join(review_texts)

        response = cohere_client.generate(
            model='command-xlarge',
            prompt=prompt,
            max_tokens=300,
            temperature=0.5
        )

        processed_reviews = response.generations[0].text.strip()
        logger.info("Reviews processed successfully with Cohere.")
        return processed_reviews
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
            # Identify selectors using Cohere
            selectors = identify_selectors_with_cohere(url)
            if not selectors:
                return render_template('index.html', error="Could not identify selectors for the URL!")

            # Extract reviews using Zyte with dynamic selectors
            reviews = extract_reviews_with_zyte(url, selectors)
            if not reviews:
                return render_template('index.html', error="No reviews found!")

            # Process reviews with Cohere AI
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
