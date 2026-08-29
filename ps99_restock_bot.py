import os
import time
import asyncio
import threading
import ctypes
import re
import secrets
import hashlib
import base64
import webbrowser
import tkinter as tk
from tkinter import ttk

from collections import deque
from urllib.parse import quote, urlencode, urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, HTTPServer

import discord
from discord import app_commands

import pyautogui
import requests
from dotenv import load_dotenv, set_key
import pydirectinput
from bs4 import BeautifulSoup
import winocr
from PIL import Image


# ============================================================
# WINDOWS NATIVE MOUSE
# ============================================================

user32 = ctypes.windll.user32

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

DISCORD_TOKEN = os.getenv(
    "DISCORD_TOKEN",
    ""
)

DISCORD_CHANNEL_ID = int(
    os.getenv(
        "DISCORD_CHANNEL_ID",
        "0"
    )
)


# ============================================================
# FIRST-RUN SETUP WIZARD
#
# If required .env values are missing, ask for them in plain
# English right in the console instead of making someone
# hand-edit a .env file. Runs once — after values are saved,
# future launches skip straight past this. This happens
# BEFORE the GUI window opens, so it's still a console-only
# step.
# ============================================================

def prompt_for_value(
    label,
    help_text,
    current_value,
    required=True
):

    if current_value:

        return current_value

    print()
    print(
        "------------------------------------------------"
    )

    print(
        f"[SETUP] {label}"
    )

    print(
        help_text
    )

    print(
        "------------------------------------------------"
    )

    while True:

        value = input(
            f"Paste your {label} here, "
            f"then press Enter: "
        ).strip()

        if value:

            return value

        if not required:

            return ""

        print(
            "That was empty — this one's required, "
            "try again."
        )


def run_setup_wizard():

    global DISCORD_TOKEN
    global DISCORD_CHANNEL_ID
    global PS99_CLIENT_ID
    global PS99_CLIENT_SECRET

    missing = (
        not DISCORD_TOKEN
        or not PS99_CLIENT_ID
        or not PS99_CLIENT_SECRET
    )

    if not missing:

        return

    print()
    print(
        "=================================================="
    )

    print(
        "  FIRST-TIME SETUP"
    )

    print(
        "  A few things are missing from your .env file."
    )

    print(
        "  Answer the questions below — this only happens "
        "once."
    )

    print(
        "=================================================="
    )

    DISCORD_TOKEN = prompt_for_value(
        "Discord Bot Token",

        "Get this from https://discord.com/developers/applications\n"
        "-> your application -> Bot -> Reset Token / Copy.\n"
        "It's a long string of letters, numbers, and dots.",

        DISCORD_TOKEN
    )

    set_key(
        ".env",
        "DISCORD_TOKEN",
        DISCORD_TOKEN
    )

    channel_id_text = prompt_for_value(
        "Discord Channel ID",

        "Right-click the channel you want alerts posted "
        "in -> Copy Channel ID.\n"
        "(If you don't see that option, enable Developer "
        "Mode in Discord: User Settings -> Advanced.)\n"
        "Leave this blank and press Enter to skip — the "
        "bot will just print alerts to this console "
        "instead.",

        str(DISCORD_CHANNEL_ID)
        if DISCORD_CHANNEL_ID
        else "",

        required=False
    )

    if channel_id_text:

        DISCORD_CHANNEL_ID = int(
            channel_id_text
        )

        set_key(
            ".env",
            "DISCORD_CHANNEL_ID",
            channel_id_text
        )

    PS99_CLIENT_ID = prompt_for_value(
        "PS99 Client ID",

        "Get this from your BIG Games developer app at "
        "https://db.biggames.io\n"
        "(create an OAuth app for Pet Simulator 99 if you "
        "haven't already).",

        PS99_CLIENT_ID
    )

    set_key(
        ".env",
        "PS99_CLIENT_ID",
        PS99_CLIENT_ID
    )

    PS99_CLIENT_SECRET = prompt_for_value(
        "PS99 Client Secret",

        "Same BIG Games developer app page, right next to "
        "the Client ID.",

        PS99_CLIENT_SECRET
    )

    set_key(
        ".env",
        "PS99_CLIENT_SECRET",
        PS99_CLIENT_SECRET
    )

    print()
    print(
        "[SETUP] Saved to .env — you won't be asked again "
        "unless you delete that file."
    )

    print()


# ============================================================
# BOOTH CAPACITY WATCHER
#
# Reads a "USED/LIMIT" counter (e.g. "25/25") off the screen
# using Windows' built-in OCR engine (Windows.Media.Ocr, via
# the winocr package) — the same engine AHK's OCR libraries
# typically use. No separate installer needed, unlike
# Tesseract, just `pip install winocr` — requires Windows
# 10/11.
#
# When the counter is full, the restock queue pauses; when a
# slot frees up, it resumes automatically.
#
# BOOTH_CAP_REGION_SIZE is a guess — use /boothcap in Discord
# to see exactly what gets captured and tune width/height
# until the crop cleanly frames just the "NN/NN" text.
# ============================================================

BOOTH_CAP_CENTER = (
    1138,
    300
)

BOOTH_CAP_REGION_SIZE = (
    90,
    30
)

BOOTH_CAP_CHECK_SECONDS = 1

# Reject any OCR read where either side of "N/N" comes out
# longer than this many digits — the real counter is always
# short, so an over-long read (e.g. "251") is a misread to
# discard, not a value to trust.
BOOTH_CAP_MAX_DIGITS = 2


# ============================================================
# BIG GAMES OAUTH
# ============================================================

PS99_CLIENT_ID = os.getenv(
    "PS99_CLIENT_ID",
    ""
)

PS99_CLIENT_SECRET = os.getenv(
    "PS99_CLIENT_SECRET",
    ""
)

PS99_ACCESS_TOKEN = os.getenv(
    "PS99_ACCESS_TOKEN",
    ""
)

OAUTH_AUTHORIZE_URL = (
    "https://db.biggames.io/oauth/authorize"
)

OAUTH_TOKEN_URL = (
    "https://db.biggames.io/oauth/token"
)

OAUTH_REDIRECT_URI = (
    "http://localhost:8080/callback"
)

OAUTH_HOST = "127.0.0.1"
OAUTH_PORT = 8080


# ============================================================
# OAUTH SCOPES
# ============================================================

OAUTH_SCOPES = [
    "player-data:pet-simulator-99:booth:read",
    "player-data:pet-simulator-99:inventory:read",
    "player-data:pet-simulator-99:profile:read",
]


# ============================================================
# OAUTH STATE
# ============================================================

oauth_state = None
oauth_code_verifier = None

oauth_lock = threading.Lock()

oauth_server = None


# ============================================================
# PS99 API
# ============================================================

PS99_API_BASE = (
    "https://ps99.biggamesapi.io"
)

PS99_ACCOUNT_BASE = (
    f"{PS99_API_BASE}/v1/account"
)


# ============================================================
# COSMIC VALUES
# ============================================================

COSMIC_DETAILS_URL = (
    "https://petsimulatorvalues.com/details.php"
)


# ============================================================
# RESTOCK SETTINGS
# ============================================================

DRY_RUN = False

ACTION_DELAY = 0.5
SEARCH_DELAY = 0.6
CONFIRM_DELAY = 0.6

ANTI_IDLE_SECONDS = 5

# Used by /huges
HUG_RAP_LIMIT = 30_000_000


# ============================================================
# ROBLOX COORDINATES
# ============================================================

COORD = {

    "make_listing": (
        550,
        580
    ),

    "search": (
        1300,
        250
    ),

    "confirm_item": (
        959,
        784
    ),

    "price": (
        953,
        530
    ),

    "submit": (
        960,
        672
    ),

    "yes": (
        800,
        700
    ),

    "close": (
        1300,
        200
    ),
}


# ============================================================
# PET COORDINATE
# ============================================================

PET_X = 537
PET_Y = 350


# ============================================================
# QUEUE / THREAD CONTROL
# ============================================================

restock_queue = deque()

queue_lock = threading.Lock()

stop_event = threading.Event()

# Set while the booth is full (per the on-screen NN/NN
# counter) — restock_worker() checks this before popping
# the next job and simply waits while it's set.
booth_full_event = threading.Event()

mouse_lock = threading.RLock()


