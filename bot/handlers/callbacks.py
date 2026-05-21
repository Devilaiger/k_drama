import logging
import asyncio
from pyrogram import filters
from pyrogram.client import Client
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import MessageNotModified, FloodWait

from bot.utils.ui import main_keyboard, auto_delete_message, safe_answer, update_media_or_text
from bot.utils.ids import make_id, resolve_id, normalize_show_slug
from bot.utils.logger import track_performance
from bot.services.shows import get_category_shows, get_show_detail, increment_view, _LEGACY_CATEGORY_MAP
from bot.services.favorites import add_favorite, remove_favorite, is_favorited
from bot.services.sessions import create_group_session, get_group_session
from bot.config import ADMIN_IDS, get_category_emoji
from bot.utils.behavior import track_behavior
logger = logging.getLogger(__name__)


async def _get_show_doc(category: str, raw_show_name: str):
    """Get (canonical_name, show_doc) with fuzzy name-match fallback."""
    doc = await get_show_detail(category, raw_show_name)
    if doc:
        return doc.get("show_name", raw_show_name), doc
    # Fallback: fuzzy match via category show list
    shows = await get_category_shows(category)
    lower = raw_show_name.lower()
    for item in shows:
        if item["show_name"].lower() == lower:
            doc = await get_show_detail(category, item["show_name"])
            return item["show_name"], doc
    for item in shows:
        if lower in item["show_name"].lower():
            doc = await get_show_detail(category, item["show_name"])
            return item["show_name"], doc
    return None, None

# --- UTILS ---
def paginate_items(items, page, items_per_page=10):
    if not items:
        return [], 0
    total_pages = (len(items) + items_per_page - 1) // items_per_page
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    return items[start_idx:end_idx], total_pages

# --- HANDLERS ---

async def category_handler(client, callback_query: CallbackQuery):
    """Handle category selection with pagination."""
    try:
        parts = callback_query.data.split("|")
        cat_id = parts[1]
        category = await resolve_id(cat_id)
        
        category = _LEGACY_CATEGORY_MAP.get(category, category)
        cat_data = await get_category_shows(category)
        if not cat_data:
            return await safe_answer(callback_query, "Category not found.", show_alert=True)

        all_shows = sorted(item["show_name"] for item in cat_data)
        page_shows, total_pages = paginate_items(all_shows, page=1)
        
        buttons = []
        for show_name in page_shows:
            show_hash = await make_id(show_name)
            buttons.append([InlineKeyboardButton(f"🎬 {show_name}", callback_data=f"show|{cat_id}|{show_hash}")])
            
        if total_pages > 1:
            nav_row = [InlineKeyboardButton(f"📄 1/{total_pages}", callback_data="noop")]
            nav_row.append(InlineKeyboardButton("➡️ Next", callback_data=f"page|{cat_id}|2"))
            buttons.append(nav_row)
            
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_main")])
        
        text = f"📂 **{category}**\n\nSelect a show:"
        markup = InlineKeyboardMarkup(buttons)
        if callback_query.message.photo:
            await callback_query.message.delete()
            await client.send_message(callback_query.message.chat.id, text, reply_markup=markup)
        else:
            await callback_query.message.edit_text(text, reply_markup=markup)
        asyncio.create_task(track_behavior(callback_query.from_user.id, 'category_open', {'category': category}))
        await safe_answer(callback_query)
    except Exception as e:
        logger.exception(f"category_handler error: {e}")
        await safe_answer(callback_query, "Error opening category.", show_alert=True)

@track_performance("pagination_handler")
async def pagination_handler(client, callback_query: CallbackQuery):
    """Handle show list pagination."""
    try:
        parts = callback_query.data.split("|")
        cat_id = parts[1]
        page = int(parts[2])
        
        category = await resolve_id(cat_id)
        category = _LEGACY_CATEGORY_MAP.get(category, category)
        cat_data = await get_category_shows(category)
        if not cat_data:
            return await safe_answer(callback_query, "Category not found.", show_alert=True)

        all_shows = sorted(item["show_name"] for item in cat_data)
        page_shows, total_pages = paginate_items(all_shows, page)
        
        buttons = []
        for show_name in page_shows:
            show_hash = await make_id(show_name)
            buttons.append([InlineKeyboardButton(f"🎬 {show_name}", callback_data=f"show|{cat_id}|{show_hash}")])
            
        nav_row = []
        if page > 1:
            nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page|{cat_id}|{page-1}"))
        nav_row.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"page|{cat_id}|{page+1}"))
        
        if nav_row:
            buttons.append(nav_row)
            
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_main")])
        
        text = f"📂 **{category}**\n\nSelect a show:"
        markup = InlineKeyboardMarkup(buttons)
        if callback_query.message.photo:
            await callback_query.message.delete()
            await client.send_message(callback_query.message.chat.id, text, reply_markup=markup)
        else:
            await callback_query.message.edit_text(text, reply_markup=markup)
        await safe_answer(callback_query)
    except Exception as e:
        logger.exception(f"pagination_handler error: {e}")

