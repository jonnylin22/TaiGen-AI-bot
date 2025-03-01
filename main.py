# -*- coding: utf-8 -*-
"""「Version 2 Copy of Paim0n Chatbot (RAG + Tavily)」的副本

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1s4jLfPRxPIOmp6HN8rFrg1k4_ds_As9b

**RAG**
"""

# Install necessary libraries
# pip install google-generativeai chromadb fastapi uvicorn pyngrok nest-asyncio flask flask-ngrok

import google.generativeai as genai
import os
from chromadb.config import Settings
import chromadb
# from google.generativeai.types import EmbedContentConfig
import uuid
from fastapi import FastAPI
from pydantic import BaseModel

# 使用 ngrok 讓 Colab 對外公開
from pyngrok import ngrok
import nest_asyncio
nest_asyncio.apply()

# 初始化 FastAPI
app = FastAPI()

# Set up ChromaDB for vector storage
def setup_chroma_db(path: str):
    client = chromadb.PersistentClient(path=path)
    return client

chroma_db_path = "./chroma_db"
chroma_client = setup_chroma_db(chroma_db_path)


# Google API Key setup
genai.configure(api_key="AIzaSyCd8Xh2bygG4Ziux4hvMfbFuKs82hUYADA")

# Load text file from Google Colab environment
def load_text_file(file_path):
    """Loads text from a file.

    Args:
        file_path: Path to the text file in Google Colab.

    Returns:
        str: Text content of the file.
    """
    try:
        with open(file_path, "r", encoding='utf-8') as f:  # Added encoding for robustness
            text_content = f.read()
        return text_content
    except FileNotFoundError:
        return None
    except Exception as e: #Catch other exceptions
        print(f"An error occurred while loading the file: {e}")
        return None


# Split text into chunks for embedding
def chunk_text(text, chunk_size=700, chunk_overlap=50):
    """Splits text into smaller chunks.

    Args:
        text: The input text string.
        chunk_size: Maximum size of each chunk.
        chunk_overlap: Number of overlapping characters between chunks.

    Returns:
        list: List of text chunks.
    """
    chunks = []
    start_index = 0
    if not isinstance(text, str):
        print("Error: Input text must be a string.")
        return []
    text_length = len(text)

    while start_index < text_length:
        end_index = min(start_index + chunk_size, text_length)
        chunk = text[start_index:end_index]
        chunks.append(chunk)
        # Corrected start_index calculation for proper overlap
        start_index += chunk_size - chunk_overlap
        if chunk_size - chunk_overlap <= 0: #Prevents infinite loops
            print("Warning: chunk_size <= chunk_overlap.  Setting chunk_overlap = 0")
            start_index = end_index
            chunk_overlap = 0

    return chunks

# Embed text chunks using Gemini API
def embed_text_with_gemini(text_chunks, model_name="models/embedding-001"):
    try:
        if not text_chunks:  # Check if the list is empty
            print("Warning: No text chunks to embed.")
            return []

        embeddings = genai.embed_content(
            model = model_name,
            content=text_chunks,
            task_type="retrieval_document",
            title="Text Chunks"
        )
        ## Printing the embeddings ##
        # print (f"embeddings = {embeddings}")
        return embeddings['embedding']  # Corrected return value
    except Exception as e:
        print(f"Error during embedding: {e}")
        return []


# Add embeddings and text chunks to ChromaDB
def add_to_chroma_db_with_metadata(client, embeddings, text_chunks, collection_name="rag_collection"):
    """Adds embeddings and text chunks and metadata to ChromaDB.

    Args:
        client: ChromaDB client.
        embeddings: List of embeddings.
        text_chunks: List of corresponding text chunks.
        collection_name: Name of the ChromaDB collection.

    Returns:
        chromadb.Collection: ChromaDB collection.
    """
    collection = client.get_or_create_collection(name=collection_name)
    #ids = [str(i) for i in range(len(text_chunks))] # Generate unique IDs

     # Check for empty embeddings or text_chunks
    if not embeddings or not text_chunks:
        print("Error: Empty embeddings or text chunks.  Cannot add to ChromaDB.")
        return collection  # Return the existing collection (possibly empty)

    # Ensure IDs are unique using UUID
    ids = [str(uuid.uuid4()) for _ in range(len(text_chunks))]

    # Define metadata for each embedding (can be adjusted based on your use case)
    metadata = [{"document_name": f"Document {i + 1}", "chunk_index": i} for i in range(len(text_chunks))]

    #Handle mismatched lengths
    if len(embeddings) != len(text_chunks):
      print("Warning Mismatched lengths between embeddings and documents")
      min_length = min(len(embeddings), len(text_chunks))
      embeddings = embeddings[:min_length]
      text_chunks = text_chunks[:min_length]
      ids = ids[:min_length]


    collection.add(
        embeddings=embeddings,
        documents=text_chunks,
        ids=ids,
    )
    return collection

