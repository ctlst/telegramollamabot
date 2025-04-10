#!/usr/bin/env python3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import requests
import os
import json
import logging
from typing import Dict, Any

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
        
    async def ensure_model_exists(self, model_name: str) -> bool:
        """Check if model exists and pull if it doesn't."""
        try:
            # Check available models
            response = requests.get(f"{API_BASE_URL}/models")
            data = response.json()
            
            if not data["success"]:
                return False
                
            available_models = [model["name"] for model in data["models"]]
            
            if model_name not in available_models:
                # Try to pull the model
                pull_response = requests.post(f"{API_BASE_URL}/models/pull/{model_name}")
                return pull_response.json()["success"]
                
            return True
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
            
            response = requests.post(
                f"{API_BASE_URL}/chat",
                json={
                    "model": model,
                    "message": update.message.text,
                    "session_id": str(user_id)
                }
            )
            
            data = response.json()
            if data["success"]:
                response_text = data["response"]
                #split into chunks
                chunks = self._split_text(response_text)

                for i, chunk in enumerate(chunks):
                    if i > 0:
                        await asyncio.sleep(5) #add delay between messages

                    await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text=chunk,
                            parse_mode='Markdown'
                        )
            else:
                await update.message.reply_text(
                    "Sorry, I encountered an error. Please try again."
                )
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await update.message.reply_text(
                "Error handling the message."
            )
    def _split_text(self, text: str) -> list[str]:
        MAX_MESSAGE_LENGTH = 4080
        chunks = []

        while len(text) > MAX_MESSAGE_LENGTH:
            chunk = text[:MAX_MESSAGE_LENGTH]
            #REMOVE WHITESPACES TO AVOID PARTIAL WORD ISSUES
            chunk = chunk.rstrip()
            chunks.append(chunk)
            text = text[MAX_MESSAGE_LENGTH:]
        if text.strip(): #add remaining text if not empty
            chunks.append(text)
        return chunks

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
