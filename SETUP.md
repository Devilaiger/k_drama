# K-Drama Bot - Setup Guide

## ✅ Prerequisites Installed

All Python dependencies have been installed in the virtual environment:
- ✅ pyrogram (Telegram bot framework)
- ✅ tgcrypto (Telegram encryption)
- ✅ pymongo (MongoDB driver)
- ✅ motor (Async MongoDB)
- ✅ flask (Web framework for keep-alive)
- ✅ python-dotenv (Environment variables)
- ✅ rapidfuzz (Fuzzy search)
- ✅ And all other required packages

## 🚀 Quick Start

### Step 1: Activate Virtual Environment

```bash
# On Linux/Mac:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

You should see `(venv)` in your terminal prompt.

### Step 2: Setup Environment File

1. Copy the example env file:
```bash
cp .env.example .env
```

2. Edit `.env` and fill in your credentials:
```bash
nano .env
```

### Step 3: Get Required Credentials

#### A. Telegram API Credentials
1. Go to https://my.telegram.org/apps
2. Log in with your Telegram account
3. Create an app (if not exists)
4. Copy **API_ID** and **API_HASH** to `.env`

#### B. Bot Token
1. Open Telegram
2. Search for @BotFather
3. Send `/newbot` command
4. Follow instructions to create your bot
5. Copy the **BOT_TOKEN** to `.env`

#### C. Your Admin ID
1. Open Telegram
2. Search for @userinfobot
3. Send `/start`
4. It will show your **Telegram user ID**
5. Copy to **ADMIN_ID** in `.env`

#### D. Storage Channel (for storing media)
1. Create a private Telegram channel
2. Add your bot as an admin with all permissions
3. Send a message in the channel
4. Forward that message to @rawdatabot
5. Copy the channel ID (format: -100123456789)
6. Put in **STORAGE_CHANNEL_ID** in `.env`

#### E. MongoDB Database
Choose one option:

**Option A: Local MongoDB** (if installed)
```
MONGO_URI=mongodb://localhost:27017/k_drama_bot
```

**Option B: MongoDB Atlas (Free Cloud)**
1. Go to https://www.mongodb.com/cloud/atlas
2. Create a free account
3. Create a free tier cluster
4. Click "Connect" → "Connect your application"
5. Copy the connection string
6. Paste as MONGO_URI in `.env`
7. Replace `<password>` with your database user password
8. Replace `myFirstDatabase` with `k_drama_bot`

Example:
```
MONGO_URI=mongodb+srv://username:password@cluster0.abc123.mongodb.net/k_drama_bot?retryWrites=true&w=majority
```

#### F. Required Channels
1. Create channels for users to join (e.g., announcement channel, support channel)
2. Add them to REQUIRED_CHANNELS in `.env`
3. Add your bot to all these channels

### Step 4: Your .env File Should Look Like:

```env
# TELEGRAM
API_ID=123456789
API_HASH=abcdef1234567890abcdef1234567890
BOT_TOKEN=123456789:ABCDefGhIjKLmnOPqRstuVWxyz_1234567890

# ADMIN
ADMIN_ID=987654321

# CHANNELS
STORAGE_CHANNEL_ID=-100123456789
MAIN_CHANNEL_LINK=https://t.me/your_channel
REQUIRED_CHANNELS=@your_required_channel

# DATABASE
MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/k_drama_bot?retryWrites=true&w=majority
```

### Step 5: Run the Bot

```bash
# Make sure virtual environment is activated
source venv/bin/activate

# Run the bot
python -m bot.main
```

You should see startup logs like:
```
2026-05-21 06:00:00,000 - bot.main - INFO - Starting K-Drama Bot...
...
2026-05-21 06:00:05,000 - bot.main - INFO - Bot started successfully!
```

### Step 6: Test the Bot

1. Open Telegram
2. Search for your bot (using the username you gave it)
3. Send `/start` command
4. The bot should respond with welcome message

## 📋 Troubleshooting

### "externally-managed-environment" Error
✅ **Already Fixed** - Virtual environment created

If you see this error, use virtual environment:
```bash
source venv/bin/activate
pip install -r requirements.txt
```

### "No module named 'bot'"
- Make sure you're in the `/home/devil/k_drama` directory
- Make sure virtual environment is activated: `source venv/bin/activate`
- Check that `bot/` folder exists in current directory

### MongoDB Connection Error
- Check if MongoDB is running (local) or accessible (cloud)
- Verify MONGO_URI in .env is correct
- Test connection: `python -c "import pymongo; print('OK')"`

### Bot Not Responding
1. Check bot token is correct (get new one from BotFather if needed)
2. Check API_ID and API_HASH are correct
3. Check bot is added to all REQUIRED_CHANNELS
4. Check your user ID (ADMIN_ID) is correct

### "Chat not found" or "Channel not found"
- Verify channel IDs are correct
- Make sure bot has access to those channels
- Check channel still exists and bot hasn't been removed

## 📁 Project Structure

```
k_drama/
├── venv/                    # Virtual environment (created by setup)
├── bot/
│   ├── handlers/           # Command handlers
│   ├── services/           # Business logic
│   ├── database/           # Database operations
│   ├── utils/              # Utility functions
│   ├── config.py           # Configuration loader
│   └── main.py             # Bot entry point
├── requirements.txt        # Python dependencies
├── .env.example           # Environment template (fill this out)
├── .env                   # Your actual secrets (DON'T commit)
└── README.md              # Project documentation
```

## 🔐 Security Notes

1. **Never commit .env file** - It contains your bot token and credentials
2. **Keep API_HASH and BOT_TOKEN private**
3. **Don't share your ADMIN_ID publicly**
4. **Regenerate bot token if compromised** (use BotFather's /token command)

## 📚 Commands Available

Once the bot is running:

- `/start` - Main menu (in private chat)
- `/search <name>` - Search for dramas
- `/get_links` - Browse all shows
- `/get_links <name>` - Get links for specific show
- `/favorites` - Your favorite shows
- `/history` - Watch history
- `/recent_updates` - Latest updates
- `/request <name>` - Request a drama
- `/help` - Help message

## 🆘 Need Help?

1. Check logs for error messages
2. Verify all credentials in .env are correct
3. Test MongoDB connection separately
4. Ensure bot has all required permissions in channels
5. Check @BotFather for bot status

## ✨ You're Ready!

Once .env is configured and bot is running:
- Users can use `/start` in private chat
- Users can use commands in groups (with proper permissions)
- Bot stores data in MongoDB
- All features work (search, favorites, etc.)

Happy K-Drama sharing! 🎬