# Retrieve relevant chunks from ChromaDB based on query
def retrieve_relevant_chunks_with_metadata(client, query, collection_name="rag_collection", model_name="models/embedding-001", n_results=3):
    """Retrieves relevant text chunks from ChromaDB based on a query.

    Args:
        client: ChromaDB client.
        query: User query string.
        collection_name: Name of the ChromaDB collection.
        model_name: Gemini embedding model to use for query.
        n_results: Number of relevant chunks to retrieve.

    Returns:
        list: List of retrieved text chunks.  Handles errors gracefully.
    """
    try:
        collection = client.get_collection(name=collection_name)
        query_embedding_response = embed_text_with_gemini([query], model_name=model_name)

        #Check for failed query embedding
        if not query_embedding_response:
            print("Error: Could not embed the query.")
            return []

        query_embedding = query_embedding_response[0]

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results
        )

        # Extract relevant text chunks and metadata
        relevant_documents = results['documents'][0]
        metadata = []
        content = []

        # Return both documents and their metadata
        for doc in relevant_documents:
            # Split the document to separate metadata from the content
            # Assuming the metadata is at the beginning of the document (e.g., 'File: <filename>')
            file_info, content_info = doc.split("\n\n", 1)  # Split by the first empty line
            metadata.append(file_info)  # Metadata (e.g., file name)
            content.append(content_info)  # Content (actual chunk text)
            return content, metadata  # Return both content and metadata
    except Exception as e:
        print(f"Error during retrieval: {e}")
        return [],[]  # Return empty lists on error


# Generate response using Gemini API with retrieved context
def generate_response_with_gemini(query, context_chunks, model_name="gemini-1.5-flash"):
    """Generates a response using the Gemini API, incorporating context.

    Args:
        query: User query string.
        context_chunks: List of relevant text chunks retrieved from ChromaDB.
        model_name: Gemini model to use for response generation.

    Returns:
        str: Generated response.  Handles API errors.
    """
    try:
        model = genai.GenerativeModel(model_name)
        context = "\n".join(context_chunks)
        prompt_content = f"""Answer the query based on the context provided.

        Context:
        {context}

        Query:
        {query}
        """

        response = model.generate_content(prompt_content)
        return response.text
    except Exception as e:
        print(f"Error during response generation: {e}")
        return "An error occurred while generating the response."


def store_embeddings_from_file(file_path):
    """Processes a file and stores its embeddings in ChromaDB with metadata included in documents."""

    # Step 1: Load text content from the file
    text_content = load_text_file(file_path)
    if not text_content:
        return "Error: Could not load the text file. Please check the file path."

    # Step 2: Split text into chunks for embedding
    text_chunks = chunk_text(text_content)
    if not text_chunks:  # Handle the case where chunking fails
        return "Error: Could not chunk the text content."

    # Step 3: Generate embeddings for the chunks
    embeddings_response = embed_text_with_gemini(text_chunks)
    if not embeddings_response:  # Handles case where embedding fails
        return "Error: Could not embed the text chunks."

    # Step 4: Set up ChromaDB client and add embeddings with metadata
    db_folder = "chroma_db"
    db_path = os.path.join(os.getcwd(), db_folder)
    chroma_client = setup_chroma_db(db_path)

    # Add embeddings and documents to ChromaDB, including metadata
    documents_with_metadata = [
        f"File: {file_path}\n\nContent: {chunk}" for chunk in text_chunks
    ]

    # Generate unique IDs for each document
    ids = [str(uuid.uuid4()) for _ in range(len(text_chunks))]

    # Add embeddings, documents, and ids to ChromaDB
    chroma_collection = add_to_chroma_db_with_metadata(chroma_client, embeddings_response, documents_with_metadata, collection_name="rag_collection")
    return f"Embeddings for {file_path} successfully stored in ChromaDB."