# ============================================================
# SHARED STATUS (read by the GUI, written by the worker
# threads and Discord event handlers)
#
# The markup percentage lives here now instead of a fixed
# COSMIC_MARKUP constant — it's the "adjustable RAP/Cosmic
# markup %" the status GUI's spinbox controls. Every price
# calculation reads the current value at the moment it's
# needed, so changing it in the GUI affects the very next
# listing without a restart.
# ============================================================

class BotStatus:

    def __init__(self):

        self.lock = threading.Lock()

        self.connected = False

        self.bot_user = ""

        self.booth_full = False

        self.booth_last_read = ""

        self.last_event = "Starting up..."

        self.markup_percent = 5.0


bot_status = BotStatus()


def get_markup_percent():

    with bot_status.lock:

        return bot_status.markup_percent


def set_markup_percent(
    value
):

    value = max(
        0.0,
        min(
            500.0,
            float(value)
        )
    )

    with bot_status.lock:

        bot_status.markup_percent = value

    return value


def set_last_event(
    text
):

    with bot_status.lock:

        bot_status.last_event = text


# ============================================================
# INVENTORY API STATUS
# ============================================================

last_inventory_refresh = {}
last_inventory_data = {}

inventory_status_lock = threading.Lock()


# ============================================================
# DISCORD
# ============================================================

intents = discord.Intents.default()

client = discord.Client(
    intents=intents
)

tree = app_commands.CommandTree(
    client
)


async def send_discord(message):

    if DISCORD_CHANNEL_ID == 0:

        print(
            "[DISCORD]",
            message
        )

        return

    channel = client.get_channel(
        DISCORD_CHANNEL_ID
    )

    if channel:

        await channel.send(
            message
        )

    else:

        print(
            "[DISCORD]",
            message
        )


# ============================================================
# PKCE
# ============================================================

def generate_pkce():

    verifier = (
        base64.urlsafe_b64encode(
            secrets.token_bytes(32)
        )
        .decode("utf-8")
        .rstrip("=")
    )

    challenge = (
        base64.urlsafe_b64encode(
            hashlib.sha256(
                verifier.encode("utf-8")
            ).digest()
        )
        .decode("utf-8")
        .rstrip("=")
    )

    return (
        verifier,
        challenge
    )


# ============================================================
# OAUTH CALLBACK
# ============================================================

class OAuthCallbackHandler(
    BaseHTTPRequestHandler
):

    def log_message(
        self,
        format,
        *args
    ):

        return

    def do_GET(self):

        global oauth_state
        global oauth_code_verifier
        global PS99_ACCESS_TOKEN

        parsed = urlparse(
            self.path
        )

        if parsed.path != "/callback":

            self.send_response(
                404
            )

            self.end_headers()

            return

        params = parse_qs(
            parsed.query
        )

        returned_state = (
            params.get(
                "state",
                [""]
            )[0]
        )

        code = (
            params.get(
                "code",
                [""]
            )[0]
        )

        error = (
            params.get(
                "error",
                [""]
            )[0]
        )

        with oauth_lock:

            expected_state = oauth_state

            verifier = oauth_code_verifier

            oauth_state = None
            oauth_code_verifier = None

        if error:

            self.send_html(
                f"""
                <html>
                <body>
                <h1>Authorization cancelled</h1>
                <p>{error}</p>
                <p>You can close this window.</p>
                </body>
                </html>
                """
            )

            return

        if (
            not expected_state
            or returned_state != expected_state
        ):

            self.send_html(
                """
                <html>
                <body>
                <h1>Authorization failed</h1>
                <p>Invalid OAuth state.</p>
                </body>
                </html>
                """
            )

            print(
                "[OAUTH] Invalid state."
            )

            return

        if not code:

            self.send_html(
                """
                <html>
                <body>
                <h1>Authorization failed</h1>
                <p>No authorization code was returned.</p>
                </body>
                </html>
                """
            )

            return

        try:

            print(
                "[OAUTH] Authorization code received."
            )

            response = requests.post(
                OAUTH_TOKEN_URL,

                auth=(
                    PS99_CLIENT_ID,
                    PS99_CLIENT_SECRET
                ),

                data={
                    "grant_type":
                        "authorization_code",

                    "code":
                        code,

                    "redirect_uri":
                        OAUTH_REDIRECT_URI,

                    "code_verifier":
                        verifier,
                },

                timeout=20
            )

            print(
                "[OAUTH] Token response:",
                response.status_code
            )

            response.raise_for_status()

            token_data = (
                response.json()
            )

            access_token = (
                token_data.get(
                    "access_token"
                )
            )

            if not access_token:

                raise ValueError(
                    "No access_token returned."
                )

            PS99_ACCESS_TOKEN = (
                access_token
            )

            set_key(
                ".env",
                "PS99_ACCESS_TOKEN",
                access_token
            )

            print(
                "[OAUTH] Access token saved."
            )

            self.send_html(
                """
                <html>
                <body>
                <h1>✅ PS99 Authorization Complete</h1>
                <p>Your access token was saved.</p>
                <p>You can close this window.</p>
                </body>
                </html>
                """
            )

            asyncio.run_coroutine_threadsafe(
                send_discord(
                    "🔐 **PS99 authorization complete!**\n"
                    "Your Player API token was successfully saved."
                ),
                client.loop
            )

        except Exception as e:

            print(
                "[OAUTH ERROR]",
                e
            )

            self.send_html(
                f"""
                <html>
                <body>
                <h1>❌ Authorization failed</h1>
                <p>{str(e)}</p>
                <p>Check the Python console.</p>
                </body>
                </html>
                """
            )

    def send_html(
        self,
        html
    ):

        body = html.encode(
            "utf-8"
        )

        self.send_response(
            200
        )

        self.send_header(
            "Content-Type",
            "text/html; charset=utf-8"
        )

        self.send_header(
            "Content-Length",
            str(len(body))
        )

        self.end_headers()

        self.wfile.write(
            body
        )


# ============================================================
# START OAUTH SERVER
# ============================================================

def start_oauth_server():

    global oauth_server

    if oauth_server is not None:
        return

    oauth_server = HTTPServer(
        (
            OAUTH_HOST,
            OAUTH_PORT
        ),
        OAuthCallbackHandler
    )

    print(
        "[OAUTH] Callback server running on",
        OAUTH_REDIRECT_URI
    )

    threading.Thread(
        target=oauth_server.serve_forever,
        daemon=True
    ).start()


# ============================================================
# BEGIN AUTHORIZATION
# ============================================================

def begin_authorization():

    global oauth_state
    global oauth_code_verifier

    if not PS99_CLIENT_ID:

        raise RuntimeError(
            "PS99_CLIENT_ID is missing from .env"
        )

    if not PS99_CLIENT_SECRET:

        raise RuntimeError(
            "PS99_CLIENT_SECRET is missing from .env"
        )

    start_oauth_server()

    verifier, challenge = (
        generate_pkce()
    )

    state = secrets.token_urlsafe(
        32
    )

    with oauth_lock:

        oauth_state = state

        oauth_code_verifier = (
            verifier
        )

    params = {

        "client_id":
            PS99_CLIENT_ID,

        "redirect_uri":
            OAUTH_REDIRECT_URI,

        "scope":
            " ".join(
                OAUTH_SCOPES
            ),

        "code_challenge":
            challenge,

        "code_challenge_method":
            "S256",

        "state":
            state,
    }

    url = (
        OAUTH_AUTHORIZE_URL
        + "?"
        + urlencode(params)
    )

    print()
    print(
        "======================================"
    )
    print(
        "[OAUTH] Opening authorization page."
    )
    print(
        "======================================"
    )

    webbrowser.open(
        url
    )

    return url


# ============================================================
# /AUTHORIZE
# ============================================================

@tree.command(
    name="authorize",
    description="Authorize this bot to access your PS99 account."
)
async def authorize_command(
    interaction: discord.Interaction
):

    if not PS99_CLIENT_ID:

        await interaction.response.send_message(
            "❌ `PS99_CLIENT_ID` is missing from `.env`.",
            ephemeral=True
        )

        return

    if not PS99_CLIENT_SECRET:

        await interaction.response.send_message(
            "❌ `PS99_CLIENT_SECRET` is missing from `.env`.",
            ephemeral=True
        )

        return

    try:

        url = await asyncio.to_thread(
            begin_authorization
        )

        await interaction.response.send_message(
            "🔐 **PS99 authorization started.**\n\n"
            "Your browser should open automatically.\n"
            "Log into BIG Games and approve access.\n\n"
            "If it didn't open, use this URL:\n"
            f"{url}",
            ephemeral=True
        )

    except Exception as e:

        await interaction.response.send_message(
            "❌ **Could not start authorization.**\n"
            f"`{e}`",
            ephemeral=True
        )


