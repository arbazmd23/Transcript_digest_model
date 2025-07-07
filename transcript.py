import streamlit as st
import json
import re
import httpx
from httpx import ReadTimeout
import asyncio

# Page config
st.set_page_config(
    page_title="Transcript Digest",
    page_icon="📝",
    layout="wide"
)

def load_api_key():
    """Load API key from Streamlit secrets"""
    try:
        api_key = st.secrets["ANTHROPIC_API_KEY"]
        return api_key
    except KeyError:
        st.error("❌ ANTHROPIC_API_KEY not found in Streamlit secrets.")
        return None

def sanitize_json_response(raw_text: str) -> str:
    """
    Sanitize the JSON response from Claude to handle common parsing issues
    """
    # Remove any leading/trailing whitespace
    raw_text = raw_text.strip()
    
    # Extract JSON from markdown code blocks if present
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
    if json_match:
        raw_text = json_match.group(1)
    
    # Remove any non-JSON content before the first {
    start_idx = raw_text.find('{')
    if start_idx > 0:
        raw_text = raw_text[start_idx:]
    
    # Remove any content after the last }
    end_idx = raw_text.rfind('}')
    if end_idx != -1:
        raw_text = raw_text[:end_idx + 1]
    
    # Fix common JSON issues
    raw_text = raw_text.replace('\n', ' ')  # Replace newlines with spaces
    raw_text = re.sub(r'\s+', ' ', raw_text)  # Replace multiple spaces with single space
    
    return raw_text.strip()

async def call_claude_for_digest(transcript_text: str):
    api_key = load_api_key()
    if not api_key:
        return {"error": "Missing ANTHROPIC_API_KEY in environment"}

    prompt = f"""
You are a startup analyst reviewing a transcript of a conversation between a startup founder and a subject matter expert (SME).

Your goal is to extract **feedback, suggestions, and strategic guidance** given by the SME to the founder.

CRITICAL: You must identify and rank insights based on their potential impact and game-changing nature. Focus on insights that could be:
- Path-breaking or revolutionary for the business
- Game-changing strategic shifts
- High-impact technical or market advantages
- Transformative business model changes

ONLY output a valid JSON object in this EXACT format (no additional text, no markdown):
{{
  "insights": [
    {{
      "insight": "detailed description of the insight",
      "confidence_score": 8.5,
      "impact_level": "game_changer",
      "reasoning": "why this insight is important and impactful"
    }},
    {{
      "insight": "detailed description of the insight",
      "confidence_score": 7.2,
      "impact_level": "high_impact",
      "reasoning": "why this insight is important and impactful"
    }}
  ],
  "quotes": [
    {{
      "timestamp": "mm:ss",
      "quote": "exact quote from SME",
      "relevance_score": 9.0,
      "context": "brief context of why this quote is significant"
    }},
    {{
      "timestamp": "mm:ss", 
      "quote": "exact quote from SME",
      "relevance_score": 8.5,
      "context": "brief context of why this quote is significant"
    }}
  ]
}}

Guidelines:
- Extract ALL significant insights (not limited to 4) - could be 2-10+ insights
- Rank insights by potential business impact and strategic importance
- Confidence scores: 1-10 scale (10 = highest confidence this will drive results)
- Impact levels: "game_changer", "high_impact", "moderate_impact", "tactical"
- Focus ONLY on what the SME contributed — advice, strategy shifts, architecture suggestions, go-to-market insights
- Quotes should be exact and impactful, with relevance scores 1-10
- Do NOT summarize the product or founder's perspective
- Extract quotes that represent the most valuable SME contributions

Transcript:
\"\"\"
{transcript_text}
\"\"\"
"""

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }

    payload = {
        "model": "claude-3-haiku-20240307",
        "max_tokens": 2048,  # Increased to handle more insights
        "temperature": 0.3,  # Slightly lower for more consistent JSON
        "messages": [{"role": "user", "content": prompt}]
    }

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:  # Increased timeout
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload
            )
    except ReadTimeout:
        return {
            "error": "Claude API timed out after 45 seconds. Try again or reduce transcript length."
        }

    if response.status_code != 200:
        return {
            "error": "Claude API request failed",
            "status": response.status_code,
            "details": response.text
        }

    data = response.json()

    try:
        # Extract the actual text and sanitize it
        raw_text = data["content"][0]["text"]
        sanitized_text = sanitize_json_response(raw_text)
        
        # Parse the sanitized JSON
        result_json = json.loads(sanitized_text)
        
        # Sort insights by confidence score (highest first)
        if "insights" in result_json:
            result_json["insights"] = sorted(
                result_json["insights"], 
                key=lambda x: x.get("confidence_score", 0), 
                reverse=True
            )
        
        # Sort quotes by relevance score (highest first)
        if "quotes" in result_json:
            result_json["quotes"] = sorted(
                result_json["quotes"], 
                key=lambda x: x.get("relevance_score", 0), 
                reverse=True
            )
        
        return result_json
        
    except json.JSONDecodeError as e:
        # Enhanced error handling with more context
        return {
            "error": "Failed to parse Claude response as JSON",
            "json_error": str(e),
            "raw_response": data["content"][0]["text"][:500] + "..." if len(data["content"][0]["text"]) > 500 else data["content"][0]["text"],
            "sanitized_attempt": sanitized_text[:500] + "..." if len(sanitized_text) > 500 else sanitized_text
        }
    except Exception as e:
        return {
            "error": "Unexpected error processing Claude response",
            "exception": str(e),
            "raw_response": data
        }

