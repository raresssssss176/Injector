import openai

client = openai.OpenAI(api_key="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")

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