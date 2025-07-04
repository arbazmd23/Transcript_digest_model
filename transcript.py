import os
import json
import streamlit as st
import httpx
from httpx import ReadTimeout

# Set page config
st.set_page_config(page_title="Transcript Digest", page_icon="📝", layout="wide")

def load_environment_variables():
    """Load API key from Streamlit secrets"""
    try:
        api_key = st.secrets["ANTHROPIC_API_KEY"]
        if api_key:
            st.success("✓ ANTHROPIC_API_KEY loaded from secrets.")
            return True
        else:
            st.error("✗ ANTHROPIC_API_KEY missing from secrets.")
            return False
    except KeyError:
        st.error("✗ ANTHROPIC_API_KEY not found in Streamlit secrets.")
        return False

async def call_claude_for_digest(transcript_text: str):
    """Call Claude API for transcript analysis - same logic as FastAPI version"""
    try:
        api_key = st.secrets["ANTHROPIC_API_KEY"]
    except KeyError:
        return {"error": "Missing ANTHROPIC_API_KEY in Streamlit secrets"}
    
    prompt = f"""
You are a startup analyst reviewing a transcript of a conversation between a startup founder and a subject matter expert (SME).
Your goal is to extract **feedback, suggestions, and strategic guidance** given by the SME to the founder.
ONLY output a JSON object in this format:
{{
  "insights": [ // 4 specific things the SME told the founder to consider or change ],
  "quotes": [  // 2 key SME quotes with estimated timestamps in mm:ss format
    {{ "timestamp": "...", "quote": "..." }},
    {{ "timestamp": "...", "quote": "..." }}
  ]
}}
Guidelines:
- Do NOT just summarize the product or the founder's perspective.
- Focus only on what the SME contributed — advice, strategy shifts, architecture suggestions, go-to-market insights, etc.
- If there's a debate, pick SME takeaways that challenge or sharpen the founder's thinking.
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
        "max_tokens": 1024,
        "temperature": 0.4,
        "messages": [{"role": "user", "content": prompt}]
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload
            )
    except ReadTimeout:
        return {
            "error": "Claude API timed out after 30 seconds. Try again or reduce transcript length."
        }
    
    if response.status_code != 200:
        return {
            "error": "Claude API request failed",
            "status": response.status_code,
            "details": response.text
        }
    
    data = response.json()
    try:
        # Extract the actual text and parse the JSON from it
        raw_text = data["content"][0]["text"]
        result_json = json.loads(raw_text)
        return result_json
    except Exception as e:
        return {
            "error": "Failed to parse Claude response",
            "exception": str(e),
            "raw_response": data
        }

def main():
    """Main Streamlit application"""
    st.title("📝 Transcript Digest")
    st.markdown("Upload a transcript to extract SME insights and feedback for startup founders.")
    
    # Check if API key is available
    if not load_environment_variables():
        st.stop()
    
    # File upload
    uploaded_file = st.file_uploader(
        "Upload transcript file", 
        type=['txt', 'md'],
        help="Upload a text file containing the transcript"
    )
    
    if uploaded_file is not None:
        try:
            # Read the file content
            transcript_text = uploaded_file.read().decode("utf-8")
            
            # Show file preview
            with st.expander("📄 Transcript Preview"):
                st.text_area("Content", transcript_text, height=200, disabled=True)
            
            # Process button
            if st.button("🔍 Analyze Transcript", type="primary"):
                with st.spinner("Analyzing transcript with Claude..."):
                    # Call the Claude API function
                    import asyncio
                    result = asyncio.run(call_claude_for_digest(transcript_text))
                
                # Display results
                if "error" in result:
                    st.error(f"Error: {result['error']}")
                    if "details" in result:
                        with st.expander("Error Details"):
                            st.text(result["details"])
                else:
                    st.success("✅ Analysis complete!")
                    
                    # Display insights
                    if "insights" in result:
                        st.subheader("💡 Key Insights")
                        for i, insight in enumerate(result["insights"], 1):
                            st.write(f"**{i}.** {insight}")
                    
                    # Display quotes
                    if "quotes" in result:
                        st.subheader("💬 Key Quotes")
                        for quote in result["quotes"]:
                            st.markdown(f"**[{quote['timestamp']}]** *\"{quote['quote']}\"*")
                    
                    # Show raw JSON
                    with st.expander("📊 Raw JSON Response"):
                        st.json(result)
                        
        except Exception as e:
            st.error(f"Failed to process transcript: {str(e)}")

if __name__ == "__main__":
    main()