# ============================================================
# PS99 API GET (generic helper, used by /booth etc.)
# ============================================================

def ps99_get(
    endpoint
):

    global PS99_ACCESS_TOKEN

    if not PS99_ACCESS_TOKEN:

        raise RuntimeError(
            "No PS99 access token. "
            "Run /authorize first."
        )

    url = (
        PS99_ACCOUNT_BASE
        + endpoint
    )

    response = requests.get(

        url,

        headers={
            "Authorization":
                f"Bearer {PS99_ACCESS_TOKEN}"
        },

        timeout=20
    )

    if response.status_code == 401:

        raise RuntimeError(
            "PS99 access token is expired "
            "or revoked. Run /authorize again."
        )

    if response.status_code == 403:

        raise RuntimeError(
            "This PS99 app does not have "
            "the required permission."
        )

    response.raise_for_status()

    result = response.json()

    if result.get(
        "status"
    ) != "ok":

        error = result.get(
            "error",
            {}
        )

        raise RuntimeError(
            error.get(
                "message",
                "Unknown PS99 API error."
            )
        )

    return result.get(
        "data"
    )


# ============================================================
# INVENTORY FETCH
# ============================================================

def get_inventory():

    global last_inventory_refresh
    global last_inventory_data

    if not PS99_ACCESS_TOKEN:

        raise RuntimeError(
            "No PS99 access token. "
            "Run /authorize first."
        )

    url = (
        PS99_ACCOUNT_BASE
        + "/inventory"
    )

    print()
    print(
        "[INVENTORY] Requesting inventory..."
    )

    response = requests.get(
        url,

        headers={
            "Authorization":
                f"Bearer {PS99_ACCESS_TOKEN}"
        },

        timeout=30
    )

    print(
        "[INVENTORY] HTTP:",
        response.status_code
    )

    if response.status_code == 401:

        raise RuntimeError(
            "PS99 access token is expired "
            "or revoked. Run /authorize again."
        )

    if response.status_code == 403:

        raise RuntimeError(
            "This PS99 app does not have "
            "the required permission."
        )

    response.raise_for_status()

    result = response.json()

    if result.get("status") != "ok":

        error = result.get(
            "error",
            {}
        )

        raise RuntimeError(
            error.get(
                "message",
                "Unknown PS99 API error."
            )
        )

    refresh = result.get(
        "refresh",
        {}
    )

    data = result.get(
        "data",
        {}
    )

    if not isinstance(
        data,
        dict
    ):
        data = {}

    items = data.get(
        "items",
        []
    )

    if not isinstance(
        items,
        list
    ):
        items = []

    with inventory_status_lock:

        last_inventory_refresh = dict(
            refresh
        )

        last_inventory_data = {
            "cached":
                data.get("cached"),

            "fetchedAt":
                data.get("fetchedAt"),

            "items":
                len(items),
        }

    if refresh:

        print(
            "[INVENTORY] Refresh used:",
            refresh.get("used")
        )

        print(
            "[INVENTORY] Refresh limit:",
            refresh.get("limit")
        )

        print(
            "[INVENTORY] Quota exhausted:",
            refresh.get("quotaExhausted")
        )

    print(
        "[INVENTORY] Items:",
        len(items)
    )

    return items


# ============================================================
# NORMALIZE INVENTORY ITEM
# ============================================================

def normalize_inventory_item(
    item
):

    item_id = str(
        item.get(
            "id",
            ""
        )
    )

    display_name = str(
        item.get(
            "displayName",
            item_id
        )
    )

    category = str(
        item.get(
            "category",
            ""
        )
    ).lower()

    item_class = str(
        item.get(
            "class",
            ""
        )
    ).lower()

    variant = str(
        item.get(
            "variant",
            ""
        )
    ).strip()

    rap = int(
        item.get(
            "rap",
            0
        ) or 0
    )

    count = int(
        item.get(
            "count",
            1
        ) or 1
    )

    return {

        "id":
            item_id,

        "name":
            display_name,

        "category":
            category,

        "class":
            item_class,

        "variant":
            variant,

        "rap":
            rap,

        "count":
            count,

        "raw":
            item,
    }


# ============================================================
# HUGE DETECTION
# ============================================================

def is_huge_item(
    item
):

    name = item["name"].lower()

    item_id = item["id"].lower()

    category = item["category"]

    item_class = item["class"]

    return (

        "huge" in name

        or

        "huge" in item_id

        or

        category == "huge"

        or

        item_class == "huge"
    )


# ============================================================
# BUILD ROBLOX SEARCH NAME
# ============================================================

def build_search_name(
    item
):

    name = item["name"].strip()

    variant = item["variant"].strip()

    # If displayName already contains the variant,
    # don't duplicate it.

    if variant:

        if variant.lower() not in name.lower():

            return (
                f"{variant} {name}"
            )

    return name


# ============================================================
# GET BASE NAME FOR COSMIC
# ============================================================

def get_cosmic_search_name(
    item
):

    name = item["name"].strip()

    variant = item["variant"].strip()

    if variant:

        if name.lower().startswith(
            variant.lower() + " "
        ):

            name = name[
                len(variant) + 1:
            ]

    # Common variant prefixes
    variants = [
        "shiny ",
        "golden ",
        "rainbow ",
        "shiny golden ",
        "shiny rainbow ",
    ]

    changed = True

    while changed:

        changed = False

        lower_name = name.lower()

        for prefix in variants:

            if lower_name.startswith(
                prefix
            ):

                name = name[
                    len(prefix):
                ].strip()

                changed = True

                break

    return name


# ============================================================
# /BOOTH
# ============================================================

@tree.command(
    name="booth",
    description="Show recent PS99 booth transactions."
)
async def booth_command(
    interaction: discord.Interaction
):

    await interaction.response.defer()

    try:

        data = await asyncio.to_thread(
            ps99_get,
            "/booth"
        )

        entries = (
            data.get(
                "entries",
                []
            )
            if data
            else []
        )

        if not entries:

            await interaction.followup.send(
                "📦 **Your booth has no recorded transactions.**"
            )

            return

        lines = [
            "🏪 **Recent Booth Transactions**",
            ""
        ]

        for entry in entries[:10]:

            kind = entry.get(
                "kind",
                "unknown"
            )

            other = (
                entry.get(
                    "otherParty",
                    {}
                )
                .get(
                    "displayName",
                    "Unknown"
                )
            )

            if kind == "sale":

                items = entry.get(
                    "given",
                    []
                )

                icon = "💰"

            else:

                items = entry.get(
                    "received",
                    []
                )

                icon = "🛒"

            lines.append(
                f"{icon} **{kind.title()}** "
                f"with `{other}`"
            )

            for item in items:

                name = item.get(
                    "displayName",
                    item.get(
                        "id",
                        "Unknown"
                    )
                )

                count = item.get(
                    "count",
                    1
                )

                rap = int(
                    item.get(
                        "rap",
                        0
                    ) or 0
                )

                lines.append(
                    f"• {count}x {name} "
                    f"({rap:,} RAP)"
                )

            lines.append("")

        await interaction.followup.send(
            "\n".join(lines)
        )

    except Exception as e:

        await interaction.followup.send(
            f"❌ **Booth lookup failed:**\n`{e}`"
        )


# ============================================================
# /HUGES
# ============================================================

