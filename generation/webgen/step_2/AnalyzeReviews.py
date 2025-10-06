import json
import os

# Attempt to import TextBlob; fall back to a simple heuristic if unavailable
try:
    from textblob import TextBlob  # type: ignore
    TEXTBLOB_AVAILABLE = True
except Exception:
    TextBlob = None  # type: ignore
    TEXTBLOB_AVAILABLE = False

def analyze_reviews(input_file=None, output_file=None, reviews_memory=None):
    """
    Reads reviews from input_file, performs sentiment analysis, 
    and saves results to output_file in JSON format.
    MEMORY_ONLY MODE: If reviews_memory (list[dict]) is provided, read from it and skip file writes.
    """
    # MEMORY-ONLY MODE: File mode disabled
    # if input_file is None:
    #     input_file = "/Users/rhettburnham/Desktop/projects/roofing-co/public/data/output/individual/step_1/raw/reviews.json"
    # if output_file is None:
    #     output_file = "/Users/rhettburnham/Desktop/projects/roofing-co/public/data/output/individual/step_2/sentiment_reviews.json"
    
    # MEMORY_ONLY: Prefer in-memory reviews; file mode disabled
    if reviews_memory is not None:
        reviews = reviews_memory
    else:
        # File mode disabled; use empty list to avoid IO
        print("AnalyzeReviews: file mode disabled; no reviews provided in memory.")
        reviews = []
    
    sentiments = []
    for review in reviews:
        # Extract the review text from the dictionary
        review_text = review.get('review_text', '')
        
        # Ensure that review_text is a string
        if not isinstance(review_text, str):
            print(f"Skipping non-string review: {review}")
            continue
        
        # Perform sentiment analysis (TextBlob when available, else heuristic)
        if TEXTBLOB_AVAILABLE:
            try:
                blob = TextBlob(review_text)
                polarity = blob.sentiment.polarity  # -1.0 to +1.0
            except Exception:
                polarity = 0.0
        else:
            # Heuristic: use rating if numeric, else keyword cues
            polarity = 0.0
            rating = review.get('rating')
            try:
                rating_num = float(rating)
                if rating_num >= 4:
                    polarity = 0.6
                elif rating_num <= 2:
                    polarity = -0.6
                else:
                    polarity = 0.0
            except Exception:
                text = (review_text or '').lower()
                pos_words = ('great','excellent','good','amazing','love','awesome','fantastic','perfect','satisfied')
                neg_words = ('bad','terrible','poor','awful','hate','horrible','worst','disappointed')
                score = sum(w in text for w in pos_words) - sum(w in text for w in neg_words)
                if score > 0:
                    polarity = 0.4
                elif score < 0:
                    polarity = -0.4
                else:
                    polarity = 0.0
        
        # Determine sentiment label based on polarity
        if polarity > 0:
            sentiment_label = 'positive'
        elif polarity < 0:
            sentiment_label = 'negative'
        else:
            sentiment_label = 'neutral'
        
        # Append the results to the sentiments list
        sentiments.append({
            'name': review.get('name', 'N/A'),
            'rating': review.get('rating', 'N/A'),
            'date': review.get('date', 'N/A'),
            'review_text': review_text,
            'sentiment': sentiment_label,
            'polarity': polarity
        })
    
    # MEMORY_ONLY: Always return results; file write disabled
    print("Sentiment analysis complete (memory-only mode).")
    return sentiments

if __name__ == "__main__":
    analyze_reviews()