def preform_rag_with_query(query):
    """Orchestrates the RAG process without specifying the data file

    Args:
        query: User query string.

    Returns:
        str: Generated response based on RAG.
    """
    db_folder = "chroma_db"
    db_path = os.path.join(os.getcwd(), db_folder)
    print(f"db_path = {db_path}")
    chroma_client = setup_chroma_db(db_path)

    # Assuming embeddings and text chunks have already been added without specifying a file
    relevant_chunks, relevant_metadata = retrieve_relevant_chunks_with_metadata(chroma_client, query)

    if not relevant_chunks:
        return "No relevant information found in the document for the query."

    rag_response = generate_response_with_gemini(query, relevant_chunks)
    return rag_response

# Main function to orchestrate RAG process
def perform_rag(file_path, query):
    """Orchestrates the RAG process.

    Args:
        file_path: Path to the text file in Google Colab.
        query: User query string.

    Returns:
        str: Generated response based on RAG.
    """
    text_content = load_text_file(file_path)
    if not text_content:
        return "Error: Could not load text file. Please check the file path."

    text_chunks = chunk_text(text_content)
    if not text_chunks: # Handle the case where chunking fails
      return "Error: Could not chunk the text content."
    embeddings_response = embed_text_with_gemini(text_chunks)
    if not embeddings_response: #Handles case where embedding fails
        return "Error: Could not embed the text chunks"

    db_folder = "chroma_db"
    # db_name = "rag_experiment"
    db_path = os.path.join(os.getcwd(), db_folder)
    chroma_client = setup_chroma_db(db_path)
    chroma_collection = add_to_chroma_db_with_metadata(chroma_client, embeddings_response, text_chunks)

    relevant_chunks = retrieve_relevant_chunks_with_metadata(chroma_client, query)
    if not relevant_chunks:
        return "No relevant information found in the document for the query."

    rag_response = generate_response_with_gemini(query, relevant_chunks)
    return rag_response

# --- Example Usage in Google Colab ---

# 1. Upload your text file to Google Colab.
#    - You can use the file upload button in the Colab sidebar (Files tab).
#    - Let's assume your file is named 'my_text_file.txt' and is in the root directory of your Colab environment.

### Example files:
#file_path = 'wishing-info.txt'  # Replace with your file name if different
file_path = 'formatted_weapon_data.txt'  # Replace with your file name if different
#file_path = 'formatted_character_data.txt'  # Replace with your file name if different
user_query = "What is the main topic of this document?" # Replace with your query
#user_query = "Which weapons have Energy Recharge as a substat?"

# Perform RAG and get the response
#output_response = perform_rag(file_path, user_query)

# Print the response
#print("Query:", user_query)
#print("RAG Response:", output_response)

### Test embedding and storing file only without query:
#file_path = 'formatted_weapon_data.txt'
#file_path = 'formatted_character_data.txt'
file_path = 'wishing-info.txt'
result = store_embeddings_from_file(file_path)
print(result)

result = store_embeddings_from_file('formatted_character_data.txt')
print(result)

result = store_embeddings_from_file('formatted_weapon_data.txt')
print(result)

result = store_embeddings_from_file('furina_story_quest.txt')
print(result)

## Test querying after file is stored first:
preform_rag_with_query("What is base rate I roll a 5 star with no pity?")

# ===== FastAPI 包裝 RAG API =====

class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    response: str

@app.post("/api/rag-query", response_model=QueryResponse)
def rag_query(request: QueryRequest):
    query = request.query
    rag_response = perform_rag(query)
    return QueryResponse(response=rag_response)

"""

---


**TavilySearch**"""

# pip install tavily-python
# from google.colab import userdata  # For Colab secrets
from tavily import TavilyClient

