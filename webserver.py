from flask import Flask
import threading
import os
from dotenv import load_dotenv
import discord
from discord.ext import commands
import traceback

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Create the Flask app
app = Flask(__name__)

# Set up the bot
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Event to show the bot is ready
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} ({bot.user.id})')

# Example command for the bot
@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")

# The Flask web server endpoint to keep the bot alive
@app.route('/')
def home():
    return "The bot is running!"

# Function to run the Flask web server in a separate thread
def run_web_server():
    app.run(host='0.0.0.0', port=8080)

# Function to run the Discord bot in a separate thread
def run_bot():
    try:
        bot.run(BOT_TOKEN)
    except Exception as e:
        traceback.print_exc()
        print("Error while running the bot:", e)

# Running the bot and web server in parallel
if __name__ == '__main__':
    # Start the Flask web server in a separate thread
    threading.Thread(target=run_web_server).start()

    # Start the bot in the main thread
    run_bot()