@track_performance("show_handler")
async def show_handler(client, callback_query: CallbackQuery):
    """Handle show menu (Seasons/Episodes)."""
    try:
        parts = callback_query.data.split("|")
        cat_id = parts[1]
        show_id = parts[2]
        
        category = await resolve_id(cat_id)
        raw_show_name = await resolve_id(show_id)
        
        category = _LEGACY_CATEGORY_MAP.get(category, category)
        show_name, show_doc = await _get_show_doc(category, raw_show_name)
        if not show_doc:
            return await safe_answer(callback_query, f"Show '{raw_show_name}' not found.", show_alert=True)

        episodes_dict = show_doc.get("episodes", {})
        seasons = sorted([k for k in episodes_dict.keys() if k != "episodes"])
        
        buttons = []
        if seasons:
            # Multi-season show
            for s in seasons:
                s_id = await make_id(s)
                buttons.append([InlineKeyboardButton(f"📂 Season {s}", callback_data=f"season|{cat_id}|{show_id}|{s_id}")])
        else:
            # Single season or flat episodes - 4 buttons per row
            episodes = episodes_dict.get("episodes", [])
            row = []
            for idx, ep in enumerate(episodes, 1):
                cb_type = "multi" if isinstance(ep, list) else "episode"
                ep_text = f"{idx}" + (" (S)" if isinstance(ep, list) else "")
                row.append(InlineKeyboardButton(ep_text, callback_data=f"{cb_type}|{cat_id}|{show_id}|flat|{idx}"))
                if len(row) == 4:
                    buttons.append(row)
                    row = []
            if row: buttons.append(row)
        
        # Favorite button
        show_slug = normalize_show_slug(show_name)
        is_fav = await is_favorited(callback_query.from_user.id, show_slug)
        fav_text = "⭐ Remove from Fav" if is_fav else "⭐ Add to Fav"
        fav_cb = f"fav_remove|{cat_id}|{show_id}" if is_fav else f"fav_add|{cat_id}|{show_id}"
        buttons.append([InlineKeyboardButton(fav_text, callback_data=fav_cb)])
        
        # Report & Back
        buttons.append([
            InlineKeyboardButton("⚠️ Report", callback_data=f"report|{cat_id}|{show_id}"),
            InlineKeyboardButton("🔙 Back", callback_data=f"cat|{cat_id}")
        ])
        
        poster_list = show_doc.get("poster", [])
        poster = poster_list[-1] if poster_list else None

        # 🔴 critical: normalize (avoid list / bad state)
        if isinstance(poster, list):
            poster = poster[-1] if poster else None

        text = f"🎬 **{show_name}**\n📂 {category}\n\nSelect a season/episode:"
        
        # Continuity Logic: If we already have a poster showing, just update it.
        # If not, and there is a poster, recreate the message to show photo.
        if poster:
            try:
                await callback_query.message.delete()
            except Exception as del_err:
                logger.debug(f"show_handler: message delete failed: {del_err}")

            await client.send_photo(
                chat_id=callback_query.message.chat.id,
                photo=poster,
                caption=text,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        else:
            if callback_query.message.photo:
                try:
                    await callback_query.message.delete()
                except Exception as del_err:
                    logger.debug(f"show_handler: no-poster delete failed: {del_err}")

                await client.send_message(
                    chat_id=callback_query.message.chat.id,
                    text=text,
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            else:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            
        asyncio.create_task(track_behavior(callback_query.from_user.id, 'show_open', {'show_name': show_name, 'category': category}))
        await safe_answer(callback_query)
    except Exception as e:
        logger.exception(f"show_handler error: {e}")

@track_performance("season_handler")
async def season_handler(client, callback_query: CallbackQuery):
    """Handle season selection."""
    try:
        parts = callback_query.data.split("|")
        cat_id, show_id, s_id = parts[1], parts[2], parts[3]
        
        category = await resolve_id(cat_id)
        raw_show_name = await resolve_id(show_id)
        season = await resolve_id(s_id)
        
        category = _LEGACY_CATEGORY_MAP.get(category, category)
        show_name, show_doc = await _get_show_doc(category, raw_show_name)
        episodes_dict = show_doc.get("episodes", {}) if show_doc else {}
        if not show_doc or season not in episodes_dict:
            return await safe_answer(callback_query, "Season not found.", show_alert=True)

        episodes = episodes_dict[season]
        
        buttons = []
        row = []
        for idx, ep in enumerate(episodes, 1):
            cb_type = "multi" if isinstance(ep, list) else "episode"
            ep_text = f"{idx}" + (" (S)" if isinstance(ep, list) else "")
            row.append(InlineKeyboardButton(ep_text, callback_data=f"{cb_type}|{cat_id}|{show_id}|{s_id}|{idx}"))
            if len(row) == 4:
                buttons.append(row)
                row = []
        if row: buttons.append(row)
                
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"show|{cat_id}|{show_id}")])
        
        await update_media_or_text(
            callback_query.message,
            f"🎬 **{show_name}**\n📂 Season {season}\n\nSelect an episode:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        await safe_answer(callback_query)
    except Exception as e:
        logger.exception(f"season_handler error: {e}")

@track_performance("episode_handler")
async def episode_handler(client, callback_query: CallbackQuery):
    """Handle episode selection (Quality/File)."""
    try:
        parts = callback_query.data.split("|")
        cat_id, show_id, s_id, ep_idx = parts[1], parts[2], parts[3], int(parts[4])
        
        category = await resolve_id(cat_id)
        raw_show_name = await resolve_id(show_id)
        season = await resolve_id(s_id) if s_id != "flat" else "episodes"
        
        category = _LEGACY_CATEGORY_MAP.get(category, category)
        show_name, show_doc = await _get_show_doc(category, raw_show_name)
        episodes_dict = show_doc.get("episodes", {}) if show_doc else {}
        if not show_doc or season not in episodes_dict:
            return await safe_answer(callback_query, "Show data missing.", show_alert=True)

        episode_data = episodes_dict[season][ep_idx-1]
        
        # Handle multi-quality
        if isinstance(episode_data, dict) and "qualities" in episode_data:
            qualities = episode_data["qualities"]
            buttons = []
            row = []
            for q in sorted(qualities.keys()):
                row.append(InlineKeyboardButton(q, callback_data=f"qual|{cat_id}|{show_id}|{s_id}|{ep_idx}|{q}"))
                if len(row) == 3:
                    buttons.append(row)
                    row = []
            if row: buttons.append(row)
            
            buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"season|{cat_id}|{show_id}|{s_id}" if s_id != "episodes" else f"show|{cat_id}|{show_id}")])
            
            await update_media_or_text(
                callback_query.message,
                f"🎬 **{show_name}** - Ep {ep_idx}\nSelect Quality:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return await safe_answer(callback_query)

        # Handle direct file (video/document/link)
        await send_media(client, callback_query, category, show_name, ep_idx, episode_data)
        
    except Exception as e:
        logger.exception(f"episode_handler error: {e}")

@track_performance("multi_handler")
async def multi_handler(client: Client, callback_query: CallbackQuery):
    """Handle split episodes parts selection."""
    try:
        parts = callback_query.data.split("|")
        cat_id, show_id, s_id, ep_idx = parts[1], parts[2], parts[3], int(parts[4])
        
        category = await resolve_id(cat_id)
        raw_show_name = await resolve_id(show_id)
        season = await resolve_id(s_id) if s_id != "flat" else "episodes"
        
        category = _LEGACY_CATEGORY_MAP.get(category, category)
        show_name, show_doc = await _get_show_doc(category, raw_show_name)
        episodes_dict = show_doc.get("episodes", {}) if show_doc else {}
        if not show_doc or season not in episodes_dict:
            return await safe_answer(callback_query, "Data not found.", show_alert=True)

        parts_list = episodes_dict[season][ep_idx-1]
        
        buttons = []
        for idx, file_id in enumerate(parts_list, 1):
            buttons.append([InlineKeyboardButton(f"▶️ Part {idx}", callback_data=f"splitpart|{cat_id}|{show_id}|{s_id}|{ep_idx}|{idx}")])
            
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"season|{cat_id}|{show_id}|{s_id}" if s_id != "episodes" else f"show|{cat_id}|{show_id}")])
        
        await update_media_or_text(
            callback_query.message,
            f"🎬 **{show_name}** - Ep {ep_idx} (Split Parts)\nSelect a part:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        await safe_answer(callback_query)
    except Exception as e:
        logger.exception(f"multi_handler error: {e}")

@track_performance("quality_handler")
async def quality_handler(client: Client, callback_query: CallbackQuery):
    """Handle quality selection playback."""
    try:
        parts = callback_query.data.split("|")
        cat_id, show_id, s_id, ep_idx, quality = parts[1], parts[2], parts[3], int(parts[4]), parts[5]
        
        category = await resolve_id(cat_id)
        raw_show_name = await resolve_id(show_id)
        season = await resolve_id(s_id) if s_id != "flat" else "episodes"
        
        category = _LEGACY_CATEGORY_MAP.get(category, category)
        show_name, show_doc = await _get_show_doc(category, raw_show_name)
        episodes_dict = show_doc.get("episodes", {}) if show_doc else {}
        if not show_doc or season not in episodes_dict:
            return await safe_answer(callback_query, "Data not found.", show_alert=True)

        episode_data = episodes_dict[season][ep_idx-1]
        media_data = episode_data["qualities"][quality]
        
        if isinstance(media_data, list):
            buttons = []
            for idx, part_data in enumerate(media_data, 1):
                if part_data is not None:
                    # Compact format: qp|cat|show|season|ep.quality.part
                    # Keeps under Telegram's 64-byte callback limit
                    cb_data = f"qp|{cat_id}|{show_id}|{s_id}|{ep_idx}.{quality}.{idx}"
                    buttons.append([InlineKeyboardButton(f"▶️ Part {idx}", callback_data=cb_data)])
                
            buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"episode|{cat_id}|{show_id}|{s_id}|{ep_idx}")])
            
            await update_media_or_text(
                callback_query.message,
                f"🎬 **{show_name}** - Ep {ep_idx} ({quality})\nSelect a part:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return await safe_answer(callback_query)

        await send_media(client, callback_query, category, f"{show_name} ({quality})", ep_idx, media_data)
    except Exception as e:
        logger.exception(f"quality_handler error: {e}")

@track_performance("qpart_handler")
async def qpart_handler(client: Client, callback_query: CallbackQuery):
    """Handle split part playback inside a specific quality."""
    try:
        # Compact format: qp|cat_id|show_id|s_id|ep.quality.part
        parts = callback_query.data.split("|")
        cat_id, show_id, s_id = parts[1], parts[2], parts[3]
        # Last segment packs ep_idx, quality, and part_idx with dots
        tail = parts[4].split(".")
        ep_idx, quality, p_idx = int(tail[0]), tail[1], int(tail[2])
        
        category = await resolve_id(cat_id)
        raw_show_name = await resolve_id(show_id)
        season = await resolve_id(s_id) if s_id != "flat" else "episodes"
        
        category = _LEGACY_CATEGORY_MAP.get(category, category)
        show_name, show_doc = await _get_show_doc(category, raw_show_name)
        episodes_dict = show_doc.get("episodes", {}) if show_doc else {}
        if not show_doc or season not in episodes_dict:
            return await safe_answer(callback_query, "Data not found.", show_alert=True)

        episode_data = episodes_dict[season][ep_idx-1]
        media_data = episode_data["qualities"][quality][p_idx-1]
        
        await send_media(client, callback_query, category, f"{show_name} ({quality}) Part {p_idx}", ep_idx, media_data)
    except Exception as e:
        logger.exception(f"qpart_handler error: {e}")

@track_performance("splitpart_handler")
async def splitpart_handler(client: Client, callback_query: CallbackQuery):
    """Handle split part playback."""
    try:
        parts = callback_query.data.split("|")
        cat_id, show_id, s_id, ep_idx, p_idx = parts[1], parts[2], parts[3], int(parts[4]), int(parts[5])
        
        category = await resolve_id(cat_id)
        raw_show_name = await resolve_id(show_id)
        season = await resolve_id(s_id) if s_id != "flat" else "episodes"
        
        category = _LEGACY_CATEGORY_MAP.get(category, category)
        show_name, show_doc = await _get_show_doc(category, raw_show_name)
        episodes_dict = show_doc.get("episodes", {}) if show_doc else {}
        if not show_doc or season not in episodes_dict:
            return await safe_answer(callback_query, "Data not found.", show_alert=True)

        episode_data = episodes_dict[season][ep_idx-1]
        file_id = episode_data[p_idx-1]
        
        await send_media(client, callback_query, category, f"{show_name} Part {p_idx}", ep_idx, file_id)
    except Exception as e:
        logger.exception(f"splitpart_handler error: {e}")

async def send_media(client, callback_query, category, show_name, ep_idx, media_data):
    """Unified media sender logic."""
    try:
        user_id = callback_query.from_user.id
        is_admin = user_id in ADMIN_IDS
        
        if isinstance(media_data, str):
            media_data = {"type": "video", "content": media_data}
            
        m_type = media_data.get("type", "video")
        content = media_data.get("content")
        caption = f"🎬 **{show_name}** - Ep {ep_idx}"
        
        if not is_admin:
            await safe_answer(callback_query, "📹 Sent! Auto-deletes in 3 min.", show_alert=False)
        else:
            await safe_answer(callback_query)

        sent_msg = None
        if m_type == "video":
            sent_msg = await client.send_video(user_id, content, caption=caption)
        elif m_type == "document":
            sent_msg = await client.send_document(user_id, content, caption=caption)
        elif m_type == "link":
            await client.send_message(user_id, f"{caption}\n\n▶️ [Watch Now]({content})", disable_web_page_preview=False)
            return

        if sent_msg and not is_admin:
            asyncio.create_task(auto_delete_message(sent_msg, 180))

        asyncio.create_task(increment_view(category, show_name))
        from bot.services.users import add_to_watch_history
        asyncio.create_task(add_to_watch_history(user_id, show_name))
        asyncio.create_task(track_behavior(user_id, 'episode_watch', {
            'show_name': show_name, 'category': category, 'episode': ep_idx
        }))
        
    except FloodWait as e:
        await safe_answer(callback_query, f"⏳ Rate limited. Wait {e.value}s", show_alert=True)
    except Exception as e:
        logger.exception(f"send_media error: {e}")
        await safe_answer(callback_query, "❌ Error sending file.", show_alert=True)


async def fav_toggle_handler(client, callback_query: CallbackQuery):
    """Handle adding/removing favorites."""
    try:
        parts = callback_query.data.split("|")
        action, cat_id, show_id = parts[0], parts[1], parts[2]
        
        category = await resolve_id(cat_id)
        show_name = await resolve_id(show_id)
        show_slug = normalize_show_slug(show_name)
        
        if action == "fav_add":
            await add_favorite(callback_query.from_user.id, category, show_name, show_slug)
            await safe_answer(callback_query, "⭐ Added to favorites!")
            asyncio.create_task(track_behavior(callback_query.from_user.id, 'fav_add', {'show_name': show_name, 'category': category}))
        else:
            await remove_favorite(callback_query.from_user.id, show_slug)
            await safe_answer(callback_query, "❌ Removed from favorites!")
            asyncio.create_task(track_behavior(callback_query.from_user.id, 'fav_remove', {'show_name': show_name, 'category': category}))
            
        # Refresh the show menu to update the button
        await show_handler(client, callback_query)
    except Exception as e:
        logger.exception(f"fav_toggle_handler error: {e}")

async def back_to_main_handler(client, callback_query: CallbackQuery):
    """Return to main menu."""
    try:
        text = "🎬 **Welcome back!**\n\nChoose a category to browse:"
        markup = await main_keyboard()
        if callback_query.message.photo:
            await callback_query.message.delete()
            await client.send_message(callback_query.message.chat.id, text, reply_markup=markup)
        else:
            await callback_query.message.edit_text(text, reply_markup=markup)
        await safe_answer(callback_query)
    except MessageNotModified:
        pass
    except Exception as e:
        logger.debug(f"back_to_main_handler error: {e}")

from bot.services.verification import get_missing_channels, live_check_and_sync
from bot.handlers.user_cmds import _build_join_buttons

async def joined_handler(client: Client, callback_query: CallbackQuery):
    """Handle I Joined button — live check then DB sync."""
    user_id = callback_query.from_user.id
    logger.info(f"joined_handler called for user {user_id}")
    
    missing = await get_missing_channels(user_id)
    logger.debug(f"get_missing_channels returned {len(missing)} missing channels")
    
    if missing:
        logger.info(f"User {user_id} has missing channels, calling live_check_and_sync")
        missing = await live_check_and_sync(client, user_id, use_cache=False)
        logger.debug(f"live_check_and_sync returned {len(missing)} missing channels")
    
    if missing:
        logger.info(f"User {user_id} still missing channels after live check, rebuilding buttons")
        buttons = await _build_join_buttons(client, missing)
        text = "🎬 **Welcome to K-Drama Bot!**\n\nTo use the bot please join our required channels first:"
        markup = InlineKeyboardMarkup(buttons)
        await safe_answer(callback_query, "You still need to join some channels.", show_alert=True)
        try:
            await callback_query.message.edit_text(text, reply_markup=markup)
        except MessageNotModified:
            logger.debug(f"Message not modified for user {user_id}")
            pass
        except Exception as e:
            logger.warning(f"joined_handler: edit_text failed for user {user_id}: {e}")
            try:
                await callback_query.message.delete()
                await client.send_message(callback_query.message.chat.id, text, reply_markup=markup)
            except Exception as e2:
                logger.warning(f"joined_handler: fallback send failed for user {user_id}: {e2}")
        return
    
    logger.info(f"User {user_id} verification complete, showing main menu")
    await safe_answer(callback_query, "✅ Membership verified!")
    text = "🎬 **Welcome back!**\n\nChoose a category to browse:"
    markup = await main_keyboard()
    if callback_query.message.photo:
        await callback_query.message.delete()
        await client.send_message(callback_query.message.chat.id, text, reply_markup=markup)
    else:
        try:
            await callback_query.message.edit_text(text, reply_markup=markup)
        except MessageNotModified:
            logger.debug(f"Message not modified for user {user_id}")
            pass
        except Exception as e:
            logger.debug(f"joined_handler: edit_text failed for user {user_id}: {e}")

@track_performance("get_links_pagination_handler")
async def get_links_pagination_handler(client, callback_query: CallbackQuery):
    """Handle /get_links pagination."""
    try:
        from bot.database.mongo import db
        from bot.services.shows import get_category_shows
        
        parts = callback_query.data.split("|")
        page = int(parts[1])
        
        # Fetch all shows
        raw_categories = await db.shows.distinct("category")
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
            return await safe_answer(callback_query, "No shows available.", show_alert=True)
        
        all_shows_with_cat.sort(key=lambda x: x["show_name"].lower())
        
        per_page = 10
        total_pages = (len(all_shows_with_cat) + per_page - 1) // per_page
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        page_shows = all_shows_with_cat[start_idx:end_idx]
        
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
            
            buttons.append([
                InlineKeyboardButton(f"🎬 {title}", url=url)
            ])
        
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"getlinks_page|{page-1}"))
        nav_buttons.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"getlinks_page|{page+1}"))
        buttons.append(nav_buttons)
        
        markup = InlineKeyboardMarkup(buttons)
        await callback_query.message.edit_text(text, reply_markup=markup)
        await safe_answer(callback_query)
    except Exception as e:
        logger.exception(f"get_links_pagination_handler error: {e}")
        await safe_answer(callback_query, "Error loading page.", show_alert=True)

def register_callback_handlers(app: Client):
    app.on_callback_query(filters.regex(r"^cat\|"))(category_handler)
    app.on_callback_query(filters.regex(r"^page\|"))(pagination_handler)
    app.on_callback_query(filters.regex(r"^getlinks_page\|"))(get_links_pagination_handler)
    app.on_callback_query(filters.regex(r"^show\|"))(show_handler)
    app.on_callback_query(filters.regex(r"^season\|"))(season_handler)
    app.on_callback_query(filters.regex(r"^episode\|"))(episode_handler)
    app.on_callback_query(filters.regex(r"^multi\|"))(multi_handler)
    app.on_callback_query(filters.regex(r"^qual\|"))(quality_handler)
    app.on_callback_query(filters.regex(r"^qp\|"))(qpart_handler)
    app.on_callback_query(filters.regex(r"^splitpart\|"))(splitpart_handler)
    app.on_callback_query(filters.regex(r"^fav_"))(fav_toggle_handler)
    app.on_callback_query(filters.regex(r"^back_to_main$"))(back_to_main_handler)
    app.on_callback_query(filters.regex(r"^joined$"))(joined_handler)
    app.on_callback_query(filters.regex(r"^noop$"))(lambda c, q: safe_answer(q))