@app.post("/api/tavily-search")
def tavily_search(query, search_depth="basic", time_range=None, include_answer=None, max_results=5, include_domains=None):
    """
    Overlay function for Tavily API search.

    Parameters:
        query (str): The search query. necessary
        search_depth (str): "basic" or "advanced".
        time_range (str or None): Time filter, e.g., "d" (day), "w" (week), "m" (month), "y" (year).
        include_answer (str): "none", "basic", or "advanced".
        max_results (int): Number of results to return.
        include_domains (list or None): List of domains to include (default is None).


    Returns:
        dict: Search results from Tavily API.
    """

   # tavily_client = TavilyClient(userdata.get('TAVILY_API_KEY'))
    tavily_client = TavilyClient("insert-tavily-api-key")
    search_params = {
      "query": query,
      "search_depth": search_depth,
      "max_results": max_results,
    }

    if time_range in ["y", "m", "w", "d"]:
        search_params["time_range"] = time_range
    if include_answer in ["basic", "advanced"]:  # 只允許 Tavily API 支援的值
        search_params["include_answer"] = include_answer
    if include_domains:
        search_params["include_domains"] = include_domains

    response = tavily_client.search(**search_params)
    return response

# Test tavily_search
result1 = tavily_search("Latest AI news")
print(result1)

# result2 = tavily_search("Latest AI news", include_domains=["reddit.com"])
# print(result2)

# result3 = tavily_search("Future of AI", time_range = "d", max_results=1, search_depth = "basic", include_answer = "basic", include_domains=["medium.com", "techcrunch.com"])
# print(result3)

import json
# for human reading
def format_result_as_json(result):
    formatted_result = {
        "query": result["query"],
        "follow_up_questions": result["follow_up_questions"],
        "answer": result["answer"],
        "images": result["images"],
        "results": [
            {
                "url": item["url"],
                "title": item["title"],
                "content": item["content"],
                "score": item["score"]
            }
            for item in result["results"]
        ],
        "response_time": result["response_time"]
    }

    json_output = json.dumps(formatted_result, ensure_ascii=False, indent=4)
    return json_output

"""---
**Crawler on certain website [reddit.com]**
"""

# pip install praw requests beautifulsoup4
import requests
from bs4 import BeautifulSoup
import praw
reddit = praw.Reddit(
    client_id="insert-praw-client-id",
    client_secret="insert-praw-client-secret",
    user_agent="chatbot"
)

@app.post("/api/checkTargetWeb")
def checkTargetWeb(url):
    """
    Check if the url is target url. If true, crawl the post title, content and top five comments.
    Target url: reddit.com
    """
    if "reddit.com" in url:
        print(f"It's a Reddit url: {url}")
        try:
            post_id = url.split("/")[-3]  # Get Reddit post ID
            submission = reddit.submission(id=post_id)

            title = submission.title.strip()
            content = submission.selftext.strip()

            # crawl top 5 comment
            submission.comments.replace_more(limit=0)  # remove "load more comments"
            comments = [comment.body.strip() for comment in submission.comments[:5]]

            # convert to json
            reddit_data = {
                "title": title,
                "content": content,
                "comments": comments
            }

            print(reddit_data)

            return reddit_data
        except Exception as e:
            print(f"Can't crawl Reddit: {e}")
            return None
    # TODO: genshin-impact.fandom.com
    # else:


result = tavily_search("How to quickly earn money in Genshin?", include_domains=["reddit.com", "genshin-impact.fandom.com"])
print(format_result_as_json(result))
for result_item in result['results']:
    url = result_item['url']
    checkTargetWeb(url)
    # print(checkTargetWeb(url))

"""

---


**Gemini Chatbot**"""

import google.generativeai as genai
import numpy as np
import os
from flask import Flask, request, jsonify
from flask_cors import CORS


# Configure the Gemini API
#secret = userdata.get('GOOGLE_API_KEY')          ### extract API key from notebook secret
# Google API Key setup
import os
os.environ['GOOGLE_API_KEY'] = 'insert-gemini-api-key'


# store conversation history
conversation_history = []

