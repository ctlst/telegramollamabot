#!/usr/bin/env python3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import requests
import os
import json
import logging
from typing import Dict, Any
import asyncio
import re


# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
API_BASE_URL = "http://localhost:5000/api"  # Adjust this to your Flask backend URL
DEFAULT_MODEL = "mistral"  # Set default model to mistral

class OllamaTelegramBot:
    def __init__(self):
        self.active_models: Dict[int, str] = {}  # Store active model for each user
        self.request_timeout = 300  # 5 minutes timeout for long responses
        
    async def ensure_model_exists(self, model_name: str) -> bool:
        """Check if model exists and pull if it doesn't."""
        try:
            # Check available models
            response = requests.get(f"{API_BASE_URL}/models", timeout=30)  # 30 second timeout for model list
            data = response.json()
            
            if not data["success"]:
                return False
                
            available_models = [model["name"] for model in data["models"]]
            
            if model_name not in available_models:
                # Try to pull the model
                pull_response = requests.post(f"{API_BASE_URL}/models/pull/{model_name}", timeout=600)  # 10 minute timeout for model pull
                return pull_response.json()["success"]
                
            return True
        except requests.exceptions.Timeout:
            logger.error(f"Timeout while ensuring model exists: {model_name}")
            return False
        except Exception as e:
            logger.error(f"Error ensuring model exists: {e}")
            return False

    async def get_user_model(self, user_id: int) -> str:
        """Get the active model for a user or set up the default model."""
        if user_id not in self.active_models:
            # Try to ensure default model exists
            if await self.ensure_model_exists(DEFAULT_MODEL):
                self.active_models[user_id] = DEFAULT_MODEL
            else:
                # If default model couldn't be loaded, try to use any available model
                response = requests.get(f"{API_BASE_URL}/models")
                data = response.json()
                if data["success"] and data["models"]:
                    self.active_models[user_id] = data["models"][0]["name"]
                else:
                    raise Exception("No models available")
                    
        return self.active_models[user_id]

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a message when the command /start is issued."""
        user = update.effective_user
        try:
            model = await self.get_user_model(user.id)
            await update.message.reply_text(
                f'Hi {user.first_name}! I\'m your Ollama chatbot.\n\n'
                f'Currently using model: {model}\n\n'
                'Available commands:\n'
                '/models - List available models\n'
                '/setmodel - Select a model to chat with\n'
                '/clear - Clear chat history\n'
                '/help - Show this help message'
            )
        except Exception as e:
            await update.message.reply_text(
                f'Hi {user.first_name}! I\'m your Ollama chatbot.\n\n'
                'Error: Could not initialize default model. Please use /setmodel to choose a model.'
            )

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a message when the command /help is issued."""
        user_id = update.effective_user.id
        try:
            model = await self.get_user_model(user_id)
            model_info = f"\nCurrently using model: {model}"
        except Exception:
            model_info = "\nNo model currently selected"
            
        await update.message.reply_text(
            'Available commands:\n'
            '/models - List available models\n'
            '/setmodel - Select a model to chat with\n'
            '/clear - Clear chat history\n'
            '/help - Show this help message' + model_info
        )

    async def list_models(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """List available models."""
        try:
            response = requests.get(f"{API_BASE_URL}/models")
            data = response.json()
            
            if data["success"]:
                current_model = await self.get_user_model(update.effective_user.id)
                models_text = "Available models:\n\n"
                for model in data["models"]:
                    prefix = "► " if model["name"] == current_model else "• "
                    models_text += f"{prefix}{model['name']} ({model['size']} GB)\n"
                models_text += f"\nCurrently using: {current_model}"
                await update.message.reply_text(models_text)
            else:
                await update.message.reply_text("Failed to fetch models. Please try again later.")
        except Exception as e:
            logger.error(f"Error listing models: {e}")
            await update.message.reply_text("Error connecting to the server. Please try again later.")

    async def set_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Set the active model for the user."""
        try:
            response = requests.get(f"{API_BASE_URL}/models")
            data = response.json()
            
            if data["success"]:
                current_model = await self.get_user_model(update.effective_user.id)
                keyboard = []
                for model in data["models"]:
                    # Add a checkmark to the currently selected model
                    name = f"✓ {model['name']}" if model["name"] == current_model else model["name"]
                    keyboard.append([InlineKeyboardButton(name, callback_data=f"model:{model['name']}")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text("Please select a model:", reply_markup=reply_markup)
            else:
                await update.message.reply_text("Failed to fetch models. Please try again later.")
        except Exception as e:
            logger.error(f"Error setting model: {e}")
            await update.message.reply_text("Error setting the model.")

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle button callbacks."""
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith("model:"):
            model_name = query.data.split(":")[1]
            if await self.ensure_model_exists(model_name):
                self.active_models[query.from_user.id] = model_name
                await query.edit_message_text(f"Model set to: {model_name}")
            else:
                await query.edit_message_text(f"Failed to set model to {model_name}. Please try again.")

    async def clear_chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Clear chat history for the user."""
        try:
            user_id = str(update.effective_user.id)
            response = requests.post(f"{API_BASE_URL}/chat/clear/{user_id}")
            data = response.json()
            
            if data["success"]:
                await update.message.reply_text("Chat history cleared!")
            else:
                await update.message.reply_text("Failed to clear chat history. Please try again.")
        except Exception as e:
            logger.error(f"Error clearing chat: {e}")
            await update.message.reply_text("Error clearing the chat.")
    

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle user messages."""
        user_id = update.effective_user.id

        try:
            model = await self.get_user_model(user_id)
    
            # Show typing indicator
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action="typing"
            )
    
            try:
                response = requests.post(
                    f"{API_BASE_URL}/chat",
                    json={
                        "model": model,
                        "message": update.message.text,
                        "session_id": str(user_id)
                    },
                    timeout=self.request_timeout
                )
                
                if not response.ok:
                    logger.error(f"HTTP error {response.status_code}: {response.text}")
                    await update.message.reply_text(
                        f"Server error: HTTP {response.status_code}. Please try again later."
                    )
                    return

                data = response.json()
            except requests.exceptions.Timeout:
                logger.error("Request timed out while waiting for model response")
                await update.message.reply_text(
                    "The request timed out while generating the response. This can happen with very long responses. Please try again or try breaking your request into smaller parts."
                )
                return
            except requests.exceptions.ConnectionError:
                logger.error("Connection error to Flask backend")
                await update.message.reply_text(
                    "Could not connect to the model server. Please ensure the server is running."
                )
                return
            except Exception as e:
                logger.error(f"Error making request to Flask backend: {e}")
                await update.message.reply_text(
                    "An error occurred while communicating with the model server. Please try again later."
                )
                return

            if data["success"]:
                response_text = data["response"]
                
                # Split into chunks but preserve Markdown formatting
                chunks = self._split_text_preserve_markdown(response_text)
            
                for i, chunk in enumerate(chunks):
                    if i > 0:
                        # Keep showing typing indicator between chunks
                        await context.bot.send_chat_action(
                            chat_id=update.effective_chat.id,
                            action="typing"
                        )
                        await asyncio.sleep(1)
                    
                    try:
                        # Escape special characters for MarkdownV2 but preserve code blocks
                        formatted_chunk = self._escape_markdown_v2(chunk)
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text=formatted_chunk,
                            parse_mode='MarkdownV2'
                        )
                    except Exception as markdown_error:
                        logger.error(f"MarkdownV2 parsing error: {markdown_error}")
                        # Fallback to plain text if markdown fails
                        try:
                            await context.bot.send_message(
                                chat_id=update.effective_chat.id,
                                text=chunk
                            )
                        except Exception as fallback_error:
                            logger.error(f"Error sending message chunk: {fallback_error}")
                            await update.message.reply_text(
                                "Failed to send part of the response. The message might be too long or contain invalid characters."
                            )
                            break
            else:
                error_msg = data.get("error", "Unknown error")
                logger.error(f"Error from model server: {error_msg}")
                await update.message.reply_text(
                    f"The model encountered an error: {error_msg}"
                )
        except Exception as e:
            logger.error(f"Unexpected error in handle_message: {e}", exc_info=True)
            await update.message.reply_text(
                "An unexpected error occurred. Please try again later."
            )

    def _split_text_preserve_markdown(self, text: str) -> list:
        """Split text into chunks while preserving Markdown code blocks."""
        MAX_MESSAGE_LENGTH = 4000  # Slightly reduced from 4096 for safety
    
        # If text is short enough, return it as a single chunk
        if len(text) <= MAX_MESSAGE_LENGTH:
            return [text]
    
        chunks = []
        remaining_text = text
    
    # Process the text ensuring code blocks aren't split
        while remaining_text:
            if len(remaining_text) <= MAX_MESSAGE_LENGTH:
                chunks.append(remaining_text)
                break
        
        # Find all code block positions
            code_block_starts = [m.start() for m in re.finditer(r'```', remaining_text)]
        
        # If no code blocks or only one marker, just split normally
            if len(code_block_starts) < 2:
                cut_point = MAX_MESSAGE_LENGTH
            
            # Try to cut at paragraph boundaries
                paragraph_boundary = remaining_text.rfind('\n\n', 0, cut_point)
                if paragraph_boundary > MAX_MESSAGE_LENGTH // 2:
                    cut_point = paragraph_boundary + 2
                else:
                # Try to cut at sentence boundaries
                    sentence_boundary = remaining_text.rfind('. ', 0, cut_point)
                    if sentence_boundary > MAX_MESSAGE_LENGTH // 2:
                        cut_point = sentence_boundary + 2
            
                chunks.append(remaining_text[:cut_point])
                remaining_text = remaining_text[cut_point:]
                continue
        
        # Process code blocks
            i = 0
            while i < len(code_block_starts) - 1:
                start = code_block_starts[i]
                end = code_block_starts[i+1]
            
            # If a code block would be split by our max length
                if start < MAX_MESSAGE_LENGTH and end > MAX_MESSAGE_LENGTH:
                # Find the last safe cut point before the code block
                    cut_point = remaining_text.rfind('\n\n', 0, start)
                    if cut_point <= 0 or cut_point < MAX_MESSAGE_LENGTH // 2:
                    # If no good break point, just cut at start of code block
                        cut_point = start
                
                    chunks.append(remaining_text[:cut_point])
                    remaining_text = remaining_text[cut_point:]
                    break
            
                i += 2  # Move to next potential code block
        
        # If we haven't added a chunk in this iteration, cut normally
            if len(remaining_text) > MAX_MESSAGE_LENGTH and i >= len(code_block_starts) - 1:
                cut_point = MAX_MESSAGE_LENGTH
                paragraph_boundary = remaining_text.rfind('\n\n', 0, cut_point)
                if paragraph_boundary > MAX_MESSAGE_LENGTH // 2:
                    cut_point = paragraph_boundary + 2
            
                chunks.append(remaining_text[:cut_point])
                remaining_text = remaining_text[cut_point:]
    
        return chunks

    def _escape_markdown_v2(self, text: str) -> str:
        """
        Escape special characters for Telegram's MarkdownV2 format while preserving code blocks.
        """
        # Split text by code blocks
        parts = text.split("```")
        
        # Characters that need to be escaped in MarkdownV2 outside of code blocks
        escape_chars = '_*[]()~`>#+-=|{}.!'
        
        for i in range(len(parts)):
            # Even indices are outside code blocks, odd indices are inside
            if i % 2 == 0:
                # Escape special characters outside code blocks
                for char in escape_chars:
                    parts[i] = parts[i].replace(char, f"\\{char}")
            else:
                # For code blocks, add language if specified
                code_lines = parts[i].strip().split('\n', 1)
                if len(code_lines) > 1 and code_lines[0]:
                    # If there's a language specified
                    lang = code_lines[0]
                    code = code_lines[1]
                    parts[i] = f"{lang}\n{code}"
                
        # Rejoin the text with code block markers
        return "```".join(parts)


def main() -> None:
    """Start the bot."""
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN environment variable is not set!")
        return

    bot = OllamaTelegramBot()
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help))
    application.add_handler(CommandHandler("models", bot.list_models))
    application.add_handler(CommandHandler("setmodel", bot.set_model))
    application.add_handler(CommandHandler("clear", bot.clear_chat))
    application.add_handler(CallbackQueryHandler(bot.button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))

    # Start the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

