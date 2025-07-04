import streamlit as st
import json
import re
import httpx
from httpx import ReadTimeout
import asyncio

# Page configuration
st.set_page_config(
    page_title="Startup Transcript Analyzer",
    page_icon="🎯",
    layout="wide"
)

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

async def call_claude_for_digest(transcript_text: str, api_key: str):
    """
    Call Claude API to analyze the transcript
    """
    if not api_key:
        return {"error": "Missing ANTHROPIC_API_KEY in Streamlit secrets"}

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
        "max_tokens": 2048,
        "temperature": 0.3,
        "messages": [{"role": "user", "content": prompt}]
    }

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
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

def process_transcript(transcript_text: str, api_key: str):
    """
    Process transcript synchronously for Streamlit
    """
    return asyncio.run(call_claude_for_digest(transcript_text, api_key))

def main():
    st.title("🎯 Startup Transcript Analyzer")
    st.markdown("### Extract insights and quotes from startup conversations")
    
    # Check for API key in secrets
    try:
        api_key = st.secrets["ANTHROPIC_API_KEY"]
        st.success("✅ API key loaded from secrets")
    except KeyError:
        st.error("❌ ANTHROPIC_API_KEY not found in Streamlit secrets")
        st.info("Please add your Anthropic API key to Streamlit secrets")
        st.stop()
    
    # File upload
    uploaded_file = st.file_uploader(
        "Upload your transcript file", 
        type=['txt', 'md'],
        help="Upload a text file containing the startup conversation transcript"
    )
    
    if uploaded_file is not None:
        # Read the file
        try:
            transcript_text = uploaded_file.read().decode('utf-8')
            
            # Show file info
            st.info(f"📄 File uploaded: {uploaded_file.name} ({len(transcript_text)} characters)")
            
            # Process button
            if st.button("🔍 Analyze Transcript", type="primary"):
                with st.spinner("Analyzing transcript with Claude..."):
                    result = process_transcript(transcript_text, api_key)
                
                # Display results
                st.markdown("## 📊 Analysis Results")
                
                # Display as JSON (formatted)
                st.json(result)
                
                # Optional: Also display in a more readable format
                if "insights" in result and "quotes" in result:
                    st.markdown("---")
                    st.markdown("## 📈 Summary")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.metric("Total Insights", len(result["insights"]))
                        if result["insights"]:
                            avg_confidence = sum(insight.get("confidence_score", 0) for insight in result["insights"]) / len(result["insights"])
                            st.metric("Average Confidence", f"{avg_confidence:.1f}/10")
                    
                    with col2:
                        st.metric("Total Quotes", len(result["quotes"]))
                        if result["quotes"]:
                            avg_relevance = sum(quote.get("relevance_score", 0) for quote in result["quotes"]) / len(result["quotes"])
                            st.metric("Average Relevance", f"{avg_relevance:.1f}/10")
                
                # Download button for JSON
                if "error" not in result:
                    json_string = json.dumps(result, indent=2)
                    st.download_button(
                        label="📥 Download JSON Results",
                        data=json_string,
                        file_name=f"transcript_analysis_{uploaded_file.name.split('.')[0]}.json",
                        mime="application/json"
                    )
        
        except Exception as e:
            st.error(f"Error reading file: {str(e)}")
    
    # Instructions
    with st.expander("📖 How to use"):
        st.markdown("""
        1. **Upload your transcript**: Upload a text file containing the conversation between a startup founder and SME
        2. **Click Analyze**: The system will extract insights and quotes using Claude AI
        3. **View Results**: Results are displayed in JSON format with confidence scores and rankings
        4. **Download**: Save the results as a JSON file for further analysis
        
        **What the analyzer extracts:**
        - **Insights**: Strategic advice from the SME with confidence scores (1-10)
        - **Quotes**: Key statements with relevance scores and context
        - **Rankings**: Automatically sorted by impact and relevance
        """)
    
    # Secrets setup instructions
    with st.expander("🔧 Setup Instructions"):
        st.markdown("""
        **To set up your Anthropic API key:**
        
        1. Go to your Streamlit app settings
        2. Navigate to the "Secrets" section
        3. Add the following:
        
        ```toml
        ANTHROPIC_API_KEY = "your_api_key_here"
        ```
        
        4. Save and restart your app
        """)

if __name__ == "__main__":
    main()