def get_embedding(text, model="models/embedding-001"):
    """Generate an embedding vector for a given text."""
    response = genai.embed_content(model=model, task_type="semantic_similarity", content=text)
    return response.get(["embedding"], [])  # Returns the embedding vector

    # Store conversation history
    conversation_history = []

def generate_response(user_input):
    """Generate a response using Gemini LLM with context-aware embeddings."""
    global conversation_history

    conversation_history.append({"role": "user", "parts": user_input})

    # Use the Gemini model to generate a response
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = genai.chat(messages=conversation_history).text

    # Add AI response to history
    bot_response = response.text
    conversation_history.append({"role": "user", "parts": bot_response})

    return bot_response

"""
# Show available models for content generation:
print("--------------------------------------------------------")
print("All Gemini Models available for content generation: ")
for m in genai.list_models():
  if 'generateContent' in m.supported_generation_methods:
    print(m.name)

print("----------------------------------------------------")
"""

# Initialize chat session
selected_model = 'gemini-1.5-flash'
model = genai.GenerativeModel(selected_model)
system_message = (
    "You are Paim0n, an AI guide specialized in assisting players with the video game Genshin Impact, developed by HoYoverse. "
    "Your role is to provide accurate and up-to-date information on all aspects of the game, including characters, builds, artifacts, weapons, "
    "team compositions, game mechanics, event guides, exploration tips, and lore discussions. "

    "You also help players complete quests by providing step-by-step guidance, puzzle solutions, and strategies for difficult encounters. "
    "Additionally, you assist with finding rare items by providing detailed locations, farming routes, estimated respawn times, and the best methods to obtain them efficiently. "
    "If players are looking for a specific area or an unfamiliar location, you offer navigation assistance, waypoints, and travel tips to help them reach their destination easily. "

    "You should stay within the context of Genshin Impact and avoid answering unrelated questions. "
    "If asked about leaks or unofficial content, politely inform the user that you only provide officially released information. "
    "Maintain an energetic and friendly tone, just like the real Paimon, but avoid excessive repetition or filler phrases. "

    "Your goal is to be the ultimate Genshin Impact companion, helping players optimize their experience, whether they need battle strategies, exploration guidance, "
    "or tips on maximizing their resources efficiently."
)
# chat = model.start_chat(history=[{"role": "system", "parts": system_message}])
# start chat
chat = model.start_chat(history=[])
# send system message as the first message and wait for completion
response = chat.send_message(system_message)
if response:  # ensure system message is processed before continuing
  print("Hi I'm Paim0n, ready to assist you in the world of Teyvat!")
else:
  print("System message not passed")

# Verify chosen model
for m in genai.list_models():
  model_name = m.name.split("/")[-1]
  if model_name == selected_model:
    # print("----------------------------------------------------")
    print("Current selected model: ", model_name)

app = Flask(__name__)
CORS(app)

# Run chatbot
@app.route('/chat', methods=['POST'])
def chat_api():
    data = request.get_json()
    user_input = data.get("message", "")

    if not user_input:
        return jsonify({"error": "No input provided"}), 400

    if user_input.lower() in ["exit", "quit", "bye"]:
        # print("Paim0n: Goodbye Traveler! ")
        return jsonify({"reply": "Paim0n: Goodbye Traveler!"})



    # Generate response
    # response = chat.send_message(user_input)
    # Use tavily search
    tavily_result = tavily_search(user_input)
    # call RAG to search documents uploaded
    rag_result = preform_rag_with_query(user_input)
    query = f"""
    Below is some external information from web search about the question:
    {tavily_result}

    Below is some external information from documents uploaded for accurate context, put more weight on matching results from.,mnbv these documents:
    {rag_result}

    Use Gemini LLM with context-aware embeddings and external information and internal information to provide a detailed and accurate answer to the query:
    "{user_input}"
    """

    response_stream = chat.send_message(query)

    bot_reply = ""
    for chunk in response_stream:
        if chunk.text:
            bot_reply += chunk.text

    # 回傳 JSON
    return jsonify({"reply": bot_reply})

    # 啟動 Flask
app.run()
# what are optimal weapons for chongyun?
# What is a recommended build for Amber?
# How do I go fishing?
# In what quest do Furina and traveler talk about Macaroni