def run_async_function(func, *args):
    """Helper function to run async functions in Streamlit"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(func(*args))
    finally:
        loop.close()

def main():
    st.title("📝 Transcript Digest")
    st.markdown("Upload a transcript to extract insights and strategic guidance from SME conversations.")
    
    # Check if API key is available
    api_key = load_api_key()
    if not api_key:
        st.stop()
    else:
        st.success("✅ ANTHROPIC_API_KEY loaded successfully")
    
    # File upload
    uploaded_file = st.file_uploader(
        "Upload transcript file", 
        type=['txt', 'md'],
        help="Upload a text file containing the transcript"
    )
    
    if uploaded_file is not None:
        # Read the file content
        try:
            transcript_text = uploaded_file.read().decode("utf-8")
            
            # Display file info
            st.info(f"📄 File uploaded: {uploaded_file.name} ({len(transcript_text)} characters)")
            
            # Process button
            if st.button("🔍 Analyze Transcript", type="primary"):
                with st.spinner("Processing transcript with Claude..."):
                    # Call the async function
                    result = run_async_function(call_claude_for_digest, transcript_text)
                    
                    # Display results
                    st.markdown("## 📊 Analysis Results")
                    
                    # Display the JSON output exactly as the original code
                    st.json(result)
                    
                    # Optional: Add download button for the JSON result
                    if not result.get("error"):
                        json_str = json.dumps(result, indent=2)
                        st.download_button(
                            label="💾 Download JSON Result",
                            data=json_str,
                            file_name=f"transcript_digest_{uploaded_file.name.split('.')[0]}.json",
                            mime="application/json"
                        )
                    
        except Exception as e:
            st.error(f"❌ Error processing file: {str(e)}")
    
    # Instructions
    with st.expander("ℹ️ Instructions"):
        st.markdown("""
        1. **Upload**: Select a transcript file (.txt or .md)
        2. **Analyze**: Click the "Analyze Transcript" button
        3. **Review**: The system will extract insights and quotes from SME conversations
        4. **Download**: Save the JSON results for later use
        
        **What the system extracts:**
        - Strategic insights ranked by impact and confidence
        - Key quotes with relevance scores
        - Game-changing business advice
        - Technical and market advantages
        """)

if __name__ == "__main__":
    main()