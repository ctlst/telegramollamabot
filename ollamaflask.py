#!/usr/bin/env python3
import ollama
import argparse
import sys
import json
from typing import Optional, Dict, Any
import time
import os
from flask import Flask, request, jsonify

app = Flask(__name__)

class OllamaService:
    def __init__(self):
        self.conversations = {}  # Store conversations by session ID

    def list_models(self) -> Dict[str, Any]:
        try:
            models_response = ollama.list()
        
        # Handle new response format
            if hasattr(models_response, 'models'):
                models_list = models_response.models
            else:
                # Fall back to the old format if needed
                models_list = models_response.get("models", [])
        
            # Extract information carefully, handling both old and new formats
            formatted_models = []
            for model in models_list:
                model_name = model.model if hasattr(model, 'model') else model.get("name", "unknown")
            
                # Try to get size in different ways
                if hasattr(model, 'size'):
                    size = model.size
                else:
                    size = model.get("size", 0)
                
                # Convert size from bytes to GB and round to 2 decimal places
                size_gb = round(size / (1024 * 1024 * 1024), 2) if size else "N/A"
            
                formatted_models.append({
                    "name": model_name,
                    "size": size_gb
                })
            
            return {
                "success": True,
                "models": formatted_models
            }
        except Exception as e:
            import traceback
            traceback.print_exc()  # Print detailed error info to logs
            return {"success": False, "error": str(e)}    

    def pull_model(self, model_name: str) -> Dict[str, Any]:
        """Pull a model from Ollama"""
        try:
            ollama.pull(model_name)
            return {"success": True, "message": f"Successfully pulled {model_name}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def chat(self, model_name: str, message: str, session_id: str) -> Dict[str, Any]:
        """Chat with the model"""
        try:
            # Initialize conversation history if it doesn't exist
            if session_id not in self.conversations:
                self.conversations[session_id] = []

            start_time = time.time()
            
            response = ollama.chat(
                model=model_name,
                messages=self.conversations[session_id] + [{"role": "user", "content": message}]
            )
            
            # Update conversation history
            self.conversations[session_id].append({"role": "user", "content": message})
            self.conversations[session_id].append({"role": "assistant", "content": response["message"]["content"]})
            
            elapsed_time = time.time() - start_time
            
            return {
                "success": True,
                "response": response["message"]["content"],
                "elapsed_time": round(elapsed_time, 2)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def generate(self, model_name: str, prompt: str) -> Dict[str, Any]:
        """Generate a single response"""
        try:
            start_time = time.time()
            response = ollama.generate(model=model_name, prompt=prompt)
            elapsed_time = time.time() - start_time
            
            return {
                "success": True,
                "response": response["response"],
                "elapsed_time": round(elapsed_time, 2)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def clear_chat_history(self, session_id: str) -> Dict[str, Any]:
        """Clear chat history for a session"""
        try:
            if session_id in self.conversations:
                self.conversations[session_id] = []
            return {"success": True, "message": "Chat history cleared"}
        except Exception as e:
            return {"success": False, "error": str(e)}

# Initialize the Ollama service
ollama_service = OllamaService()

@app.route("/api/models", methods=["GET"])
def list_models():
    return jsonify(ollama_service.list_models())

@app.route("/api/models/pull/<model_name>", methods=["POST"])
def pull_model(model_name):
    return jsonify(ollama_service.pull_model(model_name))

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json()
    if not data or "model" not in data or "message" not in data:
        return jsonify({"success": False, "error": "Missing required parameters"}), 400
    
    session_id = data.get("session_id", "default")
    return jsonify(ollama_service.chat(data["model"], data["message"], session_id))

@app.route("/api/generate", methods=["POST"])
def generate():
    data = request.get_json()
    if not data or "model" not in data or "prompt" not in data:
        return jsonify({"success": False, "error": "Missing required parameters"}), 400
    
    return jsonify(ollama_service.generate(data["model"], data["prompt"]))

@app.route("/api/chat/clear/<session_id>", methods=["POST"])
def clear_chat_history(session_id):
    return jsonify(ollama_service.clear_chat_history(session_id))

@app.errorhandler(404)
def not_found(e):
    return jsonify({"success": False, "error": "Resource not found"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"success": False, "error": "Internal server error"}), 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
