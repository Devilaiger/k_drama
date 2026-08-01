import asyncio
import re
import time
from datetime import datetime
from typing import Optional
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from bot.handlers.user_cmds import get_links_cmd
from bot.config import ADMIN_IDS
from bot.database.mongo import db
from bot.services.shows import _LEGACY_CATEGORY_MAP, get_cached_data
from bot.utils.ui import safe_answer, normalize_season
from bot.utils.ids import resolve_id
from bot.utils.logger import logger, track_performance
from bot.utils.slug import find_show_in_data, normalize_slug
from bot.services.updates import add_recent_update

# --- CONFIG & MAPS ---
IMPORT_CATEGORY_MAP = {
    "import_hindi": "K-Hindi",
    "import_orig": "K-Original",
    "import_jap": "Japanese Drama",
    "import_c": "CT Drama",
    "import_glb": "Global",
    "import_pak": "Pakistan",
    "import_anime": "Anime",
}

POSTER_CATEGORY_COMMANDS = {
    "add_poster_hindi": "K-Hindi",
    "add_poster_orig": "K-Original",
    "add_poster_jap": "Japanese Drama",
    "add_poster_c": "CT Drama",
    "add_poster_glb": "Global",
    "add_poster_pak": "Pakistan",
    "add_poster_anime": "Anime",
}

DELETE_CATEGORY_COMMANDS = {
    "delete_hindi": "K-Hindi",
    "delete_orig": "K-Original",
    "delete_jap": "Japanese Drama",
    "delete_c": "CT Drama",
    "delete_glb": "Global",
    "delete_pak": "Pakistan",
    "delete_anime": "Anime",
}

CATEGORY_ALIASES = {
    "hindi": "K-Hindi",
    "hindi_dubbed": "K-Hindi",
    "hindi_dub": "K-Hindi",
    "regional": "K-Original",
    "orig": "K-Original",
    "cdrama": "CT Drama",
    "c": "CT Drama",
    "arabic": "Global",
    "glb": "Global",
    "global": "Global",
    "japanese": "Japanese Drama",
    "jap": "Japanese Drama",
    "pakistan": "Pakistan",
    "pak": "Pakistan",
    "anime": "Anime"
}

KNOWN_CATEGORIES = {canonical for canonical in CATEGORY_ALIASES.values()}

METADATA_CATEGORY_COMMANDS = {
    "add_audio": "K-Hindi",
    "set_audio": "K-Hindi",
    "add_genre": "K-Hindi",
    "set_genre": "K-Hindi",
    "add_subs": "K-Hindi",
    "set_subs": "K-Hindi",
    "add_audio_orig": "K-Original",
    "set_audio_orig": "K-Original",
    "add_genre_orig": "K-Original",
    "set_genre_orig": "K-Original",
    "add_subs_orig": "K-Original",
    "set_subs_orig": "K-Original",
    "add_audio_jap": "Japanese Drama",
    "set_audio_jap": "Japanese Drama",
    "add_genre_jap": "Japanese Drama",
    "set_genre_jap": "Japanese Drama",
    "add_subs_jap": "Japanese Drama",
    "set_subs_jap": "Japanese Drama",
    "add_audio_c": "CT Drama",
    "set_audio_c": "CT Drama",
    "add_genre_c": "CT Drama",
    "set_genre_c": "CT Drama",
    "add_subs_c": "CT Drama",
    "set_subs_c": "CT Drama",
    "add_audio_glb": "Global",
    "set_audio_glb": "Global",
    "add_genre_glb": "Global",
    "set_genre_glb": "Global",
    "add_subs_glb": "Global",
    "set_subs_glb": "Global",
    "add_audio_pak": "Pakistan",
    "set_audio_pak": "Pakistan",
    "add_genre_pak": "Pakistan",
    "set_genre_pak": "Pakistan",
    "add_subs_pak": "Pakistan",
    "set_subs_pak": "Pakistan",
    "add_audio_anime": "Anime",
    "set_audio_anime": "Anime",
    "add_genre_anime": "Anime",
    "set_genre_anime": "Anime",
    "add_subs_anime": "Anime",
    "set_subs_anime": "Anime",
}

RELEASE_DATE_CATEGORY_COMMANDS = {
    "set_release_date": "K-Hindi",
    "set_release_date_orig": "K-Original",
    "set_release_date_jap": "Japanese Drama",
    "set_release_date_c": "CT Drama",
    "set_release_date_glb": "Global",
    "set_release_date_pak": "Pakistan",
    "set_release_date_anime": "Anime",
}

# State management
# user_id -> state_dict  with 'timestamp' key for stale detection
import_state = {}
poster_upload_state = {}

_STATE_TTL = 600  # 10 minutes — stale states are silently discarded


def _category_variants(category: str) -> list[str]:
    """Return DB category names that should be treated as this canonical category."""
    variants = {category}
    variants.update(old for old, canonical in _LEGACY_CATEGORY_MAP.items() if canonical == category)
    return list(variants)


async def _find_show_for_admin_action(data: dict, category: str, show_input: str) -> str | None:
    """Find a show in cached normalized data, then fall back to raw DB category variants."""
    actual_show_name = find_show_in_data(data, category, show_input)
    if actual_show_name:
        return actual_show_name

    query_slug = normalize_slug(show_input)
    cursor = db.shows.find(
        {"category": {"$in": _category_variants(category)}},
        {"show_name": 1}
    )
    async for doc in cursor:
        show_name = doc.get("show_name", "")
        if normalize_slug(show_name) == query_slug:
            return show_name

    return None


QUALITY_PATTERN = r'^[0-9]+(?:p|k)?(?:-10bit)?(?:\s+Hevc)?$'

SEASON_TOKEN_PATTERN = r'^[Ss]?(\d+)$'
EPISODE_TOKEN_PATTERN = r'^[Ee]?(\d+)$'


def _parse_delete_tail(tokens: list[str]) -> tuple[str | None, int | None, str | None] | None:
    """Parse optional season/episode/quality tokens after a resolved show name."""
    parts = tokens[:]
    quality = None

    # Ignore a trailing part indicator like P1 / p1 or I / i;
    # delete operates at the quality level and does not need the part index.
    while parts and re.match(r'^(?:[Pp]\d+|[Ii])$', parts[-1]):
        parts.pop()

    # Accept quality labels with modifiers, e.g. 720p-10bit, 1080p-10bit Hevc.
    for split_at in range(len(parts), 0, -1):
        candidate = " ".join(parts[split_at - 1:])
        if re.match(QUALITY_PATTERN, candidate, re.I):
            quality = re.sub(r'\s+', ' ', candidate).strip()
            parts = parts[: split_at - 1]
            break

    if not parts:
        return (None, None, None) if quality is None else None

    season_number = None
    episode_num = None
    if len(parts) == 1:
        token = parts[0]
        season_match = re.match(SEASON_TOKEN_PATTERN, token)
        if season_match:
            season_number = season_match.group(1)
        else:
            return None
    elif len(parts) == 2:
        season_token, episode_token = parts
        season_match = re.match(SEASON_TOKEN_PATTERN, season_token)
        episode_match = re.match(EPISODE_TOKEN_PATTERN, episode_token)
        if season_match and episode_match:
            season_number = season_match.group(1)
            episode_num = int(episode_match.group(1))
        else:
            return None
    else:
        return None

    if quality and not (season_number and episode_num):
        return None

    return season_number, episode_num, quality
    episode_num = None
    if len(parts) == 1:
        token = parts[0]
        if token.isdigit():
            season_number = token
        elif token.lower().startswith("s") and token[1:].isdigit():
            season_number = token[1:]
        else:
            return None
    elif len(parts) == 2:
        season_token, episode_token = parts
        if season_token.isdigit():
            season_number = season_token
        elif season_token.lower().startswith("s") and season_token[1:].isdigit():
            season_number = season_token[1:]
        else:
            return None

        if not episode_token.isdigit():
            return None
        episode_num = int(episode_token)
    else:
        return None

    if quality and not (season_number and episode_num):
        return None

    return season_number, episode_num, quality


def _get_state(state_dict: dict, user_id: int) -> Optional[dict]:
    """Return state only if it exists and is not stale (< 10 min old)."""
    state = state_dict.get(user_id)
    if not state:
        return None
    if time.time() - state.get("timestamp", 0) > _STATE_TTL:
        state_dict.pop(user_id, None)
        return None
    return state


