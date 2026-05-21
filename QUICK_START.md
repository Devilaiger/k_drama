# K-Drama Bot - Quick Start Guide

## 🎯 TL;DR (30 seconds)

```bash
# 1. Activate environment
source venv/bin/activate

# 2. Copy and edit env file
cp .env.example .env
nano .env  # Fill in your credentials

# 3. Run bot
python -m bot.main

# 4. Open Telegram → Search for your bot → Send /start
```

---

## 📋 Prerequisites Checklist

- ✅ Virtual environment: `/home/devil/k_drama/venv/`
- ✅ All packages installed: See list below

### Installed Packages (22 total)
```
Pyrogram 2.0.106        - Telegram bot framework
TgCrypto 1.2.5          - Telegram encryption
PyMongo 4.17.0          - MongoDB driver
Motor 3.7.1             - Async MongoDB
Flask 3.1.3             - Web framework
Python-dotenv 1.2.2     - Environment loader
RapidFuzz 3.14.5        - Fuzzy search
```

---

## 🔑 Required Credentials (in .env file)

| Variable | Type | How to Get | Example |
|----------|------|-----------|---------|
| `API_ID` | Number | https://my.telegram.org/apps | `123456789` |
| `API_HASH` | String | https://my.telegram.org/apps | `abcd1234...` |
| `BOT_TOKEN` | String | @BotFather `/newbot` | `123:ABC...` |
| `ADMIN_ID` | Number | @userinfobot `/start` | `987654321` |
| `STORAGE_CHANNEL_ID` | Number | Create channel + @rawdatabot | `-100123456` |
| `MONGO_URI` | URL | MongoDB local or Atlas | `mongodb+srv://...` |
| `REQUIRED_CHANNELS` | String | Your channel username | `@channel_name` |

---

## ⚡ Run the Bot

### In Development
```bash
# Terminal 1: Activate environment
source venv/bin/activate

# Terminal 1: Run bot
python -m bot.main

# Terminal 2: Check if bot is running
curl http://localhost:5000/ping
# Should return: "Keep-Alive Server Running"
```

### Expected Startup Output
```
2026-05-21 06:00:00,000 - bot.main - INFO - Bot starting...
2026-05-21 06:00:02,000 - bot.main - INFO - Bot started successfully!
```

---

## 🧪 Test the Bot

### Private Chat Test
1. Open Telegram
2. Search for your bot username (e.g., `@k_drama_bot`)
3. Send `/start` - Should show welcome menu
4. Send `/search korean` - Should show dramas

### Group Test
1. Create a Telegram group or channel
2. Add your bot to the group
3. Send `/search kdrama` in group - Should show results in same thread (if topic)

### Inline Search Test
1. In any chat, type: `@your_bot_username search_term`
2. Should show inline search results

---

## 🔧 Common Commands (Testing)

```bash
# While bot is running:

# Test MongoDB connection
python -c "from bot.config import MONGO_URI; print(f'MongoDB: {MONGO_URI}')"

# Check if bot token is valid
python -c "from bot.config import BOT_TOKEN; print(f'Token: {BOT_TOKEN}')"

# View all config values
python -c "from bot import config; import inspect; print(inspect.getsource(config))" | head -30
```

---

## 📁 Directory Structure

```
venv/                          # ← Virtual environment (CREATED)
├── bin/
│   ├── python                 # Python interpreter
│   ├── pip                    # Package manager
│   └── activate               # Activation script
│
bot/                           # Main bot code
├── handlers/
│   ├── user_cmds.py          # Commands (search, get_links)
│   ├── inline.py             # Inline search handler
│   ├── callbacks.py           # Button click handlers
│   └── ...
├── services/
│   ├── search.py             # Search logic
│   ├── shows.py              # Show data
│   └── ...
├── config.py                 # Config loader (reads .env)
└── main.py                   # Bot entry point

.env.example                   # ← Template (copy to .env and edit)
.env                          # ← Your actual config (DON'T commit!)
SETUP.md                       # Detailed setup guide
QUICK_START.md                 # This file
requirements.txt               # Python packages list
```

---

## ⚠️ Important Notes

1. **Virtual Environment Required**: Always run `source venv/bin/activate` first
2. **Don't Commit .env**: Add to .gitignore (already done)
3. **Bot Permissions**: Make sure bot is admin in all required channels
4. **MongoDB**: Must be running (local) or accessible (cloud)
5. **Keep Secrets Safe**: Don't share API_HASH or BOT_TOKEN

---

## 🐛 Troubleshooting

### "No module named bot"
```bash
# Make sure you're in the right directory
cd /home/devil/k_drama

# Make sure venv is activated
source venv/bin/activate

# Check current directory
pwd  # Should show: /home/devil/k_drama
```

### Bot doesn't respond
1. Check if bot is running (no errors on startup)
2. Verify BOT_TOKEN in .env is correct
3. Check bot is joined to REQUIRED_CHANNELS
4. Check your user ID matches ADMIN_ID

### "ModuleNotFoundError: No module named 'pyrogram'"
```bash
# Virtual environment not activated
source venv/bin/activate

# Then try again
python -m bot.main
```

### MongoDB Connection Error
```bash
# Test MongoDB connection
python -c "import pymongo; client = pymongo.MongoClient('MONGO_URI'); print('Connected!')"

# If local:
mongod --version  # Check if installed
sudo systemctl start mongod  # Start MongoDB service
```

---

## 📊 Features Ready to Test

### ✅ New Features (Just Added)
- `/get_links` - Browse all shows with pagination
- `/get_links <name>` - Get specific show links
- `/search` - Works in topic-based groups now
- Inline search - 2 keystroke minimum (was 3)
- Bot inline consistency - Always appears

### ✅ Existing Features
- `/start` - Main menu
- `/search <name>` - Find dramas
- `/favorites` - Saved shows
- `/history` - Watch history
- `/request <name>` - Request drama
- Group support (with topics)
- Inline search mode

---

## 🚀 Next Steps

1. **Fill out .env file** with your credentials
2. **Start the bot** with `python -m bot.main`
3. **Test in Telegram** - Send `/start` to your bot
4. **Invite users** to test all features
5. **Monitor logs** for any errors

---

## 📞 Support

If you encounter issues:
1. Check the logs (should show clear error messages)
2. Review SETUP.md for detailed instructions
3. Verify all .env values are correct
4. Check bot has proper permissions
5. Ensure MongoDB is accessible

Good luck! 🎬✨
