# K-Drama Bot Command Guide

Readable command reference for the current bot code. Admin commands work only for configured admins in private chat.

In examples, replace `showname` with the real show name. Hindi/K-Hindi uses the base command with no category suffix, for example:

```text
/delete showname 1 1 480p
```

---

## 1. Category Command Names

### Core category suffixes

```text
Hindi / K-Hindi           -> base commands with no suffix
K-Original                -> _orig
Japanese Drama            -> _jap
CT Drama / C Drama        -> _c
Global                    -> _glb
Pakistan                  -> _pak
Anime                     -> _anime
```

### Base and explicit category commands

```text
Base Hindi commands:
/add
/delete
/add_poster

Explicit Hindi commands:
/add_hindi
/delete_hindi
/add_poster_hindi
/import_hindi

Other category commands:
/add_orig    /delete_orig    /add_poster_orig    /import_orig
/add_jap     /delete_jap     /add_poster_jap     /import_jap
/add_c       /delete_c       /add_poster_c       /import_c
/add_glb     /delete_glb     /add_poster_glb     /import_glb
/add_pak     /delete_pak     /add_poster_pak     /import_pak
/add_anime   /delete_anime   /add_poster_anime   /import_anime
```

### Category aliases supported inside metadata and release-date commands

```text
hindi
hindi_dubbed
hindi_dub
regional
orig
cdrama
c
arabic
glb
global
japanese
jap
pakistan
pak
anime
```

---

## 2. Add Show / Add Season Commands

### Add a new show

```text
/add showname
/add_hindi showname
/add_orig showname
/add_jap showname
/add_c showname
/add_glb showname
/add_pak showname
/add_anime showname
```

### Add a new season

```text
/add showname 1
/add_hindi showname 1
/add_orig showname 1
/add_jap showname 1
/add_c showname 1
/add_glb showname 1
/add_pak showname 1
/add_anime showname 1
```

### Inline category form

```text
/add showname > c
/add showname > c 1
/add showname > japanese
/add showname > global 1
/add showname > anime 1
/add showname > orig 1
/add showname > pakistan
```

> Use the alias list above for the inline category.

---

## 3. Delete Commands

Use `/delete` for Hindi. For other categories, use the explicit category delete command.

### Delete full show

```text
/delete showname
/delete_orig showname
/delete_jap showname
/delete_c showname
/delete_glb showname
/delete_pak showname
/delete_anime showname
```

### Delete a season

```text
/delete showname 1
/delete_orig showname 1
/delete_jap showname 1
/delete_c showname 1
/delete_glb showname 1
/delete_pak showname 1
/delete_anime showname 1
```

### Delete an episode

```text
/delete showname 1 1
/delete_orig showname 1 1
/delete_jap showname 1 1
/delete_c showname 1 1
/delete_glb showname 1 1
/delete_pak showname 1 1
/delete_anime showname 1 1
```

### Delete a quality from an episode

```text
/delete showname 1 1 480p
/delete showname 1 1 720p
/delete showname 1 1 1080p
/delete showname 1 1 1080p-10bit
/delete showname 1 1 1080p-10bit Hevc
/delete showname 1 1 4k
```

```text
/delete_orig showname 1 1 480p
/delete_jap showname 1 1 720p
/delete_c showname 1 1 1080p-10bit
/delete_glb showname 1 1 1080p-10bit Hevc
/delete_pak showname 1 1 4k
/delete_anime showname 1 1 720p
```

### S-Season format (useful when show name ends in a number)

```text
/delete showname S1
/delete showname S1 1
/delete showname S1 1 480p
/delete showname S1 1 1080p
/delete_orig showname S1 1 720p
/delete_jap showname S1 1 1080p-10bit
/delete_c showname S1 1 1080p-10bit Hevc
/delete_glb showname S1 1 4k
/delete_pak showname S1 1 480p
/delete_anime showname S1 1 720p
```

### Show names with numbers example

```text
/delete_c go go squid 2
/delete_c go go squid 2 S1 1 720p
```

> If the show name contains spaces or special characters, quote it in commands to ensure correct parsing.

---

## 4. Import Episode Commands

Import commands create or update an episode entry, then the next sent message must be the video/document/link.

### Supported import commands

```text
/import_hindi
/import_orig
/import_jap
/import_c
/import_glb
/import_pak
/import_anime
```

### Basic import formats

```text
/import_hindi showname S1 E1 480p
/import_orig showname S1 E1 720p
/import_jap showname S1 E1 1080p
/import_c showname S1 E1 1080p-10bit
/import_glb showname S1 E1 1080p-10bit Hevc
```

### Quoted show names

```text
/import_hindi "show name" S1 E1 720p
/import_orig "show name" S1 E1 1080p-10bit
/import_c "go go squid 2" S1 E1 720p
```

### Split part imports

```text
/import_hindi showname S1 E1 720p P1
/import_hindi showname S1 E1 720p P2
/import_hindi showname S1 E1 720p P3
```

```text
/import_c showname S1 E1 1080p-10bit P1
/import_c showname S1 E1 1080p-10bit Hevc P2
```