def _normalize_meta_value(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if value.isdigit():
        return value
    return " ".join(part.capitalize() for part in value.split())


def _normalize_list_values(raw_value: str) -> list[str]:
    if not raw_value:
        return []
    items = re.split(r'[;,|/]+', raw_value)
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = _normalize_meta_value(item)
        if not value:
            continue
        key = value.lower()
        if key not in seen:
            seen.add(key)
            normalized.append(value)
    return normalized


def _resolve_command_category(category: str | None) -> str | None:
    if not category:
        return None
    normalized = category.strip()
    lower_key = normalized.lower()
    if lower_key in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[lower_key]
    canonical = normalized.title()
    if canonical in KNOWN_CATEGORIES:
        return canonical
    return None


def _extract_category_from_values(values_text: str) -> tuple[str | None, str]:
    """If the first value token is a category alias, separate it from the remaining values."""
    if not values_text:
        return None, ""
    parts = values_text.strip().split(None, 1)
    if not parts:
        return None, ""
    if len(parts) == 1:
        return None, values_text
    resolved_category = _resolve_command_category(parts[0])
    if resolved_category:
        remaining = parts[1].strip()
        return resolved_category, remaining
    return None, values_text


async def _resolve_show(category: str | None, show_name: str) -> tuple[str, dict] | None:
    query = {"show_name": {"$regex": f"^{re.escape(show_name)}$", "$options": "i"}}
    if category:
        query["category"] = _resolve_command_category(category)
    show_doc = await db.shows.find_one(query)
    if show_doc:
        return show_doc["show_name"], show_doc
    if category:
        alias_cat = CATEGORY_ALIASES.get(category.lower())
        if alias_cat:
            query["category"] = alias_cat
            show_doc = await db.shows.find_one(query)
            if show_doc:
                return show_doc["show_name"], show_doc
    return None


async def _set_list_field(category: str, show_name: str, field_name: str, values: list[str]):
    await db.shows.update_one(
        {"category": category, "show_name": show_name},
        {"$set": {field_name: values}}
    )


async def _append_list_field(category: str, show_name: str, field_name: str, values: list[str]):
    show_doc = await db.shows.find_one(
        {"category": category, "show_name": show_name},
        {field_name: 1}
    )
    if not show_doc:
        return None
    current = show_doc.get(field_name)
    if isinstance(current, list):
        merged = current[:]
    elif current:
        merged = [current]
    else:
        merged = []
    existing_lower = {v.lower() for v in merged}
    for value in values:
        if value.lower() not in existing_lower:
            merged.append(value)
            existing_lower.add(value.lower())
    await db.shows.update_one(
        {"category": category, "show_name": show_name},
        {"$set": {field_name: merged}}
    )
    return merged


async def _update_show_cache(category: str, show_name: str):
    from bot.utils.cache import layered_cache, _make_show_cache_key
    from bot.utils.ids import normalize_show_slug
    cache_key = _make_show_cache_key(category, normalize_show_slug(show_name))
    layered_cache.invalidate_show(cache_key)


def _parse_metadata_command_args(args_text: str) -> tuple[str | None, str | None, str]:
    show_name = None
    category = None
    values = ""
    if not args_text:
        return None, None, ""
    if ">" in args_text:
        left, right = args_text.split(">", 1)
        show_name = left.strip().strip('"')
        right = right.strip()
        if right:
            parts = right.split(None, 1)
            category = parts[0].strip()
            values = parts[1].strip() if len(parts) > 1 else ""
        return show_name, category, values

    quoted = re.match(r'^"([^"]+)"\s*(.*)$', args_text)
    if quoted:
        return quoted.group(1).strip(), None, quoted.group(2).strip()

    # If metadata keys start after the show name, split at the first key token.
    match = re.search(r'\b(audio|genre|subs|subtitles|year|release_year)\s*=', args_text, re.I)
    if match:
        show_name = args_text[:match.start()].strip().strip('"')
        values = args_text[match.start():].strip()
        return show_name, None, values

    parts = args_text.split(None, 1)
    show_name = parts[0].strip()
    values = parts[1].strip() if len(parts) > 1 else ""
    return show_name, None, values


def _parse_metadata_kv_pairs(values_text: str) -> dict[str, object]:
    pairs: dict[str, object] = {}
    if not values_text:
        return pairs
    pattern = re.compile(
        r'(audio|genre|subs|subtitles|year|release_year|release_date)\s*=\s*'
        r'(?:"([^"]+)"|([^"\s][^=]*?))'
        r'(?=\s+(?:audio|genre|subs|subtitles|year|release_year|release_date)\s*=|$)',
        re.I
    )
    for match in pattern.finditer(values_text):
        key = match.group(1).lower()
        raw_val = match.group(2) or match.group(3) or ""
        raw_val = raw_val.strip()
        if key in ["audio", "genre", "subs", "subtitles"]:
            pairs[key] = _normalize_list_values(raw_val)
        elif key in ["year", "release_year"]:
            year_val = raw_val.strip()
            pairs["release_year"] = int(year_val) if year_val.isdigit() else year_val
        elif key == "release_date":
            pairs["release_date"] = _normalize_meta_value(raw_val)
    return pairs


async def _apply_metadata_update(client: Client, message: Message, action: str, field_name: str, command_name: str, show_name: str | None, category: str | None, values_text: str):
    if not show_name:
        return await message.reply(
            f"❌ Invalid format. Use `/{action}_{field_name} \"Show Name\" value1,value2` or `/{action}_{field_name} \"Show Name\" > category value1,value2`."
        )
    if not values_text:
        return await message.reply(
            f"❌ No values provided. Usage: `/{action}_{field_name} \"Show Name\" value1,value2` or `/{action}_{field_name} \"Show Name\" > category value1,value2`."
        )

    category_from_values, remaining_values = _extract_category_from_values(values_text)
    default_category = METADATA_CATEGORY_COMMANDS.get(command_name, "K-Hindi")
    resolved_category = _resolve_command_category(category) or category_from_values or default_category
    values = _normalize_list_values(remaining_values if category_from_values else values_text)
    if not values:
        return await message.reply("❌ No valid values provided.")

    resolved = await _resolve_show(resolved_category, show_name)
    if not resolved:
        return await message.reply(f"❌ Show '{show_name}' not found in {resolved_category}.")

    actual_show_name, _ = resolved
    if action == "set":
        await _set_list_field(resolved_category, actual_show_name, field_name, values)
        await _update_show_cache(resolved_category, actual_show_name)
        return await message.reply(f"✅ Set {field_name} for **{actual_show_name}**: {', '.join(values)}")

    merged = await _append_list_field(resolved_category, actual_show_name, field_name, values)
    await _update_show_cache(resolved_category, actual_show_name)
    return await message.reply(f"✅ Added {field_name} to **{actual_show_name}**: {', '.join(values)}")


async def add_audio_cmd(client: Client, message: Message):
    args_text = message.text.split(" ", 1)[1].strip() if len(message.command) > 1 else ""
    show_name, category, values_text = _parse_metadata_command_args(args_text)
    return await _apply_metadata_update(client, message, "add", "audio", message.command[0].lower(), show_name, category, values_text)


async def set_audio_cmd(client: Client, message: Message):
    args_text = message.text.split(" ", 1)[1].strip() if len(message.command) > 1 else ""
    show_name, category, values_text = _parse_metadata_command_args(args_text)
    return await _apply_metadata_update(client, message, "set", "audio", message.command[0].lower(), show_name, category, values_text)


async def add_genre_cmd(client: Client, message: Message):
    args_text = message.text.split(" ", 1)[1].strip() if len(message.command) > 1 else ""
    show_name, category, values_text = _parse_metadata_command_args(args_text)
    return await _apply_metadata_update(client, message, "add", "genre", message.command[0].lower(), show_name, category, values_text)


async def set_genre_cmd(client: Client, message: Message):
    args_text = message.text.split(" ", 1)[1].strip() if len(message.command) > 1 else ""
    show_name, category, values_text = _parse_metadata_command_args(args_text)
    return await _apply_metadata_update(client, message, "set", "genre", message.command[0].lower(), show_name, category, values_text)


async def add_subs_cmd(client: Client, message: Message):
    args_text = message.text.split(" ", 1)[1].strip() if len(message.command) > 1 else ""
    show_name, category, values_text = _parse_metadata_command_args(args_text)
    return await _apply_metadata_update(client, message, "add", "subs", message.command[0].lower(), show_name, category, values_text)


async def set_subs_cmd(client: Client, message: Message):
    args_text = message.text.split(" ", 1)[1].strip() if len(message.command) > 1 else ""
    show_name, category, values_text = _parse_metadata_command_args(args_text)
    return await _apply_metadata_update(client, message, "set", "subs", message.command[0].lower(), show_name, category, values_text)


async def set_metadata_cmd(client: Client, message: Message):
    args_text = message.text.split(" ", 1)[1].strip() if len(message.command) > 1 else ""
    show_name, category, values_text = _parse_metadata_command_args(args_text)
    if not show_name or not values_text:
        return await message.reply(
            "❌ Invalid format. Use `/set_metadata \"Show Name\" audio=Hindi,English subs=English,Hindi genre=Romance,Drama year=2026`."
        )

    resolved_category = _resolve_command_category(category) or "K-Hindi"
    resolved = await _resolve_show(resolved_category, show_name)
    if not resolved:
        return await message.reply(f"❌ Show '{show_name}' not found in {resolved_category}.")

    actual_show_name, _ = resolved
    pairs = _parse_metadata_kv_pairs(values_text)
    if not pairs:
        return await message.reply(
            "❌ No valid metadata pairs found. Use keys audio, genre, subs, year. Example: audio=Hindi,English subs=English,Hindi genre=Romance,Drama year=2026"
        )

    if "subtitles" in pairs:
        pairs["subs"] = pairs.pop("subtitles")

    update_data: dict[str, object] = {}
    if "audio" in pairs:
        update_data["audio"] = pairs["audio"]
    if "genre" in pairs:
        update_data["genre"] = pairs["genre"]
    if "subs" in pairs:
        update_data["subs"] = pairs["subs"]
    if "release_year" in pairs:
        update_data["release_year"] = pairs["release_year"]

    await db.shows.update_one(
        {"category": resolved_category, "show_name": actual_show_name},
        {"$set": update_data}
    )
    await _update_show_cache(resolved_category, actual_show_name)

    summary: list[str] = []
    if "audio" in update_data:
        audio_values = update_data["audio"]
        if isinstance(audio_values, list):
            summary.append(f"Audio: {', '.join(audio_values)}")
    if "genre" in update_data:
        genre_values = update_data["genre"]
        if isinstance(genre_values, list):
            summary.append(f"Genre: {', '.join(genre_values)}")
    if "subs" in update_data:
        subs_values = update_data["subs"]
        if isinstance(subs_values, list):
            summary.append(f"Subs: {', '.join(subs_values)}")
    if "release_year" in update_data:
        summary.append(f"Year: {update_data['release_year']}")
    if "release_date" in update_data:
        summary.append(f"Release Date: {update_data['release_date']}")

    return await message.reply(f"✅ Updated metadata for **{actual_show_name}**:\n" + "\n".join(summary))


def _parse_release_date_args(args_text: str) -> tuple[str | None, str | None, str]:
    show_name = None
    category = None
    release_date = ""
    if not args_text:
        return None, None, ""
    if ">" in args_text:
        left, right = args_text.split(">", 1)
        show_name = left.strip().strip('"')
        right = right.strip()
        if right:
            parts = right.split(None, 1)
            category = parts[0].strip()
            release_date = parts[1].strip() if len(parts) > 1 else ""
        return show_name, category, release_date

    quoted = re.match(r'^"([^"]+)"\s+(.*)$', args_text)
    if quoted:
        return quoted.group(1).strip(), None, quoted.group(2).strip()

    parts = args_text.split(None, 1)
    show_name = parts[0].strip()
    release_date = parts[1].strip() if len(parts) > 1 else ""
    return show_name, None, release_date


async def _apply_release_date_update(client: Client, message: Message, command_name: str, show_name: str | None, category: str | None, release_date: str):
    if not show_name or not release_date:
        return await message.reply(
            f"❌ Invalid format. Use `/{command_name} \"Show Name\" April 2, 2026` or `/{command_name} \"Show Name\" > category April 2, 2026`."
        )

    resolved_category = _resolve_command_category(category) or RELEASE_DATE_CATEGORY_COMMANDS.get(command_name, "K-Hindi")
    resolved = await _resolve_show(resolved_category, show_name)
    if not resolved:
        return await message.reply(f"❌ Show '{show_name}' not found in {resolved_category}.")

    actual_show_name, _ = resolved
    await db.shows.update_one(
        {"category": resolved_category, "show_name": actual_show_name},
        {"$set": {"release_date": _normalize_meta_value(release_date)}}
    )
    await _update_show_cache(resolved_category, actual_show_name)

    return await message.reply(
        f"✅ Set release date for **{actual_show_name}** in {resolved_category}: {_normalize_meta_value(release_date)}"
    )


async def set_release_date_cmd(client: Client, message: Message):
    args_text = message.text.split(" ", 1)[1].strip() if len(message.command) > 1 else ""
    show_name, category, release_date = _parse_release_date_args(args_text)
    return await _apply_release_date_update(client, message, message.command[0].lower(), show_name, category, release_date)


admin_filter = filters.user(ADMIN_IDS)

async def _send_user_photo(client, chat_id, user_id, caption="", reply_markup=None):
    """
    Reliably send a user's current profile photo.
    get_profile_photos() doesn't exist in Pyrogram 2.0.106.
    big_file_id is CHAT_PHOTO type which send_photo() rejects.
    Solution: download via download_media() then re-upload — always works.
    Returns True if photo sent, False if user has no photo or on error.
    """
    import os
    tmp_path = None
    try:
        user = await client.get_users(user_id)
        if not getattr(user, "photo", None):
            return False
        tmp_path = await client.download_media(user.photo.big_file_id)
        if not tmp_path:
            return False
        kwargs = {"caption": caption}
        if reply_markup:
            kwargs["reply_markup"] = reply_markup
        await client.send_photo(chat_id, tmp_path, **kwargs)
        return True
    except Exception as e:
        logger.debug(f"_send_user_photo error for {user_id}: {e}")
        return False
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass



# --- IMPORT HANDLERS ---

@track_performance("import_handler")
async def import_command_handler(client: Client, message: Message):
    """Initiate import mode for an episode."""
    cmd = message.command[0]
    category = IMPORT_CATEGORY_MAP.get(cmd)
    if not category: return

    try:
        args_text = message.text.split(" ", 1)[1].strip()
    except IndexError:
        return await message.reply(
            f"**Usage:** `/{cmd} Show_Name S1 E3 720p`\n"
            f"💡 Use quotes for names with spaces if needed, or underscores."
        )

    # Parsing (Same logic as monolith)
    # 1. Quoted: "Show Name" S1 E3 720p-10bit
    match = re.match(
        r'"([^"]+)"\s+[Ss](\d+)\s+[Ee](\d+)\s+([0-9]+(?:p|k)?(?:-10bit)?(?:\s+Hevc)?)\s*(?:[Pp](\d+))?',
        args_text,
        re.I
    )
    if not match:
        # 2. Unquoted: Show_Name S1 E3 720p-10bit or Show Name S1 E3 720p-10bit
        match = re.match(
            r'(.+?)\s+[Ss](\d+)\s+[Ee](\d+)\s+([0-9]+(?:p|k)?(?:-10bit)?(?:\s+Hevc)?)\s*(?:[Pp](\d+))?',
            args_text,
            re.I
        )

    if not match:
        return await message.reply(
            f"❌ **Invalid format**\n\n"
            f"**Usage:** `/{cmd} Show_Name S1 E1 720p-10bit`\n"
            f"**Example:** `/{cmd} \"My Drama\" S1 E1 720p-10bit P1`"
        )

    show_name_input = match.group(1).strip()
    season_str = match.group(2)
    episode_num = int(match.group(3))
    quality = re.sub(r'\s+', ' ', match.group(4).strip())
    part_num = int(match.group(5)) if match.group(5) else None

    # Validate Show and Category — direct DB query, no full cache load
    show_doc_check = await db.shows.find_one(
        {"category": category, "show_name": {"$regex": f"^{re.escape(show_name_input)}$", "$options": "i"}},
        {"show_name": 1}
    )
    if not show_doc_check:
        # Try alias categories
        alias_cat = CATEGORY_ALIASES.get(category.lower())
        if alias_cat:
            show_doc_check = await db.shows.find_one(
                {"category": alias_cat, "show_name": {"$regex": f"^{re.escape(show_name_input)}$", "$options": "i"}},
                {"show_name": 1}
            )
            if show_doc_check:
                category = alias_cat
        if not show_doc_check:
            return await message.reply(
                f"❌ Show '{show_name_input}' not found in {category}.\n"
                f"💡 **Tip:** Use `/add` to create it first."
            )
    actual_show_name = show_doc_check["show_name"]

    season_key = normalize_season(season_str)
    
    import_state[message.from_user.id] = {
        "category": category,
        "show": actual_show_name,
        "season": season_key,
        "episode_index": episode_num - 1,
        "quality": quality,
        "part_num": part_num,
        "timestamp": time.time()  # For stale-state detection
    }

    await message.reply(
        f"✅ **Import Mode [Active]**\n\n"
        f"📺 Show: **{actual_show_name}**\n"
        f"📂 Category: **{category}**\n"
        f"🎬 Episode: **S{season_key} E{episode_num}**\n"
        f"🎞 Quality: **{quality}**\n\n"
        f"📤 Send the Video/File/Link now."
    )

async def handle_import_receive(client: Client, message: Message):
    """Receive and save the imported episode data."""
    user_id = message.from_user.id

    # Guard: if poster flow is active for this user, do not intercept.
    # Poster handler has higher priority and will process this message.
    if _get_state(poster_upload_state, user_id):
        logger.debug(f"handle_import_receive: skipping — poster state active for {user_id}")
        return

    state = _get_state(import_state, user_id)
    if not state or (message.text and message.text.startswith("/")): return

    def cleanup(): import_state.pop(user_id, None)

    proc = await message.reply("⏳ Processing import...")
    file_type = "video"
    file_id = None
    if message.video: 
        file_id = message.video.file_id
    elif message.document: 
        file_id = message.document.file_id
        file_type = "document"
    elif message.text and re.match(r'https?://\S+', message.text): 
        file_id = message.text
        file_type = "link"
    
    if not file_id:
        await proc.edit("❌ Please send a video, document, or valid link.")
        return

    try:
        category = state["category"]
        show_name = state["show"]
        season = state["season"]
        ep_idx = state["episode_index"]
        quality = state["quality"]
        part_num = state.get("part_num")

        # Update MongoDB
        # We store multi-quality episodes as list of dicts at index
        # [ { "qualities": { "720p": {"type": "...", "content": "..."} } }, ... ]
        
        show_doc = await db.shows.find_one({"category": category, "show_name": show_name})
        if not show_doc:
            await proc.edit("❌ Show data lost during process.")
            cleanup()
            return

        episodes = show_doc.get("episodes", {}).get(season, [])
        # Initialize if missing
        if ep_idx >= len(episodes):
            episodes.extend([None] * (ep_idx - len(episodes) + 1))
            
        current_ep = episodes[ep_idx]
        
        # Backward compatibility for old format
        if not isinstance(current_ep, dict):
            if current_ep:
                current_ep = {"qualities": {"default": {"type": "video", "content": current_ep}}}
            else:
                current_ep = {"qualities": {}}
                
        if "qualities" not in current_ep:
            current_ep["qualities"] = {}

        if part_num is not None:
            # Handle as a split part
            existing_q = current_ep["qualities"].get(quality)
            if not isinstance(existing_q, list):
                if existing_q:
                    existing_q = [existing_q]
                else:
                    existing_q = []
            
            part_idx = part_num - 1
            while len(existing_q) <= part_idx:
                existing_q.append(None)
                
            existing_q[part_idx] = {"type": file_type, "content": file_id}
            
            # Clean up trailing Nones just in case
            while existing_q and existing_q[-1] is None:
                existing_q.pop()
                
            current_ep["qualities"][quality] = existing_q
            part_msg = f" Part {part_num}"
        else:
            # Handle as single quality file
            current_ep["qualities"][quality] = {"type": file_type, "content": file_id}
            part_msg = ""
            
        episodes[ep_idx] = current_ep

        await db.shows.update_one(
            {"category": category, "show_name": show_name},
            {"$set": {f"episodes.{season}": episodes}}
        )

        # Targeted cache invalidation — only drop this specific show from L2.
        # L1 (category show list) is NOT touched — the show still exists,
        # only its episode content changed.
        from bot.utils.cache import layered_cache, _make_show_cache_key
        from bot.utils.ids import normalize_show_slug
        cache_key = _make_show_cache_key(category, normalize_show_slug(show_name))
        layered_cache.invalidate_show(cache_key)

        await proc.edit(f"✅ Saved **{state['show']}** S{season.replace('season_', '')} E{ep_idx+1} ({quality}{part_msg}) successfully!")
        
        # Log recent update
        asyncio.create_task(add_recent_update(category, show_name, season, ep_idx + 1))
        
        cleanup()

    except Exception as e:
        logger.exception(f"Import process error: {e}")
        await proc.edit(f"❌ Error: {e}")
        cleanup()

# --- POSTER HANDLERS ---

@track_performance("add_poster_handler")
async def add_poster_command(client: Client, message: Message):
    """Initiate poster upload mode."""
    cmd = message.command[0]
    category = POSTER_CATEGORY_COMMANDS.get(cmd, "K-Hindi")
    
    try:
        show_input = message.text.split(" ", 1)[1].strip()
    except IndexError:
        return await message.reply(f"**Usage:** `/{cmd} <Show Name>`")

    # Direct DB query — no full cache load
    show_doc_check = await db.shows.find_one(
        {"category": category, "show_name": {"$regex": f"^{re.escape(show_input)}$", "$options": "i"}},
        {"show_name": 1}
    )
    actual_show = show_doc_check["show_name"] if show_doc_check else None
    if not actual_show:
        return await message.reply(f"❌ Show '{show_input}' not found in {category}.")

    poster_upload_state[message.from_user.id] = {
        "category": category,
        "show": actual_show,
        "timestamp": time.time()  # For stale-state detection
    }
    await message.reply(f"🖼 **Poster Mode Active** for **{actual_show}**\n\nReply with a Photo.")

async def handle_poster_receive(client: Client, message: Message):
    """
    Save the new poster. Accepts:
      - message.photo (standard send)
      - message.document with image/* MIME (sent as file / forwarded as file)
    Never exits silently: every path either saves or replies with an error.
    State is only cleared on success to allow retry on failure.
    """
    user_id = message.from_user.id
    state = _get_state(poster_upload_state, user_id)

    # No active poster state — ignore silently (not our message to handle)
    if not state:
        return

    # --- MEDIA DETECTION ---
    photo_id = None

    if message.photo:
        # Standard photo (highest resolution is last in the list)
        photo_id = message.photo.file_id

    elif message.document and (message.document.mime_type or "").startswith("image/"):
        # Sent as file but is an image (also catches forwarded image-as-file)
        photo_id = message.document.file_id

    if photo_id is None:
        # Not a valid image — tell admin clearly, do NOT clear state so they can retry
        logger.debug(
            f"handle_poster_receive: user {user_id} sent non-image media "
            f"(photo={bool(message.photo)}, "
            f"doc_mime={getattr(message.document, 'mime_type', None)})"
        )
        await message.reply("❌ Please send a valid image (photo or image file).")
        return

    # Valid image received — clear state immediately to prevent duplicate triggers
    poster_upload_state.pop(user_id, None)

    proc = await message.reply("⏳ Uploading poster...")
    try:
        show_name = state["show"]
        category = state["category"]

        show_doc = await db.shows.find_one({"category": category, "show_name": show_name})
        if not show_doc:
            logger.warning(
                f"handle_poster_receive: show '{show_name}' not found in DB for user {user_id}"
            )
            await proc.edit("❌ Show data not found in database.")
            return

        current_posters = show_doc.get("poster", [])
        if isinstance(current_posters, str):
            current_posters = [current_posters]

        current_posters.append(photo_id)

        await db.shows.update_one(
            {"_id": show_doc["_id"]},
            {"$set": {"poster": current_posters}}
        )

        from bot.utils.cache import layered_cache, _make_show_cache_key
        from bot.utils.ids import normalize_show_slug
        cache_key = _make_show_cache_key(category, normalize_show_slug(state["show"]))
        layered_cache.invalidate_show(cache_key)

        await proc.edit(f"✅ Poster added for **{state['show']}**!")

    except Exception as e:
        logger.exception(f"handle_poster_receive error for user {user_id}: {e}")
        await proc.edit(f"❌ Error saving poster: {e}")

# --- GENERAL ADMIN ---

@track_performance("add_show_cmd")
async def add_show_cmd(client: Client, message: Message):
    """Add a new show and/or season with flexible parsing."""
    cmd = message.command[0]
    if len(message.command) < 2:
        return await message.reply(
            "**Usage:**\n"
            "• `/add Show Name` (Defaults to Hindi)\n"
            "• `/add Show Name 1` (Show + Season 1)\n"
            "• `/add Show Name > Category`\n"
            "• `/add Show Name > Category 1`"
        )

    args = message.text.split(" ", 1)[1].strip()
    category = "K-Hindi"
    show_name = None
    season_number = None

    # Support /add_hindi variants
    cmd_cat = cmd.replace("add_", "")
    if cmd_cat in CATEGORY_ALIASES:
        category = CATEGORY_ALIASES[cmd_cat]
    elif cmd == "add" and not args.startswith(">"):
        # Default for /add is K-Hindi
        category = "K-Hindi"

    if ">" in args:
        try:
            show_part, rest = args.split(">", 1)
            show_part = show_part.strip()
            rest_parts = rest.strip().split()

            show_name = show_part
            if rest_parts and rest_parts[-1].isdigit():
                season_number = rest_parts[-1]
                cat_input = " ".join(rest_parts[:-1]).lower()
                category = CATEGORY_ALIASES.get(cat_input, cat_input.title()) if cat_input else category
            else:
                cat_input = " ".join(rest_parts).lower()
                category = CATEGORY_ALIASES.get(cat_input, cat_input.title())
        except Exception:
            return await message.reply("❌ Invalid format. Use `/add Show Name > Category 1`")
    else:
        parts = args.rsplit(" ", 1)
        if parts[-1].isdigit():
            show_name = parts[0].strip()
            season_number = parts[1].strip()
        else:
            show_name = args.strip()

    try:
        # Check if show exists
        show_doc = await db.shows.find_one({"show_name": show_name, "category": category})
        
        if not show_doc:
            await db.shows.insert_one({
                "category": category,
                "show_name": show_name,
                "episodes": {},
                "poster": [],
                "audio": [],
                "genre": [],
                "subs": [],
                "release_year": None,
                "created_at": datetime.now()
            })
            await message.reply(f"Added show: **{show_name}** under **{category}**")
        
        if season_number:
            season_key = normalize_season(season_number)
            # Add season if not exists
            res = await db.shows.update_one(
                {"show_name": show_name, "category": category, f"episodes.{season_key}": {"$exists": False}},
                {"$set": {f"episodes.{season_key}": []}}
            )
            if res.modified_count:
                await message.reply(f"Added **Season {season_key}** under **{show_name}**")
            else:
                await message.reply(f"ℹ️ Season {season_key} already exists for **{show_name}**.")

        from bot.utils.cache import layered_cache, _make_show_cache_key
        from bot.utils.ids import normalize_show_slug
        # New show added — invalidate L1 so the category list refreshes
        layered_cache.invalidate_category(category)
        # Also drop L2 for this show if it was somehow cached already
        cache_key = _make_show_cache_key(category, normalize_show_slug(show_name))
        layered_cache.invalidate_show(cache_key)
        
    except Exception as e:
        logger.exception(f"Add show error: {e}")
        await message.reply(f"❌ Error adding show: {e}")


def _resolve_quality_key(qualities: dict, requested_quality: str) -> str | None:
    if requested_quality in qualities:
        return requested_quality
    lower_requested = requested_quality.lower()
    for key in qualities:
        if key.lower() == lower_requested:
            return key
    return None


async def delete_command_handler(client: Client, message: Message):
    """Delete a show, season, episode, or quality."""
    cmd = message.command[0]
    category = DELETE_CATEGORY_COMMANDS.get(cmd, "K-Hindi")

    try:
        args_text = message.text.split(" ", 1)[1].strip()
    except IndexError:
        return await message.reply(
            f"**Usage:**\n"
            f"• `/{cmd} Show Name` (Delete whole show)\n"
            f"• `/{cmd} Show Name 1` (Delete Season 1)\n"
            f"• `/{cmd} Show Name 1 2` (Delete S1 E2)\n"
            f"• `/{cmd} Show Name 1 2 720p` (Delete S1 E2 720p)"
        )

    # Build minimal data dict for _find_show_for_admin_action using L1 cache
    from bot.services.shows import get_category_shows
    _cat_shows = await get_category_shows(category)
    data = {category: {s["show_name"]: {} for s in _cat_shows}}
    tokens = args_text.split()
    actual_show_name = None
    show_name_input = args_text
    season_number = None
    episode_num = None
    quality = None

    for split_at in range(len(tokens), 0, -1):
        candidate_show = " ".join(tokens[:split_at]).strip()
        parsed_tail = _parse_delete_tail(tokens[split_at:])
        if parsed_tail is None:
            continue

        matched_show = await _find_show_for_admin_action(data, category, candidate_show)
        if matched_show:
            actual_show_name = matched_show
            show_name_input = candidate_show
            season_number, episode_num, quality = parsed_tail
            break

    if not actual_show_name:
        return await message.reply(f"❌ Show '{show_name_input}' not found in {category}.")

    # Logic to delete
    doc = await db.shows.find_one({
        "category": {"$in": _category_variants(category)},
        "show_name": actual_show_name
    })
    if not doc:
        return await message.reply(f"❌ Show missing in DB.")

    if quality and episode_num and season_number:
        season_key = str(int(season_number))
        ep_idx = episode_num - 1
        episodes = doc.get("episodes", {}).get(season_key, [])
        if ep_idx < len(episodes):
            ep = episodes[ep_idx]
            if isinstance(ep, dict) and "qualities" in ep:
                resolved_quality = _resolve_quality_key(ep["qualities"], quality)
                if resolved_quality:
                    del ep["qualities"][resolved_quality]
                    episodes[ep_idx] = ep
                    await db.shows.update_one({"_id": doc["_id"]}, {"$set": {f"episodes.{season_key}": episodes}})
                    from bot.utils.cache import layered_cache, _make_show_cache_key
                    from bot.utils.ids import normalize_show_slug
                    cache_key = _make_show_cache_key(category, normalize_show_slug(actual_show_name))
                    layered_cache.invalidate_show(cache_key)
                    return await message.reply(f"✅ Deleted **{resolved_quality}** from **S{season_key} E{episode_num}** of **{actual_show_name}**.")
        return await message.reply("❌ Quality/Episode not found.")

    if episode_num and season_number:
        season_key = str(int(season_number))
        ep_idx = episode_num - 1
        episodes = doc.get("episodes", {}).get(season_key, [])
        if ep_idx < len(episodes):
            episodes.pop(ep_idx)
            await db.shows.update_one({"_id": doc["_id"]}, {"$set": {f"episodes.{season_key}": episodes}})
            from bot.utils.cache import layered_cache, _make_show_cache_key
            from bot.utils.ids import normalize_show_slug
            cache_key = _make_show_cache_key(category, normalize_show_slug(actual_show_name))
            layered_cache.invalidate_show(cache_key)
            return await message.reply(f"✅ Deleted **S{season_key} E{episode_num}** from **{actual_show_name}**.")
        return await message.reply("❌ Episode not found.")
        
    if season_number:
        season_key = str(int(season_number))
        if season_key in doc.get("episodes", {}):
            await db.shows.update_one({"_id": doc["_id"]}, {"$unset": {f"episodes.{season_key}": ""}})
            from bot.utils.cache import layered_cache, _make_show_cache_key
            from bot.utils.ids import normalize_show_slug
            cache_key = _make_show_cache_key(category, normalize_show_slug(actual_show_name))
            layered_cache.invalidate_show(cache_key)
            return await message.reply(f"✅ Deleted **Season {season_key}** from **{actual_show_name}**.")
        return await message.reply("❌ Season not found.")

    res = await db.shows.delete_one({"_id": doc["_id"]})
    if res.deleted_count:
        from bot.utils.cache import layered_cache, _make_show_cache_key
        from bot.utils.ids import normalize_show_slug
        layered_cache.invalidate_category(category)
        cache_key = _make_show_cache_key(category, normalize_show_slug(actual_show_name))
        layered_cache.invalidate_show(cache_key)
        return await message.reply(f"✅ Deleted entire show **{actual_show_name}** from {category}.")
    await message.reply("❌ Delete failed.")

@track_performance("get_link_cmd")
async def get_link_cmd(client: Client, message: Message):
    """Resolve a slug or ID to its full details/links."""
    if len(message.command) < 2:
        return await message.reply("Usage: `/get <slug|hash>`")
    
    query = message.command[1]
    # Try hash resolution first
    identity = await resolve_id(query)
    if identity != query:
        return await message.reply(f"🔍 **Resolved Hash:**\n`{identity}`")
    
    # Try slug search
    show = await db.shows.find_one({"show_name": {"$regex": f"^{query.replace('_', ' ')}$", "$options": "i"}})
    if show:
        import json
        details = f"📺 **{show['show_name']}**\n📂 Category: {show['category']}\n\n"
        details += f"Data: `{json.dumps(show.get('episodes', {}), indent=2)}`"
        if len(details) > 4000: details = details[:4000] + "..."
        return await message.reply(details)
    
    await message.reply("❌ Nothing found for that query.")

@track_performance("user_search_cmd")
async def user_search_cmd(client: Client, message: Message):
    """Advanced user search by ID, Username, or Name with detailed profile info."""
    if len(message.command) < 2:
        return await message.reply("Usage: /user_search ID or @username or Name")
    
    query = message.text.split(" ", 1)[1].strip().replace("@", "")
    
    # Search Canonical Users
    filter_query = {
        "$or": [
            {"username":              {"$regex": f"^{query}$", "$options": "i"}},
            {"full_name":             {"$regex": query, "$options": "i"}},
            {"first_name":            {"$regex": query, "$options": "i"}},
            {"last_name":             {"$regex": query, "$options": "i"}},
            {"username_history.new":  {"$regex": f"^{query}$", "$options": "i"}},
            {"first_name_history.new":{"$regex": query, "$options": "i"}},
            {"full_name_history.new": {"$regex": query, "$options": "i"}},
        ]
    }
    if query.isdigit():
        filter_query["$or"].append({"user_id": int(query)})

    users = await db.userdb.find(filter_query).limit(10).to_list(10)
    if not users:
        return await message.reply("❌ No users found matching that query.")
    
    for u in users:
        uid = u['user_id']
        
        # Calculate activity score (same as Deep Analysis)
        interaction_count = u.get("interaction_count", 0)
        last_interaction = u.get("last_interaction")
        days_since_last = 999
        if last_interaction:
            days_since_last = (datetime.now() - last_interaction).days
        if days_since_last <= 1:
            activity_score = min(100, interaction_count * 2)
        elif days_since_last <= 7:
            activity_score = min(100, interaction_count)
        elif days_since_last <= 30:
            activity_score = min(50, interaction_count // 2)
        else:
            activity_score = min(10, interaction_count // 10)

        # Calculate preferred category
        categories = u.get("categories_browsed", [])
        preferred_category = (
            max(categories, key=lambda x: x.get("count", 0))["category"]
            if categories else "N/A"
        )

        # Browse to watch ratio
        shows_opened = len(u.get("shows_opened", []))
        episodes_watched = len(u.get("episodes_watched", []))
        if shows_opened > 0:
            bw_ratio = f"{episodes_watched}/{shows_opened}"
        else:
            bw_ratio = "N/A"

        # Favorites and reports count
        total_favorites = await db.favorites.count_documents({"user_id": uid})
        total_reports = await db.reports.count_documents({"user.user_id": uid})

        # Format dates
        last_online = u.get("last_interaction", None)
        if hasattr(last_online, "strftime"):
            last_online = last_online.strftime("%Y-%m-%d %H:%M")
        else:
            last_online = str(last_online) if last_online else "N/A"

        first_seen = u.get("created_at", None)
        if hasattr(first_seen, "strftime"):
            first_seen = first_seen.strftime("%Y-%m-%d")
        else:
            first_seen = "N/A"

        # Peak hour calculation
        timestamps = u.get("interaction_timestamps", [])
        peak_hour = "N/A"
        if timestamps:
            hour_counts = {}
            for ts in timestamps:
                h = ts.hour if hasattr(ts, "hour") else 0
                hour_counts[h] = hour_counts.get(h, 0) + 1
            peak_hour = f"{max(hour_counts, key=hour_counts.get):02d}:00"

        # Status flags
        flags = []
        if u.get("is_premium"): flags.append("💎 Premium")
        if u.get("is_verified"): flags.append("✅ Verified")
        if u.get("is_scam"): flags.append("⚠️ SCAM")
        if u.get("is_fake"): flags.append("⚠️ FAKE")
        if u.get("warned"): flags.append("🔶 Warned")
        flags_text = " | ".join(flags) if flags else "None"

        groups_count = len([c for c in u.get("chats", []) if "PRIVATE" not in str(c.get("type", ""))])
        dc_id = u.get("dc_id", "?")
        
        # Search queries summary
        searches = u.get("search_queries", [])
        recent_searches = ", ".join([s.get("query", "") for s in searches[-5:]]) if searches else "None"

        text = (
            f"🧠 **DEEP ANALYSIS - USER SEARCH**\n\n"
            f"🆔 ID: `{uid}`\n"
            f"👤 Name: {u.get('full_name', 'Unknown')}\n"
            f"📛 Username: @{u.get('username') or 'None'}\n"
            f"🌐 Language: {u.get('language_code', '?')} | DC: {dc_id}\n"
            f"🏷 Flags: {flags_text}\n\n"
            f"📊 **Activity**\n"
            f"├ Score: {activity_score}/100\n"
            f"├ Interactions: {interaction_count}\n"
            f"├ First Seen: {first_seen}\n"
            f"├ Last Seen: {last_online}\n"
            f"└ Peak Hour: {peak_hour}\n\n"
            f"🎬 **Content Behaviour**\n"
            f"├ Preferred Category: {preferred_category}\n"
            f"├ Browse→Watch: {bw_ratio}\n"
            f"├ Favorites: {total_favorites}\n"
            f"├ Reports Filed: {total_reports}\n"
            f"└ Recent Searches: {recent_searches}\n\n"
            f"🌐 **Social**\n"
            f"├ Common Chats: {groups_count}\n"
            f"└ Known Groups: {len(u.get('chats', []))}"
        )
        
        btns = []
        
        # Row 1: Profile Pics
        past_pics = u.get("profile_pic_history", [])
        pic_row = [InlineKeyboardButton("🖼 Current Pic", callback_data=f"mp_pic_curr|{uid}")]
        # Only add past buttons if there are actual history entries
        for i, _ in enumerate(past_pics[-5:], 1):
            idx_in_full = len(past_pics) - len(past_pics[-5:]) + (i - 1)
            pic_row.append(InlineKeyboardButton(f"🖼 Past {i}", callback_data=f"mp_pic_idx|{uid}|{idx_in_full}"))
        for chunk in [pic_row[j:j+4] for j in range(0, len(pic_row), 4)]:
            btns.append(chunk)
        
        # Row 2: Name History & Group List
        btns.append([
            InlineKeyboardButton("📜 Name History", callback_data=f"mp_names|{uid}"),
            InlineKeyboardButton("🏢 Group List", callback_data=f"mp_groups|{uid}")
        ])
        
        # Row 3: Last Seen & Watch History
        btns.append([
            InlineKeyboardButton("🕒 Last Seen Hist", callback_data=f"mp_lastseen|{uid}"),
            InlineKeyboardButton("🗂 Watch History", callback_data=f"user_history_{uid}")
        ])
        
        sent = await _send_user_photo(
            client, message.chat.id, uid,
            caption=text, reply_markup=InlineKeyboardMarkup(btns)
        )
        if not sent:
            await message.reply(text, reply_markup=InlineKeyboardMarkup(btns))

@track_performance("report_search_cmd")
async def report_search_cmd(client: Client, message: Message):
    """Search for reports by show or user."""
    if len(message.command) < 2:
        return await message.reply("Usage: `/report_search <Show_Name|User_ID>`")
    
    query = message.text.split(" ", 1)[1].strip()
    filter_q = {
        "$or": [
            {"report": {"$regex": query, "$options": "i"}},
            {"user.username": {"$regex": query, "$options": "i"}},
            {"user.full_name": {"$regex": query, "$options": "i"}}
        ]
    }
    if query.isdigit(): filter_q["$or"].append({"user.user_id": int(query)})
    
    reports = await db.reports.find(filter_q).sort("created_at", -1).limit(5).to_list(5)
    if not reports:
        return await message.reply("❌ No reports found.")
    
    for r in reports:
        await message.reply(
            f"🚩 **Report Search Result**\n"
            f"👤 User: {r['user']['full_name']} (@{r['user'].get('username')})\n"
            f"📄 Report: {r['report']}\n"
            f"⏰ Created: {r['created_at'].strftime('%Y-%m-%d %H:%M')}\n"
            f"🚦 Status: {r['status']}"
        )

@track_performance("user_history_cb")
async def user_history_cb(client: Client, callback_query: CallbackQuery):
    """Handle the 'History' button from max-profile/search."""
    try:
        target_uid = int(callback_query.data.split("_")[2])
        from bot.services.users import get_watch_history
        history = await get_watch_history(target_uid)
        
        if not history:
            return await safe_answer(callback_query, "Watch history is empty.", show_alert=True)
            
        text = f"📜 **Watch History for User `{target_uid}`:**\n\n"
        for item in history:
            text += f"• {item}\n"
        await callback_query.message.reply(text)
        await safe_answer(callback_query)
    except Exception as e:
        logger.exception(f"user_history_cb error: {e}")
        await safe_answer(callback_query, "Error loading history.", show_alert=True)

@track_performance("max_profile_view_history")
async def mp_history_cb(client: Client, callback_query: CallbackQuery):
    """Handle Max-Profile dynamic button views."""
    data = callback_query.data.split("|")
    action = data[0]
    uid = int(data[1])
    
    u = await db.userdb.find_one({"user_id": uid})
    if not u:
        return await safe_answer(callback_query, "❌ User data not found.", show_alert=True)
        
    if action == "mp_names":
        msg = f"📜 **Name History for {uid}** (Recent 20)\n\n"
        has_data = False
        if u.get("username_history"):
            has_data = True
            msg += "**Usernames:**\n"
            for h in u["username_history"][-20:]:
                msg += f"• `{h.get('old', 'None')}` -> `{h.get('new', 'None')}` (On {h.get('changed_at')})\n"
            msg += "\n"
        if u.get("first_name_history"):
            has_data = True
            msg += "**First Names:**\n"
            for h in u["first_name_history"][-20:]:
                msg += f"• `{h.get('old', 'None')}` -> `{h.get('new', 'None')}` (On {h.get('changed_at')})\n"
            msg += "\n"
        if u.get("full_name_history"):
            has_data = True
            msg += "**Full Names:**\n"
            for h in u["full_name_history"][-20:]:
                msg += f"• `{h.get('old', 'None')}` -> `{h.get('new', 'None')}` (On {h.get('changed_at')})\n"
                
        if not has_data: msg = "No historical name changes recorded."
        await callback_query.message.reply(msg)
        await safe_answer(callback_query)
        
    elif action == "mp_groups":
        msg = f"🏢 **Known Groups for {uid}** (Recent 20)\n\n"
        group_found = False
        for c in u.get("chats", []):
            if str(c.get("type")) == "ChatType.PRIVATE": continue
            msg += f"• **{c.get('title', 'Unknown')}**\n  ID: `{c.get('chat_id')}`\n  Type: {c.get('type')}\n\n"
            group_found = True
            
        if not group_found: msg = "No groups recorded."
        await callback_query.message.reply(msg)
        await safe_answer(callback_query)

    elif action == "mp_lastseen":
        msg = f"🕒 **Last Seen History for {uid}** (Recent 20)\n\n"
        chats = u.get("chats", [])
        if not chats:
            msg = "No last seen history recorded."
        else:
            for c in chats[-20:]:
                title = c.get("title", "DM/Unknown")
                last_seen = c.get("last_seen", "")
                if hasattr(last_seen, "strftime"):
                    last_seen = last_seen.strftime("%Y-%m-%d %H:%M")
                first_seen = c.get("first_seen", "")
                if hasattr(first_seen, "strftime"):
                    first_seen = first_seen.strftime("%Y-%m-%d %H:%M")
                chat_type = str(c.get("type", "")).replace("ChatType.", "")
                msg += f"• **{title}** ({chat_type})\n  First: {first_seen}\n  Last: {last_seen}\n\n"
        await callback_query.message.reply(msg)
        await safe_answer(callback_query)
        
    elif action == "mp_pic_idx":
        try:
            idx = int(data[2])
            pics = u.get("profile_pic_history", [])
            if 0 <= idx < len(pics):
                p = pics[idx]
                changed = p.get("changed_at", "")
                if hasattr(changed, "strftime"):
                    changed = changed.strftime("%Y-%m-%d %H:%M")
                await safe_answer(callback_query)
                try:
                    await client.send_photo(
                        callback_query.message.chat.id,
                        p["file_id"],
                        caption=f"🖼 Past Profile Picture #{idx+1}\nChanged: {changed}"
                    )
                except Exception:
                    # file_id may be CHAT_PHOTO type for old records — show info instead
                    await callback_query.message.reply(
                        f"🖼 Past Profile Picture #{idx+1}\nChanged: {changed}\n"
                        f"_(Photo unavailable — old record format)_"
                    )
            else:
                await safe_answer(callback_query, "Picture no longer in records.", show_alert=True)
        except Exception:
            await safe_answer(callback_query, "Error fetching picture.", show_alert=True)
            
    elif action == "mp_pic_past":
        pics = u.get("profile_pic_history", [])
        if not pics:
            return await safe_answer(callback_query, "No past profile pictures found.", show_alert=True)
        await safe_answer(callback_query)
        for i, p in enumerate(pics[-5:]):
            changed = p.get("changed_at", "")
            if hasattr(changed, "strftime"):
                changed = changed.strftime("%Y-%m-%d %H:%M")
            try:
                await client.send_photo(
                    callback_query.message.chat.id,
                    p["file_id"],
                    caption=f"🖼 Past Profile Picture #{i+1}\nChanged: {changed}"
                )
            except Exception:
                await callback_query.message.reply(
                    f"🖼 Past Profile Picture #{i+1}\nChanged: {changed}\n_(Photo unavailable — old record format)_"
                )
            
    elif action == "mp_pic_curr":
        await safe_answer(callback_query)
        sent = await _send_user_photo(
            client,
            callback_query.message.chat.id,
            uid,
            caption=f"🖼 Current Profile Picture for `{uid}`"
        )
        if not sent:
            await callback_query.message.reply(f"No profile picture available for `{uid}`.")

# --- PHASE 3: MISSING CALLBACKS ---

@track_performance("max_profile_cb")
async def max_profile_cb(client: Client, callback_query: CallbackQuery):
    """Handle Deep Analysis button from report card."""
    try:
        uid = int(callback_query.data.replace("max_profile_", ""))
        from bot.services.profile import calculate_max_profile, format_max_profile_text
        profile = await calculate_max_profile(uid)
        text = format_max_profile_text(profile)

        past_pics = profile.get("profile_pic_history", []) if profile else []
        btns = []

        # Pic row
        pic_row = [InlineKeyboardButton("🖼 Current Pic", callback_data=f"mp_pic_curr|{uid}")]
        for i, _ in enumerate(past_pics[-5:], 1):
            idx_in_full = len(past_pics) - len(past_pics[-5:]) + (i - 1)
            pic_row.append(InlineKeyboardButton(f"🖼 Past {i}", callback_data=f"mp_pic_idx|{uid}|{idx_in_full}"))
        for chunk in [pic_row[i:i+4] for i in range(0, len(pic_row), 4)]:
            btns.append(chunk)

        btns.append([
            InlineKeyboardButton("📜 Name History", callback_data=f"mp_names|{uid}"),
            InlineKeyboardButton("🏢 Group List",   callback_data=f"mp_groups|{uid}")
        ])
        btns.append([
            InlineKeyboardButton("🕒 Last Seen",    callback_data=f"mp_lastseen|{uid}"),
            InlineKeyboardButton("🗂 Watch History", callback_data=f"user_history_{uid}")
        ])
        btns.append([
            InlineKeyboardButton("🌐 Common Chats", callback_data=f"mp_common_chats|{uid}")
        ])

        sent = await _send_user_photo(
            client,
            callback_query.message.chat.id,
            uid,
            caption=text,
            reply_markup=InlineKeyboardMarkup(btns)
        )
        if not sent:
            await callback_query.message.reply(text, reply_markup=InlineKeyboardMarkup(btns))
        await safe_answer(callback_query)
    except Exception as e:
        logger.exception(f"max_profile_cb error: {e}")
        await safe_answer(callback_query, "Error loading profile.", show_alert=True)


@track_performance("report_view_user_cb")
async def report_view_user_cb(client: Client, callback_query: CallbackQuery):
    """Show all reports submitted by a specific user."""
    try:
        uid = int(callback_query.data.split("|")[1])
        reports = await db.reports.find(
            {"user.user_id": uid}
        ).sort("created_at", -1).limit(5).to_list(5)

        if not reports:
            return await safe_answer(callback_query, "No reports from this user.", show_alert=True)

        text = f"📋 **Reports from User `{uid}`** (last {len(reports)})\n\n"
        for r in reports:
            created = r.get("created_at", "N/A")
            if hasattr(created, "strftime"):
                created = created.strftime("%Y-%m-%d %H:%M")
            issue = str(r.get("report", ""))
            if isinstance(r.get("report"), dict):
                issue = r["report"].get("issue", "")
            text += (
                f"🚦 {r.get('status', 'N/A').upper()}\n"
                f"🎬 Show: {r.get('show_name') or r.get('report', {}).get('show_name') or 'N/A'}\n"
                f"💬 {issue[:100]}\n"
                f"📅 {created}\n\n"
            )
        await callback_query.message.reply(text)
        await safe_answer(callback_query)
    except Exception as e:
        logger.exception(f"report_view_user_cb error: {e}")
        await safe_answer(callback_query, "Error loading reports.", show_alert=True)


@track_performance("report_search_show_cb")
async def report_search_show_cb(client: Client, callback_query: CallbackQuery):
    """Show all reports about a specific show."""
    try:
        show_name = callback_query.data.split("|", 1)[1]
        reports = await db.reports.find(
            {"$or": [
                {"report.show_name": {"$regex": show_name, "$options": "i"}},
                {"show_name":        {"$regex": show_name, "$options": "i"}}
            ]}
        ).sort("created_at", -1).limit(5).to_list(5)

        if not reports:
            return await safe_answer(callback_query, "No reports for this show.", show_alert=True)

        text = f"📋 **Reports for show: {show_name}** (last {len(reports)})\n\n"
        for r in reports:
            created = r.get("created_at", "N/A")
            if hasattr(created, "strftime"):
                created = created.strftime("%Y-%m-%d %H:%M")
            user = r.get("user", {})
            issue = str(r.get("report", ""))
            if isinstance(r.get("report"), dict):
                issue = r["report"].get("issue", "")
            text += (
                f"👤 {user.get('full_name', 'Unknown')} (`{user.get('user_id', '?')}`)\n"
                f"🚦 {r.get('status', 'N/A').upper()}\n"
                f"💬 {issue[:100]}\n"
                f"📅 {created}\n\n"
            )
        await callback_query.message.reply(text)
        await safe_answer(callback_query)
    except Exception as e:
        logger.exception(f"report_search_show_cb error: {e}")
        await safe_answer(callback_query, "Error loading reports.", show_alert=True)


@track_performance("mp_common_chats_cb")
async def mp_common_chats_cb(client: Client, callback_query: CallbackQuery):
    """Show common chats for a user."""
    try:
        uid = int(callback_query.data.split("|")[1])
        u = await db.userdb.find_one({"user_id": uid}, {"common_chats": 1})
        chats = (u or {}).get("common_chats", [])
        if not chats:
            return await safe_answer(callback_query, "No common chats recorded.", show_alert=True)
        text = f"🌐 **Common Chats for `{uid}`** ({len(chats)} total)\n\n"
        for c in chats[:20]:
            text += f"• {c.get('title', 'Unknown')} (`{c.get('chat_id')}`) — {c.get('type', '')}\n"
        await callback_query.message.reply(text)
        await safe_answer(callback_query)
    except Exception as e:
        logger.exception(f"mp_common_chats_cb error: {e}")
        await safe_answer(callback_query, "Error loading common chats.", show_alert=True)


# --- REGISTRATION ---

def register_admin_data_handlers(app: Client):
    # Import commands
    app.on_message(filters.command(list(IMPORT_CATEGORY_MAP.keys())) & admin_filter & filters.private)(import_command_handler)
    
    # Poster commands
    app.on_message(filters.command(list(POSTER_CATEGORY_COMMANDS.keys()) + ["add_poster"]) & admin_filter & filters.private)(add_poster_command)
    
    # Metadata commands
    app.on_message(filters.command("add_audio") & admin_filter & filters.private)(add_audio_cmd)
    app.on_message(filters.command("set_audio") & admin_filter & filters.private)(set_audio_cmd)
    app.on_message(filters.command("add_genre") & admin_filter & filters.private)(add_genre_cmd)
    app.on_message(filters.command("set_genre") & admin_filter & filters.private)(set_genre_cmd)
    app.on_message(filters.command("add_subs") & admin_filter & filters.private)(add_subs_cmd)
    app.on_message(filters.command("set_subs") & admin_filter & filters.private)(set_subs_cmd)
    app.on_message(filters.command("set_metadata") & admin_filter & filters.private)(set_metadata_cmd)
    app.on_message(filters.command(list(RELEASE_DATE_CATEGORY_COMMANDS.keys())) & admin_filter & filters.private)(set_release_date_cmd)
    
    # General Admin
    app.on_message(filters.command(["add", "add_hindi", "add_orig", "add_jap", "add_c", "add_glb", "add_pak", "add_anime"]) & admin_filter & filters.private)(add_show_cmd)
    app.on_message(filters.command(list(DELETE_CATEGORY_COMMANDS.keys()) + ["delete"]) & admin_filter & filters.private)(delete_command_handler)
    app.on_message(filters.command("get") & admin_filter & filters.private)(get_link_cmd)
    app.on_message(filters.command("user_search") & admin_filter & filters.private)(user_search_cmd)
    app.on_message(filters.command("report_search") & admin_filter & filters.private)(report_search_cmd)
    app.on_callback_query(filters.regex(r"^user_history_\d+$") & admin_filter)(user_history_cb)
    app.on_callback_query(filters.regex(r"^mp_common_chats\|") & admin_filter)(mp_common_chats_cb)
    app.on_callback_query(filters.regex(r"^mp_") & admin_filter)(mp_history_cb)
    app.on_callback_query(filters.regex(r"^max_profile_") & admin_filter)(max_profile_cb)
    app.on_callback_query(filters.regex(r"^report_view_user\|") & admin_filter)(report_view_user_cb)
    app.on_callback_query(filters.regex(r"^report_search_show\|") & admin_filter)(report_search_show_cb)
    app.on_message(filters.command("get_links") & admin_filter)(get_links_cmd)
    # Stateful reception
    # Poster handler runs at group -1 (higher priority than import at group 0).
    # This guarantees poster images are never intercepted by the import handler.
    app.on_message((filters.photo | filters.document) & filters.private & filters.incoming, group=-1)(handle_poster_receive)
    app.on_message(filters.private & filters.incoming & ~filters.command(["start", "help"]), group=0)(handle_import_receive)