@tree.command(
    name="huges",
    description="Show your Huges under a RAP limit."
)
@app_commands.describe(
    rap_limit="Maximum RAP. Defaults to 30,000,000."
)
async def huges_command(
    interaction: discord.Interaction,
    rap_limit: int = HUG_RAP_LIMIT
):

    await interaction.response.send_message(
        "🔎 Checking your PS99 inventory..."
    )

    try:

        items = await asyncio.to_thread(
            get_inventory
        )

        huges = []

        for raw_item in items:

            item = normalize_inventory_item(
                raw_item
            )

            if not is_huge_item(
                item
            ):
                continue

            if item["rap"] <= rap_limit:

                huges.append(
                    item
                )

        huges.sort(
            key=lambda x:
            x["rap"]
        )

        if not huges:

            await interaction.followup.send(
                f"❌ No Huges found under "
                f"**{rap_limit:,} RAP**."
            )

            return

        lines = [
            f"🐾 **Huges under {rap_limit:,} RAP**",
            ""
        ]

        for i, huge in enumerate(
            huges,
            1
        ):

            variant = huge["variant"]

            variant_text = ""

            if variant:

                variant_text = (
                    f" — {variant}"
                )

            lines.append(
                f"`{i}.` **{huge['name']}**"
                f"{variant_text}"
                f" — `{huge['rap']:,} RAP`"
            )

        await interaction.followup.send(
            "\n".join(lines)
        )

    except Exception as e:

        await interaction.followup.send(
            "❌ `/huges` failed:\n"
            f"`{e}`"
        )


# ============================================================
# COSMIC VALUE PARSER
# ============================================================

def parse_value(
    value_text
):

    if not value_text:

        return None

    value_text = (
        value_text
        .strip()
        .upper()
        .replace(
            ",",
            ""
        )
        .replace(
            "$",
            ""
        )
    )

    match = re.fullmatch(
        r"([0-9]+(?:\.[0-9]+)?)\s*([KMBTQ]?)",
        value_text
    )

    if not match:

        return None

    number = float(
        match.group(1)
    )

    suffix = match.group(2)

    multiplier = {

        "":
            1,

        "K":
            1_000,

        "M":
            1_000_000,

        "B":
            1_000_000_000,

        "T":
            1_000_000_000_000,

        "Q":
            1_000_000_000_000_000,
    }.get(
        suffix,
        1
    )

    return int(
        number * multiplier
    )


# ============================================================
# GET COSMIC VALUE
# ============================================================