### Full examples

```text
/import_c go go squid 2 S1 E1 720p
/import_c "go go squid 2" S1 E1 720p
/import_jap my drama S2 E5 1080p P1
/import_glb another show S1 E3 1080p-10bit Hevc P2
```

---

## 5. Poster Commands

Send the command, then send a photo or image file.

### Poster commands

```text
/add_poster showname
/add_poster_hindi showname
/add_poster_orig showname
/add_poster_jap showname
/add_poster_c showname
/add_poster_glb showname
/add_poster_pak showname
/add_poster_anime showname
```

### Example

```text
/add_poster "My Drama"
/add_poster_orig showname
```

---

## 6. Metadata Commands

These admin-only commands add or replace metadata fields for a show.

### Add metadata values

```text
/add_audio "Show Name" Hindi,English
/add_genre "Show Name" Romance,Drama
/add_subs "Show Name" English,Hindi
```

### Set metadata values (replace existing values)

```text
/set_audio "Show Name" Hindi,English
/set_genre "Show Name" Romance,Drama
/set_subs "Show Name" English,Hindi
```

### Category-specific metadata commands

```text
/add_audio_orig "Show Name" Hindi,English
/set_genre_jap "Show Name" Romance,Drama
/add_subs_c "Show Name" English,Hindi
```

### Inline category metadata form

```text
/add_audio "Show Name" > c Hindi,English
/set_genre "Show Name" > jap Romance,Drama
/add_subs "Show Name" > glb English,Hindi
```

### Combined metadata command

```text
/set_metadata "Show Name" audio=Hindi,English subs=English,Hindi genre=Romance,Drama year=2026
/set_metadata "Show Name" > c audio=Hindi,English subs=English,Hindi genre=Romance,Drama year=2026
```

### Supported metadata keys for `/set_metadata`

```text
audio
genre
subs
subtitles  (alias for subs)
year
```

> `subtitles=` is accepted and normalized to `subs`.

---

## 7. Release Date Commands

Set a show's release date using the new release-date commands.

### Commands

```text
/set_release_date "Show Name" April 2, 2026
/set_release_date_orig "Show Name" April 2, 2026
/set_release_date_jap "Show Name" April 2, 2026
/set_release_date_c "Show Name" April 2, 2026
/set_release_date_glb "Show Name" April 2, 2026
/set_release_date_pak "Show Name" April 2, 2026
/set_release_date_anime "Show Name" April 2, 2026
```

### Inline category form

```text
/set_release_date "Show Name" > c April 2, 2026
/set_release_date "Show Name" > jap April 2, 2026
/set_release_date "Show Name" > glb April 2, 2026
```

### Examples

```text
/set_release_date "My Drama" February 14, 2026
/set_release_date_orig "Old Drama" March 1, 2026
/set_release_date "My Drama" > anime January 1, 2026
```

---

## 8. General Admin Utility Commands

These are admin-only commands available in private chat.

```text
/get <slug|hash>
/user_search <query>
/report_search <query>
/get_links <slug|hash>
```

### Examples

```text
/get my_drama_slug
/user_search actor name
/report_search bad link
/get_links 123456
```

---

## 9. Full command combos summary

### Add / delete / import / poster

```text
/add showname
/add showname 1
/add showname > c
/add showname > c 1
/add_hindi showname
/add_orig showname
/add_jap showname
/add_c showname
/add_glb showname
/add_pak showname
/add_anime showname
```

```text
/delete showname
/delete showname 1
/delete showname 1 1
/delete showname 1 1 480p
/delete showname 1 1 1080p-10bit
/delete showname 1 1 1080p-10bit Hevc
/delete showname S1 1 480p
/delete showname S1 1 1080p
/delete_c go go squid 2 S1 1 720p
```

```text
/import_hindi showname S1 E1 480p
/import_orig "Show Name" S1 E1 720p
/import_jap showname S1 E1 1080p
/import_c showname S1 E1 1080p-10bit P1
/import_glb showname S1 E1 1080p-10bit Hevc P2
/import_pak showname S1 E1 4k P1
/import_anime showname S1 E1 720p P1
```

```text
/add_poster showname
/add_poster_orig showname
/add_poster_jap showname
/add_poster_c showname
/add_poster_glb showname
/add_poster_pak showname
/add_poster_anime showname
```

### Metadata and release date

```text
/add_audio "Show Name" Hindi,English
/set_audio "Show Name" Hindi,English
/add_genre "Show Name" Romance,Drama
/set_genre "Show Name" Romance,Drama
/add_subs "Show Name" English,Hindi
/set_subs "Show Name" English,Hindi
/set_metadata "Show Name" audio=Hindi,English subs=English,Hindi genre=Romance,Drama year=2026
```

```text
/add_audio "Show Name" > c Hindi,English
/set_genre "Show Name" > jap Romance,Drama
/add_subs "Show Name" > glb English,Hindi
```

