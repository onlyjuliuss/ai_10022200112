"""
Main Streamlit Application
"""

import streamlit as st
from pathlib import Path
import logging
from src.pipeline import RAGPipeline

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="Ghana Election RAG Chatbot",
    page_icon="🇬🇭",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []

if "pipeline" not in st.session_state:
    st.session_state.pipeline = None

if "pipeline_ready" not in st.session_state:
    st.session_state.pipeline_ready = False

if "api_key" not in st.session_state:
    st.session_state.api_key = ""

if "prompt_variant" not in st.session_state:
    st.session_state.prompt_variant = "A"

@st.cache_resource(show_spinner=False)
def load_pipeline(api_key, prompt_variant="A", rebuild_index=False):
    """Load the RAG pipeline with caching."""
    try:
        pipeline = RAGPipeline(
            api_key=api_key,
            prompt_variant=prompt_variant,
            rebuild_index=rebuild_index
        )
        return pipeline
    except Exception as e:
        logger.error(f"Failed to load pipeline: {e}")
        return None

# Sidebar
with st.sidebar:
    st.title("🇬🇭 Ghana Election RAG Chatbot")

    # API Key Input
    api_key = st.text_input(
        "Groq API Key",
        type="password",
        value=st.session_state.api_key,
        help="Enter your Groq API key to use the chatbot"
    )

    if api_key != st.session_state.api_key:
        st.session_state.api_key = api_key
        st.session_state.pipeline_ready = False
        st.session_state.pipeline = None

    # Prompt Variant Selection
    prompt_variant = st.selectbox(
        "Prompt Variant",
        ["A", "B", "C"],
        index=["A", "B", "C"].index(st.session_state.prompt_variant),
        help="Select the prompt template variant"
    )

    if prompt_variant != st.session_state.prompt_variant:
        st.session_state.prompt_variant = prompt_variant
        if st.session_state.pipeline:
            st.session_state.pipeline.prompt_variant = prompt_variant

    # Initialize Pipeline Button
    if st.button("Initialize Pipeline", type="primary"):
        if not api_key:
            st.error("Please enter your Groq API key first.")
        else:
            with st.spinner("Loading pipeline..."):
                pipeline = load_pipeline(api_key, prompt_variant)
                if pipeline:
                    st.session_state.pipeline = pipeline
                    st.session_state.pipeline_ready = True
                    st.success("Pipeline initialized successfully!")
                    st.rerun()
                else:
                    st.error("Failed to initialize pipeline. Check logs for details.")

    # Rebuild Index Button
    if st.button("Rebuild Index"):
        if not api_key:
            st.error("Please enter your Groq API key first.")
        else:
            with st.spinner("Rebuilding index..."):
                pipeline = load_pipeline(api_key, prompt_variant, rebuild_index=True)
                if pipeline:
                    st.session_state.pipeline = pipeline
                    st.session_state.pipeline_ready = True
                    st.success("Index rebuilt successfully!")
                    st.rerun()
                else:
                    st.error("Failed to rebuild index. Check logs for details.")

    # Clear Conversation Button
    if st.button("Clear Conversation"):
        st.session_state.messages = []
        st.success("Conversation cleared!")
        st.rerun()

    # Status
    if st.session_state.pipeline_ready:
        st.success("Pipeline Ready")
    else:
        st.warning("Pipeline Not Initialized")

# Main content
st.title("🇬🇭 Ghana Election RAG Chatbot")

if not st.session_state.pipeline_ready:
    st.info("Please initialize the pipeline using the sidebar to start chatting.")

    # Quick start guide
    with st.expander("Quick Start Guide"):
        st.markdown("""
        1. Enter your Groq API key in the sidebar
        2. Click "Initialize Pipeline" to load the system
        3. Start asking questions about Ghana's elections!

        **Example questions:**
        - What were the election results in 2020?
        - How many votes did each party get?
        - What is the voter turnout trend?
        """)

else:
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Chat input
    if prompt := st.chat_input("Ask about Ghana elections..."):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Generate response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    response = st.session_state.pipeline.query(
                        user_query=prompt,
                        use_memory=len(st.session_state.messages) > 1
                    )
                    reply = response.get("response", "Sorry, I couldn't generate a response.")
                except Exception as e:
                    logger.error(f"Query failed: {e}")
                    reply = f"Sorry, an error occurred: {str(e)}"

            st.markdown(reply)
            st.session_state.messages.append({"role": "assistant", "content": reply})

    # Quick prompts
    if st.session_state.messages == []:
        st.markdown("### Quick Questions")
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("Election Results 2020"):
                st.session_state.messages.append({"role": "user", "content": "What were the election results in 2020?"})
                st.rerun()

        with col2:
            if st.button("Voter Turnout"):
                st.session_state.messages.append({"role": "user", "content": "What is the voter turnout trend over the years?"})
                st.rerun()

        with col3:
            if st.button("Party Performance"):
                st.session_state.messages.append({"role": "user", "content": "How have the major political parties performed in recent elections?"})
                st.rerun()
