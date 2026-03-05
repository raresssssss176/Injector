import os
import openai
from dotenv import load_dotenv

load_dotenv()


client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def summarize_car(title, description):
    """Uses OpenAI to create a high-speed technical summary of the car."""
    try:
        prompt = f"""
        Analyze this car listing:
        Title: {title}
        Description: {description}
        
        Provide a 1-sentence summary for a buyer. 
        Focus on: mechanical state, if it's a good deal, and any red flags.
        Be direct and honest.
        """

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a professional car mechanic and market analyst."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=100,
            temperature=0.7
        )

        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"OpenAI Error: {e}")
        return "AI Analysis currently unavailable."