```text
/set_release_date "Show Name" April 2, 2026
/set_release_date "Show Name" > c April 2, 2026
/set_release_date_orig "Show Name" April 2, 2026
/set_release_date_jap "Show Name" April 2, 2026
```

---

## 10. Notes

- All admin commands must be used in private chat and are restricted to configured admin IDs.
- Use quotes around show names with spaces when the command parser may otherwise split the name incorrectly.
- For delete + import quality values, the bot accepts modifiers like `1080p-10bit` and `1080p-10bit Hevc`.
- `P1`, `P2`, `P3`, etc. are only used for split-part import commands; delete commands ignore trailing `P...`/`I` part indicators.
- Metadata commands can use `> category` to target a different category than the default implied by the command name.
- `/set_metadata` can update multiple fields in one command.

```text
/add_audio "Show Name" Hindi,English
/set_audio "Show Name" Hindi,English
/add_genre "Show Name" Romance,Drama
/set_genre "Show Name" Romance,Drama
/add_subs "Show Name" English,Hindi
/set_subs "Show Name" English,Hindi
/set_release_date "Show Name" April 2, 2026
/set_release_date "Show Name" > glb April 2, 2026
/set_metadata "Show Name" audio=Hindi,English genre=Romance,Drama subs=English release_date="April 2, 2026"
/set_metadata "Show Name" > glb audio=Hindi genre=Romance release_date="April 2, 2026"
```

Release date command format:
```text
/set_release_date "Show Name" April 2, 2026
/set_release_date "Show Name" > category April 2, 2026
```

Category-specific release date commands:
```text
/set_release_date_orig "Show Name" April 2, 2026
/set_release_date_jap "Show Name" April 2, 2026
/set_release_date_c "Show Name" April 2, 2026
/set_release_date_glb "Show Name" April 2, 2026
/set_release_date_pak "Show Name" April 2, 2026
/set_release_date_anime "Show Name" April 2, 2026
```

Category-specific metadata commands:
```text
/add_audio_orig "Show Name" Korean,English
/set_audio_orig "Show Name" Korean,English
/add_genre_orig "Show Name" Romance,Thriller
/set_genre_orig "Show Name" Romance,Thriller
/add_subs_orig "Show Name" English
/set_subs_orig "Show Name" English
/add_audio_jap "Show Name" Korean,English
/set_audio_jap "Show Name" Korean,English
/add_genre_jap "Show Name" Romance,Thriller
/set_genre_jap "Show Name" Romance,Thriller
/add_subs_jap "Show Name" English
/set_subs_jap "Show Name" English
/add_audio_c "Show Name" Mandarin,English
/set_audio_c "Show Name" Mandarin,English
/add_genre_c "Show Name" Romance,Thriller
/set_genre_c "Show Name" Romance,Thriller
/add_subs_c "Show Name" English
/set_subs_c "Show Name" English
/add_audio_glb "Show Name" English,Hindi
/set_audio_glb "Show Name" English,Hindi
/add_genre_glb "Show Name" Romance,Thriller
/set_genre_glb "Show Name" Romance,Thriller
/add_subs_glb "Show Name" English
/set_subs_glb "Show Name" English
/add_audio_pak "Show Name" Urdu,English
/set_audio_pak "Show Name" Urdu,English
/add_genre_pak "Show Name" Romance,Drama
/set_genre_pak "Show Name" Romance,Drama
/add_subs_pak "Show Name" English
/set_subs_pak "Show Name" English
/add_audio_anime "Show Name" Japanese,English
/set_audio_anime "Show Name" Japanese,English
/add_genre_anime "Show Name" Action,Fantasy
/set_genre_anime "Show Name" Action,Fantasy
/add_subs_anime "Show Name" English
/set_subs_anime "Show Name" English
```

Notes:
- Use quotes when the show name contains spaces.
- The `> category` form can override the command's default category.
- For bare `/add_...` / `/set_...` commands, the default category is Hindi.
- `add_` commands append values; `set_` commands replace the field.
- Metadata values support commas for multiple items: `Hindi,English`.
- Use `release_date="April 2, 2026"` in `/set_metadata` when the value contains spaces.

## 8. Admin Utility Commands

```text
/stats
/selftest
/sync_users
/banned_list

Broadcast:
/broadcast message text
or reply to any message with:
/broadcast

Sticker setting:
reply to a sticker with:
/set_sticker

Unban:
/unban user_id
/unban @username
/unban full name

Lookup:
/get slug_or_hash

User search:
/user_search user_id
/user_search @username
/user_search full name

Report search:
/report_search showname
/report_search user_id
```

## 8. Quick Most-Used Examples

```text
Delete Hindi episode quality:
/delete showname 1 1 720p
/delete showname S1 1 720p

Delete CT Drama episode quality:
/delete_c showname 1 1 720p
/delete_c showname S1 1 720p

Delete from show ending with number:
/delete_c go go squid 2 S1 1 720p

Add CT Drama show:
/add_c go go squid 2

Import CT Drama episode:
/import_c go go squid 2 S1 E1 720p

Add CT Drama poster:
/add_poster_c go go squid 2
```
