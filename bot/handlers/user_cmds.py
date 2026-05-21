import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from bot.config import ADMIN_IDS
from bot.utils.ui import reply_with_ui, main_keyboard, safe_answer
from bot.services.verification import (
    is_banned,
    is_member_in_all_channels, get_missing_channels,
    live_check_and_sync, get_leave_count, is_warned,
    set_warned, ban_user, get_required_channel_info
)
from bot.services.favorites import get_user_favorites
from bot.services.updates import get_recent_updates, get_formatted_recent_updates

logger = logging.getLogger(__name__)

async def _build_join_buttons(client, missing_channels: list) -> list:
    """
    Build join buttons for only the channels the user has not joined yet.
    missing_channels is a list of (config_name, numeric_id) tuples.
    numeric_id may be None if channels not resolved yet — falls back to config_name.
    """
    buttons = []
    logger.debug(f"_build_join_buttons called with {len(missing_channels)} missing channels")
    for config_name, _numeric_id in missing_channels:
        info = get_required_channel_info(config_name)
        buttons.append([InlineKeyboardButton(f"Join {info['title']}", url=info["url"])])
    buttons.append([InlineKeyboardButton("I Joined", callback_data="joined")])
    return buttons

async def _gate_check(client, user_id: int, reply_fn) -> bool:
    """
    Central gate: check ban then channel membership.
    Always does a live Telegram API check — not DB-only.
    Reason: Telegram does not reliably send leave events for channels,
    so DB can show 'member' even after user left. Live check is the
    only reliable way to catch this.
    Admins always bypass all checks.
    """
    if user_id in ADMIN_IDS:
        return True

    if await is_banned(user_id):
        bot_me = await client.get_me()
        await reply_fn(
            "⛔ **You are banned from using this bot.**\n\n"
            "You repeatedly joined and left the required channels.\n"
            "Contact admin to appeal your ban.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "📩 Contact Admin",
                    url=f"https://t.me/{bot_me.username}?start=support"
                )
            ]])
        )
        return False

    # Always live check — catches users who left after being verified.
    # _handle_detected_leave inside live_check_and_sync increments leave_count
    # when a leave is detected, enabling abuse detection below.
    missing = await live_check_and_sync(client, user_id)

    if missing:
        # Abuse detection — runs here because Telegram leave events are unreliable
        leave_count = await get_leave_count(user_id)
        
        logger.info(f"User {user_id} is missing channels: leave_count={leave_count}, missing={len(missing)} channels")

        if leave_count >= 4:
            # Check if already banned (may have been banned mid-session)
            if not await is_banned(user_id):
                try:
                    tg_user = await client.get_users(user_id)
                    username = tg_user.username or ""
                    full_name = f"{tg_user.first_name or ''} {tg_user.last_name or ''}".strip()
                except Exception:
                    username, full_name = "", str(user_id)
                await ban_user(user_id, username, full_name, leave_count)
                bot_me = await client.get_me()
                logger.info(f"User {user_id} banned due to repeated leaving")
                await reply_fn(
                    "⛔ **You have been banned from using this bot.**\n\n"
                    "You repeatedly joined and left the required channels.\n"
                    "Contact admin to appeal your ban.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            "📩 Contact Admin",
                            url=f"https://t.me/{bot_me.username}?start=support"
                        )
                    ]])
                )
                return False

        elif leave_count >= 3 and not await is_warned(user_id):
            await set_warned(user_id)
            # Send warning as separate message, still show join buttons
            try:
                logger.info(f"User {user_id} warned due to repeated leaving")
                await client.send_message(
                    user_id,
                    "⚠️ **Warning!**\n\n"
                    "You have repeatedly joined and left the required channels.\n"
                    "If you do this **one more time**, you will be permanently "
                    "banned from using this bot."
                )
            except Exception as e:
                logger.warning(f"Failed to send warning to user {user_id}: {e}")

        try:
            logger.info(f"Building join buttons for user {user_id} for {len(missing)} channels")
            buttons = await _build_join_buttons(client, missing)
            logger.info(f"Sending join message with {len(buttons)} button rows to user {user_id}")
            await reply_fn(
                "🎬 **Welcome to K-Drama Bot!**\n\n"
                "To use the bot please join our required channels first:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        except Exception as e:
            logger.exception(f"Failed to send join buttons message to user {user_id}: {e}")
        return False

    return True

async def favorites_cmd(client: Client, message: Message):
    if not await is_member_in_all_channels(message.from_user.id):
        return await message.reply("Please join our channels first!")
        
    favs = await get_user_favorites(message.from_user.id)
    if not favs:
        return await message.reply("⭐ Your favorites list is empty.")

    me = await client.get_me()
    bot_username = me.username
    btn_rows = []
    for f in favs:
        category_slug = f['category'].lower().replace(" ", "_")
        btn_rows.append([InlineKeyboardButton(
            f"{f['show_name']} ({f['category']})",
            url=f"https://t.me/{bot_username}?start={category_slug}__{f['show_slug']}"
        )])
        
    await message.reply("⭐ **Your Favorites:**", reply_markup=InlineKeyboardMarkup(btn_rows))

async def recent_updates_cmd(client: Client, message: Message):
    updates = await get_recent_updates(1000)
    formatted = get_formatted_recent_updates(updates)
    
    if not formatted:
        return await message.reply("📭 No recent updates available.")
        
    text = "🔥 **Recent Updates:**\n\n"
    for idx, item in enumerate(formatted, 1):
        text += f"{idx}. {item}\n\n"
        
    await message.reply(text)

from bot.services.favorites import is_favorited
from bot.services.search import search_drama

from bot.services.shows import get_category_shows, _LEGACY_CATEGORY_MAP
from bot.database.mongo import db
from bot.services.users import upsert_user, get_watch_history
from bot.services.requests import submit_request
from bot.utils.ui import show_loading_sticker
from bot.utils.ids import decode_show_slug, make_id, normalize_show_slug
from bot.utils.logger import track_performance
from bot.utils.behavior import track_behavior

@track_performance("search_drama")
async def search_cmd(client: Client, message: Message):
    """Handle /search command. Now available globally in groups and private."""
    query = ""
    # Support /search <query> inline
    if len(message.command) > 1:
        query = message.text.split(" ", 1)[1].strip()
        
    loader = await show_loading_sticker(client, message.chat.id)
    
    # Track user
    await upsert_user(client, message.from_user, message.chat)
    
    if not query:
        if loader: await loader.delete()
        return await message.reply("🔍 Usage: `/search drama_name`")
    
    try:
        results = await search_drama(query, limit=10)
        if loader: await loader.delete()
        asyncio.create_task(track_behavior(
            message.from_user.id, 'search',
            {'query': query, 'results_count': len(results), 'source': 'command'}
        ))
        if not results:
            return await message.reply("❌ No results found. Try different keywords.")

        me = await client.get_me()  # Fetch once, not per-result
        bot_username = me.username

        text = f"🔍 **Search Results for:** `{query}`\n\n"
        buttons = []
        for doc in results:
            title = doc.get("show_name", "Unknown")
            cat = doc.get("category", "KDrama")
            slug = normalize_show_slug(title)
            cat_slug = cat.lower().replace(" ", "_")
            
            url = f"https://t.me/{bot_username}?start={cat_slug}__{slug}"
            buttons.append([InlineKeyboardButton(f"▶ {title} ({cat})", url=url)])
        
        # Handle topic-based groups: preserve message_thread_id
        reply_kwargs = {"reply_markup": InlineKeyboardMarkup(buttons)}
        if message.message_thread_id:
            reply_kwargs["message_thread_id"] = message.message_thread_id
            
        await message.reply(text, **reply_kwargs)
    except Exception as e:
        if loader: await loader.delete()
        logger.exception(f"search_cmd error: {e}")
        await message.reply("❌ Error performing search.")

# Support appeal state: user_id -> True
_support_waiting = {}

async def start_cmd(client: Client, message: Message):
    """Handle /start command with ban gate, dynamic join gate, deep linking."""
    loader = await show_loading_sticker(client, message.chat.id)
    await upsert_user(client, message.from_user, message.chat)

    user_id = message.from_user.id
    args = message.text.split()
    param = args[1] if len(args) > 1 else None

    # Support appeal deep link
    if param == "support":
        if loader: await loader.delete()
        if await is_banned(user_id):
            _support_waiting[user_id] = True
            return await message.reply(
                "📩 **Appeal your ban**\n\n"
                "Please type your message below and we will forward it to the admin."
            )
        return await message.reply("✅ You are not banned. Use /start to browse.")

    # Ban + membership gate
    if loader: await loader.delete()
    try:
        if not await _gate_check(client, user_id, message.reply):
            return
    except Exception as e:
        logger.exception(f"_gate_check failed for user {user_id}: {e}")
        try:
            await message.reply("❌ An error occurred. Please try again.")
        except Exception as e2:
            logger.exception(f"Failed to send error message: {e2}")
        return

    # Deep link handling
    if param and "__" in param:
        try:
            category_part, show_part = param.split("__", 1)
            category_key = category_part.replace("_", " ").lower().strip()

            # Resolve category: query DB distinct values, normalize to canonical name
            raw_categories = await db.shows.distinct("category")
            matched_category = None
            for c in raw_categories:
                canonical = _LEGACY_CATEGORY_MAP.get(c, c)
                if canonical.lower().strip() == category_key:
                    matched_category = canonical
                    break

            if matched_category:
                decoded_show_name = decode_show_slug(show_part).strip()
                # Fetch show list for this category from L1 cache
                cat_data = await get_category_shows(matched_category)
                all_show_names = [item["show_name"] for item in cat_data]

                matched_show = None
                lower = decoded_show_name.lower()
                for name in all_show_names:
                    if name.lower() == lower:
                        matched_show = name
                        break
                if not matched_show:
                    for name in all_show_names:
                        if lower in name.lower():
                            matched_show = name
                            break

                if matched_show:
                    shows = sorted(all_show_names)
                    if matched_show in shows:
                        shows.remove(matched_show)
                    shows.insert(0, matched_show)
                    page_shows = shows[:10]
                    total_pages = (len(shows) + 9) // 10
                    cat_id = await make_id(matched_category)
                    buttons = []
                    for s in page_shows:
                        emoji = "⭐" if s == matched_show else "🎬"
                        show_id = await make_id(s)
                        buttons.append([InlineKeyboardButton(f"{emoji} {s}", callback_data=f"show|{cat_id}|{show_id}")])
                    if total_pages > 1:
                        star_id = await make_id(matched_show)
                        buttons.append([
                            InlineKeyboardButton(f"📄 1/{total_pages}", callback_data="noop"),
                            InlineKeyboardButton("➡️ Next", callback_data=f"page|{cat_id}|2|{star_id}")
                        ])
                    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_main")])
                    return await message.reply(
                        text=f"📂 Category: **{matched_category}**\n\nSelect a show:",
                        reply_markup=InlineKeyboardMarkup(buttons)
                    )
        except Exception as e:
            logger.exception(f"start_cmd deep-link decode error: {e}")

    await reply_with_ui(message, "🎬 **Welcome back!**\n\nChoose a category to browse:", reply_markup=await main_keyboard())


async def support_text_handler(client: Client, message: Message):
    """Forward ban appeal messages to admins."""
    user_id = message.from_user.id
    if user_id not in _support_waiting:
        return
    _support_waiting.pop(user_id)
    full_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
    username = message.from_user.username or "No username"
    # Deduplicate admin IDs so appeal is never sent twice to the same admin
    seen = set()
    for admin in ADMIN_IDS:
        if admin in seen or admin == 0:
            continue
        seen.add(admin)
        try:
            await client.send_message(
                admin,
                f"📩 **Ban Appeal**\n\n"
                f"👤 {full_name} (@{username}) [`{user_id}`]\n\n"
                f"💬 {message.text}"
            )
        except Exception:
            pass
    await message.reply("✅ Your message has been forwarded to the admin.")
    # Stop propagation so report_handlers text catcher doesn't also fire
    message.stop_propagation()

@track_performance("get_links_cmd")
async def get_links_cmd(client: Client, message: Message):
    """Handle /get_links command - show links for dramas."""
    query = ""
    # Support /get_links <show_name> to search for specific show links
    if len(message.command) > 1:
        query = message.text.split(" ", 1)[1].strip()
    
    loader = await show_loading_sticker(client, message.chat.id)
    
    # Track user
    await upsert_user(client, message.from_user, message.chat)
    
    try:
        if query:
            # Specific show search
            results = await search_drama(query, limit=10)
            if loader: await loader.delete()
            
            if not results:
                return await message.reply(f"❌ No shows found matching '{query}'")
            
            me = await client.get_me()
            bot_username = me.username
            
            text = f"🔗 **Links for '{query}':**\n\n"
            buttons = []
            for doc in results:
                title = doc.get("show_name", "Unknown")
                cat = doc.get("category", "KDrama")
                slug = normalize_show_slug(title)
                cat_slug = cat.lower().replace(" ", "_")
                url = f"https://t.me/{bot_username}?start={cat_slug}__{slug}"
                
                buttons.append([
                    InlineKeyboardButton(title, url=url)
                ])
            
            reply_kwargs = {"reply_markup": InlineKeyboardMarkup(buttons)}
            if message.message_thread_id:
                reply_kwargs["message_thread_id"] = message.message_thread_id
            await message.reply(text, **reply_kwargs)
        else:
            # List all shows with pagination (page 1 by default)
            # Fetch all categories and shows
            raw_categories = await db.shows.distinct("category")
            
            if not raw_categories:
                if loader: await loader.delete()
                return await message.reply("❌ No shows available.")
            
            # Build list of all shows across all categories
            all_shows_with_cat = []
            for raw_cat in raw_categories:
                canonical_cat = _LEGACY_CATEGORY_MAP.get(raw_cat, raw_cat)
                cat_shows = await get_category_shows(canonical_cat)
                for show_doc in cat_shows:
                    all_shows_with_cat.append({
                        "show_name": show_doc.get("show_name", ""),
                        "category": canonical_cat
                    })
            
            if not all_shows_with_cat:
                if loader: await loader.delete()
                return await message.reply("❌ No shows available.")
            
            # Sort shows by name for consistent pagination
            all_shows_with_cat.sort(key=lambda x: x["show_name"].lower())
            
            # Pagination: 10 shows per page
            page = 1
            per_page = 10
            total_pages = (len(all_shows_with_cat) + per_page - 1) // per_page
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            page_shows = all_shows_with_cat[start_idx:end_idx]
            
            if loader: await loader.delete()
            
            me = await client.get_me()
            bot_username = me.username
            
            text = f"📺 **All Shows** - Page {page}/{total_pages}\n\n"
            buttons = []
            for show_doc in page_shows:
                title = show_doc.get("show_name", "Unknown")
                cat = show_doc.get("category", "KDrama")
                slug = normalize_show_slug(title)
                cat_slug = cat.lower().replace(" ", "_")
                url = f"https://t.me/{bot_username}?start={cat_slug}__{slug}"
                
                # Display: show name (left), link (right)
                buttons.append([
                    InlineKeyboardButton(f"🎬 {title}", url=url)
                ])
            
            # Add pagination controls
            if total_pages > 1:
                nav_buttons = []
                if page > 1:
                    nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"getlinks_page|{page-1}"))
                nav_buttons.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
                if page < total_pages:
                    nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"getlinks_page|{page+1}"))
                buttons.append(nav_buttons)
            
            reply_kwargs = {"reply_markup": InlineKeyboardMarkup(buttons)}
            if message.message_thread_id:
                reply_kwargs["message_thread_id"] = message.message_thread_id
            await message.reply(text, **reply_kwargs)
            
            asyncio.create_task(track_behavior(
                message.from_user.id, 'get_links',
                {'page': page, 'total_shows': len(all_shows_with_cat), 'source': 'command'}
            ))
            
    except Exception as e:
        if loader: await loader.delete()
        logger.exception(f"get_links_cmd error: {e}")
        await message.reply("❌ Error fetching show links.")

