# PS99 Restock Bot

A Discord-controlled bot for Pet Simulator 99 that prices your
Huges off live RAP and Cosmic Value, lists them automatically, and
pauses itself the moment your booth fills up — with a small
always-on-top status window and a live-adjustable markup %.

This guide walks through everything from a completely empty
computer to a running bot. Follow it top to bottom — each step
depends on the one before it.

**Important:** this bot has to run on your own Windows computer,
with Roblox open on screen, because it works by moving your mouse
and reading your screen. It can't be hosted anywhere else.

You need these three files together in one folder (e.g.
`Desktop\ps99-restock-bot\`):
- `ps99_restock_bot.py`
- `requirements.txt`
- `run.bat`

---

## Part 1 — Install Python

1. Go to **https://www.python.org/downloads/**
2. Click the yellow **Download Python** button
3. Run the installer
4. **On the very first screen, check the box "Add python.exe to
   PATH"** before clicking Install — this is the single most common
   thing people miss
5. Click through the rest with default options

You don't need to install anything extra for the status window —
it uses `tkinter`, which comes bundled with Python automatically.

---

## Part 2 — Create the Discord Bot

This makes a Discord "application" that the code can log into.

1. Go to **https://discord.com/developers/applications**
2. Click **New Application** (top right), give it any name (e.g.
   "PS99 Restock Bot"), and accept the terms
3. On the left sidebar, click **Bot**
4. Click **Reset Token**, confirm, then click **Copy** — this is
   your `DISCORD_TOKEN`. Save it somewhere temporarily (like Notepad)
   — Discord will not show it to you again
5. Still on the Bot page, make sure **Public Bot** is toggled off
   unless you want strangers able to add it to their own servers
6. On the left sidebar, click **OAuth2** → **URL Generator**
7. Under **Scopes**, check both:
   - `bot`
   - `applications.commands`
8. Under **Bot Permissions** (appears once you check `bot`), check:
   - `Send Messages`
   - `View Channels`
   - `Read Message History`
   - `Attach Files` (needed for `/boothcap`'s debug screenshots)
9. Scroll down, copy the **Generated URL**, paste it into your
   browser, pick your Discord server, and click **Authorize**

Your bot now exists in your server (it'll show offline until you
actually run it later).

### Getting your Channel ID
1. In Discord, go to **User Settings** (gear icon) → **Advanced** →
   turn on **Developer Mode**
2. Right-click the channel you want restock alerts posted in →
   **Copy Channel ID**

---

## Part 3 — Create the BIG Games (PS99) Developer App

This is what lets the bot read your PS99 inventory and booth data.

1. Go to **https://db.biggames.io/settings/developer-apps**
2. Sign in with your BIG Games account — the same one you use to
   play Pet Simulator 99. Create one if you don't have it yet
3. Click **Create app**
4. Fill in:
   - **App name** — anything, e.g. "My Restock Bot"
   - **Redirect URI** — enter exactly:
     ```
     http://localhost:8080/callback
     ```
     This must match exactly, including `http://` (not `https://`)
     and the `/callback` at the end, or authorization will fail
     later.
   - **Scopes** — add these three:
     ```
     player-data:pet-simulator-99:booth:read
     player-data:pet-simulator-99:inventory:read
     player-data:pet-simulator-99:profile:read
     ```
5. Save the app. The dashboard now shows a **Client ID** and a
   **Client Secret**
6. **Copy both now** — the secret is only ever shown once. If you
   lose it, you'll need to regenerate it.

---

## Part 4 — Start the Bot

1. Double-click **`run.bat`**
2. First run only, it installs a handful of small packages — this
   takes a minute or two, you'll see text scroll by
3. It will then ask you four questions right in that window. Paste
   each answer and press Enter:
   - **Discord Bot Token** → from Part 2, step 4
   - **Discord Channel ID** → from Part 2, "Getting your Channel ID"
     (or press Enter to skip — it'll just print to the console
     instead)
   - **PS99 Client ID** → from Part 3, step 5
   - **PS99 Client Secret** → from Part 3, step 5

These are saved to a `.env` file next to the bot, so you'll never
be asked again unless that file is deleted.

4. A small **always-on-top status window** will appear. Leave it —
   it shows connection status, queue size, booth status, and lets
   you adjust the markup percentage live

5. In Discord, type `/authorize` — a browser window opens, log into
   BIG Games and approve access. The bot can now see your inventory.

---

## Part 5 — The Status Window

The little window that pops up shows, live:
- 🟢/🔴 whether it's connected to Discord
- How many jobs are waiting in the restock queue
- Whether the booth is full (and paused) or running
- The last thing that happened (a restock, an error, a markup
  change)
- A **markup %** box — this is how much above the higher of RAP or
  Cosmic Value each item gets listed for. Change the number and
  click **Apply** (or press Enter) — it applies to the very next
  listing, no restart needed.

You can also check or change the markup from Discord with
`/markup` (leave the `percent` option blank to just check it).

---

## Part 6 — Commands

| Command | What it does |
|---|---|
| `/restock` | Lists all your Huges, cheapest RAP first |
| `/sell item:X amount:5` | Queues 5 of item X to be listed |
| `/queue` | Shows what's waiting to be listed |
| `/huges` | Shows your Huges under a RAP limit |
| `/booth` | Shows recent booth sales |
| `/markup` | Check or change the markup % |
| `/apistatus` | Shows your PS99 inventory API quota |
| `/boothcap` | Debug tool for the booth-full screen reader |
| `/stop` | Stops everything (admin only) |

---

## Troubleshooting

**"Python was not found"** — Python wasn't added to PATH. Reinstall
and check that box in Part 1, step 4.

**It asks the setup questions again on a later launch** — the
`.env` file next to the bot was deleted or moved. Recreate it by
just going through the questions again.

**`/authorize` fails or the browser shows an error** — double check
the redirect URI in your BIG Games app is *exactly*
`http://localhost:8080/callback`, with no typos and no trailing
slash difference.

**The status window doesn't show up** — check the black console
window behind it for an error message; a Python or package issue
would print there.

**Listings click the wrong spot on screen** — the click coordinates
in the bot are tuned to one specific screen size and Roblox window
position. That needs a code adjustment, not a setup fix — ask
whoever set this up for you to retune the `COORD` values.