def get_cosmic_value(
    item
):

    print()
    print(
        "[COSMIC] Looking up:",
        item
    )

    encoded_name = quote(
        item.strip()
    )

    url = (
        f"{COSMIC_DETAILS_URL}"
        f"?Name={encoded_name}"
        f"&category=all"
    )

    print(
        "[COSMIC] URL:",
        url
    )

    headers = {

        "User-Agent":
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "Chrome/151.0.0.0 "
            "Safari/537.36"
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=15
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    page_text = soup.get_text(
        " ",
        strip=True
    )

    match = re.search(
        r"\bvalue\s+"
        r"([0-9]+(?:\.[0-9]+)?"
        r"\s*[KMBTQ]?)",
        page_text,
        re.IGNORECASE
    )

    if not match:

        raise ValueError(
            f"Could not find Cosmic Value "
            f"for '{item}'."
        )

    value_text = (
        match.group(1)
    )

    value = parse_value(
        value_text
    )

    if value is None:

        raise ValueError(
            f"Could not parse Cosmic Value "
            f"'{value_text}'."
        )

    print(
        "[COSMIC] Found value:",
        f"{value:,}"
    )

    return value


# ============================================================
# CALCULATE PRICE
#
# Compares RAP against Cosmic Value and prices off whichever
# is higher, plus the current markup % — which is read live
# from bot_status, adjustable from the GUI at any time. For
# manually-typed /sell items RAP is unknown (passed as 0), so
# Cosmic Value naturally wins there.
# ============================================================

def calculate_sell_price(
    rap,
    cosmic_value
):

    if rap > cosmic_value:

        base_value = rap

        basis = "RAP"

    else:

        base_value = cosmic_value

        basis = "Cosmic Value"

    markup_percent = get_markup_percent()

    multiplier = 1 + (
        markup_percent / 100.0
    )

    price = int(
        round(
            base_value
            * multiplier
        )
    )

    print(
        "[PRICE] RAP:",
        f"{rap:,}"
    )

    print(
        "[PRICE] Cosmic Value:",
        f"{cosmic_value:,}"
    )

    print(
        "[PRICE] Basis used:",
        basis
    )

    print(
        f"[PRICE] +{markup_percent:g}% Price:",
        f"{price:,}"
    )

    return price, basis


# ============================================================
# CREATE RESTOCK JOB
# ============================================================

def create_huge_job(
    item
):

    search_name = build_search_name(
        item
    )

    cosmic_name = get_cosmic_search_name(
        item
    )

    print()
    print(
        "[JOB] Huge:",
        item["name"]
    )

    print(
        "[JOB] RAP:",
        f"{item['rap']:,}"
    )

    print(
        "[JOB] Roblox Search:",
        search_name
    )

    print(
        "[JOB] Cosmic Search:",
        cosmic_name
    )

    cosmic_value = get_cosmic_value(
        cosmic_name
    )

    price, price_basis = calculate_sell_price(
        item["rap"],
        cosmic_value
    )

    return {

        "item":
            item["name"],

        "search_name":
            search_name,

        "price":
            price,

        "price_basis":
            price_basis,

        "rap":
            item["rap"],

        "inventory_id":
            item["id"],

        "variant":
            item["variant"],

        "cosmic_value":
            cosmic_value,

        "requested_by":
            "automatic",
    }


# ============================================================
# /SELL
# ============================================================

@tree.command(
    name="sell",
    description="Sell one or more of the same item, priced above the higher of RAP/Cosmic Value."
)
@app_commands.describe(
    item="Base PS99 item/pet name",
    variant="Normal, Shiny, Golden, Rainbow, etc.",
    amount="How many copies to queue (default 1)"
)
async def sell(
    interaction: discord.Interaction,
    item: str,
    variant: str = "Normal",
    amount: int = 1
):

    if stop_event.is_set():

        await interaction.response.send_message(
            "🛑 The restock system is stopped.",
            ephemeral=True
        )

        return

    item = item.strip()
    variant = variant.strip()

    if not item:

        await interaction.response.send_message(
            "❌ You need to enter an item name.",
            ephemeral=True
        )

        return

    # Clamp amount to something sane so a typo doesn't
    # accidentally queue thousands of listings.
    if amount < 1:

        amount = 1

    elif amount > 100:

        amount = 100

    if variant.lower() in (
        "",
        "normal",
        "none",
        "regular"
    ):

        search_name = item

    else:

        search_name = (
            f"{variant} {item}"
        )

    await interaction.response.defer()

    try:

        cosmic_value = (
            await asyncio.to_thread(
                get_cosmic_value,
                item
            )
        )

        # /sell is a manually-typed item, so there's no RAP
        # figure available the way inventory-sourced Huges
        # have one — passing 0 means Cosmic Value always wins
        # here, same as before this feature existed.

        price, price_basis = (
            calculate_sell_price(
                0,
                cosmic_value
            )
        )

    except Exception as e:

        await interaction.followup.send(
            f"❌ **Cosmic Value lookup failed.**\n"
            f"`{e}`"
        )

        return

    # Cosmic Value is looked up once and reused for every
    # copy — no need to hit the site N times for identical
    # items.
    with queue_lock:

        for _ in range(amount):

            job = {

                "item":
                    item,

                "variant":
                    variant,

                "search_name":
                    search_name,

                "price":
                    price,

                "price_basis":
                    price_basis,

                "cosmic_value":
                    cosmic_value,

                "rap":
                    0,

                "inventory_id":
                    "",

                "requested_by":
                    interaction.user.name,
            }

            restock_queue.append(
                job
            )

    amount_text = (
        f"**Amount:** {amount}x\n"
        if amount > 1
        else ""
    )

    markup_percent = get_markup_percent()

    await interaction.followup.send(
        f"✅ **Added to restock queue**\n\n"
        f"**Item:** {item}\n"
        f"**Variant:** {variant}\n"
        f"{amount_text}"
        f"**Search:** `{search_name}`\n"
        f"**Cosmic Value:** {cosmic_value:,}\n"
        f"**Sell Price (+{markup_percent:g}%, based on "
        f"{price_basis}):** {price:,}"
    )


# ============================================================
# /RESTOCK
# RESTOCK ALL HUGES LOWEST RAP -> HIGHEST RAP
# ============================================================

@tree.command(
    name="restock",
    description="Restock all Huge pets from lowest RAP to highest RAP."
)
async def restock_command(
    interaction: discord.Interaction
):

    if stop_event.is_set():

        await interaction.response.send_message(
            "🛑 The restock system is stopped. "
            "Restart the Python program first.",
            ephemeral=True
        )

        return

    await interaction.response.defer()

    print()
    print("======================================")
    print("[RESTOCK] Manual Huge restock requested")
    print("======================================")

    try:

        raw_items = await asyncio.to_thread(
            get_inventory
        )

    except Exception as e:

        await interaction.followup.send(
            f"❌ **Inventory lookup failed:**\n`{e}`"
        )

        return

    huges = []

    for raw_item in raw_items:

        item = normalize_inventory_item(
            raw_item
        )

        if not is_huge_item(
            item
        ):
            continue

        huges.append(
            item
        )

    if not huges:

        await interaction.followup.send(
            "❌ No Huge pets were found in your inventory."
        )

        return

    huges.sort(
        key=lambda x:
        x["rap"]
    )

    print()
    print("======================================")
    print("[RESTOCK] HUGES SORTED BY RAP")
    print("======================================")

    for i, huge in enumerate(
        huges,
        1
    ):

        print(
            f"{i}. "
            f"{huge['name']} — "
            f"{huge['rap']:,} RAP"
        )

    added = 0
    skipped = 0

    for huge in huges:

        try:

            job = await asyncio.to_thread(
                create_huge_job,
                huge
            )

            with queue_lock:

                restock_queue.append(
                    job
                )

            added += 1

            print(
                f"[QUEUE] Added: "
                f"{huge['name']} | "
                f"RAP: {huge['rap']:,} | "
                f"Price: {job['price']:,}"
            )

        except Exception as e:

            skipped += 1

            print(
                f"[QUEUE] Could not queue "
                f"{huge['name']}: {e}"
            )

    print()
    print(
        "[RESTOCK] Found:",
        len(huges)
    )

    print(
        "[RESTOCK] Added:",
        added
    )

    print(
        "[RESTOCK] Skipped:",
        skipped
    )

    markup_percent = get_markup_percent()

    await interaction.followup.send(
        f"🐾 **Restock queued!**\n\n"
        f"**Huges found:** {len(huges)}\n"
        f"**Added:** {added}\n"
        f"**Skipped:** {skipped}\n\n"
        f"📊 **Order:** Lowest RAP → Highest RAP\n"
        f"💎 **Price:** +{markup_percent:g}% above the "
        f"higher of RAP / Cosmic Value"
    )


# ============================================================
# /QUEUE
# ============================================================

@tree.command(
    name="queue",
    description="Show the current PS99 restock queue."
)
async def queue_command(
    interaction: discord.Interaction
):

    with queue_lock:

        jobs = list(
            restock_queue
        )

    if not jobs:

        await interaction.response.send_message(
            "📦 **Restock queue is empty.**"
        )

        return

    lines = [
        "📦 **Restock Queue**",
        ""
    ]

    for i, job in enumerate(
        jobs,
        1
    ):

        rap_text = ""

        if job.get("rap", 0):

            rap_text = (
                f" — {job['rap']:,} RAP"
            )

        lines.append(
            f"`{i}.` **{job['search_name']}**"
            f"{rap_text}"
            f" — {job['price']:,}"
        )

    # Discord caps a single message at 2000 characters — a
    # long queue was silently hitting that limit. Split into
    # multiple messages instead, each safely under the cap.

    chunks = []

    current = ""

    for line in lines:

        candidate = (
            current + "\n" + line
            if current
            else line
        )

        if len(candidate) > 1900:

            chunks.append(
                current
            )

            current = line

        else:

            current = candidate

    if current:

        chunks.append(
            current
        )

    await interaction.response.send_message(
        chunks[0]
    )

    for chunk in chunks[1:]:

        await interaction.followup.send(
            chunk
        )


# ============================================================
# /MARKUP
#
# Lets you check or change the markup % from Discord too,
# not just the GUI — handy if you're away from the desk the
# bot is running on.
# ============================================================

@tree.command(
    name="markup",
    description="View or change the % markup applied over the higher of RAP/Cosmic Value."
)
@app_commands.describe(
    percent="New markup percent (e.g. 5 for +5%). Leave blank to just check the current value."
)
async def markup_command(
    interaction: discord.Interaction,
    percent: float = None
):

    if percent is None:

        current = get_markup_percent()

        await interaction.response.send_message(
            f"💎 Current markup: **+{current:g}%**"
        )

        return

    new_value = set_markup_percent(
        percent
    )

    set_last_event(
        f"Markup changed to +{new_value:g}% "
        f"(via Discord, by {interaction.user.name})"
    )

    await interaction.response.send_message(
        f"✅ Markup updated to **+{new_value:g}%**"
    )


# ============================================================
# /STOP
# ============================================================

@tree.command(
    name="stop",
    description="Stop the PS99 restock system."
)
async def stop_command(
    interaction: discord.Interaction
):

    if not interaction.user.guild_permissions.administrator:

        await interaction.response.send_message(
            "❌ You need Administrator permission.",
            ephemeral=True
        )

        return

    stop_event.set()

    with queue_lock:

        restock_queue.clear()

    await interaction.response.send_message(
        "🛑 **Stopping PS99 Restock System...**"
    )

    await asyncio.sleep(
        1
    )

    await client.close()


# ============================================================
# /APISTATUS
# ============================================================

@tree.command(
    name="apistatus",
    description="Show the current PS99 inventory API refresh status."
)
async def apistatus_command(
    interaction: discord.Interaction
):

    with inventory_status_lock:

        refresh = dict(
            last_inventory_refresh
        )

        data = dict(
            last_inventory_data
        )

    if not refresh:

        await interaction.response.send_message(
            "⚠️ **No inventory API status yet.**\n\n"
            "The bot has not successfully requested your "
            "inventory since it started."
        )

        return

    used = refresh.get(
        "used",
        "?"
    )

    limit = refresh.get(
        "limit",
        "?"
    )

    exhausted = refresh.get(
        "quotaExhausted",
        False
    )

    consumed = refresh.get(
        "consumedThisCall",
        False
    )

    resets_at = refresh.get(
        "resetsAt",
        "Unknown"
    )

    next_eligible = refresh.get(
        "nextRefreshEligibleAt",
        "Unknown"
    )

    cached = data.get(
        "cached",
        "Unknown"
    )

    fetched = data.get(
        "fetchedAt",
        "Unknown"
    )

    items = data.get(
        "items",
        "Unknown"
    )

    if exhausted:

        status = "🔴 **CAPPED**"

    else:

        status = "🟢 **AVAILABLE**"

    markup_percent = get_markup_percent()

    await interaction.response.send_message(
        "🔌 **PS99 API Status**\n\n"
        f"**Refreshes:** `{used} / {limit}`\n"
        f"**Status:** {status}\n"
        f"**Consumed on last call:** `{consumed}`\n"
        f"**Inventory cached:** `{cached}`\n"
        f"**Inventory items:** `{items}`\n"
        f"**Current markup:** `+{markup_percent:g}%`\n\n"
        f"**Next refresh eligible:** `{next_eligible}`\n"
        f"**Quota resets:** `{resets_at}`\n"
        f"**Inventory fetched:** `{fetched}`"
    )


# ============================================================
# ROBLOX CLICK
# ============================================================

def click(
    name
):

    x, y = COORD[name]

    print(
        f"[CLICK] {name}: {x}, {y}"
    )

    if not DRY_RUN:

        with mouse_lock:

            pydirectinput.moveTo(
                x - 8,
                y - 8,
                duration=0.15
            )

            pydirectinput.moveTo(
                x + 5,
                y + 3,
                duration=0.08
            )

            pydirectinput.moveTo(
                x - 2,
                y - 2,
                duration=0.05
            )

            pydirectinput.moveTo(
                x,
                y,
                duration=0.05
            )

            time.sleep(
                0.25
            )

            pydirectinput.click(
                x,
                y
            )

            pydirectinput.moveRel(
                1,
                0,
                duration=0.05
            )

    time.sleep(
        ACTION_DELAY
    )


# ============================================================
# WRITE TEXT
# ============================================================

def write_text(
    text
):

    print(
        "[TYPE]",
        text
    )

    if not DRY_RUN:

        pyautogui.write(
            str(text),
            interval=0.09
        )

    time.sleep(
        ACTION_DELAY
    )


# ============================================================
# HOTKEY
# ============================================================

def hotkey(
    *keys
):

    print(
        "[HOTKEY]",
        " + ".join(keys)
    )

    if not DRY_RUN:

        pyautogui.hotkey(
            *keys
        )

    time.sleep(
        ACTION_DELAY
    )


# ============================================================
# SELECT PET
# ============================================================

def select_pet():

    print(
        "[ITEM CLICK]",
        PET_X,
        PET_Y
    )

    if DRY_RUN:

        time.sleep(
            CONFIRM_DELAY
        )

        return

    with mouse_lock:

        pydirectinput.keyDown(
            "shift"
        )

        try:

            pydirectinput.moveTo(
                PET_X - 8,
                PET_Y - 8,
                duration=0.15
            )

            pydirectinput.moveTo(
                PET_X + 5,
                PET_Y + 3,
                duration=0.08
            )

            pydirectinput.moveTo(
                PET_X - 2,
                PET_Y - 2,
                duration=0.05
            )

            pydirectinput.moveTo(
                PET_X,
                PET_Y,
                duration=0.05
            )

            time.sleep(
                0.25
            )

            pydirectinput.click(
                PET_X,
                PET_Y
            )

            pydirectinput.moveRel(
                1,
                0,
                duration=0.05
            )

        finally:

            pydirectinput.keyUp(
                "shift"
            )

    time.sleep(
        CONFIRM_DELAY
    )


# ============================================================
# RESTOCK ONE ITEM
# ============================================================

def restock_item(
    item,
    search_name,
    price
):

    print()
    print(
        "======================================"
    )

    print(
        "RESTOCKING"
    )

    print(
        "Item:",
        item
    )

    print(
        "Search:",
        search_name
    )

    print(
        "Price:",
        f"{price:,}"
    )

    print(
        "======================================"
    )

    if stop_event.is_set():
        return False

    # --------------------------------------------------------
    # MAKE LISTING
    # --------------------------------------------------------

    click(
        "make_listing"
    )

    if stop_event.is_set():
        return False

    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    click(
        "search"
    )

    hotkey(
        "ctrl",
        "a"
    )

    write_text(
        search_name
    )

    time.sleep(
        SEARCH_DELAY
    )

    if stop_event.is_set():
        return False

    # --------------------------------------------------------
    # SELECT
    # --------------------------------------------------------

    select_pet()

    if stop_event.is_set():
        return False

    # --------------------------------------------------------
    # CONFIRM
    # --------------------------------------------------------

    click(
        "confirm_item"
    )

    if stop_event.is_set():
        return False

    # --------------------------------------------------------
    # PRICE
    # --------------------------------------------------------

    click(
        "price"
    )

    hotkey(
        "ctrl",
        "a"
    )

    write_text(
        price
    )

    if stop_event.is_set():
        return False

    # --------------------------------------------------------
    # SUBMIT
    # --------------------------------------------------------

    click(
        "submit"
    )

    if stop_event.is_set():
        return False

    # --------------------------------------------------------
    # YES
    # --------------------------------------------------------

    click(
        "yes"
    )

    print(
        "[RESTOCK] COMPLETE"
    )

    return True


# ============================================================
# BOOTH CAPACITY CAPTURE + OCR
# ============================================================

def capture_booth_region():

    cx, cy = BOOTH_CAP_CENTER

    w, h = BOOTH_CAP_REGION_SIZE

    region = (

        cx - w // 2,

        cy - h // 2,

        w,

        h
    )

    return pyautogui.screenshot(
        region=region
    )


def preprocess_booth_image(
    screenshot
):

    # Windows OCR handles color images fine — it doesn't need
    # the black/white thresholding Tesseract needed. Upscaling
    # still helps it pick out small on-screen text reliably.

    base = screenshot.convert(
        "RGB"
    )

    upscaled = base.resize(
        (
            base.width * 4,
            base.height * 4
        ),
        Image.LANCZOS
    )

    return upscaled


def run_windows_ocr(
    image
):

    # winocr's recognize_pil() is a coroutine wrapping the
    # Windows.Media.Ocr API. This function itself is called
    # from a plain background thread (either
    # booth_capacity_monitor()'s own thread, or a thread
    # spawned by asyncio.to_thread() for /boothcap) — neither
    # has a running event loop of its own, so asyncio.run()
    # here is safe and won't collide with the bot's main loop.

    result = asyncio.run(
        winocr.recognize_pil(
            image,
            lang="en"
        )
    )

    return result.text


def ocr_booth_count(
    screenshot
):

    # BOOTH_CAP_MAX_DIGITS caps how many digits either side of
    # the "/" is allowed to have. The in-game counter is a
    # small slot count (currently maxing at 25), so a "correct"
    # read is always 1-2 digits per side. Rejecting a longer
    # read means a misfire gets discarded instead of trusted.

    digit_pattern = (
        r"(\d{1,"
        + str(BOOTH_CAP_MAX_DIGITS)
        + r"})\s*/\s*(\d{1,"
        + str(BOOTH_CAP_MAX_DIGITS)
        + r"})"
    )

    image = preprocess_booth_image(
        screenshot
    )

    text = run_windows_ocr(
        image
    )

    last_text = text.strip()

    match = re.search(
        digit_pattern,
        text
    )

    if match:

        used = int(
            match.group(1)
        )

        limit = int(
            match.group(2)
        )

        return (
            used,
            limit,
            last_text
        )

    # First pass didn't parse — try again on the raw
    # (non-upscaled) crop, since occasionally the native size
    # reads better than the upscaled one.

    text = run_windows_ocr(
        screenshot.convert("RGB")
    )

    last_text = text.strip()

    match = re.search(
        digit_pattern,
        text
    )

    if match:

        used = int(
            match.group(1)
        )

        limit = int(
            match.group(2)
        )

        return (
            used,
            limit,
            last_text
        )

    return None


def read_booth_capacity():

    screenshot = capture_booth_region()

    return ocr_booth_count(
        screenshot
    )


# ============================================================
# BOOTH CAPACITY MONITOR
#
# Polls the on-screen NN/NN counter. Pauses a bit before the
# booth is literally full (limit - 2) so there's headroom,
# and resumes once it drops back below that. Also keeps
# bot_status updated for the GUI.
# ============================================================

def booth_capacity_monitor():

    print(
        "[BOOTH CAP] Started."
    )

    was_full = False

    while not stop_event.is_set():

        try:

            result = read_booth_capacity()

            if result:

                used, limit, raw_text = result

                with bot_status.lock:

                    bot_status.booth_last_read = (
                        f"{used}/{limit}"
                    )

                is_full = used >= (limit - 2)

                if is_full and not was_full:

                    booth_full_event.set()

                    with bot_status.lock:

                        bot_status.booth_full = True

                    print(
                        f"[BOOTH CAP] FULL "
                        f"({used}/{limit}) — "
                        f"pausing queue."
                    )

                    set_last_event(
                        f"Booth full ({used}/{limit}) — "
                        f"queue paused"
                    )

                    asyncio.run_coroutine_threadsafe(

                        send_discord(
                            f"⏸️ **Booth full "
                            f"({used}/{limit})** — "
                            f"restock queue paused."
                        ),

                        client.loop
                    )

                elif not is_full and was_full:

                    booth_full_event.clear()

                    with bot_status.lock:

                        bot_status.booth_full = False

                    print(
                        f"[BOOTH CAP] Slot freed "
                        f"({used}/{limit}) — "
                        f"resuming queue."
                    )

                    set_last_event(
                        f"Booth slot freed ({used}/{limit}) "
                        f"— queue resumed"
                    )

                    asyncio.run_coroutine_threadsafe(

                        send_discord(
                            f"▶️ **Booth slot freed "
                            f"({used}/{limit})** — "
                            f"restock queue resumed."
                        ),

                        client.loop
                    )

                was_full = is_full

            else:

                print(
                    "[BOOTH CAP] Could not read "
                    "a NN/NN count this check."
                )

        except Exception as e:

            print(
                "[BOOTH CAP ERROR]",
                e
            )

        stop_event.wait(
            BOOTH_CAP_CHECK_SECONDS
        )

    print(
        "[BOOTH CAP] Stopped."
    )


# ============================================================
# /BOOTHCAP
#
# Debug command: captures the exact region being watched,
# OCRs it, and sends back both the parsed value and the
# cropped image so the capture box can be tuned from
# BOOTH_CAP_CENTER / BOOTH_CAP_REGION_SIZE without guessing.
# ============================================================

@tree.command(
    name="boothcap",
    description="Debug: read and preview the booth capacity crop right now."
)
async def boothcap_command(
    interaction: discord.Interaction
):

    await interaction.response.defer()

    try:

        screenshot = await asyncio.to_thread(
            capture_booth_region
        )

        result = await asyncio.to_thread(
            ocr_booth_count,
            screenshot
        )

        debug_path = os.path.join(
            os.getcwd(),
            "boothcap_debug.png"
        )

        screenshot.save(
            debug_path
        )

        processed = await asyncio.to_thread(
            preprocess_booth_image,
            screenshot
        )

        variant_path = os.path.join(
            os.getcwd(),
            "boothcap_debug_processed.png"
        )

        processed.save(
            variant_path
        )

        if result:

            used, limit, raw_text = result

            message = (
                f"🔎 **Parsed:** {used}/{limit}\n"
                f"**Raw OCR text:** `{raw_text}`\n\n"
                f"Region: center {BOOTH_CAP_CENTER}, "
                f"size {BOOTH_CAP_REGION_SIZE}"
            )

        else:

            message = (
                "⚠️ **Could not parse a NN/NN pattern "
                "from this crop.**\n\n"
                "First image is the raw crop; second is "
                "the upscaled version actually fed to "
                "Windows OCR. If the digits aren't clean "
                "and separated in the second image, try "
                "adjusting `BOOTH_CAP_REGION_SIZE` (usually "
                "a bit larger) so there's some padding "
                "around the text."
            )

        await interaction.followup.send(
            message,
            files=[
                discord.File(
                    debug_path
                ),
                discord.File(
                    variant_path
                ),
            ]
        )

    except Exception as e:

        await interaction.followup.send(
            f"❌ **Capture failed:**\n`{e}`"
        )


# ============================================================
# GUI COLOR WATCHDOG / RECALIBRATION
#
# Watches one pixel for a red the game shows (target color
# FF094A). If that red hasn't appeared for
# COLOR_ABSENCE_TIMEOUT seconds, something's likely gotten
# out of sync — press F, wait 1s, F, wait 1s, E to
# "recalibrate the gui" (their term for it). The same F-F-E
# sequence also runs after every successful restock as a
# routine safety reset.
# ============================================================

COLOR_CHECK_COORD = (
    1449,
    281
)

COLOR_CHECK_TARGET = (
    0xFF,
    0x09,
    0x4A
)

# How far off (per RGB channel, roughly) a sampled pixel can
# be from COLOR_CHECK_TARGET and still count as "the red is
# there". Screen compression/anti-aliasing means an exact
# match is unreliable — this gives it some slack.
COLOR_CHECK_TOLERANCE = 40

# Seconds the red can be absent before triggering a
# recalibration.
COLOR_ABSENCE_TIMEOUT = 20

# How often to sample the pixel.
COLOR_CHECK_INTERVAL = 1

# Extra pause after each restock finishes, before the worker
# picks up the next queued job.
POST_RESTOCK_DELAY = 5


def color_close(
    a,
    b,
    tolerance
):

    return (
        sum(
            (x - y) ** 2
            for x, y in zip(a, b)
        )
        ** 0.5
    ) <= tolerance


def is_recalibration_red_present():

    x, y = COLOR_CHECK_COORD

    pixel = pyautogui.pixel(
        x,
        y
    )

    # pyautogui.pixel() can return RGBA on some setups —
    # only the first three values matter here.

    return color_close(
        pixel[:3],
        COLOR_CHECK_TARGET,
        COLOR_CHECK_TOLERANCE
    )


def recalibrate_gui(
    reason
):

    print()
    print(
        "[RECALIBRATE]",
        reason
    )

    if not DRY_RUN:

        with mouse_lock:

            pydirectinput.press(
                "f"
            )

            time.sleep(
                1
            )

            pydirectinput.press(
                "f"
            )

            time.sleep(
                1
            )

            pydirectinput.press(
                "e"
            )

    set_last_event(
        f"Recalibrated ({reason})"
    )


def color_watchdog():

    print(
        "[COLOR WATCHDOG] Started."
    )

    last_seen_red = time.monotonic()

    while not stop_event.is_set():

        try:

            if is_recalibration_red_present():

                last_seen_red = time.monotonic()

            else:

                elapsed = (
                    time.monotonic()
                    - last_seen_red
                )

                if elapsed >= COLOR_ABSENCE_TIMEOUT:

                    print(
                        f"[COLOR WATCHDOG] Red missing for "
                        f"{elapsed:.0f}s — recalibrating."
                    )

                    recalibrate_gui(
                        f"red missing "
                        f"{COLOR_ABSENCE_TIMEOUT}s+"
                    )

                    asyncio.run_coroutine_threadsafe(

                        send_discord(
                            "🔄 **Auto-recalibrated** — "
                            f"the red indicator hadn't shown "
                            f"up for {COLOR_ABSENCE_TIMEOUT}s."
                        ),

                        client.loop
                    )

                    # Reset the clock so this doesn't fire
                    # again every single second while the
                    # red is still absent.
                    last_seen_red = time.monotonic()

        except Exception as e:

            print(
                "[COLOR WATCHDOG ERROR]",
                e
            )

        stop_event.wait(
            COLOR_CHECK_INTERVAL
        )

    print(
        "[COLOR WATCHDOG] Stopped."
    )


# ============================================================
# RESTOCK WORKER
# ============================================================

def restock_worker():

    print(
        "[RESTOCK WORKER] Started."
    )

    while not stop_event.is_set():

        if booth_full_event.is_set():

            stop_event.wait(
                1
            )

            continue

        job = None

        with queue_lock:

            if restock_queue:

                job = (
                    restock_queue.popleft()
                )

        if not job:

            stop_event.wait(
                1
            )

            continue

        try:

            success = restock_item(

                job["item"],

                job["search_name"],

                job["price"]
            )

            if success:

                rap_text = ""

                if job.get("rap", 0):

                    rap_text = (
                        f" | RAP: {job['rap']:,}"
                    )

                basis_text = ""

                if job.get("price_basis"):

                    basis_text = (
                        f" (based on "
                        f"{job['price_basis']})"
                    )

                set_last_event(
                    f"Restocked {job['item']} for "
                    f"{job['price']:,}{basis_text}{rap_text}"
                )

                discord_rap_line = ""

                if job.get("rap", 0):

                    discord_rap_line = (
                        "\n**RAP:** "
                        + format(job["rap"], ",")
                    )

                asyncio.run_coroutine_threadsafe(

                    send_discord(

                        "✅ **Restocked**\n"
                        f"**Item:** "
                        f"{job['item']}\n"
                        f"**Search:** "
                        f"{job['search_name']}\n"
                        f"**Price:** "
                        f"{job['price']:,} diamonds"
                        f"{basis_text}"
                        f"{discord_rap_line}"
                    ),

                    client.loop
                )

                # Routine safety reset — runs after every
                # successful restock, not just when the color
                # watchdog notices something's wrong.
                recalibrate_gui(
                    "after restock"
                )

        except Exception as e:

            print(
                "[RESTOCK ERROR]",
                e
            )

            set_last_event(
                f"Restock failed for "
                f"{job.get('item', 'Unknown')}: {e}"
            )

            if not stop_event.is_set():

                asyncio.run_coroutine_threadsafe(

                    send_discord(

                        "❌ **Restock failed**\n"
                        f"**Item:** "
                        f"{job.get('item', 'Unknown')}\n"
                        f"**Error:** `{e}`"
                    ),

                    client.loop
                )

        # Pause between listings regardless of whether this
        # one succeeded or failed, before the next queued job
        # (if any) is picked up.
        if not stop_event.is_set():

            stop_event.wait(
                POST_RESTOCK_DELAY
            )

    print(
        "[RESTOCK WORKER] Stopped."
    )


# ============================================================
# ANTI-IDLE
# ============================================================

def anti_idle_worker():

    print(
        "[ANTI-IDLE] Started."
    )

    while not stop_event.is_set():

        try:

            if mouse_lock.acquire(
                blocking=False
            ):

                try:

                    x, y = (
                        pyautogui.position()
                    )

                    pyautogui.moveTo(
                        x + 1,
                        y,
                        duration=0.05
                    )

                    pyautogui.moveTo(
                        x,
                        y,
                        duration=0.05
                    )

                finally:

                    mouse_lock.release()

        except Exception as e:

            print(
                "[ANTI-IDLE ERROR]",
                e
            )

        stop_event.wait(
            ANTI_IDLE_SECONDS
        )

    print(
        "[ANTI-IDLE] Stopped."
    )


# ============================================================
# BOT READY / DISCONNECT
# ============================================================

@client.event
async def on_ready():

    with bot_status.lock:

        bot_status.connected = True

        bot_status.bot_user = str(
            client.user
        )

    set_last_event(
        f"Connected to Discord as {client.user}"
    )

    print()

    print(
        "=============================="
    )

    print(
        "PS99 RESTOCK SYSTEM ONLINE"
    )

    print(
        "=============================="
    )

    print(
        "Logged in as:",
        client.user
    )

    print(
        "Dry run:",
        DRY_RUN
    )

    print(
        "Markup:",
        f"+{get_markup_percent():g}%"
    )

    print(
        "OAuth client:",
        PS99_CLIENT_ID
    )

    print(
        "PS99 token:",
        "Configured"
        if PS99_ACCESS_TOKEN
        else "NOT CONFIGURED"
    )

    print(
        "Anti-idle:",
        f"every {ANTI_IDLE_SECONDS}s"
    )

    try:

        synced = await tree.sync()

        print(
            f"Synced {len(synced)} Discord commands."
        )

    except Exception as e:

        print(
            "Command sync failed:",
            e
        )


@client.event
async def on_disconnect():

    with bot_status.lock:

        bot_status.connected = False


# ============================================================
# STATUS GUI (always-on-top window)
#
# Runs on the MAIN thread (tkinter needs that). Discord and
# all the worker threads run in the background instead — see
# main() below. The window polls bot_status/restock_queue
# every 500ms rather than being pushed to, since those live
# on other threads and tkinter isn't thread-safe to call into
# directly from them.
# ============================================================

def start_gui():

    root = tk.Tk()

    root.title(
        "PS99 Restock Bot"
    )

    root.attributes(
        "-topmost",
        True
    )

    root.resizable(
        False,
        False
    )

    root.geometry(
        "270x260"
    )

    frame = ttk.Frame(
        root,
        padding=12
    )

    frame.pack(
        fill="both",
        expand=True
    )

    status_var = tk.StringVar(
        value="🔴 Not connected"
    )

    queue_var = tk.StringVar(
        value="Queue: 0 job(s)"
    )

    booth_var = tk.StringVar(
        value="Booth: waiting for first read"
    )

    event_var = tk.StringVar(
        value="Starting up..."
    )

    ttk.Label(
        frame,
        textvariable=status_var,
        font=("Segoe UI", 10, "bold")
    ).pack(
        anchor="w"
    )

    ttk.Label(
        frame,
        textvariable=queue_var
    ).pack(
        anchor="w",
        pady=(8, 0)
    )

    ttk.Label(
        frame,
        textvariable=booth_var
    ).pack(
        anchor="w",
        pady=(2, 0)
    )

    ttk.Separator(
        frame
    ).pack(
        fill="x",
        pady=10
    )

    ttk.Label(
        frame,
        text="Last event:"
    ).pack(
        anchor="w"
    )

    ttk.Label(
        frame,
        textvariable=event_var,
        wraplength=246,
        foreground="#555555"
    ).pack(
        anchor="w"
    )

    ttk.Separator(
        frame
    ).pack(
        fill="x",
        pady=10
    )

    ttk.Label(
        frame,
        text="Markup % (over higher of RAP/Cosmic):"
    ).pack(
        anchor="w"
    )

    markup_var = tk.StringVar(
        value=f"{get_markup_percent():g}"
    )

    def apply_markup(
        *_
    ):

        try:

            value = float(
                markup_var.get()
            )

        except ValueError:

            markup_var.set(
                f"{get_markup_percent():g}"
            )

            return

        new_value = set_markup_percent(
            value
        )

        markup_var.set(
            f"{new_value:g}"
        )

        set_last_event(
            f"Markup changed to +{new_value:g}% "
            f"(via GUI)"
        )

    markup_row = ttk.Frame(
        frame
    )

    markup_row.pack(
        anchor="w",
        pady=(4, 0),
        fill="x"
    )

    spin = ttk.Spinbox(
        markup_row,
        from_=0,
        to=500,
        increment=0.5,
        textvariable=markup_var,
        width=8
    )

    spin.pack(
        side="left"
    )

    spin.bind(
        "<Return>",
        apply_markup
    )

    spin.bind(
        "<FocusOut>",
        apply_markup
    )

    ttk.Button(
        markup_row,
        text="Apply",
        command=apply_markup
    ).pack(
        side="left",
        padx=(6, 0)
    )

    def refresh():

        with bot_status.lock:

            connected = bot_status.connected

            bot_user = bot_status.bot_user

            booth_full = bot_status.booth_full

            booth_last_read = bot_status.booth_last_read

            last_event = bot_status.last_event

        if connected:

            status_var.set(
                f"🟢 Connected as {bot_user}"
            )

        else:

            status_var.set(
                "🔴 Not connected"
            )

        with queue_lock:

            qlen = len(
                restock_queue
            )

        queue_var.set(
            f"Queue: {qlen} job(s)"
        )

        if booth_last_read:

            if booth_full:

                booth_var.set(
                    f"⏸️ Booth FULL "
                    f"({booth_last_read}) — paused"
                )

            else:

                booth_var.set(
                    f"▶️ Booth OK "
                    f"({booth_last_read})"
                )

        else:

            booth_var.set(
                "Booth: waiting for first read"
            )

        event_var.set(
            last_event
        )

        root.after(
            500,
            refresh
        )

    def on_close():

        stop_event.set()

        try:

            if client.loop and client.loop.is_running():

                asyncio.run_coroutine_threadsafe(
                    client.close(),
                    client.loop
                )

        except Exception:

            pass

        root.destroy()

    root.protocol(
        "WM_DELETE_WINDOW",
        on_close
    )

    refresh()

    root.mainloop()


# ============================================================
# START DISCORD (runs on a background thread now — the GUI
# owns the main thread instead)
# ============================================================

def start_discord_bot():

    try:

        client.run(
            DISCORD_TOKEN
        )

    except Exception as e:

        print(
            "[DISCORD] Fatal error:",
            e
        )

        set_last_event(
            f"Discord connection failed: {e}"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    run_setup_wizard()

    if not DISCORD_TOKEN:

        print(
            "ERROR: DISCORD_TOKEN is missing."
        )

        return

    if not PS99_CLIENT_ID:

        print(
            "WARNING: PS99_CLIENT_ID is missing."
        )

    if not PS99_CLIENT_SECRET:

        print(
            "WARNING: PS99_CLIENT_SECRET is missing."
        )

    # --------------------------------------------------------
    # DISCORD (background thread — GUI needs the main thread)
    # --------------------------------------------------------

    threading.Thread(
        target=start_discord_bot,
        daemon=True
    ).start()

    # --------------------------------------------------------
    # RESTOCK WORKER
    # --------------------------------------------------------

    threading.Thread(
        target=restock_worker,
        daemon=True
    ).start()

    # --------------------------------------------------------
    # ANTI-IDLE
    # --------------------------------------------------------

    threading.Thread(
        target=anti_idle_worker,
        daemon=True
    ).start()

    # --------------------------------------------------------
    # BOOTH CAPACITY MONITOR
    # --------------------------------------------------------

    threading.Thread(
        target=booth_capacity_monitor,
        daemon=True
    ).start()

    # --------------------------------------------------------
    # COLOR WATCHDOG / RECALIBRATION
    # --------------------------------------------------------

    threading.Thread(
        target=color_watchdog,
        daemon=True
    ).start()

    # --------------------------------------------------------
    # STATUS GUI (blocking — this is what keeps main() alive)
    # --------------------------------------------------------

    start_gui()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()