async def request_cmd(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply("Usage: /request <drama name>")
    drama_name = " ".join(message.command[1:])
    await submit_request(message.from_user.id, drama_name)
    await message.reply(f"✅ Your request for **{drama_name}** has been submitted!")

    # Duplicate search_cmd removed to respect the primary global search_cmd at line 51

async def history_cmd(client: Client, message: Message):
    loader = await show_loading_sticker(client, message.chat.id)
    try:
        history = await get_watch_history(message.from_user.id)
        if loader: await loader.delete()
        
        if not history:
            return await message.reply("📜 Your watch history is empty.")
        text = "📜 **Your Watch History:**\n\n"
        for item in history:
            text += f"• {item}\n"
        await message.reply(text)
    except Exception as e:
        if loader: await loader.delete()
        logger.exception(f"history_cmd error: {e}")
        await message.reply("❌ Error loading history.")

@track_performance("my_favorites_cb")
async def my_favorites_cb(client: Client, callback_query: CallbackQuery):
    await safe_answer(callback_query)
    callback_query.message.from_user = callback_query.from_user
    await favorites_cmd(client, callback_query.message)

@track_performance("global_metadata_harvester")
async def silent_metadata_harvester(client: Client, message: Message):
    """Silently harvests user data on every witnessed message globally without interrupting flow."""
    if getattr(message, "from_user", None):
        await upsert_user(client, message.from_user, message.chat)

def register_user_handlers(app: Client):
    app.on_message(filters.incoming, group=-2)(silent_metadata_harvester)
    app.on_message(filters.command("start") & filters.private)(start_cmd)
    app.on_message(filters.command("help") & filters.private)(lambda c, m: m.reply(
        "📚 **K-Drama Bot Help**\n\n"
        "/start - Browse categories\n"
        "/search - Find dramas\n"
        "/get_links - Show links for dramas\n"
        "/favorites - Your list\n"
        "/recent_updates - New content\n"
        "/request - Request a drama\n"
        "/history - Watch history"
    ))
    app.on_message(filters.command("favorites") & filters.private)(favorites_cmd)
    app.on_callback_query(filters.regex("^my_favorites$"))(my_favorites_cb)
    app.on_message(filters.command("recent_updates") & filters.private)(recent_updates_cmd)
    app.on_message(filters.command("request") & filters.private)(request_cmd)
    app.on_message(filters.command("history") & filters.private)(history_cmd)
    app.on_message(filters.command("search"))(search_cmd)
    app.on_message(filters.command("get_links"))(get_links_cmd)
    # Support appeal: catches text from users in _support_waiting state at group=10
    app.on_message(filters.text & filters.private & ~filters.regex(r"^/"), group=10)(support_text_handler)
