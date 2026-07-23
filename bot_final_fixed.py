# -*- coding: utf-8 -*-
import hashlib
import hmac
import html
import json
import logging
import os
import sqlite3
import sys
import threading
import traceback
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, request as flask_request
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    ParseMode,
)
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    Filters,
    MessageHandler,
    Updater,
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
logging.getLogger('telegram').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE_PATH = os.path.join(BASE_DIR, 'bot_debug.log')
file_handler = logging.FileHandler(LOG_FILE_PATH, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", 6407498844))
CHANNEL_ID = os.getenv("CHANNEL_ID", "@smyard")
SCREENSHOT_CHANNEL_ID = os.getenv("SCREENSHOT_CHANNEL_ID", "@smyardsgallary")
DISCUSSION_GROUP_ID = os.getenv("DISCUSSION_GROUP_ID", "-1002777496302")
STOCK_CHANNEL_ID = os.getenv("STOCK_CHANNEL_ID", "-1002861193688")
ESCROW_LOG_CHANNEL_ID = os.getenv("ESCROW_LOG_CHANNEL_ID", "-1002872620027")
MAX_SCREENSHOTS = 10

COINBASE_ADDRESS = os.getenv("COINBASE_ADDRESS", "")
BINANCE_ADDRESS = os.getenv("BINANCE_ADDRESS", "")
BTC_ADDRESS = os.getenv("BTC_ADDRESS", "")
ETH_ADDRESS = os.getenv("ETH_ADDRESS", "")
USDT_ADDRESS = os.getenv("USDT_ADDRESS", "")
USDC_ADDRESS = os.getenv("USDC_ADDRESS", "")

CRYPTOMUS_MERCHANT_ID = os.getenv("CRYPTOMUS_MERCHANT_ID", "")
CRYPTOMUS_API_KEY = os.getenv("CRYPTOMUS_API_KEY", "")
CRYPTOMUS_WEBHOOK_URL = os.getenv("CRYPTOMUS_WEBHOOK_URL", "")

if not BOT_TOKEN:
    logger.error("BOT_TOKEN not found in environment")
    sys.exit(1)

PLATFORMS = ["YouTube", "TikTok", "Instagram", "Facebook"]
YOUTUBE_TYPES = ["Monetized Channel", "Aged Channel", "Gaming Channel", "Organic Channel", "3-Features Enabled Channel"]
DEFAULT_TYPES = ["Verified Account", "Personal Account", "Business Account"]

# Use Railway persistent volume if available, otherwise use local directory
_DATA_DIR = os.getenv("DATABASE_DIR", os.path.join("/app/data" if os.path.isdir("/app/data") else BASE_DIR))
DATABASE_NAME = os.path.join(_DATA_DIR, "listings.db")

# ===== CUSTOMER CONVERSATION STATES =====
# Admin states (0-15)
(
    MAIN_MENU, CREATE_PLATFORM, CREATE_TYPE, 
    CREATE_DETAILS, CREATE_PRICE, CREATE_SELLER_CONTACT,
    SCREENSHOT_ASK, SCREENSHOT_UPLOAD, CREATE_CONFIRM,
    MARK_SOLD, ENTER_PRODUCT_ID, ENTER_TXID, ENTER_PAYMENT_METHOD,
    ENTER_ORDER_NUMBER, ADMIN_RELIST_MENU, ADMIN_MARK_SOLD, ENTER_ORDER_TXID,
    ASSIGN_UPGRADE_USER, ASSIGN_UPGRADE_TYPE, ASSIGN_UPGRADE_DUR,
    ENTER_SELLER_NAME
) = range(21)

# Customer states (15-33)
(
    CUSTOMER_MENU, BUYER_ESCROW_INFO, BUYER_ENTER_PRODUCT_ID,
    BUYER_CONFIRM_PRODUCT, BUYER_PAYMENT_METHODS, BUYER_PAYMENT_INSTRUCTIONS,
    BUYER_CONFIRM_PAYMENT, SELLER_INFO, SELLER_PLATFORM, SELLER_LINK,
    SELLER_DETAILS, SELLER_PRICE, SELLER_CONTACT,
    SELLER_SCREENSHOTS, SELLER_CONFIRM,
    CUSTOMER_MANAGE_LISTINGS, CUSTOMER_CONFIRM_SOLD,
    CUSTOMER_EDIT_FIELD, CUSTOMER_EDIT_INPUT
) = range(15, 34)

# Browse / Search states (33-39)
(
    BROWSE_MENU, BROWSE_PLATFORM_LIST, BROWSE_LISTING_DETAIL,
    BROWSE_FILTER_MENU, BROWSE_FILTER_PRICE, BROWSE_FILTER_SUBS,
    BROWSE_SEARCH_KEYWORD, BROWSE_FILTER_AGE
) = range(35, 43)

# Order Management states - Stage 1 (40-43)
(
    ADMIN_ORDERS_PANEL, ADMIN_ORDER_DETAIL, CUSTOMER_MY_ORDERS, CUSTOMER_ORDER_DETAIL
) = range(43, 47)

# Group link states - Stage 2 (44-45)
(
    ADMIN_ADD_GROUP_LINK, ADMIN_CONFIRM_GROUP_LINK
) = range(47, 49)

ADMIN_REJECT_REASON = 50
ENTER_ORDER_PAYMENT_METHOD = 51
ENTER_CUSTOM_CRYPTO = 52
ADMIN_EDIT_REVIEW = 53
ADMIN_EDIT_BUMP_TIME = 54





# ===== DATABASE FUNCTIONS =====   
def init_database():
    """Initialize the SQLite database"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS listings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        listing_id TEXT UNIQUE NOT NULL,
        platform TEXT NOT NULL,
        account_type TEXT NOT NULL,
        channel_age TEXT,
        subscribers INTEGER,
        views INTEGER,
        niche TEXT,
        features TEXT,
        monetization TEXT,
        region TEXT,
        status TEXT,
        price REAL NOT NULL,
        screenshots TEXT,
        seller_contact TEXT,
        status_flag TEXT DEFAULT 'draft',
        published_time DATETIME,
        channel_message_id TEXT,         -- Will hold comma-separated historical IDs
        screenshot_message_id TEXT,
        discussion_message_id TEXT,
        stock_message_id TEXT,
        created_by INTEGER NOT NULL,
        last_bumped_at DATETIME,         -- TRACKS BUMP TIME
        bump_cooldown_days INTEGER DEFAULT 3, -- CUSTOMIZABLE COOLDOWN
        likes INTEGER,
        growth TEXT,
        extra_monetization TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE NOT NULL,
        username TEXT,
        role TEXT DEFAULT 'owner',
        added_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS customer_listings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        listing_id TEXT UNIQUE NOT NULL,
        platform TEXT NOT NULL,
        account_type TEXT NOT NULL,
        channel_age TEXT,
        subscribers INTEGER,
        views INTEGER,
        niche TEXT,
        features TEXT,
        monetization TEXT,
        region TEXT,
        status TEXT,
        price REAL NOT NULL,
        screenshots TEXT,
        seller_contact TEXT,
        customer_id INTEGER NOT NULL,
        customer_username TEXT,
        status_flag TEXT DEFAULT 'pending',
        admin_notes TEXT,
        growth TEXT,
        channel_link TEXT,
        likes INTEGER,
        extra_monetization TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_number TEXT UNIQUE NOT NULL,
        product_id TEXT NOT NULL,
        customer_id INTEGER NOT NULL,
        customer_username TEXT,
        platform TEXT NOT NULL,
        total_price REAL NOT NULL,
        escrow_fee REAL NOT NULL,
        amount_to_pay REAL NOT NULL,
        payment_method TEXT NOT NULL,
        payment_address TEXT NOT NULL,
        payment_status TEXT DEFAULT 'pending',
        admin_notified INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS upgrade_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_number TEXT UNIQUE NOT NULL,
        customer_id INTEGER NOT NULL,
        customer_username TEXT,
        upgrade_type TEXT NOT NULL,
        duration_days INTEGER NOT NULL,
        amount_to_pay REAL NOT NULL,
        payment_status TEXT DEFAULT 'pending',
        payment_confirmed_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS edit_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        listing_id TEXT NOT NULL,
        field_name TEXT NOT NULL,
        new_value TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS ap_guidance_media (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL,
        file_id TEXT NOT NULL,
        media_type TEXT NOT NULL DEFAULT 'photo',
        sort_order INTEGER DEFAULT 0,
        FOREIGN KEY(post_id) REFERENCES ap_guidance_posts(id) ON DELETE CASCADE
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS ap_promo_media (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL,
        file_id TEXT NOT NULL,
        media_type TEXT NOT NULL DEFAULT 'photo',
        sort_order INTEGER DEFAULT 0,
        FOREIGN KEY(post_id) REFERENCES ap_promo_posts(id) ON DELETE CASCADE
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS bot_settings (
        setting_key TEXT PRIMARY KEY,
        setting_value TEXT NOT NULL,
        description TEXT
    )
    ''')

    # Add seller_id explicitly    
    cursor.execute('SELECT 1 FROM admins WHERE user_id = ?', (OWNER_ID,))
    if not cursor.fetchone():
        cursor.execute('INSERT INTO admins (user_id, username, role) VALUES (?, ?, ?)', 
                       (OWNER_ID, "Owner", "owner"))
    
    conn.commit()
    conn.close()
    logger.info("Database initialized: %s", DATABASE_NAME)

    add_orders_table_columns()
    run_db_migrations()
    add_seller_contact_column()
    add_seller_telegram_id_to_listings()
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("ALTER TABLE listings ADD COLUMN channel_age TEXT")
        conn.commit()
        conn.close()
    except Exception:
        pass
        
    add_transactions_log_table()
    run_stage_3_migrations()
    run_stage_4_migrations()
    run_stage_5_migrations()
    seed_initial_listing_ids()

def seed_initial_listing_ids():
    """Seed initial listing IDs so the next listings start at the requested sequence."""
    seeds = [
        ('YT-211', 'YouTube'),
        ('TT-191', 'TikTok'),
        ('IG-158', 'Instagram'),
        ('FB-109', 'Facebook')
    ]
    try:
        conn = get_connection()
        cursor = conn.cursor()
        for seed_id, platform in seeds:
            # Check if this exact seed ID or any higher ID already exists
            prefix = seed_id.split('-')[0]
            cursor.execute("SELECT listing_id FROM listings WHERE listing_id LIKE ?", (f"{prefix}-%",))
            existing = cursor.fetchall()
            
            # Also check customer_listings
            cursor.execute("SELECT listing_id FROM customer_listings WHERE listing_id LIKE ?", (f"{prefix}-%",))
            existing.extend(cursor.fetchall())
            
            max_num = 0
            for row in existing:
                parts = row[0].split('-')
                if len(parts) == 2 and parts[1].isdigit():
                    max_num = max(max_num, int(parts[1]))
            
            target_num = int(seed_id.split('-')[1])
            if max_num < target_num:
                # Insert seed row
                cursor.execute("""
                    INSERT INTO listings (
                        listing_id, platform, account_type, channel_age, subscribers, views, niche, features, 
                        monetization, region, status, price, screenshots, seller_contact, status_flag, created_by, published_time
                    ) VALUES (?, ?, 'N/A', 'N/A', 0, 0, 'N/A', 'N/A', 'N/A', 'N/A', 'No Strikes', 0, '', 'N/A', 'sold', 0, CURRENT_TIMESTAMP)
                """, (seed_id, platform))
                logger.info(f"✅ Seeded initial listing ID: {seed_id} for {platform}")
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error seeding initial listing IDs: {e}")

def run_stage_5_migrations():
    """Run migrations for Phase 5 features (Auto Pilot Packages)."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS auto_pilot_packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT,
            account_type TEXT,
            channel_age TEXT,
            subscribers INTEGER,
            views INTEGER,
            niche TEXT,
            features TEXT,
            monetization TEXT,
            growth TEXT,
            region TEXT,
            status TEXT,
            price REAL,
            seller_name TEXT,
            seller_contact TEXT,
            seller_telegram_id INTEGER,
            txid TEXT,
            screenshots TEXT,
            likes INTEGER,
            extra_monetization TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        # Add columns if table already exists without them
        for col_name, col_type in [
            ("seller_telegram_id", "INTEGER"),
            ("niche", "TEXT"),
            ("features", "TEXT"),
            ("monetization", "TEXT"),
            ("growth", "TEXT"),
            ("region", "TEXT"),
            ("status", "TEXT"),
            ("channel_link", "TEXT"),
            ("last_generated_listing_id", "TEXT"),
            ("channel_age", "TEXT"),
            ("likes", "INTEGER"),
            ("extra_monetization", "TEXT")
        ]:
            try:
                cursor.execute(f"ALTER TABLE auto_pilot_packages ADD COLUMN {col_name} {col_type}")
                logger.info(f"✅ Successfully added column {col_name} to auto_pilot_packages")
            except Exception as e:
                # Silently ignore duplicate column errors, but log others
                if "duplicate column name" not in str(e).lower():
                    logger.warning(f"Failed to add column {col_name} to auto_pilot_packages: {e}")

        cursor.execute("PRAGMA table_info(auto_pilot_packages)")
        actual_cols = [r[1] for r in cursor.fetchall()]
        logger.info(f"ℹ️ Current auto_pilot_packages columns: {actual_cols}")
        logger.info("✅ Created auto_pilot_packages table")
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS ap_promo_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            content_text TEXT,
            media_file_id TEXT,
            media_type TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS ap_guidance_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            content_text TEXT,
            media_file_id TEXT,
            media_type TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        logger.info("✅ Created ap_promo_posts and ap_guidance_posts tables")
        
        conn.commit()
        conn.close()
        logger.info("✅ Stage 5 migrations ready")
    except Exception as e:
        logger.error(f"Error running Stage 5 migrations: {e}")

def run_stage_4_migrations():
    """Run migrations for Phase 4 features (Escrow Log, Reviews)."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Add escrow_message_id to orders
        cursor.execute("PRAGMA table_info(orders)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'escrow_message_id' not in columns:
            cursor.execute("ALTER TABLE orders ADD COLUMN escrow_message_id TEXT")
            logger.info("✅ Added escrow_message_id to orders table")
            
        # Add escrow_message_id to transactions_log
        cursor.execute("PRAGMA table_info(transactions_log)")
        log_columns = [col[1] for col in cursor.fetchall()]
        if 'escrow_message_id' not in log_columns:
            cursor.execute("ALTER TABLE transactions_log ADD COLUMN escrow_message_id TEXT")
            logger.info("✅ Added escrow_message_id to transactions_log table")

        # Add channel_link to listings (for deal group welcome message)
        cursor.execute("PRAGMA table_info(listings)")
        listing_cols = [col[1] for col in cursor.fetchall()]
        if 'channel_link' not in listing_cols:
            cursor.execute("ALTER TABLE listings ADD COLUMN channel_link TEXT")
            logger.info("✅ Added channel_link to listings table")

        # Add channel_link to customer_listings
        cursor.execute("PRAGMA table_info(customer_listings)")
        cl_cols = [col[1] for col in cursor.fetchall()]
        if 'channel_link' not in cl_cols:
            cursor.execute("ALTER TABLE customer_listings ADD COLUMN channel_link TEXT")
            logger.info("✅ Added channel_link to customer_listings table")

        # Create platform_reviews table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS platform_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_number TEXT NOT NULL,
            reviewer_id INTEGER NOT NULL,
            reviewer_name TEXT,
            rating INTEGER NOT NULL,
            comment TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active'
        )
        ''')

        # Create user_reviews table (Rate the Other Party)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_number TEXT NOT NULL,
            reviewer_id INTEGER NOT NULL,
            reviewer_name TEXT,
            target_user_id INTEGER,
            target_username TEXT,
            rating INTEGER NOT NULL,
            comment TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        logger.info("✅ Review tables ready")
        
        conn.commit()
        conn.close()
        logger.info("✅ Stage 4 migrations ready")
    except Exception as e:
        logger.error(f"Error running Stage 4 migrations: {e}")

def run_stage_3_migrations():
    """Run migrations for Phase 3 features (Badges, Group Pool)."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # 1. Users Table (for badges)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            display_name TEXT,
            badge_type TEXT DEFAULT 'Regular',
            badge_expires_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN display_name TEXT")
            logger.info("✅ Added display_name to users table")
        except Exception:
            pass
        
        # 2. Available Groups Table (for Group Pooling)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS available_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT UNIQUE NOT NULL,
            invite_link TEXT NOT NULL,
            status TEXT DEFAULT 'available',
            assigned_order_id TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Add transaction_group_id to orders
        cursor.execute("PRAGMA table_info(orders)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'transaction_group_id' not in columns:
            cursor.execute("ALTER TABLE orders ADD COLUMN transaction_group_id TEXT")
            logger.info("✅ Added transaction_group_id to orders table")
        if 'buyer_joined' not in columns:
            cursor.execute("ALTER TABLE orders ADD COLUMN buyer_joined BOOLEAN DEFAULT 0")
        if 'seller_joined' not in columns:
            cursor.execute("ALTER TABLE orders ADD COLUMN seller_joined BOOLEAN DEFAULT 0")
        if 'welcome_sent' not in columns:
            cursor.execute("ALTER TABLE orders ADD COLUMN welcome_sent BOOLEAN DEFAULT 0")

        # Add admin_notes and growth to customer_listings
        cursor.execute("PRAGMA table_info(customer_listings)")
        cl_columns = [col[1] for col in cursor.fetchall()]
        if 'admin_notes' not in cl_columns:
            cursor.execute("ALTER TABLE customer_listings ADD COLUMN admin_notes TEXT")
            logger.info("✅ Added admin_notes to customer_listings")
        if 'growth' not in cl_columns:
            cursor.execute("ALTER TABLE customer_listings ADD COLUMN growth TEXT")
            logger.info("✅ Added growth to customer_listings")
            
        conn.commit()
        conn.close()
        logger.info("✅ Stage 3 migrations ready")
    except Exception as e:
        logger.error(f"Error running Stage 3 migrations: {e}")

def run_db_migrations():
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        
        # 1. Migrate listings table
        cursor.execute("PRAGMA table_info(listings)")
        listings_cols = [col[1] for col in cursor.fetchall()]
        
        listings_to_add = [
            ('last_bumped_at', 'DATETIME'),
            ('bump_cooldown_days', 'INTEGER DEFAULT 3'),
            ('likes', 'INTEGER'),
            ('growth', 'TEXT'),
            ('extra_monetization', 'TEXT')
        ]
        for col_name, col_type in listings_to_add:
            if col_name not in listings_cols:
                try:
                    cursor.execute(f"ALTER TABLE listings ADD COLUMN {col_name} {col_type}")
                    logger.info(f"✅ Added column {col_name} to listings table")
                except Exception as e:
                    logger.error(f"Failed to add column {col_name} to listings: {e}")
                    
        # 2. Migrate customer_listings table
        cursor.execute("PRAGMA table_info(customer_listings)")
        cust_cols = [col[1] for col in cursor.fetchall()]
        
        cust_to_add = [
            ('admin_notes', 'TEXT'),
            ('growth', 'TEXT'),
            ('channel_link', 'TEXT'),
            ('channel_age', 'TEXT'),
            ('likes', 'INTEGER'),
            ('extra_monetization', 'TEXT')
        ]
        for col_name, col_type in cust_to_add:
            if col_name not in cust_cols:
                try:
                    cursor.execute(f"ALTER TABLE customer_listings ADD COLUMN {col_name} {col_type}")
                    logger.info(f"✅ Added column {col_name} to customer_listings table")
                except Exception as e:
                    logger.error(f"Failed to add column {col_name} to customer_listings: {e}")
                    
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Migration error: {e}")
    
def add_seller_contact_column():
    """Add seller_contact column to database if it doesn't exist"""
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        
        # Check if seller_contact column exists
        cursor.execute("PRAGMA table_info(listings)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'seller_contact' not in columns:
            cursor.execute("ALTER TABLE listings ADD COLUMN seller_contact TEXT")
            conn.commit()
            logger.info("Added seller_contact column to listings table")
        conn.close()
    except Exception as e:
        logger.error("Error adding seller_contact column: %s", e)

def add_seller_telegram_id_to_listings():
    """Add seller_telegram_id field to track actual seller for notifications."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(listings)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'seller_telegram_id' not in columns:
            cursor.execute("ALTER TABLE listings ADD COLUMN seller_telegram_id INTEGER")
            logger.info("✅ Added seller_telegram_id to listings table")
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error adding seller_telegram_id: {e}")

def add_transactions_log_table():
    """Add transactions_log table for completed transactions."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_number TEXT UNIQUE NOT NULL,
            product_id TEXT NOT NULL,
            platform TEXT NOT NULL,
            seller_name TEXT NOT NULL,
            buyer_name TEXT NOT NULL,
            price REAL NOT NULL,
            payment_method TEXT,
            txid TEXT,
            status TEXT DEFAULT 'completed',
            completed_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        cursor.execute("PRAGMA table_info(transactions_log)")
        existing_cols = [col[1] for col in cursor.fetchall()]
        if 'payment_method' not in existing_cols:
            cursor.execute("ALTER TABLE transactions_log ADD COLUMN payment_method TEXT")
        conn.commit()
        conn.close()
        logger.info("✅ transactions_log table ready")
    except Exception as e:
        logger.error(f"Error creating transactions_log table: {e}")

def get_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row  # Allow dict-like access
    return conn

def row_get(row, key, default=None):
    """Safely get a value from a sqlite3.Row or dict. Works like dict.get()."""
    try:
        val = row[key]
        return val if val is not None else default
    except (KeyError, IndexError, TypeError):
        return default

def is_admin(user_id):
    """Check if user is admin"""
    if user_id == OWNER_ID:
        return True
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    return result is not None

import random

def generate_order_number(platform=None):
    """Generate a sequential 6-digit order number (e.g. 120101)"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT order_number FROM orders ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    
    if row and row[0]:
        try:
            clean_str = row[0].replace('#', '').replace('ORD-', '')
            last_num = int(clean_str)
            new_num = last_num + 1
        except Exception:
            new_num = 120000
    else:
        new_num = 120000
        
    return f"{new_num}"

def calculate_escrow_fee(price, seller_id=None):
    """Calculate escrow fee (5% with $5 minimum). Applies 30% discount if seller is Pro, 60% if VIP."""
    fee = float(price) * 0.05
    fee = max(fee, 5.0)
    
    if seller_id:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT badge_type, badge_expires_at FROM users WHERE telegram_id = ?", (seller_id,))
        res = cursor.fetchone()
        conn.close()
        
        if res:
            badge, expires = res[0], res[1]
            if expires and badge in ('Pro', 'VIP'):
                from datetime import datetime as _dt
                if _dt.strptime(expires, '%Y-%m-%d %H:%M:%S') > _dt.now():
                    if badge == 'Pro':
                        fee = fee * 0.70  # 30% discount
                    elif badge == 'VIP':
                        fee = fee * 0.40  # 60% discount
    return fee

def format_number(val):
    """Formats a number with commas (e.g., 4700 -> 4,700)"""
    if val is None or str(val).lower() == 'n/a':
        return 'N/A'
    try:
        # Remove existing commas first, then convert to float/int
        clean_val = str(val).replace(',', '')
        return f"{int(float(clean_val)):,}"
    except (ValueError, TypeError):
        return str(val)


# ===== CRYPTOMUS PAYMENT INTEGRATION =====

def create_cryptomus_invoice(order_id, amount_usd, product_id):
    """Create a Cryptomus payment invoice and return the payment URL."""
    import base64, json as _json
    
    payload = {
        "amount": f"{amount_usd:.2f}",
        "currency": "USD",
        "order_id": order_id,
        "url_callback": CRYPTOMUS_WEBHOOK_URL,
        "url_return": "https://t.me/smyards_bot",
        "url_success": "https://t.me/smyards_bot",
        "is_payment_multiple": False,
        "lifetime": 3600,
        "to_currency": "USDT",
        "additional_data": product_id,
    }

    payload_json = _json.dumps(payload)
    payload_b64 = base64.b64encode(payload_json.encode()).decode()
    sign = hashlib.md5(f"{payload_b64}{CRYPTOMUS_API_KEY}".encode()).hexdigest()

    headers = {
        "merchant": CRYPTOMUS_MERCHANT_ID,
        "sign": sign,
        "Content-Type": "application/json",
    }

    try:
        import requests as _requests
        resp = _requests.post(
            "https://api.cryptomus.com/v1/payment",
            json=payload,
            headers=headers,
            timeout=15
        )
        data = resp.json()
        if data.get("state") == 0:
            return data["result"]["url"]
        else:
            logger.error(f"Cryptomus invoice error: {data}")
            return None
    except Exception as e:
        logger.error(f"Cryptomus API request failed: {e}")
        return None


def verify_cryptomus_webhook(data: dict) -> bool:
    """Verify that the webhook actually came from Cryptomus."""
    import base64, json as _json
    received_sign = data.get("sign")
    if not received_sign:
        return False
    payload = {k: v for k, v in data.items() if k != "sign"}
    payload_json = _json.dumps(payload, separators=(",", ":"), sort_keys=True)
    payload_b64 = base64.b64encode(payload_json.encode()).decode()
    expected_sign = hashlib.md5(f"{payload_b64}{CRYPTOMUS_API_KEY}".encode()).hexdigest()
    return hmac.compare_digest(received_sign, expected_sign)


# Flask app for receiving Cryptomus webhooks
flask_app = Flask(__name__)
_bot_instance = None  # set in main()

@flask_app.route("/cryptomus-webhook", methods=["POST"])
def cryptomus_webhook():
    """Receive and handle Cryptomus payment confirmation webhooks."""
    import json as _json
    try:
        data = flask_request.get_json(force=True)
        logger.info(f"Cryptomus webhook received: {data}")
        if not verify_cryptomus_webhook(data):
            logger.warning("Cryptomus webhook verification failed!")
            return "FORBIDDEN", 403
        status = data.get("status", "")
        order_id = data.get("order_id", "")
        amount = data.get("amount", "0")
        currency = data.get("currency", "")
        payment_currency = data.get("payment_currency", "")
        if status in ("paid", "paid_over"):
            conn = get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """UPDATE orders SET payment_status = 'confirmed', 
                    payment_confirmed_at = CURRENT_TIMESTAMP,
                    payment_method = ? WHERE order_number = ?""",
                    (payment_currency or currency, order_id)
                )
                conn.commit()
                cursor.execute("SELECT * FROM orders WHERE order_number = ?", (order_id,))
                order = cursor.fetchone()
                if order:
                    cursor.execute("PRAGMA table_info(orders)")
                    columns = [col[1] for col in cursor.fetchall()]
                    order_dict = dict(zip(columns, order))
            finally:
                conn.close()

            if _bot_instance and order:
                order_db_id = order_dict.get('id', 0)
                seller_id = order_dict.get('seller_id')
                product_id = order_dict.get('product_id', 'N/A')
                buyer_username = order_dict.get('customer_username', 'N/A')
                total_price = order_dict.get('total_price', 0)
                
                # ===== HANDLE BADGE UPGRADE ORDERS =====
                if str(product_id).startswith('BADGE_'):
                    tier = str(product_id).replace('BADGE_', '')
                    buyer_id = order_dict.get('customer_id')
                    from datetime import timedelta
                    expires_at = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
                    
                    conn2 = get_connection()
                    try:
                        cur2 = conn2.cursor()
                        cur2.execute("""
                            INSERT INTO users (telegram_id, username, badge_type, badge_expires_at)
                            VALUES (?, ?, ?, ?)
                            ON CONFLICT(telegram_id) DO UPDATE SET
                                badge_type=excluded.badge_type,
                                badge_expires_at=excluded.badge_expires_at
                        """, (buyer_id, buyer_username, tier, expires_at))
                        conn2.commit()
                    finally:
                        conn2.close()
                    
                    if buyer_id:
                        try:
                            _bot_instance.send_message(
                                chat_id=buyer_id,
                                text=f"⭐ **Your {tier} Badge is now ACTIVE!**\n\nExpires: {expires_at}\n\nEnjoy your premium benefits!",
                                parse_mode="Markdown"
                            )
                        except: pass
                    
                    _bot_instance.send_message(
                        chat_id=OWNER_ID,
                        text=f"⭐ Badge Upgrade Payment Received!\nUser @{buyer_username} ({buyer_id}) upgraded to {tier}.\nExpires: {expires_at}"
                    )
                    return "OK", 200  # Skip deal group logic
                
                # ===== HANDLE NORMAL ESCROW ORDERS =====
                conn = get_connection()
                try:
                    cursor = conn.cursor()
                    cursor.execute("SELECT id, chat_id, invite_link FROM available_groups WHERE status = 'available' ORDER BY created_at ASC LIMIT 1")
                    available_group = cursor.fetchone()
                    
                    if available_group:
                        group_db_id, group_chat_id, group_invite_link = available_group
                        
                        # Mark group as in use
                        cursor.execute("UPDATE available_groups SET status = 'in_use', assigned_order_id = ? WHERE id = ?", (order_id, group_db_id))
                        # Update order
                        cursor.execute("UPDATE orders SET transaction_group_id = ?, transaction_group_link = ?, order_status = 'group_link_set' WHERE order_number = ?", 
                                       (group_chat_id, group_invite_link, order_id))
                        conn.commit()
                        
                        # Attempt to rename the group
                        try:
                            _bot_instance.set_chat_title(chat_id=group_chat_id, title=f"SMyards - Transaction {order_id} Group")
                        except Exception as e:
                            logger.error(f"Failed to rename Deal Group {group_chat_id}: {e}")
                            
                        # Notify Admin (Automated)
                        admin_text = (
                            f"✅ <b>PAYMENT CONFIRMED!</b>\n\n"
                            f"🆔 Order: <code>{order_id}</code>\n"
                            f"💵 Amount: {amount} {currency} ({payment_currency})\n"
                            f"📦 Product: <code>{product_id}</code>\n"
                            f"👤 Buyer: @{buyer_username}\n\n"
                            f"🤖 <b>AUTOMATED:</b> A Deal Group was successfully assigned from the pool!\n"
                            f"🔗 Link: {group_invite_link}"
                        )
                        _bot_instance.send_message(chat_id=OWNER_ID, text=admin_text, parse_mode="HTML")
                        
                        # Notify Buyer
                        buyer_id = order_dict.get('customer_id')
                        if buyer_id:
                            safe_order_id = html_escape(order_id)
                            safe_group_invite_link = html_escape(group_invite_link)
                            buyer_text = (
                                f"✅ <b>PAYMENT CONFIRMED!</b>\n\n"
                                f"Your escrow payment for order <code>{safe_order_id}</code> is secured.\n\n"
                                f"🔗 <b>Join the Deal Group Here:</b>\n{safe_group_invite_link}\n\n"
                                f"The seller and admin are waiting for you!"
                            )
                            try:
                                _bot_instance.send_message(chat_id=buyer_id, text=buyer_text, parse_mode="HTML")
                            except Exception as e:
                                logger.error(f"Failed to notify buyer {buyer_id}: {e}")
                        
                        # Notify Seller (skip if admin)
                        if seller_id and seller_id != OWNER_ID:
                            safe_product_id = html_escape(product_id)
                            safe_buyer_username = html_escape(safe_telegram_username(buyer_username))
                            seller_text = (
                                f"✅ <b>PAYMENT CONFIRMED FOR YOUR LISTING!</b>\n\n"
                                f"📦 <b>Product:</b> <code>{safe_product_id}</code>\n"
                                f"🆔 <b>Order:</b> <code>{safe_order_id}</code>\n"
                                f"👤 <b>Buyer:</b> {safe_buyer_username}\n\n"
                                f"The buyer's payment is fully secured in our escrow!\n\n"
                                f"🔗 <b>Join the Deal Group Here:</b>\n{safe_group_invite_link}\n\n"
                                f"Please join to proceed with transferring the account."
                            )
                            try:
                                _bot_instance.send_message(chat_id=seller_id, text=seller_text, parse_mode="HTML")
                            except Exception as e:
                                logger.error(f"Failed to notify seller {seller_id}: {e}")
                    else:
                        # FALLBACK: No groups available, ask admin
                        try:
                            keyboard = [[InlineKeyboardButton("🔗 Add Group Link", callback_data=f"add_group_link_{order_db_id}")]]
                            admin_text = (
                                f"✅ <b>PAYMENT CONFIRMED!</b>\n\n"
                                f"🆔 Order: <code>{order_id}</code>\n"
                                f"💵 Amount: {amount} {currency}\n"
                                f"💳 Paid in: {payment_currency}\n"
                                f"📦 Product: <code>{product_id}</code>\n"
                                f"👤 Buyer: @{buyer_username}\n\n"
                                f"⚠️ <b>NO AVAILABLE DEAL GROUPS IN POOL!</b>\n"
                                f"➡️ Click below to manually add a deal group link."
                            )
                            _bot_instance.send_message(
                                chat_id=OWNER_ID,
                                text=admin_text,
                                reply_markup=InlineKeyboardMarkup(keyboard),
                                parse_mode="HTML"
                            )
                        except Exception as e:
                            logger.error(f"Failed to notify admin of payment: {e}")
                            
                        # Notify Seller (Manual Fallback)
                        if seller_id and seller_id != OWNER_ID:
                            try:
                                seller_text = (
                                    f"✅ **PAYMENT CONFIRMED FOR YOUR LISTING!**\n\n"
                                    f"📦 **Product:** `{product_id}`\n"
                                    f"🆔 **Order:** `{order_id}`\n"
                                    f"👤 **Buyer:** @{buyer_username}\n\n"
                                    f"🔗 The deal group link will be shared shortly!\n"
                                    f"⏳ Admin is setting up the secure transaction group..."
                                )
                                _bot_instance.send_message(chat_id=seller_id, text=seller_text, parse_mode="Markdown")
                            except Exception as e:
                                logger.error(f"Failed to notify seller {seller_id}: {e}")
                                
                finally:
                    conn.close()


        return "OK", 200
    except Exception as e:
        logger.error(f"Cryptomus webhook error: {e}")
        return "ERROR", 500


def run_flask():
    """Run Flask in a background thread alongside the Telegram bot."""
    flask_app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)), debug=False, use_reloader=False)

def get_user_bump_cooldown(user_id):
    """Returns the allowed cooldown days based on user badge and DB settings."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Load dynamic settings
    settings = {'bump_cooldown_regular': 4, 'bump_cooldown_pro': 2, 'bump_cooldown_vip': 1}
    try:
        cursor.execute("SELECT setting_key, setting_value FROM bot_settings")
        for k, v in cursor.fetchall():
            if k in settings:
                settings[k] = int(v)
    except:
        pass
        
    cursor.execute("SELECT badge_type, badge_expires_at FROM users WHERE telegram_id = ?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    
    if res:
        badge, expires = res[0], res[1]
        if expires:
            from datetime import datetime as _dt
            if _dt.strptime(expires, '%Y-%m-%d %H:%M:%S') > _dt.now():
                if badge == 'VIP': return settings['bump_cooldown_vip']
                if badge == 'Pro': return settings['bump_cooldown_pro']
    return settings['bump_cooldown_regular']
def get_seller_name(seller_id):
    """Helper to get a display name for a seller."""
    if not seller_id: return "Seller"
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT display_name, username FROM users WHERE telegram_id = ?", (seller_id,))
        res = cur.fetchone()
        if res:
            if res[0]: return res[0]
            if res[1]: return f"@{res[1]}"
        cur.execute("SELECT customer_username FROM customer_listings WHERE customer_id = ? LIMIT 1", (seller_id,))
        res = cur.fetchone()
        if res and res[0]: return f"@{res[0]}"
    except Exception:
        pass
    finally:
        conn.close()
    return "Seller"


def get_seller_username(seller_id):
    """Helper to get a telegram username for a seller for direct message links."""
    if not seller_id: return "smyards"
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT username FROM users WHERE telegram_id = ?", (seller_id,))
        res = cur.fetchone()
        if res and res[0]: return res[0].strip().lstrip('@')
        cur.execute("SELECT customer_username FROM customer_listings WHERE customer_id = ? LIMIT 1", (seller_id,))
        res = cur.fetchone()
        if res and res[0]: return res[0].strip().lstrip('@')
        # Fall back to seller_contact URL from listings (e.g. https://t.me/DramaGodcoinDRG)
        cur.execute("SELECT seller_contact FROM listings WHERE seller_telegram_id = ? AND seller_contact LIKE '%t.me/%' LIMIT 1", (seller_id,))
        res = cur.fetchone()
        if res and res[0]:
            contact = res[0].strip()
            if 't.me/' in contact:
                username = contact.split('t.me/')[-1].strip('/').split('?')[0]
                if username:
                    return username
    except Exception:
        pass
    finally:
        conn.close()
    return "smyards"

def html_escape(value):
    """Escape dynamic text before sending HTML-formatted Telegram messages."""
    if value is None:
        return ""
    return html.escape(str(value))

def safe_telegram_username(username, fallback="Unknown"):
    """Render Telegram usernames safely without breaking parse modes."""
    cleaned = str(username or "").strip().lstrip("@")
    if not cleaned:
        return fallback
    return f"@{cleaned}"

def get_listing_post_text(listing):
    """Format listing text for main channel - PER-PLATFORM FORMAT"""
    import json as _json
    import html as _html

    def _fmt_num(val):
        try:
            return f"{int(float(str(val).replace(',',''))):,}"
        except Exception:
            return str(val) if val else 'N/A'

    def _e(val, fallback='N/A'):
        return _html.escape(str(val)) if val else fallback

    listing_id = row_get(listing, 'listing_id', 'N/A')
    platform    = row_get(listing, 'platform', 'N/A')
    channel_age = _e(row_get(listing, 'channel_age', 'N/A'))
    region      = _e(row_get(listing, 'region', 'N/A'))
    subscribers = _fmt_num(row_get(listing, 'subscribers', 0))
    views       = _fmt_num(row_get(listing, 'views', 0))
    likes       = _fmt_num(row_get(listing, 'likes', 0))
    niche       = _e(row_get(listing, 'niche', 'N/A'))
    status      = _e(row_get(listing, 'status', 'No Strikes'))
    growth      = _e(row_get(listing, 'growth', 'N/A'))
    features    = _e(row_get(listing, 'features', 'N/A'))
    price_raw   = row_get(listing, 'price', 0)
    price       = _fmt_num(price_raw)

    # Parse extra_monetization JSON
    extra_mon_raw = row_get(listing, 'extra_monetization') or row_get(listing, 'monetization') or ''
    extra_mon = {}
    try:
        parsed = _json.loads(extra_mon_raw)
        if isinstance(parsed, dict):
            extra_mon = parsed
    except Exception:
        # Legacy: treat as the primary monetization string
        extra_mon = {'Monetization': extra_mon_raw} if extra_mon_raw else {}

    # Badge
    seller_id = row_get(listing, 'created_by') or row_get(listing, 'seller_telegram_id')
    badge_str = ""
    if seller_id:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT badge_type, badge_expires_at FROM users WHERE telegram_id = ?", (seller_id,))
            res = cursor.fetchone()
            if res:
                badge_type, expires = res[0], res[1]
                if expires:
                    from datetime import datetime as _dt
                    if _dt.strptime(expires, '%Y-%m-%d %H:%M:%S') > _dt.now():
                        if badge_type == "VIP":
                            badge_str = " 🛡️ <b>VIP Seller</b>"
                        elif badge_type == "Pro":
                            badge_str = " 🔹 <b>Pro Seller</b>"
        except Exception:
            pass
        finally:
            conn.close()

    # Format features as bullet list
    def _fmt_features(feat_str):
        if not feat_str or feat_str == 'N/A':
            return '    - N/A'
        lines = []
        for part in feat_str.replace('\n', ',').split(','):
            part = part.strip().lstrip('-').strip()
            if part:
                lines.append(f"    - {_html.escape(part)}")
        return '\n'.join(lines) if lines else '    - N/A'

    feats_block = _fmt_features(features)

    if platform == 'YouTube':
        mon      = extra_mon.get('Monetization', 'N/A')
        adv_feat = extra_mon.get('Advanced Features', extra_mon.get('Advanced/3rd Features', 'N/A'))
        return (
            f"🟥 <b>NEW Youtube Channel FOR SALE</b>{badge_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"- 🆔 <b>Account ID:</b> <code>{listing_id}</code>\n\n"
            f"📋 <b>BASIC INFO</b>\n"
            f"    - 📱 <b>Platform:</b> YouTube\n"
            f"    - 📅 <b>Channel Age:</b> {channel_age}\n"
            f"    - 🌍 <b>Region/Audience:</b> {region}\n\n"
            f"📊 <b>STATISTICS</b>\n"
            f"    - 👥 <b>Subscribers:</b> {subscribers}\n"
            f"    - 👀 <b>Views:</b> {views}\n\n"
            f"⚙️ <b>Properties</b>\n"
            f"    - 🗃️ <b>Niche:</b> {niche}\n"
            f"    - ✅ <b>Status:</b> {status}\n"
            f"    - 📈 <b>Growth:</b> {growth}\n\n"
            f"💵 <b>Monetization</b>\n"
            f"    - 💲 <b>Monetization:</b> {_e(mon)}\n"
            f"    - 🔧 <b>Advanced/3rd Features:</b> {_e(adv_feat)}\n\n"
            f"⚙️ <b>FEATURES</b>\n"
            f"{feats_block}\n\n"
            f"💰 <b>PRICING</b>\n"
            f"    - 💵 <b>Price:</b> ${price}"
        )

    elif platform == 'TikTok':
        mon      = extra_mon.get('Monetization', 'N/A')
        creator  = extra_mon.get('Creator Marketplace', 'N/A')
        subs_g   = extra_mon.get('Subscriptions & Gifts', 'N/A')
        affiliate= extra_mon.get('Affiliate Marketing', 'N/A')
        return (
            f"⬛️ <b>NEW TikTok Channel FOR SALE</b>{badge_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"- 🆔 <b>Account ID:</b> <code>{listing_id}</code>\n\n"
            f"📋 <b>BASIC INFO</b>\n"
            f"    - 📱 <b>Platform:</b> TikTok\n"
            f"    - 📅 <b>Channel Age:</b> {channel_age}\n"
            f"    - 🌍 <b>Region/Audience:</b> {region}\n\n"
            f"📊 <b>STATISTICS</b>\n"
            f"    - 👥 <b>Followers:</b> {subscribers}\n"
            f"    - 👀 <b>Views:</b> {views}\n"
            f"    - 👍 <b>Likes:</b> {likes}\n\n"
            f"⚙️ <b>Properties</b>\n"
            f"    - 🗃️ <b>Niche:</b> {niche}\n"
            f"    - ✅ <b>Status:</b> {status}\n"
            f"    - 📈 <b>Growth:</b> {growth}\n\n"
            f"💵 <b>Monetization</b>\n"
            f"    - 💲 <b>Monetization:</b> {_e(mon)}\n"
            f"    - 🛒 <b>Creator Marketplace:</b> {_e(creator)}\n"
            f"    - 🎁 <b>Subscriptions &amp; Gifts:</b> {_e(subs_g)}\n"
            f"    - 🏧 <b>Affiliate Marketing:</b> {_e(affiliate)}\n\n"
            f"⚙️ <b>FEATURES</b>\n"
            f"{feats_block}\n\n"
            f"💰 <b>PRICING</b>\n"
            f"    - 💵 <b>Price:</b> ${price}"
        )

    elif platform == 'Instagram':
        ads_r    = extra_mon.get('Ads on Reels', 'N/A')
        gifts_r  = extra_mon.get('Gifts (Reels)', 'N/A')
        ig_subs  = extra_mon.get('Instagram Subscriptions', 'N/A')
        return (
            f"🟪 <b>NEW Instagram Account FOR SALE</b>{badge_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"- 🆔 <b>Account ID:</b> <code>{listing_id}</code>\n\n"
            f"📋 <b>BASIC INFO</b>\n"
            f"    - 📱 <b>Platform:</b> Instagram\n"
            f"    - 📅 <b>Account Age:</b> {channel_age}\n"
            f"    - 🌍 <b>Region/Audience:</b> {region}\n\n"
            f"📊 <b>STATISTICS</b>\n"
            f"    - 👥 <b>Followers:</b> {subscribers}\n"
            f"    - 👀 <b>Views:</b> {views}\n"
            f"    - 👍 <b>Interactions:</b> {likes}\n\n"
            f"⚙️ <b>Properties</b>\n"
            f"    - 🗃️ <b>Niche:</b> {niche}\n"
            f"    - ✅ <b>Status:</b> {status}\n"
            f"    - 📈 <b>Growth:</b> {growth}\n\n"
            f"💵 <b>Monetization</b>\n"
            f"    - 💲 <b>Ads on Reels:</b> {_e(ads_r)}\n"
            f"    - 🎁 <b>Gifts (Reels):</b> {_e(gifts_r)}\n"
            f"    - 🕴 <b>Instagram Subscriptions:</b> {_e(ig_subs)}\n\n"
            f"⚙️ <b>FEATURES</b>\n"
            f"{feats_block}\n\n"
            f"💰 <b>PRICING</b>\n"
            f"    - 💵 <b>Price:</b> ${price}"
        )

    elif platform == 'Facebook':
        mon_ads  = extra_mon.get('Monetization Content Ads', 'N/A')
        stars    = extra_mon.get('Facebook Stars', 'N/A')
        fb_subs  = extra_mon.get('Facebook Subscriptions', 'N/A')
        collabs  = extra_mon.get('Facebook Brand Collabs', 'N/A')
        return (
            f"🟦 <b>NEW Facebook Page FOR SALE</b>{badge_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"- 🆔 <b>Account ID:</b> <code>{listing_id}</code>\n\n"
            f"📋 <b>BASIC INFO</b>\n"
            f"    - 📱 <b>Platform:</b> Facebook\n"
            f"    - 📅 <b>Account Age:</b> {channel_age}\n"
            f"    - 🌍 <b>Region/Audience:</b> {region}\n\n"
            f"📊 <b>STATISTICS</b>\n"
            f"    - 👥 <b>Followers:</b> {subscribers}\n"
            f"    - 👀 <b>Views:</b> {views}\n"
            f"    - 👍 <b>Engagement:</b> {likes}\n\n"
            f"⚙️ <b>Properties</b>\n"
            f"    - 🗃️ <b>Niche:</b> {niche}\n"
            f"    - ✅ <b>Status:</b> {status}\n"
            f"    - 📈 <b>Growth:</b> {growth}\n\n"
            f"💵 <b>Monetization</b>\n"
            f"    - 💲 <b>Monetization Content Ads:</b> {_e(mon_ads)}\n"
            f"    - 🎁 <b>Facebook Stars:</b> {_e(stars)}\n"
            f"    - 🕴 <b>Facebook Subscriptions:</b> {_e(fb_subs)}\n"
            f"    - 👥 <b>Facebook Brand Collabs:</b> {_e(collabs)}\n\n"
            f"⚙️ <b>FEATURES</b>\n"
            f"{feats_block}\n\n"
            f"💰 <b>PRICING</b>\n"
            f"    - 💵 <b>Price:</b> ${price}"
        )

    else:
        # Fallback for unknown platforms
        return (
            f"🎯 <b>NEW {_e(platform)} ACCOUNT FOR SALE</b>{badge_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"- 🆔 <b>Account ID:</b> <code>{listing_id}</code>\n\n"
            f"📋 <b>BASIC INFO</b>\n"
            f"    - 📱 <b>Platform:</b> {_e(platform)}\n"
            f"    - 📅 <b>Account Age:</b> {channel_age}\n"
            f"    - 🌍 <b>Region/Audience:</b> {region}\n\n"
            f"📊 <b>STATISTICS</b>\n"
            f"    - 👥 <b>Subscribers:</b> {subscribers}\n"
            f"    - 👀 <b>Views:</b> {views}\n\n"
            f"⚙️ <b>FEATURES</b>\n"
            f"{feats_block}\n\n"
            f"💰 <b>PRICING</b>\n"
            f"    - 💵 <b>Price:</b> ${price}"
        )


def get_details_template(platform):
    """Return the platform-specific details template to show the user."""
    if platform == 'YouTube':
        return (
            "📋 *Copy the template below, fill in your values, and send it back:*\n\n"
            "```\n"
            "Channel Age: 2006\n"
            "Region/Audience: USA\n\n"
            "Subscribers: 15,000\n"
            "Views: 250,000\n\n"
            "Niche: Gaming\n"
            "Status: No Strikes\n"
            "Growth: Organic\n\n"
            "Monetization: Enabled\n"
            "Advanced Features: Enabled\n\n"
            "Features:\n"
            "- Active\n"
            "- Original email\n"
            "- High Traffic\n"
            "```"
        )
    elif platform == 'TikTok':
        return (
            "📋 *Copy the template below, fill in your values, and send it back:*\n\n"
            "```\n"
            "Channel Age: 2006\n"
            "Region/Audience: USA\n\n"
            "Followers: 15,000\n"
            "Views: 250,000\n"
            "Likes: 50,000\n\n"
            "Niche: Gaming\n"
            "Status: No Strikes\n"
            "Growth: Organic\n\n"
            "Monetization: Enabled\n"
            "Creator Marketplace: Enabled\n"
            "Subscriptions & Gifts: Enabled\n"
            "Affiliate Marketing: Enabled\n\n"
            "Features:\n"
            "- Active\n"
            "- Original email\n"
            "- High Traffic\n"
            "```"
        )
    elif platform == 'Instagram':
        return (
            "📋 *Copy the template below, fill in your values, and send it back:*\n\n"
            "```\n"
            "Account Age: 2006\n"
            "Region/Audience: USA\n\n"
            "Followers: 15,000\n"
            "Views: 250,000\n"
            "Interactions: 50,000\n\n"
            "Niche: Gaming\n"
            "Status: No Strikes\n"
            "Growth: Organic\n\n"
            "Ads on Reels: Enabled\n"
            "Gifts (Reels): Enabled\n"
            "Instagram Subscriptions: Enabled\n\n"
            "Features:\n"
            "- Active\n"
            "- Original email\n"
            "- High Traffic\n"
            "```"
        )
    elif platform == 'Facebook':
        return (
            "📋 *Copy the template below, fill in your values, and send it back:*\n\n"
            "```\n"
            "Account Age: 2006\n"
            "Region/Audience: USA\n\n"
            "Followers: 15,000\n"
            "Views: 250,000\n"
            "Engagement: 50,000\n\n"
            "Niche: Gaming\n"
            "Status: No Strikes\n"
            "Growth: Organic\n\n"
            "Monetization Content Ads: Enabled\n"
            "Facebook Stars: Enabled\n"
            "Facebook Subscriptions: Enabled\n"
            "Facebook Brand Collabs: Enabled\n\n"
            "Features:\n"
            "- Active\n"
            "- Original email\n"
            "- High Traffic\n"
            "```"
        )
    else:
        return (
            "📋 *Copy the template below, fill in your values, and send it back:*\n\n"
            "```\n"
            "Account Age: 2006\n"
            "Region/Audience: USA\n\n"
            "Subscribers: 15,000\n"
            "Views: 250,000\n\n"
            "Niche: Gaming\n"
            "Status: No Strikes\n"
            "Growth: Organic\n\n"
            "Monetization: Enabled\n\n"
            "Features:\n"
            "- Active\n"
            "- Original email\n"
            "```"
        )


def parse_platform_details(platform, text):
    """Parse the user's filled-in template into a structured dict."""
    import json as _json

    details = {}
    extra_mon = {}
    features_lines = []
    in_features = False

    for line in text.split('\n'):
        line = line.strip()

        # Detect start of Features block
        if line.lower().startswith('features:') or line.lower() == 'features':
            in_features = True
            val_part = line.split(':', 1)[1].strip() if ':' in line else ''
            if val_part:
                features_lines.append(val_part)
            continue

        # Collect feature bullet lines
        if in_features:
            if line.startswith('-'):
                features_lines.append(line.lstrip('-').strip())
            elif ':' in line:
                # New key:value found — exit features mode
                in_features = False
            else:
                if line:
                    features_lines.append(line)
                continue

        if ':' not in line:
            continue

        key, value = [p.strip() for p in line.split(':', 1)]
        kl = key.lower()

        # Universal fields
        if 'age' in kl:
            details['channel_age'] = value
        elif 'region' in kl or 'audience' in kl:
            details['region'] = value
        elif kl in ('followers', 'subscribers'):
            try: details['subscribers'] = int(value.replace(',', ''))
            except: details['subscribers'] = value
        elif 'view' in kl:
            try: details['views'] = int(value.replace(',', ''))
            except: details['views'] = value
        elif 'like' in kl or 'interaction' in kl or 'engagement' in kl:
            try: details['likes'] = int(value.replace(',', ''))
            except: details['likes'] = value
        elif 'niche' in kl:
            details['niche'] = value
        elif 'status' in kl:
            details['status'] = value
        elif 'growth' in kl:
            details['growth'] = value

        # Platform-specific monetization fields
        elif platform == 'YouTube':
            if 'monetization' == kl:
                extra_mon['Monetization'] = value
            elif 'advanced' in kl:
                extra_mon['Advanced Features'] = value

        elif platform == 'TikTok':
            if 'monetization' == kl:
                extra_mon['Monetization'] = value
            elif 'creator' in kl and 'marketplace' in kl:
                extra_mon['Creator Marketplace'] = value
            elif 'subscription' in kl or 'gift' in kl:
                extra_mon['Subscriptions & Gifts'] = value
            elif 'affiliate' in kl:
                extra_mon['Affiliate Marketing'] = value

        elif platform == 'Instagram':
            if 'ads on reels' in kl or ('ads' in kl and 'reel' in kl):
                extra_mon['Ads on Reels'] = value
            elif 'gift' in kl:
                extra_mon['Gifts (Reels)'] = value
            elif 'instagram subscription' in kl or ('subscription' in kl and 'instagram' in kl):
                extra_mon['Instagram Subscriptions'] = value

        elif platform == 'Facebook':
            if 'monetization content ads' in kl or ('monetization' in kl and 'content' in kl):
                extra_mon['Monetization Content Ads'] = value
            elif 'stars' in kl:
                extra_mon['Facebook Stars'] = value
            elif 'facebook subscription' in kl or ('subscription' in kl and 'facebook' in kl):
                extra_mon['Facebook Subscriptions'] = value
            elif 'brand collabs' in kl or 'collabs' in kl:
                extra_mon['Facebook Brand Collabs'] = value

        else:
            if 'monetiz' in kl:
                extra_mon['Monetization'] = value

    if features_lines:
        details['features'] = '\n'.join(f"- {f}" for f in features_lines)

    details['extra_monetization'] = _json.dumps(extra_mon) if extra_mon else '{}'
    # Also store primary monetization for backward compat
    details['monetization'] = extra_mon.get('Monetization', extra_mon.get('Monetization Content Ads', 'N/A'))

    return details



def execute_bump_logic(listing_id, bot, ignore_cooldown=False):
    """Re-posts a listing to the top of the main channel and updates the DB."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM listings WHERE listing_id = ?", (listing_id,))
    listing = cursor.fetchone()
    conn.close()

    if not listing:
        logger.error(f"Bump failed: listing {listing_id} not found.")
        return False, "Listing not found."

    # Check cooldown
    if not ignore_cooldown and listing['last_bumped_at']:
        last_bump = datetime.strptime(listing['last_bumped_at'].split(".")[0], "%Y-%m-%d %H:%M:%S")
        delta = datetime.utcnow() - last_bump
        cooldown_days = get_user_bump_cooldown(row_get(listing, 'created_by'))
        allowed_seconds = cooldown_days * 86400
        if delta.total_seconds() < allowed_seconds:
            logger.warning(f"Bump rejected for {listing_id}: cooldown not expired.")
            remaining = allowed_seconds - delta.total_seconds()
            days = int(remaining // 86400)
            hours = int((remaining % 86400) // 3600)
            return False, f"Cooldown active. Try again in {days}d {hours}h."

    try:
        screenshots_str = listing['screenshots']
        if not screenshots_str:
            screenshots = []
        else:
            try:
                screenshots = json.loads(screenshots_str)
            except json.JSONDecodeError:
                # Fallback for old DB records
                screenshots = [s.strip() for s in screenshots_str.split(',') if s.strip()]
                
        has_screenshots = len(screenshots) > 0

        post_text = get_listing_post_text(listing)

        seller_id = row_get(listing, 'created_by')
        seller_name = get_seller_name(seller_id)
        seller_username = get_seller_username(seller_id)

        reply_markup = generate_buttons(
            listing_id=listing['listing_id'],
            seller_contact=row_get(listing, 'seller_contact'),
            stock_message_id=row_get(listing, 'stock_message_id'),
            seller_id=seller_id,
            seller_name=seller_name
        )

        caption_msg_id = None
        if has_screenshots:
            media_group = []
            for i, photo_id in enumerate(screenshots):
                if i == 0:
                    media_group.append(InputMediaPhoto(media=photo_id, caption=post_text, parse_mode='HTML'))
                else:
                    media_group.append(InputMediaPhoto(media=photo_id))
            messages = bot.send_media_group(chat_id=CHANNEL_ID, media=media_group, timeout=60)
            if messages:
                caption_msg_id = messages[0].message_id

            new_message = bot.send_message(
                chat_id=CHANNEL_ID,
                text=f"<b>🆔 Account ID:</b> <code>{listing['listing_id']}</code>",
                parse_mode='HTML',
                reply_markup=reply_markup,
                timeout=20
            )
        else:
            new_message = bot.send_message(
                chat_id=CHANNEL_ID,
                text=post_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
            caption_msg_id = new_message.message_id

        new_msg_id = new_message.message_id
        
        # Update button IDs
        old_ids = listing['channel_message_id'] or ''
        updated_ids = f"{old_ids},{new_msg_id}".strip(',')
        
        # Update caption IDs
        old_caption_ids = listing['screenshot_message_id'] or ''
        if caption_msg_id:
            updated_caption_ids = f"{old_caption_ids},{caption_msg_id}".strip(',')
        else:
            updated_caption_ids = old_caption_ids

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE listings SET channel_message_id = ?, screenshot_message_id = ?, last_bumped_at = CURRENT_TIMESTAMP WHERE listing_id = ?",
            (updated_ids, updated_caption_ids, listing_id)
        )
        conn.commit()
        conn.close()

        logger.info(f"Bump successful for {listing_id} -> new message ID: {new_msg_id}")
        return True, "Successfully bumped to the top!"

    except Exception as e:
        logger.error(f"Bump failed for {listing_id}: {e}")
        logger.error(traceback.format_exc())
        return False, "Internal error occurred."

def handle_bump_action(query, bot, listing_id, ignore_cooldown=False, as_alert=True):
    """Unified handler for executing bump logic and answering the callback query."""
    success, message = execute_bump_logic(listing_id, bot, ignore_cooldown)
    if as_alert:
        try:
            if success:
                query.answer(f"\U0001f680 {message}", show_alert=True)
            else:
                # Use edit instead of answer for cooldown messages to avoid Telegram char limits
                query.answer("\u274c Bump not available yet.", show_alert=False)
                query.edit_message_text(
                    f"\u23f3 **Bump Cooldown Active**\n\n{message}\n\n"
                    "Come back when the cooldown expires!",
                    parse_mode="Markdown",
                    reply_markup=query.message.reply_markup
                )
        except Exception as e:
            logger.error(f"handle_bump_action display error: {e}")
    else:
        if success:
            query.message.reply_text(f"\U0001f680 {message}")
        else:
            query.message.reply_text(f"\u274c {message}")
    return success



    
    
    # ===== EXISTING CUSTOMER FUNCTIONS =====
def customer_view_listings_menu(update, context):
    """Displays active inventory items registered directly under the caller's unique ID."""
    user_id = update.effective_user.id
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT listing_id, platform, price, last_bumped_at, bump_cooldown_days, status_flag 
        FROM listings WHERE created_by = ? AND status_flag = 'published'
        ORDER BY created_at DESC
    """, (user_id,))
    user_items = cursor.fetchall()
    conn.close()
    
    if not user_items:
        text = "📭 **You don't have any active listings on the platform currently.**"
        keyboard = [[InlineKeyboardButton("⬅️ Back to Menu", callback_data="customer_main")]]
        update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='MARKDOWN')
        return CUSTOMER_MENU

    text = "📋 **Your Registered Inventory Assets:**\nSelect an option below to manage optimization properties:"
    keyboard = []
    
    for item in user_items:
        # Calculate scheduling metrics via timestamp conversions
        available = True
        cooldown_msg = ""
        
        if item['last_bumped_at']:
            last_bump = datetime.strptime(item['last_bumped_at'].split(".")[0], "%Y-%m-%d %H:%M:%S")
            delta = datetime.utcnow() - last_bump
            cooldown_days = get_user_bump_cooldown(user_id)
            allowed_seconds = cooldown_days * 86400
            
            if delta.total_seconds() < allowed_seconds:
                available = False
                remaining = allowed_seconds - delta.total_seconds()
                days = int(remaining // 86400)
                hours = int((remaining % 86400) // 3600)
                cooldown_msg = f" (⏳ {days}d {hours}h)"

        bump_status_icon = "🟢" if available else "⏳"
        keyboard.append([
            InlineKeyboardButton(f"{item['listing_id']} - Manage Item", callback_data=f"manage_item_{item['listing_id']}"),
            InlineKeyboardButton(f"{bump_status_icon} Bump{cooldown_msg}", callback_data=f"bump_item_{item['listing_id']}")
        ])
        
    keyboard.append([InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="customer_main")])
    update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='MARKDOWN')
    return CUSTOMER_MANAGE_LISTINGS



def handle_customer_edit_input(update, context):
    new_value = update.message.text.strip()
    listing_id = context.user_data.get("targeted_id")
    field = context.user_data.get("edit_field")
    user_id = update.effective_user.id
    
    if not listing_id or not field:
        update.message.reply_text("❌ Error: Missing edit context.")
        return CUSTOMER_MENU
        
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO edit_requests (listing_id, field_name, new_value) VALUES (?, ?, ?)",
            (listing_id, field, new_value)
        )
        edit_req_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()
        
    text = (f"📝 **Listing Edit Request**\n\n"
            f"**Listing ID:** `{listing_id}`\n"
            f"**Field:** {field.title()}\n"
            f"**New Value:**\n{new_value}\n\n"
            f"Do you approve this change?")
    keyboard = [
        [InlineKeyboardButton("✅ Approve", callback_data=f"admin_approve_edit_{edit_req_id}"),
         InlineKeyboardButton("❌ Reject", callback_data=f"admin_reject_edit_{edit_req_id}")]
    ]
    context.bot.send_message(chat_id=OWNER_ID, text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    reply_kb = [[InlineKeyboardButton("🔙 Return to My Listings", callback_data="return_listings_view")]]
    update.message.reply_text(
        "✅ **Your edit request has been submitted successfully for approval!**\n\n"
        "You will be notified once it's reviewed.",
        reply_markup=InlineKeyboardMarkup(reply_kb),
        parse_mode="Markdown"
    )
    return CUSTOMER_MENU

def customer_manage_item_callback(update, context):
    query = update.callback_query
    query.answer()
    data = query.data
    
    # 1. Open the Action Menu
    if data.startswith("manage_item_"):
        listing_id = data.replace("manage_item_", "")
        context.user_data["targeted_id"] = listing_id
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status_flag FROM listings WHERE listing_id = ?", (listing_id,))
        live_item = cursor.fetchone()
        conn.close()
        
        # If it is a published live listing, show the tools
        if live_item and live_item['status_flag'] == 'published':
            text = f"⚙️ **Inventory Management Panel:** `[{listing_id}]` \n\nSelect an action below:"
            keyboard = [
                [InlineKeyboardButton("🆙 Bump to the Top", callback_data=f"bump_item_{listing_id}")],
                [InlineKeyboardButton("✏️ Edit Listing Details", callback_data=f"edit_listing_{listing_id}")],
                [InlineKeyboardButton("❌ Mark Asset As Sold (External)", callback_data="customer_trigger_sold")],
                [InlineKeyboardButton("🔙 Return to Listings", callback_data="return_listings_view")]
            ]
        else:
            # If it is still pending admin approval
            text = f"⏳ **Status View:** `[{listing_id}]`\n\nThis listing is currently Pending Admin Approval. It will be manageable once it goes live."
            keyboard = [[InlineKeyboardButton("🔙 Return to Listings", callback_data="return_listings_view")]]
            
        query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
        return CUSTOMER_MENU

    # 4. Edit Listing Menu
    elif data.startswith("edit_listing_"):
        listing_id = data.replace("edit_listing_", "")
        context.user_data["targeted_id"] = listing_id
        text = f"✏️ **Edit Listing:** `[{listing_id}]`\n\nWhich field would you like to edit?\n\n*Note: Any edits will require admin approval before going live.*"
        keyboard = [
            [InlineKeyboardButton("💰 Price", callback_data=f"edit_field_price"),
             InlineKeyboardButton("📝 Features", callback_data=f"edit_field_features")],
            [InlineKeyboardButton("📅 Channel Age", callback_data=f"edit_field_channel_age"),
             InlineKeyboardButton("🌍 Region", callback_data=f"edit_field_region")],
            [InlineKeyboardButton("👥 Subscribers", callback_data=f"edit_field_subscribers"),
             InlineKeyboardButton("👀 Views", callback_data=f"edit_field_views")],
            [InlineKeyboardButton("✅ Status", callback_data=f"edit_field_status"),
             InlineKeyboardButton("🗃️ Niche", callback_data=f"edit_field_niche")],
            [InlineKeyboardButton("💲 Monetization", callback_data=f"edit_field_monetization")],
            [InlineKeyboardButton("🔙 Cancel", callback_data=f"manage_item_{listing_id}")]
        ]
        query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
        return CUSTOMER_EDIT_FIELD

    # 5. Handle Field Selection
    elif data.startswith("edit_field_"):
        field = data.replace("edit_field_", "")
        context.user_data["edit_field"] = field
        listing_id = context.user_data.get("targeted_id")
        
        if field == "price":
            prompt = "💰 Please enter the new **Price** (in USD, numbers only):"
        elif field == "features":
            prompt = "📝 Please enter the new **Features and Description**.\n\n**Example:**\n*1. Monetized\n2. Organic Subs\n3. Gaming Niche*"
        elif field == "channel_age":
            prompt = "📅 Please enter the new **Channel Age** (e.g. 2018):"
        elif field == "region":
            prompt = "🌍 Please enter the new **Region** (e.g. USA, Global):"
        elif field == "subscribers":
            prompt = "👥 Please enter the new **Subscribers** count (e.g. 15000):"
        elif field == "views":
            prompt = "👀 Please enter the new **Views** count (e.g. 100000):"
        elif field == "status":
            prompt = "✅ Please enter the new **Status** (e.g. No Strikes):"
        elif field == "niche":
            prompt = "🗃️ Please enter the new **Niche** (e.g. Gaming, Crypto):"
        elif field == "monetization":
            prompt = "💲 Please enter the new **Monetization** status (e.g. Enabled, Disabled):"
        else:
            prompt = f"Please enter the new value for **{field.title()}**:"
            
        text = f"✏️ **Edit {field.title()}:** `[{listing_id}]`\n\n{prompt}"
        keyboard = [[InlineKeyboardButton("🔙 Cancel", callback_data=f"edit_listing_{listing_id}")]]
        query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
        return CUSTOMER_EDIT_INPUT
        
    elif data == "cancel_edit":
        return customer_manage_item_callback(update, context)

    # 2. Trigger the Bump Sequence
    elif data.startswith("bump_item_"):
        listing_id = data.replace("bump_item_", "")
        handle_bump_action(query, context.bot, listing_id, ignore_cooldown=False, as_alert=True)
        return CUSTOMER_MANAGE_LISTINGS

    # 3. Ask for Confirmation to Mark Sold
    elif data == "customer_trigger_sold":
        listing_id = context.user_data.get("targeted_id")
        text = f"⚠️ **CRITICAL WARNING:** Are you absolutely certain you want to mark `{listing_id}` as **SOLD**?\n\nThis permanently locks the active feed buttons and cannot be reversed."
        keyboard = [
            [InlineKeyboardButton("✅ Yes, Mark as Sold!", callback_data="customer_confirm_sold_execution")],
            [InlineKeyboardButton("❌ Cancel", callback_data="return_listings_view")]
        ]
        query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
        return CUSTOMER_MENU


def process_sold_state_modification(listing_id, bot, transaction_type="admin", escrow_log_url=None):
    """Iterates historically linked channel records to update structural states uniformly."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM listings WHERE listing_id = ?", (listing_id,))
    listing = cursor.fetchone()
    conn.close()
    
    if not listing:
        return False

    # 1. Structure Action Buttons conditionally
    if transaction_type == "admin" and escrow_log_url:
        sold_keyboard = [[InlineKeyboardButton("🤝 Sold via Escrow Service - View Proof", url=escrow_log_url)]]
    else:
        # Fallback for external user declarations (Unclickable status button)
        sold_keyboard = [[InlineKeyboardButton("🔄 Youtube Channel IS SOLD/Removed", callback_data="dead_button_trigger")]]
        
    reply_markup = InlineKeyboardMarkup(sold_keyboard)
    
    # 2. Update the Action Menu in the Main Channel (Does not break the photo album)
    if listing['channel_message_id']:
        msg_ids = [m.strip() for m in str(listing['channel_message_id']).split(',') if m.strip().isdigit()]
        for msg_id_str in msg_ids:
            try:
                bot.edit_message_text(
                    chat_id=CHANNEL_ID,
                    message_id=int(msg_id_str),
                    text=f"🔄 <b>STATUS UPDATE:</b> Channel <code>{listing_id}</code> Has Been Successfully SOLD.",
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"Failed cleaning main post instance {listing_id} at msg {msg_id_str}: {e}")

    # 3. (Stock channel sync removed — browsing now happens inside the bot)

    # 4. Commit status conversions permanently into active DB layers
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE listings SET status_flag = 'sold' WHERE listing_id = ?", (listing_id,))
    conn.commit()
    conn.close()
    
    return True
        

# --- CUSTOMER EXECUTION SWITCH ENTRYPOINT ---
def customer_confirm_sold_callback(update, context):
    """Processes user-initiated self-service termination logic maps."""
    query = update.callback_query
    query.answer()
    
    listing_id = context.user_data.get("targeted_id")
    
    # Fire processing adjustments down external pipelines
    if process_sold_state_modification(listing_id, context.bot, transaction_type="external"):
        query.edit_message_text(f"✅ **Listing `{listing_id}` has been successfully marked as sold and locked.**", parse_mode='MARKDOWN')
    else:
        query.edit_message_text("❌ **An error occurred preventing the listing from updating.**")
        
    return CUSTOMER_MENU
    
    


        
        
        
        
# ===== EXISTING ADMIN FUNCTIONS =====
# == BUTTON GENERATION ==

def get_latest_escrow_log_link():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT escrow_message_id FROM orders WHERE escrow_message_id IS NOT NULL ORDER BY id DESC LIMIT 1")
        res = cursor.fetchone()
        if res and res[0]:
            return f"https://t.me/Escrow_Log/{res[0]}"
        return "https://t.me/Escrow_Log"
    except Exception:
        return "https://t.me/Escrow_Log"
    finally:
        conn.close()

def generate_buttons(listing_id, seller_contact=None, stock_message_id=None, seller_id=None, seller_name="Seller", **kwargs):
    """Generates the unified button layout for main channel posts.
    Browsing now happens inside the bot instead of a separate stock channel."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    # --- URL VARIABLES ---
    ADMIN_URL = "https://t.me/smyards"          # Where "Contact Admin" goes
    BOT_USERNAME = "smyardbot"                  # The bot username for deep links
    # ---------------------------------------------------------------

    # Fetch seller stats
    badge = "Regular"
    rating = 0.0
    trades = 0
    if seller_id:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT badge_type, badge_expires_at FROM users WHERE telegram_id = ?", (seller_id,))
            res = cursor.fetchone()
            if res:
                badge_type, expires = res[0], res[1]
                if expires:
                    from datetime import datetime as _dt
                    if _dt.strptime(expires, '%Y-%m-%d %H:%M:%S') > _dt.now():
                        badge = badge_type
            
            cursor.execute("SELECT AVG(rating) FROM user_reviews WHERE target_user_id = ?", (seller_id,))
            res = cursor.fetchone()
            if res and res[0] is not None:
                rating = float(res[0])
                
            cursor.execute("SELECT COUNT(*) FROM orders WHERE seller_id = ? AND order_status = 'completed'", (seller_id,))
            res = cursor.fetchone()
            if res:
                trades = res[0]
        except Exception:
            pass
        finally:
            conn.close()
            
    # Clean seller_name by removing the word Support
    clean_seller_name = seller_name.replace(" Support", "").replace("Support", "").strip() if seller_name else "Seller"
    
    badge_icon = "👑 VIP" if badge == "VIP" else ("💎 Pro" if badge == "Pro" else "®️ Regular")
    rating_str = f"⭐ {rating:.1f} Rating" if rating > 0 else "⭐ New Rating"
    trades_str = f"🤝 {trades} Transactions"
    seller_btn_text = f"👤 {clean_seller_name} - {badge_icon} Seller - {rating_str} - {trades_str}"

    # Extract seller username for contact button
    seller_contact_username = ""
    if seller_contact:
        import urllib.parse
        seller_contact_username = seller_contact.split('/')[-1].replace('@', '').strip()
        # If it's malformed like "EliteTube Support", try to get it from db instead
        if " " in seller_contact_username and seller_id:
            conn = get_connection()
            try:
                cur = conn.cursor()
                cur.execute("SELECT customer_username FROM customer_listings WHERE customer_id = ? LIMIT 1", (seller_id,))
                res = cur.fetchone()
                if res and res[0]:
                    seller_contact_username = res[0]
            except:
                pass
            finally:
                conn.close()

    keyboard = [
        # Row 1 - Seller Info (wide)
        [
            InlineKeyboardButton(seller_btn_text, url=f"https://t.me/{BOT_USERNAME}?start=seller_{seller_id}" if seller_id else f"https://t.me/{BOT_USERNAME}?start=browse")
        ],
        # Row 2 - Buy + Contact Seller
        [
            InlineKeyboardButton(f"🛒 Buy This Account ({listing_id})", url=f"https://t.me/{BOT_USERNAME}?start=buy_{listing_id}"),
            InlineKeyboardButton(f"📞 Contact Seller", url=f"https://t.me/{seller_contact_username}" if seller_contact_username else f"https://t.me/{BOT_USERNAME}?start=browse")
        ],
        # Row 3 - Sell + About
        [
            InlineKeyboardButton("💵 Sell Your Account", url=f"https://t.me/{BOT_USERNAME}?start=sell"),
            InlineKeyboardButton("🛡 About US", url="https://t.me/smyard/3")
        ],
        # Row 4 - Market (wide)
        [
            InlineKeyboardButton("🏛 Accounts Market", url=f"https://t.me/{BOT_USERNAME}?start=browse")
        ],
        # Row 5 - Contact Admin + Help Center
        [
            InlineKeyboardButton("🕴 Contact Admin", url="https://t.me/smyards"),
            InlineKeyboardButton("📢 Help Center", url=f"https://t.me/{BOT_USERNAME}?start=help")
        ],
        # Row 6 - Transactions (wide)
        [
            InlineKeyboardButton("🤝 Successful Transactions | 👁️‍🗨️ Platform Reviews", url=get_latest_escrow_log_link())
        ],
    ]
    return InlineKeyboardMarkup(keyboard)
    
    
def publish_to_main_channel(listing, screenshots, bot):
    """Publish listing to main channel as an album with details in the caption and buttons below"""
    try:
        listing_id = row_get(listing, 'listing_id', 'N/A')
        post_text = get_listing_post_text(listing)

        # Send Media Group (Album)
        caption_message_id = None
        if screenshots and len(screenshots) > 0:
            media_group = []
            for i, photo_file_id in enumerate(screenshots):
                if i == 0:
                    media_group.append(InputMediaPhoto(media=photo_file_id, caption=post_text, parse_mode='HTML'))
                else:
                    media_group.append(InputMediaPhoto(media=photo_file_id))
            
            # The bot waits for the images to finish uploading
            messages = bot.send_media_group(chat_id=CHANNEL_ID, media=media_group, timeout=60)
            if messages:
                caption_message_id = messages[0].message_id
        else:
            msg = bot.send_message(chat_id=CHANNEL_ID, text=post_text, parse_mode='HTML', timeout=20)
            caption_message_id = msg.message_id

        seller_id = row_get(listing, 'seller_telegram_id') or row_get(listing, 'created_by')
        seller_name = get_seller_name(seller_id)
        seller_username = get_seller_username(seller_id)
        
        # Generate the full unified button set (Contact Seller, Contact Admin,
        # Place Order, Browse Listings, Sell, Feedback)
        reply_markup = generate_buttons(
            listing_id=listing_id,
            seller_contact=row_get(listing, 'seller_contact'),
            seller_id=seller_id,
            seller_name=seller_name
        )

        # Companion button message
        button_text = (
            f"<b>🆔 Account ID:</b> <code>{listing_id}</code>\n\n"
        )
        
        button_message = bot.send_message(
            chat_id=CHANNEL_ID,
            text=button_text,
            parse_mode='HTML',
            reply_markup=reply_markup,
            timeout=20
        )

        return caption_message_id, button_message.message_id
        
    except Exception as e:
        import traceback
        logger.error("Main channel publish failed: %s", e, exc_info=True)
        return None, None


def admin_button_callback(update, context):
    """Handle admin button callbacks - UPDATED WITH NEW ROUTING"""
    query = update.callback_query
    data = query.data
    # Skip default answer for bump actions so they can show custom alerts
    if not (data.startswith("admin_bump_listing_") or data.startswith("admin_run_bump_")):
        query.answer()
    
    # NEW ROUTING SECTION - Check these first
    if data == "admin_settings":
        return admin_settings(update, context)
    elif data == "admin_back_main":
        return admin_start(update, context)
    # Handle Edit Approvals
    elif data.startswith("admin_approve_edit_") or data.startswith("admin_reject_edit_"):
        action = "approve" if data.startswith("admin_approve_edit_") else "reject"
        req_id = data.replace(f"admin_{action}_edit_", "")
        
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM edit_requests WHERE id = ?", (req_id,))
            req = cursor.fetchone()
            
            if not req or req['status'] != 'pending':
                query.edit_message_text("❌ Request not found or already processed.")
                return MAIN_MENU
                
            listing_id = req['listing_id']
            field = req['field_name']
            new_value = req['new_value']
            
            if action == "approve":
                cursor.execute("UPDATE edit_requests SET status = 'approved' WHERE id = ?", (req_id,))
                
                # Sanitize field just to be safe, but they match schema directly
                allowed_fields = ['price', 'features', 'channel_age', 'region', 'subscribers', 'views', 'status', 'niche', 'monetization']
                db_field = field if field in allowed_fields else "features"
                
                cursor.execute(f"UPDATE listings SET {db_field} = ? WHERE listing_id = ?", (new_value, listing_id))
                
                cursor.execute("SELECT * FROM listings WHERE listing_id = ?", (listing_id,))
                listing = cursor.fetchone()
                conn.commit()

                # Parse the comma-separated channel_message_id (button posts)
                raw_ids = row_get(listing, 'channel_message_id', '') if listing else ''
                button_msg_ids = [mid.strip() for mid in str(raw_ids).split(',') if mid.strip()] if raw_ids else []
                
                # Parse the comma-separated screenshot_message_id (caption/text posts)
                raw_caption_ids = row_get(listing, 'screenshot_message_id', '') if listing else ''
                caption_msg_ids = [mid.strip() for mid in str(raw_caption_ids).split(',') if mid.strip()] if raw_caption_ids else []

                if listing and button_msg_ids:
                    post_text = get_listing_post_text(listing)
                    reply_markup = generate_buttons(
                        listing_id=listing_id,
                        seller_contact=row_get(listing, 'seller_contact'),
                        stock_message_id=row_get(listing, 'stock_message_id'),
                        seller_id=row_get(listing, 'created_by')
                    )

                    # Determine which caption IDs to update
                    target_caption_ids = list(caption_msg_ids)
                    if not target_caption_ids:
                        # Fallback for old posts before tracking was added
                        try:
                            import json
                            screenshots_raw = row_get(listing, 'screenshots') or '[]'
                            screenshots = json.loads(screenshots_raw)
                            num_screenshots = len(screenshots) if screenshots else 0
                            offset = max(num_screenshots, 1)
                            for b_id in button_msg_ids:
                                target_caption_ids.append(str(int(b_id) - offset))
                        except Exception:
                            pass

                    # 1. Update ALL caption/text posts
                    for cid in target_caption_ids:
                        try:
                            context.bot.edit_message_caption(
                                chat_id=CHANNEL_ID,
                                message_id=int(cid),
                                caption=post_text,
                                parse_mode='HTML'
                            )
                        except Exception as e1:
                            # Fallback if it's a text-only message (no photo)
                            try:
                                context.bot.edit_message_text(
                                    chat_id=CHANNEL_ID,
                                    message_id=int(cid),
                                    text=post_text,
                                    parse_mode='HTML'
                                )
                            except Exception:
                                pass

                    # 2. Update ONLY the buttons of the last companion post (resetting text back to short version)
                    last_id = button_msg_ids[-1]
                    companion_text = f"<b>🆔 Account ID:</b> <code>{listing_id}</code>"
                    try:
                        context.bot.edit_message_text(
                            chat_id=CHANNEL_ID,
                            message_id=int(last_id),
                            text=companion_text,
                            parse_mode='HTML',
                            reply_markup=reply_markup
                        )
                    except Exception as edit_err:
                        logger.warning(f"Edit approval (conv) channel button update failed for {listing_id}: {edit_err}")

                query.edit_message_text(f"✅ Edit approved. Listing `{listing_id}` updated on channel.")
                if listing:
                    try:
                        context.bot.send_message(chat_id=row_get(listing, 'created_by'), text=f"✅ Your edit request for listing `{listing_id}` ({field}) has been approved!")
                    except:
                        pass
            else:
                cursor.execute("UPDATE edit_requests SET status = 'rejected' WHERE id = ?", (req_id,))
                conn.commit()
                query.edit_message_text(f"❌ Edit request `{req_id}` rejected.")
                
                cursor.execute("SELECT created_by FROM listings WHERE listing_id = ?", (listing_id,))
                lst = cursor.fetchone()
                if lst:
                    try:
                        context.bot.send_message(chat_id=lst['created_by'], text=f"❌ Your edit request for listing `{listing_id}` ({field}) was rejected by the admin.")
                    except:
                        pass
        finally:
            conn.close()
        return MAIN_MENU

    elif data == "group_pool_status":
        return admin_group_pool_status(update, context)
    elif data == "admin_bump_settings":
        return admin_bump_settings(update, context)
    elif data.startswith("admin_bump_edit_"):
        return admin_bump_settings_edit(update, context)
    elif data == "reviews_management" or data.startswith("admin_reviews_page_"):
        return admin_reviews_management(update, context)
    elif data == "ap_dashboard":
        import auto_pilot
        auto_pilot.ap_dashboard(update, context)
        return ConversationHandler.END
    # ---- Auto Pilot pool/package/play callbacks ----
    # These are fired from auto_pilot messages while the admin ConversationHandler
    # is still active, so we must route them here to prevent the ConversationHandler
    # from swallowing them as "Unhandled".
    elif data.startswith("ap_pool_plat_") or data.startswith("ap_pool_page_"):
        import auto_pilot
        auto_pilot.ap_pool_list(update, context)
        return MAIN_MENU
    elif data.startswith("ap_view_pkg_"):
        import auto_pilot
        auto_pilot.ap_view_package(update, context)
        return MAIN_MENU
    elif data.startswith("ap_play1_"):
        import auto_pilot
        auto_pilot.ap_play_part_1(update, context)
        return MAIN_MENU
    elif data.startswith("ap_play2_"):
        import auto_pilot
        auto_pilot.ap_play_part_2(update, context)
        return MAIN_MENU
    elif data.startswith("ap_del_") and not data.startswith("ap_del_promo_") and not data.startswith("ap_del_guide_"):
        import auto_pilot
        auto_pilot.ap_delete_package(update, context)
        return MAIN_MENU
    elif data == "ap_add_new":
        import auto_pilot
        auto_pilot.ap_add_new(update, context)
        return MAIN_MENU
    elif data.startswith("ap_promo_pool_") or data.startswith("ap_guide_pool_"):
        import auto_pilot
        auto_pilot.ap_content_pool_list(update, context)
        return MAIN_MENU
    elif data.startswith("ap_view_promo_") or data.startswith("ap_view_guide_"):
        import auto_pilot
        auto_pilot.ap_view_content(update, context)
        return MAIN_MENU
    elif data.startswith("ap_publish_promo_") or data.startswith("ap_publish_guide_"):
        import auto_pilot
        auto_pilot.ap_publish_content(update, context)
        return MAIN_MENU
    elif data.startswith("ap_del_promo_") or data.startswith("ap_del_guide_"):
        import auto_pilot
        auto_pilot.ap_delete_content(update, context)
        return MAIN_MENU

    elif data == "admin_pre_pending_orders":
        return admin_pre_pending_orders_panel(update, context)
    elif data.startswith("del_review_"):
        return admin_delete_review(update, context)
    elif data.startswith("del_plat_rev_"):
        return admin_delete_platform_review(update, context)
    elif data.startswith("edit_plat_rev_") or data.startswith("edit_user_rev_"):
        return admin_prompt_edit_review(update, context)
    elif data == "admin_pending_menu":
        return admin_pending_menu(update, context)
    elif data == "admin_pending_edits" or data.startswith("admin_pending_edits_page_"):
        return admin_pending_edits(update, context)
    elif data.startswith("admin_view_pending_edit_"):
        return admin_view_pending_edit(update, context)
    elif data == "admin_pending_listings" or data.startswith("admin_pending_page_"):
        return admin_pending_listings(update, context)
    elif data.startswith("admin_reject_reason_"):
        return admin_reject_listing_prompt(update, context)
    elif data.startswith("admin_view_pending_"):
        return admin_view_pending_listing(update, context)
    elif data.startswith("approve_listing_"):
        approve_customer_listing(update, context)
        return admin_pending_listings(update, context)
    elif data.startswith("reject_listing_"):
        return admin_reject_listing_prompt(update, context)
    elif data == "admin_upgrades_mgmt":
        return admin_upgrades_management(update, context)
    elif data == "admin_assign_upgrade":
        return admin_assign_upgrade_start(update, context)
    elif data == "admin_upgrade_orders":
        return admin_upgrade_orders(update, context)
    elif data == "admin_pre_upgrade_orders":
        return admin_pre_upgrade_orders(update, context)
    
    # EXISTING ROUTING - Keep all the original logic
    if data == "new_listing":
        keyboard = []
        for platform in PLATFORMS:
            keyboard.append([InlineKeyboardButton(platform, callback_data=f"platform_{platform}")])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_back_main")])
        
        query.edit_message_text(
            text="Select Platform:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return CREATE_PLATFORM
    elif data.startswith("platform_"):
        platform = data.replace("platform_", "")
        context.user_data["listing"] = {"platform": platform}
        
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="back_platform")]]
        
        query.edit_message_text(
            text=f"Platform: {platform}\n\n🔗 **Enter Channel/Account Link:**\n_(e.g. https://youtube.com/@channel)_\n\nType 'skip' if not available.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return CREATE_TYPE
    
    elif data == "view_listings":
        return admin_view_listings(update, context)
        
    elif data.startswith("admin_hub_"):
        return admin_item_hub_callback(update, context)
        
    elif data.startswith("admin_run_"):
        return admin_hub_execution_callback(update, context)
    
    elif data == "back_main":
        return admin_start(update, context)
    
    elif data == "back_platform":
        keyboard = []
        for platform in PLATFORMS:
            keyboard.append([InlineKeyboardButton(platform, callback_data=f"platform_{platform}")])
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back_main")])
        
        query.edit_message_text(
            text="Select Platform:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return CREATE_PLATFORM
    
    elif data == "add_screenshots":
        context.user_data["screenshots"] = []
        query.edit_message_text(
            text=f"📸 Send up to {MAX_SCREENSHOTS} screenshots\n\n"
            f"• Send photos one by one\n"
            f"• Maximum: {MAX_SCREENSHOTS} screenshots\n"
            f"• Type 'done' when finished\n"
            f"• Type 'cancel' to abort\n\n"
            f"Ready for screenshot 1:"
        )
        return SCREENSHOT_UPLOAD
    
    elif data == "skip_screenshots":
        context.user_data["screenshots"] = []
        return admin_show_final_preview(update, context)
    
    elif data == "back_to_price":
        query.edit_message_text("💰 Enter Price (USD):\n\nExample: 150\n\nType 'cancel' to abort.")
        return CREATE_PRICE
    
    elif data == "back_to_seller_contact":
        query.edit_message_text(
            "📞 Enter Seller Contact Link:\n\n"
            "Examples:\n• https://t.me/username\n• https://wa.me/1234567890\n\n"
            "Type 'skip' to leave blank, 'cancel' to abort."
        )
        return CREATE_SELLER_CONTACT
    
    elif data in ["save_draft", "publish_now", "edit_again", "cancel_create"]:
        return admin_handle_confirmation(update, context)

    elif data.startswith("payment_"):
        return admin_handle_payment_method(update, context)
    
    elif data == "cancel_sale":
        query.edit_message_text("❌ Sale marking cancelled.")
        return admin_start(update, context)
		
    elif data == "admin_orders_panel":
        return admin_orders_panel(update, context)
    
    elif data.startswith("admin_order_"):
        return admin_view_order_detail(update, context)
    
    elif data.startswith("confirm_order_payment_"):
        query.answer("Payment confirmation feature coming in Stage 2", show_alert=True)
        return MAIN_MENU
    
    elif data.startswith("add_group_link_"):
        return admin_add_group_link(update, context)
    
    elif data.startswith("mark_completed_"):
        return admin_mark_order_completed(update, context)
    
    elif data.startswith("admin_delete_order_"):
        return admin_delete_prepending_order(update, context)
    
    elif data.startswith("admin_listings_page_"):
        return admin_view_listings(update, context)
        
    elif data.startswith("admin_platform_"):
        return admin_view_listings(update, context)
    elif data.startswith("admin_manage_listing_"):
        return admin_manage_listing(update, context)
    elif data.startswith("admin_bump_listing_"):
        listing_id = int(data.replace("admin_bump_listing_", ""))
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT listing_id FROM listings WHERE id = ?", (listing_id,))
        result = cursor.fetchone()
        conn.close()
        if result:
            handle_bump_action(query, context.bot, result[0], ignore_cooldown=True, as_alert=True)
        else:
            query.answer("❌ Listing not found", show_alert=True)
        return admin_view_listings(update, context)
    elif data.startswith("admin_mark_sold_listing_"):
        db_id = int(data.replace("admin_mark_sold_listing_", ""))
        # Fetch the real string listing_id (e.g. YT-236) from the DB
        _conn = get_connection()
        _row = _conn.execute("SELECT listing_id FROM listings WHERE id = ?", (db_id,)).fetchone()
        _conn.close()
        real_listing_id = _row[0] if _row else str(db_id)
        context.user_data['admin_marking_sold_id'] = real_listing_id
        
        query.edit_message_text(
            f"📝 <b>Mark Listing as SOLD</b>\n\n"
            f"Listing: <code>{real_listing_id}</code>\n\n"
            "Please enter the <b>seller name</b> (for privacy, only first part will be shown):\n\n"
            "Type 'cancel' to abort.",
            parse_mode=ParseMode.HTML
        )
        return ADMIN_MARK_SOLD
    elif data.startswith("admin_delete_listing_"):
        return admin_delete_listing(update, context)
    elif data == "confirm_delete_listing":
        return confirm_delete_listing(update, context)
    elif data == "admin_view_listings_reset":
        return admin_view_listings_reset(update, context)
        
    # --- REVIEW CALLBACKS (handled here so ConversationHandler doesn't silently swallow them for admins) ---\nelif data.startswith('rate_plat_') or data.startswith('rate_user_'):'rate_plat_') or data.startswith('rate_user_'):

        return handle_review_rating(update, context)
    elif data.startswith('rvcmt_'):
        return handle_review_comment_preset(update, context)
    elif data.startswith('rv_write_'):
        return handle_review_write_prompt(update, context)
    
    # If no match found, stay in main menu
    return MAIN_MENU


    
def admin_handle_confirmation(update, context):
    """Handle confirmation callbacks - SIMPLIFIED WORKING VERSION"""
    query = update.callback_query
    query.answer()
    data = query.data
    
    logger.info(f"✅ Confirmation callback received: {data}")
    
    if data == "save_draft":
        # Save as draft
        listing = context.user_data["listing"]
        screenshots = context.user_data.get("screenshots", [])
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO listings (
                listing_id, platform, account_type, channel_age, price, seller_contact, 
                status_flag, created_by, seller_telegram_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            listing.get('listing_id'),
            listing.get('platform'),
            listing.get('account_type', 'N/A'),
            listing.get('channel_age', 'N/A'),
            listing.get('price'),
            listing.get('seller_contact'),
            'draft',
            update.effective_user.id,
            update.effective_user.id
        ))
        conn.commit()
        conn.close()
        
        query.edit_message_text(f"✅ Saved as draft: {listing.get('listing_id')}")
        return admin_start(update, context)
    
    elif data == "publish_now":
        logger.info("🟢 PUBLISH NOW clicked - Starting clean unified publish process")
        
        # 1. Gather listing data from context
        listing = context.user_data.get("listing")
        screenshots = context.user_data.get("screenshots", [])
        
        if not listing:
            query.edit_message_text("❌ Error: Listing data not found in session.")
            return
            
        try:
            # 2. Post ONE unified album post to the MAIN CHANNEL
            logger.info("➡️ Step 1: Posting album to main channel...")
            
            caption_msg_id, main_message_id = publish_to_main_channel(
                listing=listing, 
                screenshots=screenshots, 
                bot=context.bot
            )
            
            if not main_message_id:
                raise Exception("Main channel posting failed.")
            
            # 3. Stock channel posting deprecated — browsing now happens in-bot
            stock_message_id = None  # admin_create_stock_post removed (deprecated)
            
            # 4. Save the exact message references into the Database
            logger.info("➡️ Step 3: Saving to database...")
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO listings (
                    listing_id, platform, account_type, channel_age, subscribers, views,
                    niche, features, monetization, region, status, price,
                    screenshots, seller_contact, status_flag, channel_message_id, 
                    screenshot_message_id, stock_message_id, created_by, seller_telegram_id,
                    growth, likes, extra_monetization
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                listing.get('listing_id'), listing.get('platform'), listing.get('account_type', 'N/A'),
                listing.get('channel_age', 'N/A'),
                listing.get('subscribers', 0), listing.get('views', 0),
                listing.get('niche', 'Mixed'), listing.get('features', 'N/A'),
                listing.get('monetization', 'N/A'), listing.get('region', 'N/A'),
                listing.get('status', 'No Strikes'), listing.get('price'),
                json.dumps(screenshots), listing.get('seller_contact'), 'published',
                str(main_message_id), str(caption_msg_id) if caption_msg_id else None, str(stock_message_id) if stock_message_id else None,
                update.effective_user.id,
                listing.get('seller_telegram_id', update.effective_user.id),
                listing.get('growth', ''),
                listing.get('likes', 0),
                listing.get('extra_monetization', '{}')
            ))
            conn.commit()
            conn.close()
            
            # Send confirmation UI to admin panel
            success_msg = f"✅ **PUBLISHED SUCCESSFULLY!**\n\n🆔 ID: `{listing.get('listing_id')}`\n📱 Platform: {listing.get('platform')}\n🛍 Now visible in the in-bot browse menu!"
            query.edit_message_text(success_msg, parse_mode='MARKDOWN')
            logger.info("✅ Finished execution sequence smoothly.")
            
        except Exception as e:
            logger.error(f"❌ Error during execution flow: {e}")
            import traceback
            logger.error(traceback.format_exc())
            query.edit_message_text(f"❌ Error during publishing: {str(e)[:100]}")
        
        # Clean session memory state
        context.user_data.clear()
        return admin_start(update, context)
    elif data == "edit_again":
        query.edit_message_text("✏️ Send corrected details:")
        return CREATE_DETAILS
    
    elif data == "cancel_create":
        query.edit_message_text("❌ Creation cancelled.")
        context.user_data.clear()
        return admin_start(update, context)
    
    return MAIN_MENU

def clean_number_input(value):
    """Clean number input from user"""
    if not value:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    value_str = str(value)
    cleaned = ''.join(char for char in value_str if char.isdigit())
    if cleaned:
        return int(cleaned)
    return 0

def admin_handle_channel_age(update, context):
    """Handles the channel/account link, then sends the platform-specific details template."""
    text = update.message.text.strip()
    context.user_data["listing"]["channel_link"] = "" if text.lower() == 'skip' else text
    context.user_data["listing"]['account_type'] = 'N/A'
    
    platform = context.user_data['listing'].get('platform', 'YouTube')
    template = get_details_template(platform)
    
    update.message.reply_text(
        f"\U0001f4f1 *Platform:* {platform}\n\n{template}\n\n"
        f"Fill in your values and send it back. Type 'cancel' to abort.",
        parse_mode='Markdown'
    )
    return CREATE_DETAILS

def admin_handle_details(update, context):
    """Handle listing details input — uses per-platform template parser."""
    text = update.message.text
    
    if text.lower() == 'cancel':
        update.message.reply_text("\u274c Creation cancelled.")
        return admin_start(update, context)
    
    listing = context.user_data.get("listing", {})
    platform = listing.get('platform', 'YouTube')
    
    details = parse_platform_details(platform, text)
    
    if not details.get('channel_age') and not details.get('subscribers'):
        update.message.reply_text(
            "\u26a0\ufe0f Please fill in the template properly.\n\n"
            "Make sure you copy the template, fill in the values, and send it back.\n"
            "Type 'cancel' to abort."
        )
        return CREATE_DETAILS
    
    context.user_data["listing"].update(details)
    
    update.message.reply_text("💰 Enter Price (USD):\n\nExample: 150\n\nType 'cancel' to abort.")
    return CREATE_PRICE

def admin_handle_price(update, context):
    """Handle price input and generate sequential listing ID"""
    text = update.message.text
    
    if text.lower() == 'cancel':
        update.message.reply_text("❌ Creation cancelled.")
        return admin_start(update, context)
    
    try:
        price = float(text)
        context.user_data["listing"]["price"] = price
        
        platform = context.user_data["listing"]["platform"]
        
        # Custom platform codes
        platform_codes = {
            'YouTube': 'YT',
            'TikTok': 'TT', 
            'Instagram': 'IG',
            'Facebook': 'FB'
        }
        
        platform_code = platform_codes.get(platform, platform[:2].upper())
        
        conn = get_connection()
        cursor = conn.cursor()
        
        # Find the highest existing number across BOTH tables to avoid collisions with pending customer listings
        cursor.execute("SELECT listing_id FROM listings WHERE listing_id LIKE ?", (f"{platform_code}-%",))
        existing_main = [r[0] for r in cursor.fetchall()]
        cursor.execute("SELECT listing_id FROM customer_listings WHERE listing_id LIKE ?", (f"{platform_code}-%",))
        existing_customer = [r[0] for r in cursor.fetchall()]
        max_num = 0
        for eid in existing_main + existing_customer:
            parts = eid.split('-')
            if len(parts) == 2 and parts[1].isdigit():
                max_num = max(max_num, int(parts[1]))
        listing_id = f"{platform_code}-{max_num + 1:03d}"
        logger.info(f"Generated listing ID: {listing_id}")
        
        conn.close()
        
        context.user_data["listing"]["listing_id"] = listing_id
        
        update.message.reply_text(
            f"✅ Generated Account ID: **{listing_id}**\n\n"
            "📞 Enter Seller Contact Link:\n\n"
            "This link will be shown in the 'Contact Seller' button.\n"
            "Examples:\n"
            "• https://t.me/username (Telegram)\n"
            "• https://wa.me/1234567890 (WhatsApp)\n"
            "• https://example.com/contact\n\n"
            "Type 'skip' to leave blank, 'cancel' to abort.",
            parse_mode='MARKDOWN'
        )
        return CREATE_SELLER_CONTACT
        
    except ValueError:
        update.message.reply_text("❌ Invalid price. Enter a number (e.g., 150):")
        return CREATE_PRICE
    except Exception as e:
        logger.error(f"Error in admin_handle_price: {e}")
        update.message.reply_text("❌ Error generating listing ID. Please try again.")
        return CREATE_PRICE

def admin_handle_seller_contact(update, context):
    """Handle seller contact input, then ask for seller Telegram ID."""
    text = update.message.text.strip()
    
    if text.lower() == 'cancel':
        update.message.reply_text("❌ Creation cancelled.")
        return admin_start(update, context)
    
    if text.lower() == 'skip':
        context.user_data["listing"]["seller_contact"] = None
    else:
        context.user_data["listing"]["seller_contact"] = text
    
    # Now ask for the seller's Telegram ID
    update.message.reply_text(
        "\U0001f511 **Enter Seller Telegram ID:**\n\n"
        "This is the seller's numeric Telegram user ID (not username).\n"

        "Example: `6407498844`\n\n"
        "Used to link the listing to the seller's profile.\n"
        "Type 'skip' to use your own ID, 'cancel' to abort.",
        parse_mode='MARKDOWN'
    )
    return ENTER_PRODUCT_ID

def admin_handle_seller_tg_id(update, context):
    """Handle seller Telegram ID input for new listing, then show screenshot prompt."""
    # Only handle this if we're in the listing creation flow
    if 'listing' not in context.user_data:

        return MAIN_MENU

    text = update.message.text.strip()
    
    if text.lower() == 'cancel':
        update.message.reply_text("❌ Creation cancelled.")
        context.user_data.clear()
        return admin_start(update, context)
    
    if text.lower() == 'skip':
        context.user_data["listing"]["seller_telegram_id"] = update.effective_user.id
    else:
        try:
            context.user_data["listing"]["seller_telegram_id"] = int(text)
        except ValueError:
            update.message.reply_text("❌ Invalid Telegram ID. Please enter a numeric ID or type 'skip'.")
            return ENTER_PRODUCT_ID
    
    # Now ask for seller display name
    update.message.reply_text(
        "✏️ *Enter Seller Display Name:*\n\n"
        "This name will appear on the seller profile button.\n"
        "Example: `Drama God`, `SubMarket`\n\n"
        "Type 'skip' to use their Telegram username instead.",
        parse_mode='MARKDOWN'
    )
    return ENTER_SELLER_NAME

def admin_handle_seller_display_name(update, context):
    """Handle seller display name input, save to users table, then show screenshot prompt."""
    if 'listing' not in context.user_data:
        return MAIN_MENU

    text = update.message.text.strip()

    if text.lower() == 'cancel':
        update.message.reply_text("❌ Creation cancelled.")
        context.user_data.clear()
        return admin_start(update, context)

    seller_tg_id = context.user_data["listing"].get("seller_telegram_id")
    display_name = None if text.lower() == 'skip' else text

    if seller_tg_id and display_name:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (telegram_id, display_name)
                VALUES (?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET display_name = excluded.display_name
            """, (seller_tg_id, display_name))
            conn.commit()
            conn.close()
            logger.info(f"✅ Saved seller display name '{display_name}' for TG ID {seller_tg_id}")
        except Exception as e:
            logger.error(f"Failed to save seller display name: {e}")

    # Now show screenshot prompt
    keyboard = [
        [InlineKeyboardButton("📸 Yes, add screenshots", callback_data="add_screenshots")],
        [InlineKeyboardButton("⏭️ No, skip for now", callback_data="skip_screenshots")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_seller_contact")]
    ]

    update.message.reply_text(
        "📸 Add Screenshots?\n\n"
        f"You can add up to {MAX_SCREENSHOTS} screenshots of the account.\n"
        "Customers will see them when they click the 'Screenshots' button.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SCREENSHOT_ASK
    
def admin_handle_screenshot_upload(update, context):
    """Handle screenshot photo uploads"""
    if 'screenshots' not in context.user_data:
        context.user_data['screenshots'] = []
    
    if update.message.photo:
        photo = update.message.photo[-1]
        context.user_data['screenshots'].append(photo.file_id)
        
        count = len(context.user_data['screenshots'])
        
        if count >= MAX_SCREENSHOTS:
            update.message.reply_text(f"✅ Maximum {MAX_SCREENSHOTS} screenshots reached!")
            return admin_show_final_preview(update, context)
        else:
            update.message.reply_text(
                f"📸 Screenshot {count} received!\n"
                f"Send another photo or type 'done' to finish."
            )
    elif update.message.text:
        text = update.message.text.lower()
        if text == 'done':
            return admin_show_final_preview(update, context)
        elif text == 'cancel':
            update.message.reply_text("❌ Creation cancelled.")
            return admin_start(update, context)
        else:
            update.message.reply_text("Please send photos or type 'done' to finish.")
    
    return SCREENSHOT_UPLOAD


def admin_handle_txid(update, context):
    """Handle TXid input"""
    txid = update.message.text.strip()
    
    if txid.lower() == 'cancel':
        update.message.reply_text("❌ Cancelled.")
        return admin_start(update, context)
    
    context.user_data["sold_listing"]["txid"] = txid
    
    # Show payment method options
    keyboard = [
        [InlineKeyboardButton("💳 Crypto (ETH)", callback_data="payment_eth")],
        [InlineKeyboardButton("₿ Crypto (BTC)", callback_data="payment_btc")],
        [InlineKeyboardButton("💵 Crypto (USDT)", callback_data="payment_usdt")],
        [InlineKeyboardButton("💸 PayPal", callback_data="payment_paypal")],
        [InlineKeyboardButton("🏦 Bank Transfer", callback_data="payment_bank")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_sale")]
    ]
    
    update.message.reply_text(
        "💳 Select Payment Method:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ENTER_PAYMENT_METHOD

def admin_handle_payment_method(update, context):
    """Handle payment method selection - FIXED: Now asks for order number"""
    query = update.callback_query
    query.answer()
    data = query.data
    
    if data == "cancel_sale":
        query.edit_message_text("❌ Sale marking cancelled.")
        return admin_start(update, context)
    
    # Map callback data to display names
    payment_methods = {
        "payment_eth": "Crypto (ETH)",
        "payment_btc": "Crypto (BTC)",
        "payment_usdt": "Crypto (USDT)",
        "payment_paypal": "PayPal",
        "payment_bank": "Bank Transfer"
    }
    
    payment_method = payment_methods.get(data, "Crypto (ETH)")
    context.user_data["sold_listing"]["payment_method"] = payment_method
    
    # Ask for order number instead of completing sale
    query.edit_message_text(
        f"💳 Payment Method: {payment_method}\n\n"
        f"📝 Enter Order Number:\n\n"
        f"Example: YT#1059, IG#1258, FB#1236, TT#1025\n\n"
        f"This order number will be shown in the escrow log post.\n\n"
        f"Type 'cancel' to abort."
    )
    
    # Set order_number to None initially
    context.user_data["sold_listing"]["order_number"] = None
    
    # Now we need to handle the order number input
    return ENTER_ORDER_NUMBER

def admin_handle_order_number(update, context):
    """Handle order number input - NEW FUNCTION"""
    order_number = update.message.text.strip().upper()
    
    if order_number.lower() == 'cancel':
        update.message.reply_text("❌ Cancelled.")
        return admin_start(update, context)
    
    # Validate order number format
    if not any(prefix in order_number for prefix in ['YT#', 'IG#', 'FB#', 'TT#']):
        update.message.reply_text(
            "❌ Invalid order number format.\n"
            "Must be: YT#xxxx, IG#xxxx, FB#xxxx, or TT#xxxx\n\n"
            "Please enter a valid order number or type 'cancel':"
        )
        return ENTER_ORDER_NUMBER
    
    context.user_data["sold_listing"]["order_number"] = order_number
    
    # Complete the sale
    return admin_complete_sale(update, context)

def admin_complete_sale(update, context):
    """Complete the sale marking process"""
    query = None
    if update.callback_query:
        query = update.callback_query
        query.answer()
    
    sold_data = context.user_data.get("sold_listing", {})
    
    if not sold_data:
        if query:
            query.edit_message_text("❌ Error: Sale data missing.")
        else:
            update.message.reply_text("❌ Error: Sale data missing.")
        return admin_start(update, context)
    
    try:
        # Since these functions were undefined, we'll just update the main post and skip escrow/stock logs
        escrow_message_id = 0
        main_updated = admin_update_main_post_as_sold(sold_data, context.bot, escrow_message_id)
        stock_updated = False
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE listings SET status_flag = 'sold' WHERE listing_id = ?",
            (sold_data["listing_id"],)
        )
        conn.commit()
        conn.close()
        
        # Build success message
        success_msg = f"✅ Successfully marked as SOLD!\n\n"
        success_msg += f"🆔 Product: {sold_data['listing_id']}\n"
        success_msg += f"🛍 Order #: {sold_data.get('order_number', 'N/A')}\n"
        success_msg += f"💰 Price: ${sold_data['price']}\n"
        success_msg += f"💳 Payment: {sold_data['payment_method']}\n\n"
        success_msg += f"📝 Escrow log: ✅ Posted\n"
        
        if query:
            query.edit_message_text(success_msg)
        else:
            update.message.reply_text(success_msg)
    except Exception as e:
        if query:
            query.edit_message_text(f"❌ Error completing sale: {e}")
        else:
            update.message.reply_text(f"❌ Error completing sale: {e}")
            
    return admin_start(update, context)

# admin_mark_sold_with_transaction - asks for seller/buyer names
def admin_handle_sold_seller_name(update, context):
    """Handle seller name input for transaction logging."""
    text = update.message.text.strip()
    
    if text.lower() == 'cancel':
        update.message.reply_text("❌ Cancelled.")
        return MAIN_MENU
    
    context.user_data['tx_seller_name'] = text
    
    update.message.reply_text(
        "👤 <b>Enter Buyer Name:</b>\n\n"
        "Example: John, Alice, etc.\n\n"
        "Type 'cancel' to abort.",
        parse_mode=ParseMode.HTML
    )
    return ADMIN_MARK_SOLD  # Keep routing correctly

# admin_handle_sold_buyer_name
def admin_handle_sold_buyer_name(update, context):
    """Handle buyer name input for transaction logging."""
    text = update.message.text.strip()
    
    if text.lower() == 'cancel':
        update.message.reply_text("❌ Cancelled.")
        return MAIN_MENU
    
    context.user_data['tx_buyer_name'] = text
    
    update.message.reply_text(
        "📝 <b>Enter Transaction ID (TXid):</b>\n\n"
        "This should be a blockchain transaction link or ID.\n"
        "Example: https://etherscan.io/tx/0x123abc...\n\n"
        "Type 'skip' if no TXid, or 'cancel' to abort.",
        parse_mode=ParseMode.HTML
    )
    return ADMIN_MARK_SOLD

# Updated ENTER_TXID handler to save transaction log
def admin_handle_txid_with_transaction_log(update, context):
    """Handle TXid and save to transaction log."""
    txid = update.message.text.strip()
    
    if txid.lower() == 'cancel':
        update.message.reply_text("❌ Cancelled.")
        context.user_data.pop('tx_seller_name', None)
        context.user_data.pop('tx_buyer_name', None)
        return MAIN_MENU
    
    if txid.lower() == 'skip':
        txid = None
    
    listing_id = context.user_data.get('admin_marking_sold_id')
    seller_name = context.user_data.get('tx_seller_name', 'Unknown')
    buyer_name = context.user_data.get('tx_buyer_name', 'Unknown')
    
    conn = get_connection()
    cursor = conn.cursor()
    # Use listing_id (like YT-236) not internal id; also fetch seller_contact for name
    cursor.execute("SELECT listing_id, platform, price, channel_message_id, seller_contact FROM listings WHERE listing_id = ?", (listing_id,))
    listing = cursor.fetchone()
    
    if listing:
        l_id, platform, price, channel_msg_id, seller_contact = listing
        
        # Generate proper sequential order number matching the escrow format
        order_num = generate_order_number(platform)
        
        # Build main post URL for the "View Account Info" button on Post 1
        main_post_url = None
        if channel_msg_id:
            first_id = str(channel_msg_id).split(',')[0].strip()
            if first_id.lower() != 'none' and first_id.isdigit():
                main_post_url = helper_get_tg_url(CHANNEL_ID, first_id)
        
        # Post to Escrow_Log_Channel FIRST — returns (post1_id for SOLD link, post2_id for review edits)
        escrow_post1_id, escrow_msg_id = post_escrow_completion(
            context.bot, order_num, l_id, platform,
            seller_name, buyer_name, price, txid, main_post_url
        )
        
        # Insert transaction log entry INCLUDING escrow_message_id (post2 id)
        # so update_escrow_post_with_review can find and update the reviews post later
        cursor.execute("""
            INSERT INTO transactions_log 
            (order_number, product_id, platform, seller_name, buyer_name, price, payment_method, txid, status, escrow_message_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?)
        """, (order_num, l_id, platform, seller_name, buyer_name, price, None, txid, escrow_msg_id))
        
        # Mark listing as sold
        cursor.execute("UPDATE listings SET status_flag = 'sold' WHERE listing_id = ?", (l_id,))
        conn.commit()
        conn.close()
        
        # Edit main channel post to show as SOLD (links to Post 1 — the static info post)
        sold_data = {
            'listing_id': l_id,
            'channel_message_id': channel_msg_id,
            'order_number': order_num,
            'price': price,
            'payment_method': 'N/A'
        }
        admin_update_main_post_as_sold(sold_data, context.bot, escrow_post1_id or 0)
        
        update.message.reply_text(
            f"✅ <b>Transaction Logged &amp; Listing Marked Sold!</b>\n\n"
            f"Order: <code>{order_num}</code>\n"
            f"Product: <code>{l_id}</code>\n"
            f"Seller: {seller_name}\n"
            f"Buyer: {buyer_name}\n"
            f"Amount: ${price:,.2f}\n\n"
            f"📣 Escrow_Log_Channel post: {'✅ Posted' if escrow_msg_id else '❌ Failed'}\n"
            f"📝 Main channel post: updated to SOLD.",
            parse_mode=ParseMode.HTML
        )
    else:
        conn.close()
        update.message.reply_text("❌ Listing not found. Make sure you used the correct Listing ID (e.g. YT-236).")
    
    # Clean up
    context.user_data.pop('admin_marking_sold_id', None)
    context.user_data.pop('tx_seller_name', None)
    context.user_data.pop('tx_buyer_name', None)
    
    return MAIN_MENU

# Update admin_button_callback to route new states
def route_admin_mark_sold_flow(update, context):
    """Route admin mark sold to transaction logging flow."""
    if update.message and update.message.text:
        text = update.message.text.strip()
        
        if 'tx_seller_name' not in context.user_data:
            return admin_handle_sold_seller_name(update, context)
        elif 'tx_buyer_name' not in context.user_data:
            return admin_handle_sold_buyer_name(update, context)
        else:
            return admin_handle_txid_with_transaction_log(update, context)
    
    return MAIN_MENU


def helper_get_tg_url(channel_id, message_id):
    """Helper to cleanly format Telegram links for both public and private channels"""
    ch_str = str(channel_id).strip()
    if ch_str.startswith('-100'):
        return f"https://t.me/c/{ch_str[4:]}/{message_id}"
    elif ch_str.startswith('@'):
        return f"https://t.me/{ch_str[1:]}/{message_id}"
    return f"https://t.me/{ch_str}/{message_id}"

def admin_show_final_preview(update, context):
    """Show final preview before saving"""
    listing = context.user_data["listing"]
    screenshots = context.user_data.get("screenshots", [])
    
    preview = admin_format_preview(listing, len(screenshots))
    
    keyboard = [
        [InlineKeyboardButton("✅ Save as Draft", callback_data="save_draft")],
        [InlineKeyboardButton("▶️ Publish Now", callback_data="publish_now")],
        [InlineKeyboardButton("✏️ Edit Again", callback_data="edit_again")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_create")]
    ]
    
    # Safe fallback if triggered from a CallbackQuery instead of a text message
    send_msg = update.message.reply_text if update.message else update.callback_query.message.reply_text
    
    send_msg(
        preview,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )
    return CREATE_CONFIRM

def admin_format_preview(listing, screenshot_count=0):
    """Format listing for preview with Emoji-Based Sections"""
    screenshot_info = f"📸 Screenshots: {screenshot_count} uploaded" if screenshot_count > 0 else "📸 Screenshots: None"
    
    post_text = get_listing_post_text(listing)
    
    return f"""
{post_text}
━━━━━━━━━━━━━━━━━━━━━━
{screenshot_info}
━━━━━━━━━━━━━━━━━━━━━━
"""

def admin_update_main_post_as_sold(sold_data, bot, escrow_message_id):
    """Update main channel post to show SOLD status"""
    try:
        channel_message_id = sold_data.get('channel_message_id')
        if not channel_message_id or str(channel_message_id).lower() == 'none':
            return True
            
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT platform, channel_age, subscribers, views, price
            FROM listings WHERE listing_id = ?
        """, (sold_data.get('listing_id'),))
        listing_details = cursor.fetchone()
        conn.close()
        
        if not listing_details:
            return False
        
        platform, channel_age, subscribers, views, price = listing_details
        # Safely parse message_id — guard against old tuple-string values like "(110, 111)"
        raw_eid = str(escrow_message_id).strip().strip('()')
        try:
            safe_escrow_id = int(raw_eid.split(',')[0].strip())
        except (ValueError, IndexError):
            safe_escrow_id = 0
        escrow_url = helper_get_tg_url(ESCROW_LOG_CHANNEL_ID, safe_escrow_id) if safe_escrow_id else None
        
        price_str = str(price)
        if price_str.replace('.', '', 1).isdigit():
            price_str = str(int(float(price_str)))
        
        subs_formatted = f"{int(subscribers):,}" if subscribers and str(subscribers).isdigit() else "N/A"
        views_formatted = f"{int(views):,}" if views and str(views).isdigit() else "N/A"
        
        platform_colors = {'youtube': '🔴', 'instagram': '🟣', 'tiktok': '⚫', 'facebook': '🔵'}
        platform_emoji = platform_colors.get(platform.lower(), '🟢')
        
        proof_text = f'\n<b>Transaction Proof:</b> <a href="{escrow_url}">View Escrow Log</a>' if escrow_url else ''
        sold_text = f"""
<b>🆔 Account ID:</b> <code>{sold_data.get('listing_id')}</code>
━━━━━━━━━━━━━━━━━━━━━━
<b>✅ SOLD ANNOUNCEMENT</b>
━━━━━━━━━━━━━━━━━━━━━━

<b>{platform} Account - SOLD</b>

{platform_emoji} <b>{platform} Account</b> | <b>{channel_age}</b> | <b>{subs_formatted} Subs</b> | <b>{views_formatted} Views</b>

<b>Order #:</b> <code>{sold_data.get('order_number', 'N/A')}</code>
<b>Sold For:</b> ${price_str}{proof_text}

━━━━━━━━━━━━━━━━━━━━━━
This listing has been sold via escrow.
"""
        if escrow_url:
            keyboard = [[InlineKeyboardButton("✅ SOLD - View Transaction Proof", url=escrow_url)]]
        else:
            keyboard = [[InlineKeyboardButton("✅ SOLD", callback_data="dead_button_trigger")]]
        
        chat_id = CHANNEL_ID if isinstance(CHANNEL_ID, str) and CHANNEL_ID.startswith('@') else int(CHANNEL_ID)
        
        # Clean string of parens and quotes before splitting
        clean_msg_ids = str(channel_message_id).replace('(', '').replace(')', '').replace("'", '').replace('"', '')
        msg_ids = [m.strip() for m in clean_msg_ids.split(',') if m.strip().isdigit()]
        
        if not msg_ids:
            return True
            
        # The buttons post is always the LAST message in the group
        buttons_msg_id = msg_ids[-1]
        
        try:
            # The buttons post is a text message (bot.send_message), so edit_message_text is correct
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=int(buttons_msg_id),
                text=sold_text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard),
                disable_web_page_preview=True
            )
        except Exception:
            # Fallback for legacy posts that might have been single-photo posts with buttons attached
            try:
                # Most listing posts are photos, so try caption edit first
                bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=int(msg_id_str),
                    caption=sold_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception:
                # Fallback for text-only posts
                try:
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=int(msg_id_str),
                        text=sold_text,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                except Exception as ex:
                    logger.error(f"Error updating post as sold {msg_id_str}: {ex}")
        return True
        
    except Exception as e:
        logger.error(f"Error updating main post as sold: {e}")
        return False

def admin_view_listings(update, context):
    """Admin paginated list of all listings with platform filtering (like customer browse)."""
    query = update.callback_query
    
    # Get page and platform from callback data
    page = 0
    platform_filter = None
    
    if query and query.data.startswith("admin_listings_page_"):
        parts = query.data.replace("admin_listings_page_", "").split("_")
        page = int(parts[0])
        if len(parts) > 1:
            platform_filter = "_".join(parts[1:])
        context.user_data['listings_page'] = page
        context.user_data['admin_platform_filter'] = platform_filter
    elif query and query.data.startswith("admin_platform_"):
        platform_filter = query.data.replace("admin_platform_", "")
        page = 0
        context.user_data['listings_page'] = page
        context.user_data['admin_platform_filter'] = platform_filter
    else:
        platform_filter = context.user_data.get('admin_platform_filter')
        page = context.user_data.get('listings_page', 0)
    
    PAGE_SIZE = 10
    offset = page * PAGE_SIZE
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Build query with platform filter
    if platform_filter:
        cursor.execute("SELECT COUNT(*) FROM listings WHERE platform = ? AND status_flag = 'published'", (platform_filter,))
        total = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT id, listing_id, platform, account_type, subscribers, price, 
                   status_flag, created_at
            FROM listings
            WHERE platform = ? AND status_flag = 'published'
            ORDER BY COALESCE(last_bumped_at, created_at) DESC
            LIMIT ? OFFSET ?
        """, (platform_filter, PAGE_SIZE, offset))
    else:
        cursor.execute("SELECT COUNT(*) FROM listings WHERE status_flag = 'published'")
        total = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT id, listing_id, platform, account_type, subscribers, price, 
                   status_flag, created_at
            FROM listings
            WHERE status_flag = 'published'
            ORDER BY COALESCE(last_bumped_at, created_at) DESC
            LIMIT ? OFFSET ?
        """, (PAGE_SIZE, offset))
    
    listings = cursor.fetchall()
    
    # Get platform counts
    cursor.execute("""
        SELECT platform, COUNT(*) FROM listings WHERE status_flag = 'published' GROUP BY platform
    """)
    platform_counts = dict(cursor.fetchall())
    conn.close()
    
    if not listings and not platform_filter:
        text = "📋 <b>ADMIN ACCOUNTS MARKET</b>\n\n📭 No listings found."
        keyboard = [[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_back_main")]]
        if query:
            query.answer()
            query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        return MAIN_MENU
    
    # If no platform filter, show platform selection
    if not platform_filter:
        text = "📋 <b>ADMIN ACCOUNTS MARKET</b>\n\nSelect a platform or view all:"
        keyboard = []
        for plat in PLATFORMS:
            count = platform_counts.get(plat, 0)
            emoji = {"YouTube": "🔴", "Instagram": "🟣", "TikTok": "⚫", "Facebook": "🔵"}.get(plat, "🟢")
            keyboard.append([InlineKeyboardButton(f"{emoji} {plat} ({count})", callback_data=f"admin_platform_{plat}")])
        keyboard.append([InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_back_main")])
        
        if query:
            query.answer()
            query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        else:
            update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        return MAIN_MENU
    
    # Show listings for platform
    text = f"📋 <b>ACCOUNTS MARKET - {platform_filter}</b> (Page {page + 1})\n\n"
    keyboard = []
    
    for listing in listings:
        lid, listing_id, platform, acc_type, subs, price, status, created = listing
        status_badge = "✅" if status == "published" else "❌"
        subs_fmt = format_number(subs)
        price_fmt = f"${price:,.0f}" if price else "$0"
        
        text += (
            f"{status_badge} <b>{listing_id}</b> | {platform}\n"
            f"👤 {acc_type} | 👥 {subs_fmt} subs | {price_fmt}\n\n"
        )
        
        keyboard.append([
            InlineKeyboardButton(f"Manage {listing_id}", callback_data=f"admin_manage_listing_{lid}")
        ])
    
    # Pagination
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️ Previous", callback_data=f"admin_listings_page_{page-1}_{platform_filter}"))
    if offset + PAGE_SIZE < total:
        nav_row.append(InlineKeyboardButton("Next ▶️", callback_data=f"admin_listings_page_{page+1}_{platform_filter}"))
    
    if nav_row:
        keyboard.append(nav_row)
    
    keyboard.append([InlineKeyboardButton("🔙 Back to Platforms", callback_data="admin_view_listings_reset")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_back_main")])
    
    if query:
        query.answer()
        query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    else:
        update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    
    return MAIN_MENU

def admin_item_hub_callback(update, context):
    query = update.callback_query
    query.answer()
    listing_id = query.data.replace("admin_hub_", "")
    context.user_data["product_id"] = listing_id
    text = f"⚙️ **Managing:** `{listing_id}`\nChoose an action:"
    keyboard = [
        [InlineKeyboardButton("🆙 Bump to the Top", callback_data=f"admin_run_bump_{listing_id}")],
        [InlineKeyboardButton("💰 Mark as Sold", callback_data=f"admin_run_sold_{listing_id}")],
        [InlineKeyboardButton("⬅️ Back to List", callback_data="view_listings")]
    ]
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return MAIN_MENU

def admin_hub_execution_callback(update, context):
    query = update.callback_query
    query.answer()
    data = query.data
    
    if data.startswith("admin_run_bump_"):
        listing_id = data.replace("admin_run_bump_", "")
        handle_bump_action(query, context.bot, listing_id, ignore_cooldown=True, as_alert=False)
        return admin_view_listings(update, context)
        
    elif data.startswith("admin_run_sold_"):
        listing_id = data.replace("admin_run_sold_", "")
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT listing_id, platform, price, channel_message_id, stock_message_id, 
                      subscribers, views, account_type, status_flag 
               FROM listings WHERE listing_id = ?""",
            (listing_id,)
        )
        listing = cursor.fetchone()
        conn.close()
        
        if not listing:
            query.message.reply_text("❌ Error: Listing not found in database.")
            return MAIN_MENU
            
        (l_id, platform, price, channel_message_id, stock_message_id,
         subscribers, views, account_type, status_flag) = listing
        
        context.user_data["sold_listing"] = {
            "listing_id": l_id,
            "platform": platform,
            "price": price,
            "channel_message_id": channel_message_id,
            "stock_message_id": stock_message_id,
            "subscribers": subscribers,
            "views": views,
            "account_type": account_type,
            "current_status": status_flag
        }
        
        query.message.reply_text(
            f"✅ **Selected for Sale:** {l_id}\n"
            f"📱 **Platform:** {platform}\n"
            f"💰 **Price:** ${price}\n\n"
            f"📄 **Please enter the Transaction ID (TXid) or Escrow link:**\n\n"
            f"Type 'cancel' to abort.",
            parse_mode=ParseMode.MARKDOWN
        )
        return ENTER_TXID
        
        
        
        
        
        
        

# ===== CUSTOMER HANDLERS =====
def customer_start(update, context):
    """REORGANIZED Customer Dashboard"""
    query = update.callback_query
    user = update.effective_user
    # Ensure user is in database
    conn = get_connection()
    try:
        conn.execute("INSERT OR IGNORE INTO users (telegram_id, username) VALUES (?, ?)", 
                     (update.effective_user.id, update.effective_user.username))
        conn.commit()
    finally:
        conn.close()
    
    dashboard_text = (
        f"👋 <b>Welcome, {user.first_name} To Platform Dashboard!</b>\n\n"
        f"What would you like to do?"
    )
    
    keyboard = [
        [InlineKeyboardButton("🏛 Accounts Market (Browse All Listed Accounts)", callback_data="browse_menu")],
        [InlineKeyboardButton("🛒 Buy An Account", callback_data="buyer_start"), InlineKeyboardButton("💵 Sell Your Account", callback_data="seller_start")],
        [InlineKeyboardButton("💼 My Listings", callback_data="view_my_listings"), InlineKeyboardButton("🚛 My Orders", callback_data="customer_my_orders")],
        [InlineKeyboardButton("⭐️ Upgrade Badges", callback_data="upgrade_badge_menu"), InlineKeyboardButton("👤 Profile & Feedback", callback_data="user_profile_feedback")],
        [InlineKeyboardButton("📢 Help Center", callback_data="customer_help_center"), InlineKeyboardButton("🎧 Contact Support", callback_data="customer_support")],
        [InlineKeyboardButton("💬 Join Our Discussion Community", url="https://t.me/smyardchat")]
    ]
    
    if query:
        query.answer()
        query.edit_message_text(
            dashboard_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
    else:
        update.message.reply_text(
            dashboard_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
    
    return CUSTOMER_MENU

    
# ===== IN-BOT BROWSE & SEARCH SYSTEM =====

def browse_menu(update, context):
    """Main browse entry — shows platform categories with live counts."""
    query = update.callback_query
    context.user_data.pop('browse_filters', None)  # reset filters when entering fresh

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT platform, COUNT(*) FROM listings
        WHERE status_flag = 'published'
        GROUP BY platform
    """)
    counts = dict(cursor.fetchall())
    conn.close()

    text = (
        "🛍 <b>Browse Listed Channels</b>\n\n"
        "Pick a platform to explore available accounts, or use search to "
        "filter by price, subscribers, and more.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

    keyboard = []
    for plat in PLATFORMS:
        count = counts.get(plat, 0)
        emoji = {"YouTube": "🔴", "Instagram": "🟣", "TikTok": "⚫", "Facebook": "🔵"}.get(plat, "🟢")
        keyboard.append([InlineKeyboardButton(f"{emoji} {plat} ({count})", callback_data=f"browse_platform_{plat}")])

    keyboard.append([InlineKeyboardButton("🔍 Search / Filter", callback_data="browse_filter_menu")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Dashboard", callback_data="back_to_customer_start")])

    if query:
        query.answer()
        query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    else:
        update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

    return BROWSE_MENU

def _build_listing_query(filters):
    """Builds a WHERE clause + params list from active filters dict."""
    where = ["status_flag = 'published'"]
    params = []

    if filters.get('platform'):
        where.append("platform = ?")
        params.append(filters['platform'])
    if filters.get('min_price') is not None:
        where.append("price >= ?")
        params.append(filters['min_price'])
    if filters.get('max_price') is not None:
        where.append("price <= ?")
        params.append(filters['max_price'])
    if filters.get('min_subs') is not None:
        where.append("subscribers >= ?")
        params.append(filters['min_subs'])
    if filters.get('channel_age') is not None:
        where.append("channel_age = ?")
        params.append(filters['channel_age'])
    if filters.get('monetized_only'):
        where.append("monetization = 'Enabled'")
    if filters.get('keyword'):
        where.append("(niche LIKE ? OR features LIKE ? OR account_type LIKE ?)")
        kw = f"%{filters['keyword']}%"
        params.extend([kw, kw, kw])

    where_clause = " AND ".join(where)
    return where_clause, params

def browse_listings(update, context, page=0):
    """Shows a paginated list of listings matching current filters (newest/bumped first)."""
    query = update.callback_query
    filters = context.user_data.get('browse_filters', {})
    where_clause, params = _build_listing_query(filters)

    PAGE_SIZE = 5
    offset = page * PAGE_SIZE

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM listings WHERE {where_clause}", params)
    total = cursor.fetchone()[0]

    cursor.execute(f"""
        SELECT listing_id, platform, account_type, subscribers, price, monetization
        FROM listings
        WHERE {where_clause}
        ORDER BY COALESCE(last_bumped_at, created_at) DESC
        LIMIT ? OFFSET ?
    """, params + [PAGE_SIZE, offset])
    rows = cursor.fetchall()
    conn.close()

    context.user_data['browse_page'] = page

    if not rows:
        text = "🔍 <b>No listings match your filters.</b>\n\nTry adjusting your search criteria."
        keyboard = [
            [InlineKeyboardButton("🔧 Adjust Filters", callback_data="browse_filter_menu")],
            [InlineKeyboardButton("🔙 Back to Browse", callback_data="browse_menu")]
        ]
        query.answer()
        query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        return BROWSE_PLATFORM_LIST

    plat_label = filters.get('platform', 'All Platforms')
    text = f"🛍 <b>{plat_label} Listings</b> ({total} found)\n\nTap a listing to view full details:"

    keyboard = []
    for r in rows:
        subs_fmt = format_number(r['subscribers'])
        price_fmt = f"${int(float(r['price'])):,}" if str(r['price']).replace('.', '', 1).isdigit() else f"${r['price']}"
        mon_icon = "✅" if r['monetization'] == 'Enabled' else "▫️"
        btn_text = f"{r['listing_id']} | {subs_fmt} subs | {price_fmt} {mon_icon}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"browse_view_{r['listing_id']}")])

    # Pagination row
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️ Previous", callback_data=f"browse_page_{page-1}"))
    if offset + PAGE_SIZE < total:
        nav_row.append(InlineKeyboardButton("Next ▶️", callback_data=f"browse_page_{page+1}"))
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton("🔧 Filters", callback_data="browse_filter_menu")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Browse", callback_data="browse_menu")])

    query.answer()
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return BROWSE_PLATFORM_LIST

def browse_platform_callback(update, context):
    """Handle platform selection from the browse menu."""
    query = update.callback_query
    platform = query.data.replace("browse_platform_", "")
    filters = context.user_data.get('browse_filters', {})
    filters['platform'] = platform
    context.user_data['browse_filters'] = filters
    return browse_listings(update, context, page=0)

def browse_page_callback(update, context):
    """Handle pagination button clicks."""
    query = update.callback_query
    page = int(query.data.replace("browse_page_", ""))
    return browse_listings(update, context, page=page)

def browse_view_listing(update, context):
    """Show full details of a single listing with screenshots and buttons."""
    query = update.callback_query
    listing_id = query.data.replace("browse_view_", "")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT listing_id, platform, account_type, subscribers, views, price, 
               monetization, niche, features, region, status, channel_message_id
        FROM listings WHERE listing_id = ? AND status_flag = 'published'
    """, (listing_id,))
    listing = cursor.fetchone()
    conn.close()

    if not listing:
        query.answer("This listing is no longer available.", show_alert=True)
        return browse_listings(update, context, page=context.user_data.get('browse_page', 0))

    (l_id, platform, account_type, subscribers, views, price, monetization, 
     niche, features, region, status, channel_msg_id) = listing

    subs_fmt = format_number(subscribers)
    views_fmt = format_number(views)
    price_fmt = f"${int(float(price)):,}" if str(price).replace('.', '', 1).isdigit() else f"${price}"

    text = (
        f"🎯 <b>{platform} ACCOUNT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 <b>Account ID:</b> <code>{l_id}</code>\n"
        f"👤 <b>Type:</b> {account_type}\n"
        f"🌍 <b>Region:</b> {region or 'N/A'}\n\n"
        f"👥 <b>Subscribers:</b> {subs_fmt}\n"
        f"👀 <b>Views:</b> {views_fmt}\n"
        f"✅ <b>Status:</b> {status or 'N/A'}\n\n"
        f"🗃️ <b>Niche:</b> {niche or 'Mixed'}\n"
        f"🔧 <b>Features:</b> {features or 'N/A'}\n"
        f"💲 <b>Monetization:</b> {monetization or 'N/A'}\n\n"
        f"💵 <b>Price:</b> {price_fmt}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )

    keyboard = [
        [InlineKeyboardButton("🛍 Place Order | Start Escrow", callback_data=f"buy_from_browse_{l_id}")],
    ]
    
    # Add More Info button with link to main channel post
    if channel_msg_id:
        try:
            channel_link = helper_get_tg_url(CHANNEL_ID, int(channel_msg_id))
            keyboard.append([InlineKeyboardButton("ℹ️ More Info & Screenshots", url=channel_link)])
        except:
            pass
    
    keyboard.append([InlineKeyboardButton("🔙 Back to Listings", callback_data=f"browse_page_{context.user_data.get('browse_page', 0)}")])

    query.answer()
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return BROWSE_LISTING_DETAIL

def buy_from_browse_callback(update, context):
    """Show listing details + escrow fee confirmation — same flow as channel post deep link."""
    query = update.callback_query
    listing_id = query.data.replace("buy_from_browse_", "")
    query.answer()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM listings WHERE listing_id = ? AND status_flag = 'published'", (listing_id,))
    listing = cursor.fetchone()
    conn.close()

    if not listing:
        query.edit_message_text("❌ This listing is no longer available.")
        return browse_menu(update, context)

    price = float(listing["price"])
    escrow_fee = calculate_escrow_fee(price, row_get(listing, "created_by"))
    platform = listing["platform"]
    account_type = listing["account_type"]
    subs_fmt = format_number(listing["subscribers"])
    views_fmt = format_number(listing["views"])
    price_fmt = f"${price:,.0f}"
    fee_fmt = f"${escrow_fee:.2f}"
    order_number = generate_order_number(platform)

    # Save pending order so confirm_pay_escrow can find it
    context.user_data['pending_order'] = {
        'listing_id': listing_id,
        'platform': platform,
        'price': price,
        'escrow_fee': escrow_fee,
        'seller_id': row_get(listing, "created_by"),
        'order_number': order_number
    }

    text = (
        f"🎯 <b>{platform} ACCOUNT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>📋 BASIC INFO</b>\n"
        f"• 🆔 <b>Account ID:</b> <code>{listing_id}</code>\n"
        f"• 👤 <b>Type:</b> {account_type}\n"
        f"• 🌍 <b>Region:</b> {listing['region'] or 'N/A'}\n\n"
        f"<b>📊 STATISTICS</b>\n"
        f"• 👥 <b>Subscribers:</b> {subs_fmt}\n"
        f"• 👀 <b>Views:</b> {views_fmt}\n"
        f"• ✅ <b>Status:</b> {listing['status'] or 'N/A'}\n\n"
        f"<b>⚙️ FEATURES</b>\n"
        f"• 🗃️ <b>Niche:</b> {listing['niche'] or 'Mixed'}\n"
        f"• 🔧 <b>Features:</b> {listing['features'] or 'N/A'}\n"
        f"• 💲 <b>Monetization:</b> {listing['monetization'] or 'N/A'}\n\n"
        f"<b>💰 PRICING & ESCROW</b>\n"
        f"• 💵 <b>Account Price:</b> {price_fmt}\n"
        f"• 🔐 <b>Escrow Fee (5%, min $5):</b> <b>{fee_fmt} USDT</b>\n\n"
        f"<b>🛡️ How Escrow Works:</b>\n"
        f"1. You pay the escrow fee\n"
        f"2. Admin creates a private group with you, seller & admin\n"
        f"3. Seller transfers the account to you\n"
        f"4. You confirm receipt\n"
        f"5. Admin releases funds to the seller\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )
    keyboard = [
        [InlineKeyboardButton(f"💳 Pay Escrow Fee ({fee_fmt})", callback_data=f"confirm_pay_escrow_{listing_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_customer_start")]
    ]
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CUSTOMER_MENU



def browse_filter_menu(update, context):
    """Shows the filter/search options."""
    query = update.callback_query
    filters = context.user_data.get('browse_filters', {})

    active_summary = []
    if filters.get('platform'):
        active_summary.append(f"Platform: {filters['platform']}")
    if filters.get('min_price') is not None or filters.get('max_price') is not None:
        lo = filters.get('min_price', 0)
        hi = filters.get('max_price', '∞')
        active_summary.append(f"Price: ${lo}–${hi}")
    if filters.get('min_subs') is not None:
        active_summary.append(f"Min Subs: {filters['min_subs']:,}")
    if filters.get('channel_age') is not None:
        active_summary.append(f"Channel Age: {filters['channel_age']}")
    if filters.get('monetized_only'):
        active_summary.append("Monetized only")
    if filters.get('keyword'):
        active_summary.append(f"Keyword: \"{filters['keyword']}\"")

    summary_text = "\n".join(f"• {s}" for s in active_summary) if active_summary else "No filters applied yet."

    text = (
        f"🔍 <b>Search & Filter</b>\n\n"
        f"<b>Active filters:</b>\n{summary_text}\n\n"
        f"Choose what to filter by:"
    )

    keyboard = [
        [InlineKeyboardButton("💵 Set Price Range", callback_data="browse_set_price")],
        [InlineKeyboardButton("👥 Min Subscribers", callback_data="browse_set_subs")],
        [InlineKeyboardButton("📅 Channel Age", callback_data="browse_set_age")],
        [InlineKeyboardButton(
            ("✅ " if filters.get('monetized_only') else "▫️ ") + "Monetized Only",
            callback_data="browse_toggle_monetized"
        )],
        [InlineKeyboardButton("🔤 Search Keyword", callback_data="browse_set_keyword")],
        [InlineKeyboardButton("✅ Apply Filters", callback_data="browse_apply_filters")],
        [InlineKeyboardButton("♻️ Clear All Filters", callback_data="browse_clear_filters")],
        [InlineKeyboardButton("🔙 Back to Browse", callback_data="browse_menu")]
    ]

    query.answer()
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return BROWSE_FILTER_MENU


def browse_toggle_monetized(update, context):
    query = update.callback_query
    filters = context.user_data.get('browse_filters', {})
    filters['monetized_only'] = not filters.get('monetized_only', False)
    context.user_data['browse_filters'] = filters
    return browse_filter_menu(update, context)


def browse_clear_filters(update, context):
    query = update.callback_query
    context.user_data['browse_filters'] = {}
    query.answer("Filters cleared!")
    return browse_filter_menu(update, context)


def browse_apply_filters(update, context):
    """Apply filters and show results."""
    return browse_listings(update, context, page=0)


def browse_set_price_prompt(update, context):
    query = update.callback_query
    query.answer()
    query.edit_message_text(
        "💵 <b>Set Price Range</b>\n\n"
        "Send the range as: <code>min-max</code>\n"
        "Example: <code>50-300</code>\n\n"
        "Or send just a number for minimum only (e.g. <code>100</code>).",
        parse_mode=ParseMode.HTML
    )
    context.user_data['awaiting_filter'] = 'price'
    return BROWSE_FILTER_PRICE


def browse_set_subs_prompt(update, context):
    query = update.callback_query
    query.answer()
    query.edit_message_text(
        "👥 <b>Set Minimum Subscribers</b>\n\n"
        "Send a number, e.g. <code>1000</code>",
        parse_mode=ParseMode.HTML
    )
    context.user_data['awaiting_filter'] = 'subs'
    return BROWSE_FILTER_SUBS


def browse_set_age_prompt(update, context):
    query = update.callback_query
    query.answer()
    query.edit_message_text(
        "📅 <b>Set Channel Age</b>\n\n"
        "Send a specific year, e.g. <code>2006</code>",
        parse_mode=ParseMode.HTML
    )
    context.user_data['awaiting_filter'] = 'age'
    return BROWSE_FILTER_AGE


def browse_set_keyword_prompt(update, context):
    query = update.callback_query
    query.answer()
    query.edit_message_text(
        "🔤 <b>Search Keyword</b>\n\n"
        "Send a keyword to search in niche, features, or account type "
        "(e.g. <code>gaming</code>, <code>monetized</code>).",
        parse_mode=ParseMode.HTML
    )
    context.user_data['awaiting_filter'] = 'keyword'
    return BROWSE_SEARCH_KEYWORD


def browse_handle_filter_input(update, context):
    """Handles text input for price range, subs, or keyword filters."""
    text = update.message.text.strip()
    awaiting = context.user_data.get('awaiting_filter')
    filters = context.user_data.get('browse_filters', {})

    if awaiting == 'price':
        try:
            if '-' in text:
                lo, hi = text.split('-', 1)
                filters['min_price'] = float(lo.strip())
                filters['max_price'] = float(hi.strip())
            else:
                filters['min_price'] = float(text.strip())
                filters.pop('max_price', None)
        except ValueError:
            update.message.reply_text("❌ Invalid format. Send like <code>50-300</code>", parse_mode=ParseMode.HTML)
            return BROWSE_FILTER_PRICE

    elif awaiting == 'subs':
        try:
            filters['min_subs'] = int(text.replace(',', '').strip())
        except ValueError:
            update.message.reply_text("❌ Invalid number. Send digits only, e.g. 1000")
            return BROWSE_FILTER_SUBS

    elif awaiting == 'age':
        filters['channel_age'] = text.strip()

    elif awaiting == 'keyword':
        filters['keyword'] = text.strip()

    context.user_data['browse_filters'] = filters
    context.user_data.pop('awaiting_filter', None)

    keyboard = [
        [InlineKeyboardButton("✅ Apply Filters", callback_data="browse_apply_filters")],
        [InlineKeyboardButton("🔧 Set More Filters", callback_data="browse_filter_menu")]
    ]
    update.message.reply_text(
        "✅ Filter saved! Apply now or add more filters.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return BROWSE_FILTER_MENU


def show_user_listings(update, context):   
    query = update.callback_query if update.callback_query else None
    user_id = update.effective_user.id
    
    page = 0
    if query and query.data.startswith("my_listings_page_"):
        page = int(query.data.replace("my_listings_page_", ""))
        context.user_data['my_listings_page'] = page
    else:
        page = context.user_data.get('my_listings_page', 0)
        
    PAGE_SIZE = 10
    offset = page * PAGE_SIZE
    
    # --- SQLITE DATABASE FETCH ---
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        conn.row_factory = sqlite3.Row 
        cursor = conn.cursor()
        
        # Get the user's Telegram username for contact-link matching
        username = update.effective_user.username or ''
        contact_pattern = f'%t.me/{username}%' if username else None
        
        # Count total items first
        if contact_pattern:
            cursor.execute("""
                SELECT COUNT(*) FROM (
                    SELECT listing_id FROM customer_listings WHERE customer_id = ? AND status_flag = 'pending'
                    UNION
                    SELECT listing_id FROM listings 
                    WHERE created_by = ? OR seller_telegram_id = ? OR seller_contact LIKE ?
                )
            """, (user_id, user_id, user_id, contact_pattern))
        else:
            cursor.execute("""
                SELECT COUNT(*) FROM (
                    SELECT listing_id FROM customer_listings WHERE customer_id = ? AND status_flag = 'pending'
                    UNION
                    SELECT listing_id FROM listings WHERE created_by = ? OR seller_telegram_id = ?
                )
            """, (user_id, user_id, user_id))
        total = cursor.fetchone()[0]
        
        # Fetch paginated listing rows
        if contact_pattern:
            cursor.execute("""
                SELECT listing_id, account_type, status_flag, created_at
                FROM customer_listings WHERE customer_id = ? AND status_flag = 'pending'
                UNION
                SELECT listing_id, account_type, status_flag, created_at
                FROM listings 
                WHERE created_by = ? OR seller_telegram_id = ? OR seller_contact LIKE ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """, (user_id, user_id, user_id, contact_pattern, PAGE_SIZE, offset))
        else:
            cursor.execute("""
                SELECT listing_id, account_type, status_flag, created_at
                FROM customer_listings WHERE customer_id = ? AND status_flag = 'pending'
                UNION
                SELECT listing_id, account_type, status_flag, created_at
                FROM listings WHERE created_by = ? OR seller_telegram_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """, (user_id, user_id, user_id, PAGE_SIZE, offset))
        
        user_listings = cursor.fetchall()
        conn.close()
    except Exception as e:
        print(f"Database error fetching user listings: {e}")
        user_listings = []
        total = 0
    # -----------------------------
    
    if not user_listings and total == 0:
        text = (
            "📦 <b>Your Listings</b>\n\n"
            "You don't have any YouTube channels currently listed for sale.\n\n"
            "Click below to start a new listing!"
        )
        keyboard = [
            [InlineKeyboardButton("➕ Create New Listing", callback_data="start_sell_flow")],
            [InlineKeyboardButton("🔙 Back to Dashboard", callback_data="back_to_customer_start")]
        ]
    else:
        text = f"📦 <b>Your Active Listings</b> (Page {page + 1})\n\nSelect a channel below to manage it:"
        keyboard = []
        
        for listing in user_listings:
            l_id = listing['listing_id']
            # FIX: Pulling account_type ("Monetized") instead of Niche
            acc_type = listing['account_type'] if listing['account_type'] else "Channel"
            status = listing['status_flag'].upper() if listing['status_flag'] else "UNKNOWN"
            
            btn_text = f"🆔 {l_id} | {acc_type} ({status})"
            # FIX: Pointing strictly to the new management hub router
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"manage_item_{l_id}")])
            
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("◀️ Previous", callback_data=f"my_listings_page_{page-1}"))
        if offset + PAGE_SIZE < total:
            nav_row.append(InlineKeyboardButton("Next ▶️", callback_data=f"my_listings_page_{page+1}"))
        
        if nav_row:
            keyboard.append(nav_row)
            
        keyboard.append([InlineKeyboardButton("🔙 Back to Dashboard", callback_data="back_to_customer_start")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if query:
        query.answer()
        query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        update.message.reply_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        
    return CUSTOMER_MENU


def transactions_log_view(update, context):
    """Show paginated transaction log."""
    query = update.callback_query if update.callback_query else None

    if query and query.data.startswith("txlog_page_"):
        page = int(query.data.replace("txlog_page_", ""))
        context.user_data['txlog_page'] = page
    else:
        page = context.user_data.get('txlog_page', 0)

    PAGE_SIZE = 10
    offset = page * PAGE_SIZE

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM transactions_log")
    total = cursor.fetchone()[0]
    cursor.execute("""
        SELECT id, order_number, product_id, platform, seller_name, buyer_name, price, txid
        FROM transactions_log
        ORDER BY completed_at DESC
        LIMIT ? OFFSET ?
    """, (PAGE_SIZE, offset))
    transactions = cursor.fetchall()
    conn.close()

    if not transactions:
        text = "📊 <b>PLATFORM TRANSACTIONS LOG</b>\n\n📭 No transactions yet."
        keyboard = [[InlineKeyboardButton("🔙 Back to Dashboard", callback_data="open_dashboard")]]
        if query:
            query.answer()
            query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        else:
            update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        return CUSTOMER_MENU

    text = f"📊 <b>PLATFORM TRANSACTIONS LOG</b> (Page {page + 1})\n\n"
    platform_emojis = {'YouTube': '📺', 'Instagram': '📷', 'TikTok': '🎵', 'Facebook': '👤'}

    for _, order_num, product_id, platform, seller_name, buyer_name, price, txid in transactions:
        emoji = platform_emojis.get(platform, '📱')
        seller_display = seller_name[:3] + "***" if len(seller_name) > 3 else seller_name
        buyer_display = buyer_name[:3] + "***" if len(buyer_name) > 3 else buyer_name
        text += (
            f"✅ <b>Successful Transaction via Escrow</b>\n"
            f"{emoji} <b>Platform:</b> {platform}\n"
            f"🆔 <b>Account ID:</b> <code>{product_id}</code>\n"
            f"🛍 <b>Order:</b> <code>{order_num}</code>\n"
            f"👤 <b>Seller:</b> {seller_display}\n"
            f"👤 <b>Buyer:</b> {buyer_display}\n"
            f"💰 <b>Price:</b> ${price:,.2f}\n"
            f"🔒 <b>Warranty Active</b> ✅\n"
            f"🛍 <b>Account Delivered</b> ✅\n"
        )
        if txid:
            text += f"📄 <b>TXid:</b> <a href='{txid}'>View Transaction</a>\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━\n\n"

    keyboard = []
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️ Previous", callback_data=f"txlog_page_{page-1}"))
    if offset + PAGE_SIZE < total:
        nav_row.append(InlineKeyboardButton("Next ▶️", callback_data=f"txlog_page_{page+1}"))
    if nav_row:
        keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("🔙 Back to Dashboard", callback_data="open_dashboard")])

    if query:
        query.answer()
        query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    else:
        update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CUSTOMER_MENU


def buyer_start(update, context):
    """Start buyer flow"""
    query = update.callback_query
    query.answer()
    
    text = """🛡️ **ESCROW SERVICE SYSTEM - HOW IT WORKS?**
________________________________
✅ **100% Secure Transactions:**
________________________________
1. You choose the account you want to buy
2. You pay the escrow fee (5% of price, minimum $5)
3. We hold the payment securely
4. Seller transfers the account to you
5. You confirm receipt
6. We release payment to seller

____________________
🛡️ **Your Protection:**
____________________
• No risk of scams
• Escrow agent mediates the transaction
• Money-back guarantee if seller fails to deliver
• 24/7 support throughout the process

_______________
💰 **Escrow Fee:**
_______________
• 5% of the total price
• Minimum $5 fee
• Covers transaction security & support

Click below to enter the Account ID of the account you want to buy:"""
    
    keyboard = [
        [InlineKeyboardButton("🔢 Enter Account ID", callback_data="enter_product_id")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_customer")]
    ]
    
    query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return BUYER_ESCROW_INFO

def buyer_enter_product_id(update, context):
    """Ask for Account ID"""
    query = update.callback_query
    query.answer()
    
    text = """🔢 **Enter Account ID**

Please enter the **Account ID** of the account you want to purchase.

You can find the Account ID on the account listing in the main channel @smyard.

**Example:** `YT-088` or `IG-102`

Type the Account ID below:"""
    
    query.edit_message_text(text=text, parse_mode=ParseMode.MARKDOWN)
    return BUYER_ENTER_PRODUCT_ID

def handle_buyer_product_id(update, context):
    """Handle Account ID input from buyer — show full details and escrow fee for confirmation."""
    product_id = update.message.text.strip().upper()
    
    if product_id.lower() == 'cancel':
        update.message.reply_text("❌ Operation cancelled.")
        return customer_start(update, context)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "SELECT * FROM listings WHERE listing_id = ?",
            (product_id,)
        )
        listing = cursor.fetchone()
        conn.close()
        
        if not listing:
            update.message.reply_text(
                f"❌ **Product not found:** `{product_id}`\n\n"
                "Please check the Account ID and try again.\n"
                "Enter another Account ID or type 'cancel':",
                parse_mode=ParseMode.MARKDOWN
            )
            return BUYER_ENTER_PRODUCT_ID
        
        status_clean = str(listing['status_flag']).strip().lower()
        if status_clean != 'published':
            update.message.reply_text(
                f"❌ This listing is not available for purchase.\n"
                "Enter another Account ID or type 'cancel':",
                parse_mode=ParseMode.MARKDOWN
            )
            return BUYER_ENTER_PRODUCT_ID
        
        price = float(listing['price']) if listing['price'] else 0.0
        escrow_fee = calculate_escrow_fee(price, row_get(listing, 'created_by'))
        
        subs_fmt = format_number(listing['subscribers'])
        views_fmt = format_number(listing['views'])
        price_fmt = f"${price:,.0f}"
        fee_fmt = f"${escrow_fee:.2f}"

        # Store order info for next step
        context.user_data['pending_order'] = {
            'listing_id': listing['listing_id'],
            'platform': listing['platform'],
            'price': price,
            'escrow_fee': escrow_fee,
            'seller_id': row_get(listing, 'created_by'),
            'order_number': generate_order_number(listing['platform'])
        }

        text = (
            f"🎯 <b>{listing['platform']} ACCOUNT</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>📋 BASIC INFO</b>\n"
            f"• 🆔 <b>Account ID:</b> <code>{listing['listing_id']}</code>\n"
            f"• 👤 <b>Type:</b> {listing['account_type']}\n"
            f"• 🌍 <b>Region:</b> {listing['region'] or 'N/A'}\n\n"
            f"<b>📊 STATISTICS</b>\n"
            f"• 👥 <b>Subscribers:</b> {subs_fmt}\n"
            f"• 👀 <b>Views:</b> {views_fmt}\n"
            f"• ✅ <b>Status:</b> {listing['status'] or 'N/A'}\n\n"
            f"<b>⚙️ FEATURES</b>\n"
            f"• 🗃️ <b>Niche:</b> {listing['niche'] or 'Mixed'}\n"
            f"• 🔧 <b>Features:</b> {listing['features'] or 'N/A'}\n"
            f"• 💲 <b>Monetization:</b> {listing['monetization'] or 'N/A'}\n\n"
            f"<b>💰 PRICING & ESCROW</b>\n"
            f"• 💵 <b>Account Price:</b> {price_fmt}\n"
            f"• 🔐 <b>Escrow Fee (5%, min $5):</b> <b>{fee_fmt} USDT</b>\n\n"
            f"<b>🛡️ How Escrow Works:</b>\n"
            f"1. You pay the escrow fee\n"
            f"2. Admin creates a private group with you, seller, and themselves\n"
            f"3. Seller transfers the account to you\n"
            f"4. You confirm receipt of the account\n"
            f"5. Admin releases funds to the seller\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━"
        )
        
        keyboard = [
            [InlineKeyboardButton(f"💳 Pay Escrow Fee ({fee_fmt})", callback_data=f"confirm_pay_escrow_{product_id}")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_to_escrow_info")]
        ]
        
        update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        return BUYER_PAYMENT_METHODS
        
    except Exception as e:
        logger.error(f"Error in handle_buyer_product_id: {e}", exc_info=True)
        update.message.reply_text("❌ An error occurred. Please try again or contact @smyards")
        return BUYER_ENTER_PRODUCT_ID

def notify_seller_on_order_created(seller_telegram_id, order_number, product_id, price, escrow_fee, buyer_username, context):
    """Notify seller when order created - uses seller_telegram_id field."""
    if not seller_telegram_id:
        logger.warning(f"[SELLER NOTIFY] ❌ seller_telegram_id is NULL for order {order_number}")
        return
    
    if seller_telegram_id == OWNER_ID:
        logger.info(f"[SELLER NOTIFY] Skipping admin-owned listing (seller_id = OWNER_ID)")
        return
    
    try:
        logger.info(f"[SELLER NOTIFY] Sending to seller_telegram_id={seller_telegram_id}")
        
        text = (
            f"🛍 <b>NEW ORDER PLACED ON YOUR LISTING!</b>\n\n"
            f"📦 <b>Account ID:</b> <code>{product_id}</code>\n"
            f"🆔 <b>Order Number:</b> <code>{order_number}</code>\n"
            f"💰 <b>Account Price:</b> ${price:,.2f}\n"
            f"🛡️ <b>Escrow Fee:</b> ${escrow_fee:.2f}\n"
            f"👤 <b>Buyer:</b> @{buyer_username}\n\n"
            f"⏳ <b>Status:</b> Waiting for buyer to complete escrow fee payment...\n\n"
            f"Once payment is confirmed, you'll receive an invitation to the secure deal group."
        )
        
        context.bot.send_message(
            chat_id=int(seller_telegram_id),
            text=text,
            parse_mode=ParseMode.HTML
        )
        logger.info(f"[SELLER NOTIFY] ✅ SUCCESS! Message sent to seller_telegram_id={seller_telegram_id}")
        
    except ValueError as e:
        logger.error(f"[SELLER NOTIFY] ❌ ValueError (bad seller_telegram_id={seller_telegram_id}): {e}")
    except Exception as e:
        logger.error(f"[SELLER NOTIFY] ❌ Exception: {type(e).__name__}: {e}", exc_info=True)
		
def confirm_pay_escrow(update, context):
    """Create escrow order with seller_telegram_id tracking."""
    query = update.callback_query
    query.answer()
    
    product_id = query.data.replace("confirm_pay_escrow_", "")
    pending = context.user_data.get('pending_order', {})
    
    if not pending or pending.get('listing_id') != product_id:
        query.edit_message_text("❌ Order info expired. Please enter the Account ID again.")
        return BUYER_ENTER_PRODUCT_ID
    
    listing_id = pending['listing_id']
    platform = pending['platform']
    price = pending['price']
    escrow_fee = pending['escrow_fee']
    order_number = pending['order_number']
    user = update.effective_user
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        logger.debug("Fetching listing %s", listing_id)
        
        cursor.execute("""
            SELECT created_by, seller_contact, platform, seller_telegram_id 
            FROM listings WHERE listing_id = ?
        """, (listing_id,))
        listing_result = cursor.fetchone()
        
        if listing_result:
            created_by, seller_contact, _, seller_telegram_id = listing_result
            logger.debug("Listing found: created_by=%s, seller_telegram_id=%s", created_by, seller_telegram_id)
        else:
            seller_telegram_id = None
            seller_contact = None
            logger.warning("Listing %s not found", listing_id)
        
        conn.close()

        # Save order with seller_telegram_id
        conn = get_connection()
        cursor = conn.cursor()
        logger.debug("Saving order with seller_telegram_id=%s", seller_telegram_id)
        
        cursor.execute("""
            INSERT OR IGNORE INTO orders
            (order_number, product_id, customer_id, customer_username, platform,
             total_price, escrow_fee, amount_to_pay, payment_method, payment_address,
             payment_status, seller_id, order_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, 'pending')
        """, (
            order_number, listing_id, user.id,
            user.username or str(user.id), platform,
            price, escrow_fee, escrow_fee,
            "cryptomus", "auto-generated",
            seller_telegram_id
        ))
        conn.commit()
        # No seller notification here - wait until payment is verified
        
        cursor.execute("SELECT id FROM orders WHERE order_number = ?", (order_number,))
        order_row = cursor.fetchone()
        conn.close()
        order_db_id = order_row[0] if order_row else 0

        # No notifications here - wait until payment is actually verified

        query.edit_message_text("⏳ Generating your secure payment link, please wait...")

        payment_url = create_cryptomus_invoice(order_number, escrow_fee, listing_id)

        if not payment_url:
            query.edit_message_text(
                "❌ Could not generate payment link right now.\n\n"
                "Please contact @smyards for assistance.",
                parse_mode=ParseMode.HTML
            )
            return CUSTOMER_MENU

        text = (
            f"🏁 <b>Ready to Pay!</b>\n\n"
            f"🆔 <b>Order Number:</b> <code>{order_number}</code>\n"
            f"📦 <b>Account ID:</b> <code>{listing_id}</code>\n"
            f"💵 <b>Escrow Fee:</b> <b>${escrow_fee:.2f} USDT</b>\n\n"
            f"Click the button below to pay securely via Cryptomus.\n\n"
            f"✅ Payment is confirmed <b>automatically</b> — no need to notify us manually."
        )

        keyboard = [
            [InlineKeyboardButton(f"💳 Pay ${escrow_fee:.2f} USDT via Cryptomus", url=payment_url)],
            [InlineKeyboardButton("🔙 Back to Dashboard", callback_data="back_to_customer_start")]
        ]

        query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        context.user_data.pop('pending_order', None)
        return CUSTOMER_MENU

    except Exception as e:
        logger.error("Error creating escrow order: %s", e, exc_info=True)
        query.edit_message_text("❌ An error occurred. Please contact @smyards for assistance.")
        return CUSTOMER_MENU

    except Exception as e:
        logger.error("Error in confirm_pay_escrow: %s", e, exc_info=True)
        query.edit_message_text("❌ An error occurred. Please contact @smyards for assistance.")
        return CUSTOMER_MENU
		
def handle_payment_method(update, context):
    """Handle payment method selection and show instructions"""
    query = update.callback_query
    query.answer()
    
    payment_methods = {
        "pay_coinbase": "Coinbase", "pay_binance": "Binance",
        "pay_btc": "Bitcoin (BTC)", "pay_eth": "Ethereum (ETH)",
        "pay_usdt": "USDT", "pay_usdc": "USDC"
    }
    
    method_key = query.data
    method_name = payment_methods.get(method_key, "Unknown")
    
    payment_addresses = {
        "pay_coinbase": COINBASE_ADDRESS, "pay_binance": BINANCE_ADDRESS,
        "pay_btc": BTC_ADDRESS, "pay_eth": ETH_ADDRESS,
        "pay_usdt": USDT_ADDRESS, "pay_usdc": USDC_ADDRESS
    }
    
    address = payment_addresses.get(method_key, "")
    
    if not address:
        query.edit_message_text(
            "⚠️ Payment method temporarily unavailable. Please choose another method or contact admin @smyards",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back_to_payment_methods")]])
        )
        return BUYER_PAYMENT_METHODS
    
    context.user_data["buy_order"]["payment_method"] = method_name
    context.user_data["buy_order"]["payment_address"] = address
    
    price = context.user_data["buy_order"]["price"]
    escrow_fee = calculate_escrow_fee(price)
    
    network_clean = method_name.split('(')[-1].replace(')', '') if '(' in method_name else method_name
    
    text = f"""💳 **Payment Instructions - {method_name}**

📋 **Order Summary:**
• 🆔 Account ID: `{context.user_data['buy_order']['product_id']}`
• 📱 Platform: {context.user_data['buy_order']['platform']}
• 💵 Account Price: ${price:,.2f}
• 🛡️ Escrow Fee: ${escrow_fee:,.2f}

💰 **Amount to Pay:** **${escrow_fee:,.2f}**

📝 **Send Payment to:**
`{address}`

**Important Instructions:**
1. Send exactly **${escrow_fee:,.2f}**
2. Use the network: **{network_clean}**
3. Do NOT send from an exchange (use personal wallet)
4. After sending, click "✅ Confirm Payment" below
5. We'll verify your payment within 15 minutes
⚠️ **Note:** Include the Account ID in the payment memo: `{context.user_data['buy_order']['product_id']}`"""


    keyboard = [
        [InlineKeyboardButton("✅ I've Paid - Confirm Payment", callback_data="confirm_payment")],
        [InlineKeyboardButton("⬅️ Choose Different Method", callback_data="back_to_payment_methods")]
    ]
    
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return BUYER_PAYMENT_INSTRUCTIONS

def confirm_payment(update, context):
    """Handle payment confirmation"""
    query = update.callback_query
    query.answer()
    
    platform = context.user_data["buy_order"]["platform"]
    order_number = generate_order_number(platform)
    price = context.user_data["buy_order"]["price"]
    escrow_fee = calculate_escrow_fee(price)
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO orders (
            order_number, product_id, customer_id, customer_username,
            platform, total_price, escrow_fee, amount_to_pay,
            payment_method, payment_address, payment_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        order_number, context.user_data["buy_order"]["product_id"],
        update.effective_user.id, update.effective_user.username,
        platform, price, escrow_fee, escrow_fee,
        context.user_data["buy_order"]["payment_method"],
        context.user_data["buy_order"]["payment_address"], 'pending'
    ))
    conn.commit()
    conn.close()
    
    admin_text = f"""🆕 **NEW ORDER PLACED!**

📋 **Order Details:**
• 🆔 **Order Number:** `{order_number}`
• 🆔 **Account ID:** `{context.user_data['buy_order']['product_id']}`
• 👤 **Customer:** @{update.effective_user.username} (ID: {update.effective_user.id})
• 📱 **Platform:** {platform}
• 💵 **Account Price:** ${price:,.2f}
• 🛡️ **Escrow Fee:** ${escrow_fee:,.2f}
• 💳 **Payment Method:** {context.user_data['buy_order']['payment_method']}
• ⏰ **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

**Action Required:**
1. Verify payment received
2. Contact seller
3. Create group chat with buyer & seller
4. Process the transaction"""

    keyboard = [[
        InlineKeyboardButton("✅ Verify Payment", callback_data=f"verify_payment_{order_number}"),
        InlineKeyboardButton("📞 Contact Buyer", url=f"https://t.me/{update.effective_user.username}" if update.effective_user.username else f"tg://user?id={update.effective_user.id}")
    ]]
    
    context.bot.send_message(
        chat_id=OWNER_ID,
        text=admin_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    
    text = f"""✅ **Order Submitted Successfully!**

📋 **Your Order Details:**
• 🆔 **Order Number:** `{order_number}`
• 🆔 **Account ID:** `{context.user_data['buy_order']['product_id']}`
• 📱 **Platform:** {platform}
• 💵 **Amount Paid:** ${escrow_fee:,.2f}
• 💳 **Payment Method:** {context.user_data['buy_order']['payment_method']}

📞 **Next Steps:**
1. We've notified our escrow agent (@smyards)\n2. They will verify your payment within 15 minutes\n3. Once verified, they'll contact the seller'll contact the seller

4. You'll be added to a secure group chat with the seller and agent
5. Complete the transaction safely
▶️ **Please wait for our agent to contact you.**
You can also contact us @smyards if you have any questions."""
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f3e0 Back to Main Menu", callback_data="back_to_customer")]]), parse_mode=ParseMode.MARKDOWN)
    if "buy_order" in context.user_data:
        del context.user_data["buy_order"]
    return CUSTOMER_MENU

# ===== CUSTOMER SUBMISSION HANDLER =====
def seller_start(update, context):
    """Start seller flow"""
    query = update.callback_query
    query.answer()
    text = """💰 **SELL YOUR ACCOUNT NOW:**

_____________________________________
✅ **Why Sell With Our Platform?**
_____________________________________
• Reach thousands of serious buyers
• Secure escrow protection
• Get paid quickly & safely
• Professional listing presentation

___________________
📋 **How It Works:**
___________________
1. Submit your account details
2. Our team reviews & approves
3. Your account gets listed on our platform
4. Buyers contact you via our system
5. We handle secure payment via escrow
6. You get paid after successful account transfer

_____________________________
⚖️ **Service Terms & Rules:** 
_____________________________
⏰ **Approval Time:** 2-12 hours
💰 **Commission:** 5% escrow fee (paid by buyer)
🛡 **Security:** 100% protected transactions

Ready to list your account?"""
    keyboard = [
        [InlineKeyboardButton("\U0001f4dd List Your Account Now", callback_data="seller_list_account")],
        [InlineKeyboardButton("\u2b05\ufe0f Back", callback_data="back_to_customer")]
    ]
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return SELLER_INFO

def seller_list_account(update, context):
    """Start listing process for seller"""
    query = update.callback_query
    query.answer()
    keyboard = [[InlineKeyboardButton(platform, callback_data=f"customer_platform_{platform}")] for platform in PLATFORMS]
    keyboard.append([InlineKeyboardButton("\u2b05\ufe0f Back", callback_data="back_to_seller_info")])
    query.edit_message_text(
        text="\U0001f4f1 **Select Platform**\n\nChoose the platform of the account you want to sell:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    return SELLER_PLATFORM

def customer_platform_callback(update, context):
    """Handle platform selection for customer seller"""
    query = update.callback_query
    query.answer()
    platform = query.data.replace("customer_platform_", "")
    context.user_data["customer_listing"] = {"platform": platform, "account_type": "Standard"}
    text = f"\U0001f4f1 **Platform:** {platform}\n\nPlease enter the **Link** to your account/channel:\n_(Type 'cancel' to abort)_"

    query.edit_message_text(text=text, parse_mode=ParseMode.MARKDOWN)
    
    return SELLER_LINK

def handle_customer_link(update, context):
    """Handle the customer submitting their channel link with duplicate check"""
    text = update.message.text
    
    if text.lower() == 'cancel':
        update.message.reply_text("\u274c Listing cancelled.")
        return customer_start(update, context)
        
    # Duplicate link check
    check_link = text.strip()
    if check_link.lower() != 'skip':
        conn = get_connection()
        cursor = conn.cursor()
        
        # Check customer_listings (pending or approved)
        cursor.execute("""
            SELECT customer_username FROM customer_listings 
            WHERE channel_link = ? AND status_flag IN ('pending', 'approved')
            LIMIT 1
        """, (check_link,))
        res_cl = cursor.fetchone()
        
        # Check main listings (pending or published)
        cursor.execute("""
            SELECT created_by FROM listings 
            WHERE channel_link = ? AND status_flag IN ('pending', 'published')
            LIMIT 1
        """, (check_link,))
        res_l = cursor.fetchone()
        
        if res_cl or res_l:
            seller_identifier = ""
            if res_cl and res_cl[0]:
                seller_identifier = f"@{res_cl[0]}"
            elif res_l:
                seller_identifier = get_seller_name(res_l[0])
            else:
                seller_identifier = "another user"
                
            conn.close()
            
            keyboard = [
                [InlineKeyboardButton("🎧 This channel is mine - Contact Support", url="https://t.me/smyards")],
                [InlineKeyboardButton("🔄 Enter another account link", callback_data="seller_list_account")],
                [InlineKeyboardButton("🔙 Back", callback_data="customer_main")]
            ]
            
            update.message.reply_text(
                f"⚠️ **Duplicate Account Link!**\n\n"
                f"This channel is already listed by {seller_identifier}. If this is a mistake, or you recently bought this channel, please contact support.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            # Stay in SELLER_LINK state so they can enter a new one
            return SELLER_LINK
            
        conn.close()
        
    context.user_data["customer_listing"]["channel_link"] = check_link if check_link.lower() != 'skip' else ''
    
    platform = context.user_data["customer_listing"].get("platform", "YouTube")
    template = get_details_template(platform)
    
    update.message.reply_text(
        f"\ud83d\udcf1 *Platform:* {platform}\n\n{template}\n\n"
        f"Fill in your values and send it back. Type 'cancel' to abort.",
        parse_mode=ParseMode.MARKDOWN
    )
    return SELLER_DETAILS

def handle_customer_details(update, context):
    """Handle customer details — uses per-platform template parser"""
    text = update.message.text
    
    if text.lower() == 'cancel':
        update.message.reply_text("\u274c Listing cancelled.")
        return customer_start(update, context)
    
    if "customer_listing" not in context.user_data:
        context.user_data["customer_listing"] = {}
    
    platform = context.user_data["customer_listing"].get("platform", "YouTube")
    details = parse_platform_details(platform, text)
    
    if not details.get('channel_age') and not details.get('subscribers'):
        update.message.reply_text(
            "\u26a0\ufe0f *Please fill in the template properly.*\n\n"
            "Make sure you copy the template, fill in the values, and send it back.\n"
            "Type 'cancel' to abort.",
            parse_mode=ParseMode.MARKDOWN
        )
        return SELLER_DETAILS
    
    link = context.user_data["customer_listing"].get("channel_link", "")
    details['admin_notes'] = f"Channel Link: {link}" if link else ''
    
    context.user_data["customer_listing"].update(details)
    
    update.message.reply_text(
        "💰 **Enter Your Asking Price (USD)**\n\n"
        "Enter the price you want to sell your account for.\n"
        "**Example:** 500\n\n"
        "Type 'cancel' to cancel.",
        parse_mode=ParseMode.MARKDOWN
    )
    return SELLER_PRICE

def handle_customer_price(update, context):
    """Handle customer seller price input"""
    text = update.message.text
    
    if text.lower() == 'cancel':
        update.message.reply_text("❌ Listing cancelled.")
        return customer_start(update, context)
    
    try:
        price = float(text)
        context.user_data["customer_listing"]["price"] = price
        
        # Auto-set seller contact from their Telegram username
        # ID is intentionally NOT assigned here — it will be assigned at actual submission
        # time (customer_submit_listing) to prevent race conditions with other listings.
        if update.effective_user.username:
            context.user_data["customer_listing"]["seller_contact"] = f"https://t.me/{update.effective_user.username}"
        else:
            context.user_data["customer_listing"]["seller_contact"] = f"tg://user?id={update.effective_user.id}"
        
        # Skip contact step — go straight to screenshots
        context.user_data["customer_screenshots"] = []
        instructions = (
            f"📸 **Upload Screenshots** (REQUIRED)\n\n"
            f"__________________________\n"
            f"**Screenshots Instructions:**\n"
            f"__________________________\n"
            f"1- Include Screenshots for the all account analytics (for last month and lifetime), account status, account standing and All Earn/Monetization Tab.\n"
            f"2- Make sure that all screenshots are in ENGLISH only\n\n"
            f"You can upload up to {MAX_SCREENSHOTS} screenshots.\n"
            f"Send photos one by one.\n\n"
            f"**When finished, type 'done'**\n"
            f"**To cancel, type 'cancel'**\n\n"
            f"Ready for screenshot 1:"
        )
        update.message.reply_text(instructions, parse_mode=ParseMode.MARKDOWN)
        return SELLER_SCREENSHOTS
        
    except ValueError:
        update.message.reply_text("❌ Invalid price. Please enter a number (e.g., 500):")
        return SELLER_PRICE

def handle_customer_contact(update, context):
    """Handle customer seller contact input"""
    text = update.message.text.strip()
    
    if text.lower() == 'cancel':
        update.message.reply_text("❌ Listing cancelled.")
        return customer_start(update, context)
    
    if text.lower() == 'skip':
        context.user_data["customer_listing"]["seller_contact"] = f"https://t.me/{update.effective_user.username}" if update.effective_user.username else f"tg://user?id={update.effective_user.id}"
    else:
        context.user_data["customer_listing"]["seller_contact"] = text
    
    context.user_data["customer_screenshots"] = []
    instructions = (
        f"📸 **Upload Screenshots** (REQUIRED)\n\n"
        f"__________________________\n"
        f"**Screenshots Instructions:**\n"
        f"__________________________\n"
        f"1- Include Screenshots for the all account analytics (for last month and lifetime), account status, account standing and All Earn/Monetization Tab.\n"
        f"2- Make sure that all screenshots are in ENGLISH only\n\n"
        f"You can upload up to {MAX_SCREENSHOTS} screenshots.\n"
        f"Send photos one by one.\n\n"
        f"**When finished, type 'done'**\n"
        f"**To cancel, type 'cancel'**\n\n"
        f"Ready for screenshot 1:"
    )
    update.message.reply_text(instructions, parse_mode=ParseMode.MARKDOWN)
    return SELLER_SCREENSHOTS

def customer_add_screenshots(update, context):
    """Start screenshot upload for customer"""
    query = update.callback_query
    query.answer()
    
    context.user_data["customer_screenshots"] = []
    
    query.edit_message_text(
        f"📸 **Upload Screenshots**\n\n"
        f"You can upload up to {MAX_SCREENSHOTS} screenshots.\n"
        f"Send photos one by one.\n\n"
        f"**When finished, type 'done'**\n"
        f"**To cancel, type 'cancel'**\n\n"
        f"Ready for screenshot 1:"
    )
    return SELLER_SCREENSHOTS

def handle_customer_screenshot_upload(update, context):
    """Handle customer screenshot upload"""
    if 'customer_screenshots' not in context.user_data:
        context.user_data['customer_screenshots'] = []
    
    if update.message.photo:
        photo = update.message.photo[-1]
        context.user_data['customer_screenshots'].append(photo.file_id)
        
        count = len(context.user_data['customer_screenshots'])
        
        if count >= MAX_SCREENSHOTS:
            update.message.reply_text(f"✅ Maximum {MAX_SCREENSHOTS} screenshots reached!")
            return show_customer_preview(update, context)
        else:
            update.message.reply_text(f"📸 Screenshot {count} received!\nSend another photo or type 'done' to finish.")
    elif update.message.text:
        text = update.message.text.lower()
        if text == 'done':
            if len(context.user_data.get('customer_screenshots', [])) == 0:
                update.message.reply_text("❌ Screenshots are required. Please upload at least 1 screenshot, or type 'cancel' to exit.")
                return SELLER_SCREENSHOTS
            return show_customer_preview(update, context)
        elif text == 'cancel':
            update.message.reply_text("❌ Listing cancelled.")
            return customer_start(update, context)
        else:
            update.message.reply_text("Please send photos or type 'done' to finish.")
    
    return SELLER_SCREENSHOTS

def show_customer_preview(update, context):
    """Show preview for customer seller"""
    listing = context.user_data["customer_listing"]
    screenshots = context.user_data.get("customer_screenshots", [])
    
    post_text = get_listing_post_text(listing)
    
    text = (
        "📋 <b>LISTING PREVIEW</b>\n\n"
        "✅ <b>Your account is ready for submission!</b>\n\n"
        f"{post_text}\n\n"
        f"📸 <b>Screenshots:</b> {len(screenshots)} uploaded\n\n"
        "⏰ <b>What Happens Next:</b>\n"
        "1. You submit this listing\n"
        "2. Our team reviews it (2-12 hours)\n"
        "3. If approved, it gets listed on our platform\n"
        "4. You'll be notified when it's live\n"
        "5. Buyers can then contact you and Buy it\n\n"
        "<b>Ready to submit?</b>"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Submit for Review", callback_data="customer_submit_listing")],
        [InlineKeyboardButton("✏️ Edit Again", callback_data="customer_edit_again")],
        [InlineKeyboardButton("❌ Cancel", callback_data="customer_cancel_listing")]
    ]
    
    if update.message:
        update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    else:
        query = update.callback_query
        query.answer()
        query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    
    return SELLER_CONFIRM

def customer_skip_screenshots(update, context):
    """Skip screenshots for customer"""
    query = update.callback_query
    query.answer()
    
    context.user_data["customer_screenshots"] = []
    return show_customer_preview(update, context)

def customer_submit_listing(update, context):
    """Submit customer listing for review"""
    query = update.callback_query
    query.answer()
    
    listing = context.user_data.get("customer_listing", {})
    screenshots = context.user_data.get("customer_screenshots", [])
    
    # Auto-capture user display name
    user_first = update.effective_user.first_name or ""
    user_last = update.effective_user.last_name or ""
    display_name = f"{user_first} {user_last}".strip()
    if display_name:
        conn_user = get_connection()
        try:
            cur = conn_user.cursor()
            cur.execute("""
                INSERT INTO users (telegram_id, username, display_name)
                VALUES (?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    display_name=excluded.display_name,
                    username=COALESCE(excluded.username, username)
            """, (update.effective_user.id, update.effective_user.username, display_name))
            conn_user.commit()
        except Exception:
            pass
        finally:
            conn_user.close()

    # Save to database securely
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # Generate the final listing ID HERE at submission time (not at price entry)
        # This prevents race conditions where two sessions generate the same ID simultaneously.
        platform = listing.get('platform', 'YouTube')
        platform_codes = {'YouTube': 'YT', 'TikTok': 'TT', 'Instagram': 'IG', 'Facebook': 'FB'}
        platform_code = platform_codes.get(platform, platform[:2].upper())
        cursor.execute("SELECT listing_id FROM listings WHERE listing_id LIKE ?", (f"{platform_code}-%",))
        existing_main = [r[0] for r in cursor.fetchall()]
        cursor.execute("SELECT listing_id FROM customer_listings WHERE listing_id LIKE ?", (f"{platform_code}-%",))
        existing_customer = [r[0] for r in cursor.fetchall()]
        max_num = 0
        for eid in existing_main + existing_customer:
            parts = eid.split('-')
            if len(parts) == 2 and parts[1].isdigit():
                max_num = max(max_num, int(parts[1]))
        final_listing_id = f"{platform_code}-{max_num + 1:03d}"
        listing['listing_id'] = final_listing_id
        context.user_data["customer_listing"]["listing_id"] = final_listing_id
        cursor.execute('''
            INSERT INTO customer_listings (
                listing_id, platform, account_type, channel_age, subscribers, views,
                niche, features, monetization, region, status, price,
                screenshots, seller_contact, customer_id, customer_username,
                status_flag, admin_notes, growth, channel_link, likes, extra_monetization
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            listing.get('listing_id'),
            listing.get('platform'),
            listing.get('account_type', 'N/A'),
            listing.get('channel_age', 'N/A'),
            listing.get('subscribers', 0),
            listing.get('views', 0),
            listing.get('niche', 'Mixed'),
            listing.get('features', 'N/A'),
            listing.get('monetization', 'N/A'),
            listing.get('region', 'N/A'),
            listing.get('status', 'No Strikes'),
            listing.get('price'),
            json.dumps(screenshots),
            listing.get('seller_contact'),
            update.effective_user.id,
            update.effective_user.username,
            'pending',
            listing.get('admin_notes', ''),
            listing.get('growth', ''),
            listing.get('channel_link', ''),
            listing.get('likes', 0),
            listing.get('extra_monetization', '{}')
        ))
        conn.commit()
    finally:
        conn.close()
    
    # Safely escape strings for HTML
    import html as _html_mod
    def _s(v): return _html_mod.escape(str(v)) if v else 'N/A'
    
    admin_text = (
        f"🆕 <b>NEW CUSTOMER LISTING FOR REVIEW</b>\n\n"
        f"📋 <b>Listing Details:</b>\n"
        f"• 🆔 Listing ID: <code>{_s(listing.get('listing_id'))}</code>\n"
        f"• 👤 Seller: @{_s(update.effective_user.username)} (ID: <code>{update.effective_user.id}</code>)\n"
        f"• 🔗 Account Link: <a href='{_s(listing.get('channel_link'))}'>Link</a>\n"
        f"• 📱 Platform: {_s(listing.get('platform'))}\n"
        f"• 📅 Channel Age: {_s(listing.get('channel_age', 'N/A'))}\n"
        f"• 👤 Type: {_s(listing.get('account_type'))}\n"
        f"• 👥 Subscribers: {_s(listing.get('subscribers', 'N/A'))}\n"
        f"• 👀 Views: {_s(listing.get('views', 'N/A'))}\n"
        f"• 💰 Price: ${_s(listing.get('price', 0))}\n"
        f"• 📸 Screenshots: {len(screenshots)} uploaded\n"
        f"• 📞 Contact: {_s(listing.get('seller_contact'))}\n"
        f"• ⏰ Submitted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"Approve this listing to publish it on @smyard"
    )

    keyboard = [[
        InlineKeyboardButton("✅ Approve & Publish", callback_data=f"approve_listing_{listing.get('listing_id')}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"reject_listing_{listing.get('listing_id')}")
    ]]
    
    context.bot.send_message(
        chat_id=OWNER_ID,
        text=admin_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )
    
    # Confirm to customer
    text = f"""✅ **Listing Submitted Successfully!**

📋 **Your Listing Details:**
• 🆔 **Listing ID:** `{listing.get('listing_id')}`
• 📱 **Platform:** {listing.get('platform')}
• 💰 **Price:** ${listing.get('price', 0):,.2f}
• 📸 **Screenshots:** {len(screenshots)} uploaded

⏰ **What Happens Next:**
1. Our team will review your listing
2. Approval time: 2-12 hours
3. You'll be notified when it's approved
4. Once approved, it will be listed on @smyard
5. Buyers can then contact you

📞 **Need help?** Contact @smyards

Thank you for choosing SMYARDS!"""
    
    keyboard = [[InlineKeyboardButton("🏠 Back to Main Menu", callback_data="back_to_customer")]]
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    
    # Clear customer data elegantly
    context.user_data.pop("customer_listing", None)
    context.user_data.pop("customer_screenshots", None)
    
    return CUSTOMER_MENU

	
	
	
	
    
    
# ===== ADMIN APPROVAL HANDLERS =====
def approve_customer_listing(update, context):
    """Approve and publish a customer listing - FIXED FOR UNIFIED PIPELINE"""
    query = update.callback_query
    query.answer()
    
    listing_id = query.data.replace("approve_listing_", "")
    logger.info(f"Admin approving customer listing: {listing_id}")
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM customer_listings WHERE listing_id = ?", (listing_id,))
        customer_listing = cursor.fetchone()
        
        if not customer_listing:
            query.edit_message_text("❌ Listing not found.")
            return
        
        # Get column names
        cursor.execute("PRAGMA table_info(customer_listings)")
        columns = [col[1] for col in cursor.fetchall()]
        listing_dict = dict(zip(columns, customer_listing))
        
        # Convert screenshots
        screenshots_str = listing_dict.get('screenshots', '[]')
        if not screenshots_str:
            screenshots = []
        else:
            try:
                screenshots = json.loads(screenshots_str)
            except json.JSONDecodeError:
                screenshots = [s.strip() for s in screenshots_str.split(',') if s.strip()]
        
        # ID was already assigned at submission time — reuse it directly
        new_listing_id = listing_id
        logger.info(f"Approving customer listing with pre-assigned ID: {new_listing_id}")
        
        # Prepare listing data
        listing_data = {
            'listing_id': new_listing_id,
            'platform': listing_dict.get('platform'),
            'account_type': listing_dict.get('account_type'),
            'price': listing_dict.get('price'),
            'subscribers': listing_dict.get('subscribers'),
            'views': listing_dict.get('views'),
            'niche': listing_dict.get('niche'),
            'features': listing_dict.get('features'),
            'monetization': listing_dict.get('monetization'),
            'region': listing_dict.get('region'),
            'status': listing_dict.get('status'),
            'seller_contact': listing_dict.get('seller_contact'),
            'created_by': listing_dict.get('customer_id'),
            'seller_telegram_id': listing_dict.get('customer_id'),
            'channel_link': listing_dict.get('channel_link'),
            'channel_age': listing_dict.get('channel_age', 'N/A'),
            'growth': listing_dict.get('growth', ''),
            'likes': listing_dict.get('likes', 0),
            'extra_monetization': listing_dict.get('extra_monetization', '{}')
        }
        
        # --- NEW UNIFIED PUBLISHING PIPELINE ---
        
        # 1. Publish to main channel directly (handles album + caption + buttons)
        caption_msg_id, main_message_id = publish_to_main_channel(
            listing=listing_data, 
            screenshots=screenshots, 
            bot=context.bot
        )
        
        if not main_message_id:
            raise Exception("Failed to publish to main channel")
            
        # 2. Stock channel posting deprecated — browsing now happens in-bot
        stock_message_id = None  # admin_create_stock_post removed (deprecated)
        
        # 3. Save to main listings table
        cursor.execute('''
            INSERT INTO listings (
                listing_id, platform, account_type, channel_age, subscribers, views,
                niche, features, monetization, region, status, price,
                screenshots, seller_contact, status_flag, channel_message_id, 
                screenshot_message_id, discussion_message_id, stock_message_id, created_by, seller_telegram_id, channel_link,
                growth, likes, extra_monetization
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            new_listing_id, listing_dict.get('platform'), listing_dict.get('account_type', 'N/A'),
            listing_dict.get('channel_age', 'N/A'),
            listing_dict.get('subscribers', 0), listing_dict.get('views', 0),
            listing_dict.get('niche', 'Mixed'), listing_dict.get('features', 'N/A'),
            listing_dict.get('monetization', 'N/A'), listing_dict.get('region', 'N/A'),
            listing_dict.get('status', 'No Strikes'), listing_dict.get('price'),
            json.dumps(screenshots), listing_dict.get('seller_contact'), 'published',
            str(main_message_id), 
            str(caption_msg_id) if caption_msg_id else None,

            None,  # discussion_message_id obsolete
            str(stock_message_id) if stock_message_id else None, 
            listing_dict.get('customer_id'),
            listing_dict.get('customer_id'),
            listing_dict.get('channel_link'),
            listing_dict.get('growth', ''),
            listing_dict.get('likes', 0),
            listing_dict.get('extra_monetization', '{}')
        ))
        
        # Update customer listing status
        cursor.execute("UPDATE customer_listings SET status_flag = 'approved' WHERE listing_id = ?", (listing_id,))
        conn.commit()
        
        # Notify seller
        try:
            seller_text = f"""\u2705 **Your Listing Has Been Approved!**\n\n\U0001f389 Congratulations! Your account `{listing_id}` has been approved and is now live.\nBuyers can now see it and purchase it.\n\nTo manage your listing:\n1. Go to your Dashboard\n2. Click \U0001f4cb My Listings\n3. Select this listing to edit or mark as sold."""
            context.bot.send_message(
                chat_id=listing_dict.get('customer_id'),
                text=seller_text,
                parse_mode='MARKDOWN'
            )
        except Exception as e:
            logger.error(f"Error notifying seller: {e}")
        
        query.edit_message_text(
            f"✅ Listing approved and published!\n• 🆔 ID: `{new_listing_id}`\n• Main Channel: ✅\n• In-Bot Browse: ✅",
            parse_mode='MARKDOWN'
        )
        
    except Exception as e:
        logger.error(f"Error approving listing: {e}", exc_info=True)
        query.edit_message_text(f"❌ Error: {str(e)[:100]}")
    finally:
        conn.close()

def reject_customer_listing(update, context):
    """Reject a customer listing"""
    query = update.callback_query
    query.answer()
    
    listing_id = query.data.replace("reject_listing_", "")
    
    context.user_data['rejecting_listing_id'] = listing_id
    query.edit_message_text("❌ Please enter the reason for rejection:")
    return ADMIN_REJECT_REASON

	
# ===== BACK BUTTON HANDLERS =====
def back_to_customer(update, context):
    return customer_start(update, context)

def back_to_escrow_info(update, context):
    return buyer_start(update, context)

def back_to_seller_info(update, context):
    return seller_start(update, context)

def back_to_seller_platform(update, context):
    return seller_list_account(update, context)

def back_to_payment_methods(update, context):
    """Go back to payment methods"""
    query = update.callback_query
    query.answer()
    
    if "buy_order" not in context.user_data:
        return buyer_enter_product_id(update, context)
    
    order = context.user_data["buy_order"]
    
    text = f"""Choose your payment method:"""
    
    keyboard = [
        [InlineKeyboardButton("💳 Pay via Cryptomus", callback_data="pay_cryptomus")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_escrow_info")]
    ]
    
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return BUYER_PAYMENT_METHODS

def admin_panel(update, context):
    return admin_start(update, context)


def admin_setname(update, context):
    """Admin command to set a seller's display name. Usage: /setname <telegram_id> <New Name>"""
    if update.effective_user.id != OWNER_ID:
        return
        
    args = context.args
    if len(args) < 2:
        update.message.reply_text("Usage: /setname <telegram_id> <New Name>")
        return
        
    try:
        target_id = int(args[0])
    except ValueError:
        update.message.reply_text("❌ Invalid telegram ID.")
        return
        
    new_name = " ".join(args[1:])
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (telegram_id, display_name)
            VALUES (?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                display_name=excluded.display_name
        """, (target_id, new_name))
        conn.commit()
        update.message.reply_text(f"✅ Seller name for {target_id} updated to: {new_name}")
    except Exception as e:
        update.message.reply_text(f"❌ Database error: {e}")
    finally:
        conn.close()

def admin_start(update, context):
    """REORGANIZED Admin Dashboard"""
    query = update.callback_query
    user = update.effective_user
    
    dashboard_text = (
        f"✅ <b>ADMIN DASHBOARD</b>\n\n"
        f"Welcome, {user.first_name}!"
    )
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM customer_listings WHERE status_flag = 'pending'")
    pending_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT count(*) FROM edit_requests WHERE status = 'pending'")
    pending_edits_count = cursor.fetchone()[0]
    conn.close()
    
    total_pending = pending_count + pending_edits_count
    
    keyboard = [
        [InlineKeyboardButton(f"🔔 Pending Approvals ({total_pending})", callback_data="admin_pending_menu")],
        [InlineKeyboardButton("➕ New Listing", callback_data="new_listing"), InlineKeyboardButton("📦 Market", callback_data="view_listings")],
        [InlineKeyboardButton("📦 Orders", callback_data="admin_orders_panel"), InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings")],
        [InlineKeyboardButton("🤖 Auto Pilot", callback_data="ap_dashboard")]
    ]
    
    if query:
        query.answer()
        query.edit_message_text(
            dashboard_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
    else:
        update.message.reply_text(
            dashboard_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
    
    return MAIN_MENU

def admin_settings(update, context):
    """Admin Settings Panel"""
    query = update.callback_query
    query.answer()
    
    keyboard = [
        [InlineKeyboardButton("⭐ Upgrades Mgmt", callback_data="admin_upgrades_mgmt"), InlineKeyboardButton("🌟 Reviews Management", callback_data="reviews_management")],
        [InlineKeyboardButton("🏕️ Deal Group Pool", callback_data="group_pool_status"), InlineKeyboardButton("⏳ Bump Time Cooldowns", callback_data="admin_bump_settings")],
        [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_back_main")],
    ]
    
    query.edit_message_text(
        "\u2699\ufe0f <b>Admin Settings</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )
    return MAIN_MENU

def admin_bump_settings(update, context):
    query = update.callback_query
    query.answer()
    
    conn = get_connection()
    cursor = conn.cursor()
    settings = {'bump_cooldown_regular': 4, 'bump_cooldown_pro': 2, 'bump_cooldown_vip': 1}
    try:
        cursor.execute("SELECT setting_key, setting_value FROM bot_settings")
        for k, v in cursor.fetchall():
            if k in settings:
                settings[k] = int(v)
    except:
        pass
    conn.close()
    
    text = (
        "⏳ <b>Bump Time Cooldowns</b>\n\n"
        f"Current settings (in days):\n"
        f"• Regular Users: <b>{settings['bump_cooldown_regular']} days</b>\n"
        f"• Pro Users: <b>{settings['bump_cooldown_pro']} days</b>\n"
        f"• VIP Users: <b>{settings['bump_cooldown_vip']} days</b>\n\n"
        f"Select a tier below to edit its cooldown time:"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("Edit Regular", callback_data="admin_bump_edit_regular"),
            InlineKeyboardButton("Edit Pro", callback_data="admin_bump_edit_pro"),
            InlineKeyboardButton("Edit VIP", callback_data="admin_bump_edit_vip")
        ],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="admin_settings")]
    ]
    
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return MAIN_MENU

def admin_bump_settings_edit(update, context):
    query = update.callback_query
    query.answer()
    
    tier = query.data.replace("admin_bump_edit_", "")
    context.user_data['editing_bump_tier'] = tier
    
    tier_name = tier.title() if tier != 'vip' else 'VIP'
    
    keyboard = [[InlineKeyboardButton("🔙 Cancel", callback_data="admin_bump_settings")]]
    query.edit_message_text(
        f"⏳ Enter the new bump cooldown (in days) for <b>{tier_name}</b> users:\n\n"
        f"<i>Please reply with a valid number (e.g., 2).</i>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    return ADMIN_EDIT_BUMP_TIME

def admin_handle_bump_settings_edit(update, context):
    text = update.message.text
    tier = context.user_data.get('editing_bump_tier')
    
    if text.lower() == 'cancel':
        update.message.reply_text("Edit cancelled.")
        return admin_start(update, context)
        
    if not tier:
        update.message.reply_text("Error: Tier not found. Please try again.")
        return admin_start(update, context)
        
    try:
        new_val = int(text)
        if new_val < 0:
            raise ValueError("Must be positive")
    except ValueError:
        update.message.reply_text("❌ Invalid number. Please reply with a valid positive integer.")
        return ADMIN_EDIT_BUMP_TIME
        
    setting_key = f"bump_cooldown_{tier}"
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO bot_settings (setting_key, setting_value, description)
        VALUES (?, ?, ?)
        ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value
    """, (setting_key, str(new_val), f"Bump cooldown in days for {tier.title()} users"))
    conn.commit()
    conn.close()
    
    context.user_data.pop('editing_bump_tier', None)
    
    tier_name = tier.title() if tier != 'vip' else 'VIP'
    update.message.reply_text(
        f"✅ Successfully updated <b>{tier_name}</b> bump cooldown to <b>{new_val} days</b>.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Bump Settings", callback_data="admin_bump_settings")]]),
        parse_mode="HTML"
    )
    return MAIN_MENU

def admin_upgrades_management(update, context):
    """Show all active badge upgrades for admin."""
    query = update.callback_query
    query.answer()
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.telegram_id, u.username, u.badge_type, u.badge_expires_at
        FROM users u
        WHERE u.badge_type != 'Regular'
        ORDER BY u.badge_expires_at DESC
        LIMIT 20
    """)
    users = cursor.fetchall()
    conn.close()
    
    if not users:
        text = "\u2b50 **Upgrades Management**\n\nNo active badge upgrades."
    else:
        text = "\u2b50 **Active Badge Upgrades**\n\n"
        for u in users:
            uid, uname, badge, expires = u
            text += f"\u2022 @{uname} ({uid}) - **{badge}** expires `{expires}`\n"
    
    keyboard = [
        [InlineKeyboardButton("➕ Assign Upgrade", callback_data="admin_assign_upgrade")],
        [InlineKeyboardButton("✅ Upgrade Orders", callback_data="admin_upgrade_orders"), InlineKeyboardButton("⏳ Pre-upgrade Orders", callback_data="admin_pre_upgrade_orders")],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="admin_settings")]
    ]
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return MAIN_MENU



def admin_assign_upgrade_start(update, context):
    query = update.callback_query
    query.answer()
    query.edit_message_text(
        "\u2795 **Assign Upgrade to User**\n\n"
        "Please enter the user's Telegram @username or Telegram ID:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f519 Cancel", callback_data="admin_upgrades_mgmt")]])
    )
    return ASSIGN_UPGRADE_USER


def admin_handle_upgrade_username(update, context):
    text = update.message.text.strip()
    if text.startswith("@"):
        text = text[1:]

    conn = get_connection()
    cursor = conn.cursor()
    if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
        cursor.execute("SELECT telegram_id, username FROM users WHERE telegram_id = ?", (text,))
    else:
        cursor.execute("SELECT telegram_id, username FROM users WHERE LOWER(username) = ?", (text.lower(),))
    res = cursor.fetchone()
    conn.close()

    if not res:
        update.message.reply_text(
            "\u274c User not found in database. Make sure they have started the bot before.\n"
            "Try another username or /cancel."
        )
        return ASSIGN_UPGRADE_USER

    context.user_data['assign_upgrade_uid'] = res[0]
    context.user_data['assign_upgrade_uname'] = res[1] or str(res[0])

    keyboard = [
        [InlineKeyboardButton("\U0001f539 Pro", callback_data="assign_type_Pro")],
        [InlineKeyboardButton("\U0001f48e VIP", callback_data="assign_type_VIP")],
        [InlineKeyboardButton("\U0001f519 Cancel", callback_data="admin_upgrades_mgmt")]
    ]
    uname = context.user_data['assign_upgrade_uname']
    update.message.reply_text(
        f"\u2705 Found user **@{uname}**.\n\nSelect the upgrade type:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ASSIGN_UPGRADE_TYPE


def admin_handle_upgrade_type(update, context):
    query = update.callback_query
    query.answer()
    tier = query.data.replace("assign_type_", "")
    context.user_data['assign_upgrade_tier'] = tier
    uname = context.user_data.get('assign_upgrade_uname', '?')
    query.edit_message_text(
        f"Selected **{tier}** for @{uname}.\n\nEnter the duration in days (e.g. 30):",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f519 Cancel", callback_data="admin_upgrades_mgmt")]])
    )
    return ASSIGN_UPGRADE_DUR


def admin_handle_upgrade_duration(update, context):
    text = update.message.text.strip()
    if not text.isdigit():
        update.message.reply_text("\u274c Please enter a valid number of days.")
        return ASSIGN_UPGRADE_DUR

    days = int(text)
    uid = context.user_data.get('assign_upgrade_uid')
    uname = context.user_data.get('assign_upgrade_uname')
    tier = context.user_data.get('assign_upgrade_tier')

    from datetime import datetime, timedelta
    expiry = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
            INSERT INTO users (telegram_id, username, badge_type, badge_expires_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                badge_type = excluded.badge_type,
                badge_expires_at = excluded.badge_expires_at
        """, (uid, uname, tier, expiry))
    conn.commit()
    conn.close()

    try:
        context.bot.send_message(
            chat_id=uid,
            text=f"\U0001f389 **Congratulations!**\n\nYou have been granted a **{tier}** upgrade for {days} days!\n\nCheck your Dashboard to see your new perks.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Could not notify user {uid} of upgrade: {e}")

    update.message.reply_text(
        f"\u2705 Successfully assigned **{tier}** to @{uname} for {days} days.",
        parse_mode="Markdown"
    )
    return MAIN_MENU


def admin_upgrade_orders(update, context):
    """Show confirmed upgrade orders to admin."""
    query = update.callback_query
    query.answer()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT order_number, customer_username, upgrade_type, duration_days, amount_to_pay, payment_confirmed_at "
        "FROM upgrade_orders WHERE payment_status = 'confirmed' ORDER BY payment_confirmed_at DESC LIMIT 15"
    )
    orders = cursor.fetchall()
    conn.close()

    if not orders:
        query.edit_message_text(
            "\u2705 **Completed Upgrade Orders**\n\nNo completed orders yet.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f519 Back", callback_data="admin_upgrades_mgmt")]])
        )
        return MAIN_MENU

    text = "\u2705 **Completed Upgrade Orders** (Last 15)\n\n"
    for o in orders:
        text += f"\U0001f4e6 `{o[0]}` | @{o[1]} | **{o[2]}** ({o[3]}d) | ${o[4]} | `{o[5]}`\n"

    query.edit_message_text(text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f519 Back", callback_data="admin_upgrades_mgmt")]]))
    return MAIN_MENU


def admin_pre_upgrade_orders(update, context):
    """Show pending upgrade orders to admin."""
    query = update.callback_query
    query.answer()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT order_number, customer_username, upgrade_type, amount_to_pay, created_at "
        "FROM upgrade_orders WHERE payment_status = 'pending' ORDER BY created_at DESC LIMIT 15"
    )
    orders = cursor.fetchall()
    conn.close()

    if not orders:
        query.edit_message_text(
            "\u23f3 **Pending Upgrade Orders**\n\nNo pending orders right now.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f519 Back", callback_data="admin_upgrades_mgmt")]])
        )
        return MAIN_MENU

    text = "\u23f3 **Pending Upgrade Orders** (Last 15)\n\n"
    for o in orders:
        text += f"\U0001f4e6 `{o[0]}` | @{o[1]} | **{o[2]}** | ${o[3]} | `{o[4]}`\n"

    query.edit_message_text(text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f519 Back", callback_data="admin_upgrades_mgmt")]]))
    return MAIN_MENU


def customer_upgrade_badge_menu(update, context):
    """Show badge upgrade sub-menu to customer."""
    query = update.callback_query
    query.answer()
    keyboard = [
        [InlineKeyboardButton("\U0001f4cb My Current Upgrade Badge", callback_data="my_current_badge")],
        [InlineKeyboardButton("\U0001f6d2 Purchase an Upgrade Subscription", callback_data="purchase_upgrade_menu")],
        [InlineKeyboardButton("\U0001f519 Back to Dashboard", callback_data="back_to_customer_start")],
    ]
    query.edit_message_text(
        "\u2b50 **Badge Upgrades**\n\nChoose an option below:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return CUSTOMER_MENU


def customer_my_current_badge(update, context):
    """Show user's active badge/subscription info."""
    query = update.callback_query
    user_id = update.effective_user.id
    query.answer()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT badge_type, badge_expires_at FROM users WHERE telegram_id = ?", (user_id,))
    res = cursor.fetchone()
    conn.close()

    current_badge = "Regular"
    expires_str = "N/A"
    is_active = False
    if res:
        current_badge = res[0] or "Regular"
        if res[1]:
            from datetime import datetime as _dt
            expires_dt = _dt.strptime(res[1], '%Y-%m-%d %H:%M:%S')
            if expires_dt > _dt.now():
                expires_str = res[1]
                is_active = True
            else:
                current_badge = "Regular (Expired)"

    if current_badge in ("Regular", "Regular (Expired)"):
        perks = "\u2022 Bump listings every 4 days\n\u2022 Standard escrow fees"
        status_icon = "\u2b50"
    elif "Pro" in current_badge:
        perks = "\u2022 Bump listings every 2 days\n\u2022 Buyers get 50% off Escrow Fees\n\u2022 Pro flair on your listings"
        status_icon = "\U0001f539"
    elif "VIP" in current_badge:
        perks = "\u2022 Bump listings every 1 day\n\u2022 Buyers get 50% off Escrow Fees\n\u2022 VIP flair on your listings\n\u2022 Priority support"
        status_icon = "\U0001f48e"
    else:
        perks = "\u2022 Standard access"
        status_icon = "\u2b50"

    active_str = "Active \u2705" if is_active else "No active subscription"
    text = (
        f"{status_icon} **Your Current Badge: {current_badge}**\n\n"
        f"**Status:** {active_str}\n"
        f"**Expires:** `{expires_str}`\n\n"
        f"**Your perks:**\n{perks}"
    )
    keyboard = [
        [InlineKeyboardButton("\U0001f6d2 Upgrade / Change Plan", callback_data="purchase_upgrade_menu")],
        [InlineKeyboardButton("\U0001f519 Back", callback_data="upgrade_badge_menu")],
    ]
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return CUSTOMER_MENU


def customer_purchase_upgrade_menu(update, context):
    """Show available upgrade tiers for purchase."""
    query = update.callback_query
    query.answer()
    text = (
        "\U0001f6d2 **Purchase an Upgrade Subscription**\n\n"
        "**\U0001f539 Pro Badge \u2014 $15 / 30 Days**\n"
        "   \u2022 Bump listings every 2 days\n"
        "   \u2022 Buyers get 30% off Escrow Fees\n"
        "   \u2022 Pro flair on your listings\n\n"
        "**\U0001f48e VIP Badge \u2014 $35 / 30 Days**\n"
        "   \u2022 Bump listings every 1 day\n"
        "   \u2022 Buyers get 60% off Escrow Fees\n"
        "   \u2022 VIP flair on your listings\n"
        "   \u2022 Priority support\n\n"
        "Select a tier to proceed with payment:"
    )
    keyboard = [
        [InlineKeyboardButton("\U0001f539 Upgrade to Pro ($15)", callback_data="upgrade_tier_Pro")],
        [InlineKeyboardButton("\U0001f48e Upgrade to VIP ($35)", callback_data="upgrade_tier_VIP")],
        [InlineKeyboardButton("\U0001f519 Back", callback_data="upgrade_badge_menu")],
    ]
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return CUSTOMER_MENU



def customer_process_upgrade(update, context):
    """Process the badge upgrade purchase via Cryptomus."""
    import time as _time
    query = update.callback_query
    tier = query.data.replace("upgrade_tier_", "")
    user_id = update.effective_user.id
    username = update.effective_user.username or str(user_id)
    query.answer("Generating payment link...", show_alert=False)
    
    amount = 15.00 if tier == "Pro" else 35.00
    duration_days = 30
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Generate unique order number
        import random
        while True:
            order_id = f"sub-{random.randint(10000, 99999)}"
            cursor.execute("SELECT 1 FROM upgrade_orders WHERE order_number = ?", (order_id,))
            if not cursor.fetchone():
                break

        # Always insert the order so admin can see it in Pre-upgrade Orders
        cursor.execute("""
            INSERT INTO upgrade_orders (order_number, customer_id, customer_username, upgrade_type, duration_days, amount_to_pay, payment_status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (order_id, user_id, username, tier, duration_days, amount, "pending"))
        conn.commit()
        payment_url = create_cryptomus_invoice(order_id, amount, f"BADGE_{tier}")
    finally:
        conn.close()

    if payment_url:
        keyboard = [
            [InlineKeyboardButton("\U0001f4b3 Pay via Cryptomus", url=payment_url)],
            [InlineKeyboardButton("\u2705 I Have Paid", callback_data="check_upgrade_payment")],
            [InlineKeyboardButton("\U0001f519 Back", callback_data="upgrade_badge_menu")],
        ]
        query.edit_message_text(
            f"\U0001f4b3 **Pay for {tier} Badge**\n\n"
            f"Amount: **${amount:.2f}**\n\n"
            f"Click Pay below, complete the payment, then tap 'I Have Paid'. "
            f"Your badge will activate automatically once payment is confirmed.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        query.edit_message_text(
            "\u274c Failed to generate payment link. Please try again or contact support.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f519 Back", callback_data="upgrade_badge_menu")]])
        )
    return CUSTOMER_MENU


def admin_group_pool_status(update, context):
    """Show status of the automated deal group pool."""
    query = update.callback_query
    query.answer()
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM available_groups WHERE status = 'available'")
    available_count = cursor.fetchone()[0]
    cursor.execute("SELECT count(*) FROM available_groups WHERE status = 'in_use'")
    in_use_count = cursor.fetchone()[0]
    conn.close()
    
    text = (
        f"🏊 **Deal Group Pool Status**\n\n"
        f"🟢 **Available Groups:** `{available_count}`\n"
        f"🔴 **Groups In Use:** `{in_use_count}`\n\n"
        f"**How to add more groups:**\n"
        f"1. Create a Telegram Group.\n"
        f"2. Add the bot to the group.\n"
        f"3. Generate an invite link for the group.\n"
        f"4. Type this command inside the group:\n"
        f"`/pool https://t.me/+yourlink`\n\n"
        f"The bot will save it and automatically assign it to the next paid order!"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="admin_settings")]
    ]
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return MAIN_MENU

def admin_reviews_management(update, context):
    """Show the list of user reviews for admin to manage."""
    query = update.callback_query
    
    page = 0
    if query.data.startswith("admin_reviews_page_"):
        page = int(query.data.replace("admin_reviews_page_", ""))
        
    query.answer()
    
    PAGE_SIZE = 10
    offset = page * PAGE_SIZE
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT count(*) FROM user_reviews")
    total_reviews = cursor.fetchone()[0]
    
    cursor.execute("SELECT id, order_number, reviewer_name, target_username, rating, comment FROM user_reviews ORDER BY id DESC LIMIT ? OFFSET ?", (PAGE_SIZE, offset))
    user_revs = cursor.fetchall()
    conn.close()
    
    if not user_revs:
        query.edit_message_text(
            "⭐ <b>Reviews Management</b>\n\nThere are no user reviews yet.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_settings")]])
        )
        return MAIN_MENU
        
    text = "⭐ <b>Reviews Management</b>\n\n👤 <b>User Reviews:</b>\n"
    keyboard = []
    
    for rid, order_num, reviewer, target, rating, comment in user_revs:
        stars = '⭐' * rating
        target_display = "Platform" if target == "SMYARDS Platform" else f"@{target}"
        short_comment = (comment[:60] + '...') if comment and len(comment) > 60 else (comment or '-')
        text += f"ID: <code>U{rid}</code> | <code>{order_num}</code> | {stars}\n"
        text += f"By: @{reviewer} → {target_display}\n"
        text += f"“{short_comment}”\n"
        text += "━━━━━━━━━━━━\n"
        keyboard.append([
            InlineKeyboardButton(f"✏️ Edit U{rid}", callback_data=f"edit_user_rev_{rid}"),
            InlineKeyboardButton(f"🗑️ Del U{rid}", callback_data=f"del_review_{rid}")
        ])
        
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"admin_reviews_page_{page-1}"))
    if offset + PAGE_SIZE < total_reviews:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"admin_reviews_page_{page+1}"))
        
    if nav_row:
        keyboard.append(nav_row)
        
    keyboard.append([InlineKeyboardButton("🔙 Back to Settings", callback_data="admin_settings")])
    
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return MAIN_MENU

def admin_pending_menu(update, context):
    query = update.callback_query
    query.answer()
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM customer_listings WHERE status_flag = 'pending'")
    pending_listings_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT count(*) FROM edit_requests WHERE status = 'pending'")
    pending_edits_count = cursor.fetchone()[0]
    conn.close()
    
    text = "🔔 **Pending Approvals**\n\nPlease select a category to review:"
    keyboard = [
        [InlineKeyboardButton(f"🔔 Pending Approval Listings ({pending_listings_count})", callback_data="admin_pending_listings")],
        [InlineKeyboardButton(f"📝 Pending Approval Editing ({pending_edits_count})", callback_data="admin_pending_edits")],
        [InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin_back_main")]
    ]
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return MAIN_MENU

def admin_pending_edits(update, context):
    query = update.callback_query
    query.answer()
    
    page = 0
    if query.data.startswith("admin_pending_edits_page_"):
        page = int(query.data.replace("admin_pending_edits_page_", ""))
        
    PAGE_SIZE = 10
    offset = page * PAGE_SIZE
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT count(*) FROM edit_requests WHERE status = 'pending'")
    total = cursor.fetchone()[0]
    
    if total == 0:
        query.edit_message_text("✅ No pending edit requests.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_pending_menu")]]))
        conn.close()
        return MAIN_MENU
        
    cursor.execute("SELECT id, listing_id, field_name FROM edit_requests WHERE status = 'pending' ORDER BY created_at ASC LIMIT ? OFFSET ?", (PAGE_SIZE, offset))
    edits = cursor.fetchall()
    conn.close()
    
    text = f"📝 **Pending Approval Editing** (Page {page + 1})\n\n"
    keyboard = []
    
    for e in edits:
        keyboard.append([InlineKeyboardButton(f"[{e['listing_id']}] Edit: {e['field_name'].title()}", callback_data=f"admin_view_pending_edit_{e['id']}")])
        
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"admin_pending_edits_page_{page-1}"))
    if offset + PAGE_SIZE < total:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"admin_pending_edits_page_{page+1}"))
        
    if nav_row:
        keyboard.append(nav_row)
        
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_pending_menu")])
    
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return MAIN_MENU

def admin_view_pending_edit(update, context):
    query = update.callback_query
    query.answer()
    
    req_id = query.data.replace("admin_view_pending_edit_", "")
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM edit_requests WHERE id = ?", (req_id,))
    req = cursor.fetchone()
    conn.close()
    
    if not req or req['status'] != 'pending':
        query.edit_message_text("❌ Edit request not found or already processed.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_pending_edits")]]))
        return MAIN_MENU
        
    listing_id = req['listing_id']
    field = req['field_name']
    new_value = req['new_value']
    
    text = (f"📝 **Listing Edit Request**\n\n"
            f"**Listing ID:** `{listing_id}`\n"
            f"**Field:** {field.title()}\n"
            f"**New Value:**\n{new_value}\n\n"
            f"Do you approve this change?")
            
    keyboard = [
        [InlineKeyboardButton("✅ Approve", callback_data=f"admin_approve_edit_{req_id}"),
         InlineKeyboardButton("❌ Reject", callback_data=f"admin_reject_edit_{req_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_pending_edits")]
    ]
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return MAIN_MENU

def admin_pending_listings(update, context):
    query = update.callback_query
    query.answer()
    
    page = 0
    if query.data.startswith("admin_pending_page_"):
        page = int(query.data.replace("admin_pending_page_", ""))
        
    PAGE_SIZE = 10
    offset = page * PAGE_SIZE
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT count(*) FROM customer_listings WHERE status_flag = 'pending'")
    total_listings = cursor.fetchone()[0]
    
    cursor.execute("SELECT id, listing_id, platform, customer_username, price FROM customer_listings WHERE status_flag = 'pending' ORDER BY created_at ASC LIMIT ? OFFSET ?", (PAGE_SIZE, offset))
    listings = cursor.fetchall()
    conn.close()
    
    if not listings:
        query.edit_message_text("✅ No pending listings to approve.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_pending_menu")]]))
        return MAIN_MENU
        
    text = f"🔔 **Pending Listings ({total_listings} total)**\n\n"
    keyboard = []
    
    for lst in listings:
        db_id, listing_id, platform, username, price = lst
        keyboard.append([InlineKeyboardButton(f"{platform} - ${price} (@{username})", callback_data=f"admin_view_pending_{listing_id}")])
        
    # Pagination
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"admin_pending_page_{page-1}"))
    if offset + PAGE_SIZE < total_listings:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"admin_pending_page_{page+1}"))
    if nav_row:
        keyboard.append(nav_row)
        
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_pending_menu")])
    
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return MAIN_MENU

def admin_reject_listing_prompt(update, context):
    query = update.callback_query
    listing_id = query.data.replace("admin_reject_reason_", "")
    
    context.user_data["rejecting_listing_id"] = listing_id
    
    query.answer()
    query.edit_message_text(
        f"Please type the rejection reason for listing `{listing_id}` below (it will be sent to the seller):",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="admin_pending_listings")]])
    )
    return ADMIN_REJECT_REASON

def admin_delete_review(update, context):
    """Delete a user review."""
    query = update.callback_query
    review_id = query.data.replace("del_review_", "")
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_reviews WHERE id = ?", (review_id,))
    conn.commit()
    conn.close()
    
    query.answer("Review deleted!", show_alert=True)
    return admin_reviews_management(update, context)

def admin_delete_platform_review(update, context):
    """Soft-delete a platform review and update the Escrow_Log_Channel post."""
    query = update.callback_query
    review_id = query.data.replace("del_plat_rev_", "")
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT order_number FROM platform_reviews WHERE id = ?", (review_id,))
    row = cursor.fetchone()
    order_num = row[0] if row else None
    cursor.execute("UPDATE platform_reviews SET status = 'deleted' WHERE id = ?", (review_id,))
    conn.commit()
    conn.close()
    
    if order_num:
        update_escrow_post_with_review(context.bot, order_num)
    
    query.answer("Platform review deleted and post updated!", show_alert=True)
    return admin_reviews_management(update, context)

def admin_prompt_edit_review(update, context):
    """Ask admin to type a new rating and comment for an existing review."""
    query = update.callback_query
    query.answer()
    
    if query.data.startswith("edit_plat_rev_"):
        rev_id = query.data.replace("edit_plat_rev_", "")
        r_type = 'platform'
    else:
        rev_id = query.data.replace("edit_user_rev_", "")
        r_type = 'user'
        
    context.user_data['editing_review'] = {'id': rev_id, 'type': r_type}
    
    query.edit_message_text(
        f"✏️ <b>Edit Review ({r_type.title()} #{rev_id})</b>\n\n"
        "Send the new rating and comment in this format:\n"
        "<code>5|Excellent service</code>\n\n"
        "Rating must be 1-5. Or send <code>cancel</code> to abort.",
        parse_mode=ParseMode.HTML
    )
    return ADMIN_EDIT_REVIEW

def admin_handle_edit_review(update, context):
    """Process admin's edited review text."""
    text = update.message.text.strip()
    
    if text.lower() == 'cancel':
        update.message.reply_text("❌ Edit cancelled.")
        return admin_start(update, context)
        
    if '|' not in text:
        update.message.reply_text(
            "❌ Invalid format. Use <code>rating|comment</code> (e.g. <code>5|Great!</code>). Try again.",
            parse_mode=ParseMode.HTML
        )
        return ADMIN_EDIT_REVIEW
        
    try:
        rating_str, comment = text.split('|', 1)
        rating = int(rating_str.strip())
        if rating < 1 or rating > 5:
            raise ValueError("Rating out of range")
    except Exception:
        update.message.reply_text("❌ Rating must be a number between 1 and 5. Try again.")
        return ADMIN_EDIT_REVIEW
        
    edit_data = context.user_data.get('editing_review')
    if not edit_data:
        return admin_start(update, context)
        
    rev_id = edit_data['id']
    r_type = edit_data['type']
    comment = comment.strip()
    
    conn = get_connection()
    cursor = conn.cursor()
    
    if r_type == 'platform':
        cursor.execute("UPDATE platform_reviews SET rating = ?, comment = ? WHERE id = ?", (rating, comment, rev_id))
        cursor.execute("SELECT order_number FROM platform_reviews WHERE id = ?", (rev_id,))
        row = cursor.fetchone()
        order_num = row[0] if row else None
        conn.commit()
        conn.close()
        if order_num:
            update_escrow_post_with_review(context.bot, order_num)
    else:
        cursor.execute("UPDATE user_reviews SET rating = ?, comment = ? WHERE id = ?", (rating, comment, rev_id))
        conn.commit()
        conn.close()
    
    context.user_data.pop('editing_review', None)
    update.message.reply_text("✅ <b>Review updated successfully!</b>", parse_mode=ParseMode.HTML)
    return admin_start(update, context)

def admin_view_pending_listing(update, context):
    query = update.callback_query
    listing_id = query.data.replace("admin_view_pending_", "")
    query.answer()
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM customer_listings WHERE listing_id = ?", (listing_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        query.edit_message_text("❌ Listing not found.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_pending_listings")]]))
        return MAIN_MENU
    
    listing = {
        'listing_id': row_get(row, 'listing_id'),
        'platform': row_get(row, 'platform'),
        'account_type': row_get(row, 'account_type'),
        'channel_age': row_get(row, 'channel_age', 'N/A') or 'N/A',
        'subscribers': row_get(row, 'subscribers', 0),
        'views': row_get(row, 'views', 0),
        'niche': row_get(row, 'niche', 'Mixed'),
        'features': row_get(row, 'features', 'N/A'),
        'monetization': row_get(row, 'monetization', 'Enabled'),
        'region': row_get(row, 'region', 'USA'),
        'status': row_get(row, 'status', 'No Strikes'),
        'price': row_get(row, 'price', 0),
        'seller_contact': row_get(row, 'seller_contact'),
        'admin_notes': row_get(row, 'admin_notes', ''),
        'growth': row_get(row, 'growth', '')
    }
    
    text = (
        f"🆕 <b>NEW CUSTOMER LISTING FOR REVIEW</b>\n\n"
        f"📋 <b>Listing Details:</b>\n"
        f"• 🆔 Listing ID: <code>{listing['listing_id']}</code>\n"
    )
    # Safely handle customer username and id from the row since they are not in the listing dict
    c_username = row_get(row, 'customer_username', 'Unknown')
    c_id = row_get(row, 'customer_id', 'Unknown')
    channel_link = row_get(row, 'channel_link', '')
    raw_screenshots = str(row_get(row, 'screenshots', '') or '')
    n_screenshots = len(raw_screenshots.split(',')) if raw_screenshots else 0
    import html as _html_mod
    def _s(v): return _html_mod.escape(str(v)) if v else 'N/A'

    text += (
        f"• 👤 Seller: @{_s(c_username)} (ID: <code>{_s(c_id)}</code>)\n"
        f"• 🔗 Account Link: <a href='{_s(channel_link)}'>Link</a>\n"
        f"• 📱 Platform: {_s(listing['platform'])}\n"
        f"• 📅 Channel Age: {_s(listing['channel_age'])}\n"
        f"• 👤 Type: {_s(listing['account_type'])}\n"
        f"• 👥 Subscribers: {_s(listing['subscribers'])}\n"
        f"• 👀 Views: {_s(listing['views'])}\n"
        f"• 💰 Price: ${_s(listing['price'])}\n"
        f"• 📸 Screenshots: {n_screenshots} uploaded\n"
        f"• 📞 Contact: {_s(listing['seller_contact'])}\n"
        f"• ⏰ Submitted: {_s(row_get(row, 'created_at', 'N/A'))}\n\n"
        f"Approve this listing to publish it on @smyard"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_listing_{listing_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"admin_reject_reason_{listing_id}")
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_pending_listings")]
    ]
    
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return MAIN_MENU

def admin_handle_reject_reason(update, context):
    text = update.message.text
    listing_id = context.user_data.get("rejecting_listing_id")
    
    if not listing_id:
        # Fallback if state is reached incorrectly
        update.message.reply_text("⚠️ No listing selected for rejection. Please go back and try again.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Dashboard", callback_data="admin_back_main")]]))
        return MAIN_MENU

    if text.lower() == 'cancel':
        context.user_data.pop("rejecting_listing_id", None)
        update.message.reply_text("Rejection cancelled.")
        return admin_start(update, context)
        
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT customer_id FROM customer_listings WHERE listing_id = ?", (listing_id,))
    res = cursor.fetchone()
    
    if res:
        seller_id = res[0]
        cursor.execute("UPDATE customer_listings SET status_flag = 'rejected' WHERE listing_id = ?", (listing_id,))
        conn.commit()
        
        # Notify Seller
        try:
            context.bot.send_message(
                chat_id=seller_id,
                text=f"❌ **Your listing `{listing_id}` was rejected.**\n\n**Reason:** {text}",
                parse_mode="Markdown"
            )
        except:
            pass
            
        update.message.reply_text(f"✅ Listing {listing_id} rejected. Seller notified.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin_back_main")]]))
    
    conn.close()
    return MAIN_MENU


# ===== GLOBAL CALLBACK HANDLER =====

# CUSTOMER CALLBACK
def customer_callback(update, context):
    query = update.callback_query
    query.answer()
    data = query.data
    logger.debug("Customer callback: %s", data)

    routes = {
        "start_customer_mode": customer_start,
        "customer_main": customer_start,
        "open_dashboard": customer_start,
        "buyer_start": buyer_start,
        "enter_product_id": buyer_enter_product_id,
        "confirm_payment": confirm_payment,
        "seller_start": seller_start,
        "seller_list_account": seller_list_account,
        "customer_add_screenshots": customer_add_screenshots,
        "customer_skip_screenshots": customer_skip_screenshots,
        "customer_submit_listing": customer_submit_listing,
        "back_to_customer": back_to_customer,
        "back_to_escrow_info": back_to_escrow_info,
        "back_to_seller_info": back_to_seller_info,
        "back_to_seller_platform": back_to_seller_platform,
        "back_to_payment_methods": back_to_payment_methods,
        "admin_panel": admin_panel,
        "user_profile_feedback": user_profile_feedback,
        "view_my_listings": show_user_listings,
        "return_listings_view": show_user_listings,
        "back_to_customer_start": customer_start,
        "start_sell_flow": seller_start,
        "customer_support": customer_support_callback,
        "customer_help_center": customer_help_center,
        "customer_trigger_sold": customer_manage_item_callback,
        "customer_confirm_sold_execution": customer_confirm_sold_callback,
        "browse_menu": browse_menu,
        "browse_filter_menu": browse_filter_menu,
        "browse_toggle_monetized": browse_toggle_monetized,
        "browse_clear_filters": browse_clear_filters,
        "browse_apply_filters": browse_apply_filters,
        "browse_set_price": browse_set_price_prompt,
        "browse_set_subs": browse_set_subs_prompt,
        "browse_set_age": browse_set_age_prompt,
        "browse_set_keyword": browse_set_keyword_prompt,
    }
    
    # --- ROUTING ---
    if data in routes:
        return routes[data](update, context)
        
    # --- DYNAMIC HUB HANDLERS ---
    if data.startswith("manage_item_") or data.startswith("bump_item_") or data.startswith("edit_listing_") or data.startswith("edit_field_") or data == "cancel_edit":
        return customer_manage_item_callback(update, context)
    elif data.startswith("pay_"):
        return handle_payment_method(update, context)
    elif data.startswith("customer_platform_"):
        return customer_platform_callback(update, context)
    elif data == "customer_edit_again":
        query.edit_message_text("✏️ Send corrected details in same format as before:")
        return SELLER_DETAILS
    elif data == "customer_cancel_listing":
        query.edit_message_text("❌ Listing cancelled.")
        return customer_start(update, context)
    elif data.startswith("browse_platform_"):
        return browse_platform_callback(update, context)
    elif data.startswith("browse_page_"):
        return browse_page_callback(update, context)
    elif data.startswith("browse_view_"):
        return browse_view_listing(update, context)
    elif data.startswith("buy_from_browse_"):
        return buy_from_browse_callback(update, context)
    elif data.startswith("txlog_page_"):
        return transactions_log_view(update, context)
    elif data == "customer_my_orders":
        return customer_my_orders(update, context)
    elif data.startswith("customer_order_"):
        return customer_view_order_detail(update, context)
    elif data.startswith("confirm_pay_escrow_"):
        return confirm_pay_escrow(update, context)
    elif data.startswith("my_listings_page_"):
        return show_user_listings(update, context)
    elif data.startswith("my_orders_page_"):
        return customer_my_orders(update, context)
    elif data.startswith("profile_page_"):
        return user_profile_feedback(update, context)
    elif data.startswith("leave_review_platform_") or data.startswith("leave_review_user_") or data.startswith("leave_review_"):
        return customer_leave_review_prompt(update, context)
    elif data.startswith("rate_order_"):
        return customer_rate_order(update, context)
    elif data == "upgrade_badge_menu":
        return customer_upgrade_badge_menu(update, context)
    elif data == "my_current_badge":
        return customer_my_current_badge(update, context)
    elif data == "purchase_upgrade_menu":
        return customer_purchase_upgrade_menu(update, context)
    elif data.startswith("upgrade_tier_"):
        return customer_process_upgrade(update, context)
    elif data == "check_upgrade_payment":
        query.edit_message_text(
            "Our team will verify your payment and activate your badge within minutes.\n"
            "You will receive a notification once it's active.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Dashboard", callback_data="back_to_customer_start")]])
        )
        return CUSTOMER_MENU
    elif data == "back_customer_main":
        return customer_start(update, context)

    # --- SELLER PROFILE SUB-MENUS ---
    elif data.startswith("sp_main_"):
        return seller_profile_main_menu(update, context)
    elif data.startswith("help_view_"):
        return customer_help_center_view(update, context)
    elif data.startswith("sp_listings_"):
        return seller_profile_listings(update, context)
    elif data.startswith("sp_feedback_"):
        return seller_profile_feedback(update, context)
    
    # --- REVIEW CALLBACKS (handled here so ConversationHandler doesn't silently swallow them) ---\nelif data.startswith('rate_plat_') or data.startswith('rate_user_'):'rate_plat_') or data.startswith('rate_user_'):

        return handle_review_rating(update, context)
    elif data.startswith('rvcmt_'):
        return handle_review_comment_preset(update, context)
    elif data.startswith('rv_write_'):
        return handle_review_write_prompt(update, context)

    logger.warning("Unhandled callback data: %s", data)
    return CUSTOMER_MENU


def customer_help_center(update, context):
    """Dynamically renders the Help Center from the Guidance Posts Pool."""
    query = update.callback_query
    
    if query:
        query.answer()
        chat_id = query.message.chat_id
        try:
            query.delete_message()
        except Exception:
            pass
    else:
        chat_id = update.message.chat_id

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title FROM ap_guidance_posts ORDER BY id ASC")
        posts = cursor.fetchall()
    except Exception:
        posts = []
    finally:
        conn.close()

    if not posts:
        keyboard = [[InlineKeyboardButton("🔙 Back to Dashboard", callback_data="back_to_customer_start")]]
        context.bot.send_message(
            chat_id,
            "📢 <b>Help Center</b>\n\nNo guidance posts are available yet. Check back soon!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
        return CUSTOMER_MENU

    keyboard = []
    for post_id, title in posts:
        keyboard.append([InlineKeyboardButton(title, callback_data=f"help_view_{post_id}")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Dashboard", callback_data="back_to_customer_start")])

    context.bot.send_message(
        chat_id,
        "📢 <b>Help Center</b>\n\nSelect a topic below to read the full guide:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )
    return CUSTOMER_MENU


def customer_help_center_view(update, context):
    """Shows the content of a single guidance post with multi-media support."""
    query = update.callback_query
    query.answer()
    post_id = int(query.data.replace("help_view_", ""))
    chat_id = query.message.chat_id
    bot = context.bot

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT title, content_text FROM ap_guidance_posts WHERE id = ?", (post_id,))
        post = cursor.fetchone()
        # Fetch multi-media from new table
        cursor.execute(
            "SELECT file_id, media_type FROM ap_guidance_media WHERE post_id = ? ORDER BY sort_order ASC",
            (post_id,)
        )
        media_rows = cursor.fetchall()
        # Fallback: also check old single-media columns on ap_guidance_posts
        if not media_rows:
            cursor.execute("SELECT media_file_id, media_type FROM ap_guidance_posts WHERE id = ? AND media_file_id IS NOT NULL", (post_id,))
            legacy = cursor.fetchone()
            if legacy and legacy[0]:
                media_rows = [(legacy[0], legacy[1])]
    except Exception:
        post = None
        media_rows = []
    finally:
        conn.close()

    back_kb = [[InlineKeyboardButton("🔙 Back to Help Center", callback_data="customer_help_center")]]

    # Delete old message to avoid 'no text to edit' errors
    try:
        query.delete_message()
    except Exception:
        pass

    if not post:
        bot.send_message(chat_id, "❌ This guide could not be found. It may have been removed.",
                         reply_markup=InlineKeyboardMarkup(back_kb))
        return CUSTOMER_MENU

    title, content_text = post
    header_text = f"📢 <b>{title}</b>\n\n{content_text or ''}"

    photos = [(fid, mt) for fid, mt in media_rows if mt == 'photo']
    videos = [(fid, mt) for fid, mt in media_rows if mt == 'video']

    if len(photos) > 1:
        # Send as a photo album, put text caption on the last photo
        from telegram import InputMediaPhoto
        media_group = []
        for idx, (fid, _) in enumerate(photos):
            if idx == len(photos) - 1:
                media_group.append(InputMediaPhoto(fid, caption=header_text, parse_mode=ParseMode.HTML))
            else:
                media_group.append(InputMediaPhoto(fid))
        bot.send_media_group(chat_id, media_group)
        bot.send_message(chat_id, "⬆️ Refer to the images above.",
                         reply_markup=InlineKeyboardMarkup(back_kb))
    elif len(photos) == 1:
        bot.send_photo(chat_id, photos[0][0], caption=header_text, parse_mode=ParseMode.HTML,
                       reply_markup=InlineKeyboardMarkup(back_kb))
    elif videos:
        bot.send_video(chat_id, videos[0][0], caption=header_text, parse_mode=ParseMode.HTML,
                       reply_markup=InlineKeyboardMarkup(back_kb))
    else:
        # Text-only post
        bot.send_message(chat_id, header_text, parse_mode=ParseMode.HTML,
                         reply_markup=InlineKeyboardMarkup(back_kb))

    return CUSTOMER_MENU


def customer_support_callback(update, context):
    """Displays the Support & FAQ panel"""
    query = update.callback_query
    query.answer()
    
    text = (
        "🎧 **SMyards Support & FAQ**\n\n"
        "🤝 **How does escrow work?**\n"
        "The buyer pays the secure escrow bot. Once the funds are confirmed, the seller safely hands over the channel assets. After verification, funds are released to the seller.\n\n"
        "📞 Need urgent admin help? Contact @smyards directly."
    )
    keyboard = [[InlineKeyboardButton("🔙 Back to Dashboard", callback_data="back_to_customer_start")]]
    query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    # Stays in the customer menu state
    return CUSTOMER_MENU

def verify_payment(update, context):
    """Admin verifies payment"""
    query = update.callback_query
    query.answer()
    order_number = query.data.replace("verify_payment_", "")
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE orders SET payment_status = 'verified' WHERE order_number = ?", (order_number,))
        cursor.execute("SELECT customer_id, product_id, total_price, customer_username, seller_id FROM orders WHERE order_number = ?", (order_number,))
        result = cursor.fetchone()
        
        group_assigned = False
        group_invite_link = None
        
        # Auto-assign Deal Group from pool
        cursor.execute("SELECT id, chat_id, invite_link FROM available_groups WHERE status = 'available' ORDER BY created_at ASC LIMIT 1")
        available_group = cursor.fetchone()
        
        if available_group and result:
            group_db_id, group_chat_id, group_invite_link = available_group
            customer_id, product_id, total_price, buyer_username, seller_id = result
            
            # Mark group in use and update order
            cursor.execute("UPDATE available_groups SET status = 'in_use', assigned_order_id = ? WHERE id = ?", (order_number, group_db_id))
            cursor.execute("UPDATE orders SET transaction_group_id = ?, transaction_group_link = ?, order_status = 'group_link_set' WHERE order_number = ?", 
                           (group_chat_id, group_invite_link, order_number))
            group_assigned = True
            
            # Attempt to rename the group
            try:
                context.bot.set_chat_title(chat_id=group_chat_id, title=f"SMyards - Transaction {order_number} Group")
            except Exception as e:
                logger.error(f"Error renaming group {group_chat_id}: {e}")
                
            # Notify Seller
            if seller_id:
                try:
                    context.bot.send_message(
                        chat_id=seller_id,
                        text=f"✅ **Payment Verified for order {order_number}!**\n\nA secure Deal Group has been created. Join here to hand over the account:\n{group_invite_link}"
                    )
                except Exception as e:
                    pass
            
        conn.commit()
    finally:
        conn.close()
    
    if result:
        try:
            if group_assigned:
                customer_text = f"✅ **Payment Verified!**\n\nYour payment for order `{order_number}` has been verified!\n\nYour secure Deal Group has been created automatically. Join here to proceed:\n{group_invite_link}"
            else:
                customer_text = f"✅ **Payment Verified!**\n\nYour payment for order `{order_number}` has been verified!\n\nOur agent will now contact the seller and create a secure group chat for the transaction."
            context.bot.send_message(
                chat_id=result[0],
                text=customer_text,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Error notifying customer: {e}")
            
    if group_assigned:
        query.edit_message_text(f"✅ Payment for order `{order_number}` verified!\n🤖 A Deal Group was automatically assigned from the pool.", parse_mode=ParseMode.MARKDOWN)
    else:
        query.edit_message_text(f"✅ Payment for order `{order_number}` verified!\nCustomer has been notified.\n⚠️ No Deal Groups available in pool. You must create one manually.", parse_mode=ParseMode.MARKDOWN)





# ===== ORDER MANAGEMENT SYSTEM ===== #

def add_orders_table_columns():
    """Add missing columns to orders table for order management."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Check which columns exist
        cursor.execute("PRAGMA table_info(orders)")
        existing_cols = {col[1] for col in cursor.fetchall()}
        
        # Add seller_id if missing
        if 'seller_id' not in existing_cols:
            cursor.execute("ALTER TABLE orders ADD COLUMN seller_id INTEGER")
            logger.info("Added seller_id column to orders table")
        
        # Add transaction_group_link if missing
        if 'transaction_group_link' not in existing_cols:
            cursor.execute("ALTER TABLE orders ADD COLUMN transaction_group_link TEXT")
            logger.info("Added transaction_group_link column to orders table")
        
        # Add payment_confirmed_at if missing
        if 'payment_confirmed_at' not in existing_cols:
            cursor.execute("ALTER TABLE orders ADD COLUMN payment_confirmed_at DATETIME")
            logger.info("Added payment_confirmed_at column to orders table")
        
        # Add completed_at if missing
        if 'completed_at' not in existing_cols:
            cursor.execute("ALTER TABLE orders ADD COLUMN completed_at DATETIME")
            logger.info("Added completed_at column to orders table")
        
        # Add order_status if missing (pending, group_link_set, completed)
        if 'order_status' not in existing_cols:
            cursor.execute("ALTER TABLE orders ADD COLUMN order_status TEXT DEFAULT 'pending'")
            logger.info("Added order_status column to orders table")
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error adding orders columns: {e}")


def admin_orders_panel(update, context):
    """Show admin the pending orders panel (only orders where payment is confirmed)."""
    query = update.callback_query
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, order_number, product_id, platform, total_price, escrow_fee, 
               customer_username, order_status, created_at
        FROM orders
        WHERE payment_status = 'confirmed' AND order_status IN ('pending', 'group_link_set')
        ORDER BY created_at DESC
        LIMIT 10
    """)
    orders = cursor.fetchall()
    conn.close()

    if not orders:
        text = "📦 <b>PENDING ORDERS</b>\n\n✅ No pending orders right now!"
        keyboard = [
            [InlineKeyboardButton("⏳ View Pre-Pending Orders", callback_data="admin_pre_pending_orders")],
            [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_back_main")]
        ]
        query.answer()
        query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        return MAIN_MENU

    text = "📦 <b>PENDING ORDERS</b>\n\n"
    keyboard = [
        [InlineKeyboardButton("⏳ View Pre-Pending Orders", callback_data="admin_pre_pending_orders")]
    ]

    for order in orders:
        order_id, order_num, product_id, platform, price, fee, buyer, status, created = order
        status_emoji = "⏳" if status == "pending" else "🔗"
        
        text += (
            f"{status_emoji} <b>{order_num}</b> | {platform}\n"
            f"💰 ${price:,.0f} (Fee: ${fee:.2f})\n"
            f"👤 {buyer}\n"
            f"📅 {created[:10]}\n\n"
        )
        
        keyboard.append([
            InlineKeyboardButton(f"View {order_num}", callback_data=f"admin_order_{order_id}")
        ])

    keyboard.append([InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_back_main")])
    
    query.answer()
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return MAIN_MENU

def admin_pre_pending_orders_panel(update, context):
    """Show admin orders that haven't paid escrow yet (payment_status = 'pending')."""
    query = update.callback_query
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, order_number, product_id, platform, total_price, escrow_fee, 
               customer_username, order_status, created_at
        FROM orders
        WHERE payment_status = 'pending' AND order_status = 'pending'
        ORDER BY created_at DESC
        LIMIT 10
    """)
    orders = cursor.fetchall()
    conn.close()

    if not orders:
        text = "⏳ <b>PRE-PENDING ORDERS</b>\n\n✅ No unpaid pre-pending orders right now!"
        keyboard = [[InlineKeyboardButton("🔙 Back to Orders", callback_data="admin_orders_panel")]]
        query.answer()
        query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        return MAIN_MENU

    text = "⏳ <b>PRE-PENDING ORDERS (Unpaid Escrow)</b>\n\n"
    keyboard = []

    for order in orders:
        order_id, order_num, product_id, platform, price, fee, buyer, status, created = order
        
        text += (
            f"⏳ <b>{order_num}</b> | {platform}\n"
            f"💰 Acc: ${price:,.0f} | Fee: ${fee:.2f}\n"
            f"👤 Buyer: {buyer}\n"
            f"🆔 Prod: {product_id}\n"
            f"📅 {created[:10]}\n\n"
        )
        keyboard.append([
            InlineKeyboardButton(f"View {order_num}", callback_data=f"admin_order_{order_id}")
        ])

    keyboard.append([InlineKeyboardButton("🔙 Back to Orders", callback_data="admin_orders_panel")])
    
    query.answer()
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return MAIN_MENU

def admin_view_order_detail(update, context):
    """Show full order details for admin."""
    query = update.callback_query
    order_id = int(query.data.replace("admin_order_", ""))
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM orders WHERE id = ?
    """, (order_id,))
    order = cursor.fetchone()
    
    if not order:
        query.answer("Order not found.", show_alert=True)
        return MAIN_MENU
    
    # Get column names
    cursor.execute("PRAGMA table_info(orders)")
    columns = [col[1] for col in cursor.fetchall()]
    order_dict = dict(zip(columns, order))
    conn.close()

    # Get listing info for product details
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT account_type, niche FROM listings WHERE listing_id = ?", 
                   (order_dict['product_id'],))
    listing = cursor.fetchone()
    conn.close()

    account_type = listing[0] if listing else "N/A"
    niche = listing[1] if listing else "N/A"

    status_badge = {
        'pending': '⏳ Awaiting Payment',
        'group_link_set': '🔗 Group Link Set',
        'completed': '✅ Completed'
    }.get(order_dict['order_status'], order_dict['order_status'])

    text = (
        f"<b>📦 ORDER DETAILS</b>\n\n"
        f"<b>Order Number:</b> <code>{order_dict['order_number']}</code>\n"
        f"<b>Status:</b> {status_badge}\n\n"
        f"<b>📋 ACCOUNT INFO</b>\n"
        f"• <b>Account ID:</b> <code>{order_dict['product_id']}</code>\n"
        f"• <b>Platform:</b> {order_dict['platform']}\n"
        f"• <b>Type:</b> {account_type}\n"
        f"• <b>Niche:</b> {niche}\n\n"
        f"<b>💳 PRICING</b>\n"
        f"• <b>Account Price:</b> ${order_dict['total_price']:,.2f}\n"
        f"• <b>Escrow Fee:</b> ${order_dict['escrow_fee']:.2f}\n\n"
        f"<b>👥 BUYER INFO</b>\n"
        f"• <b>Username:</b> @{order_dict['customer_username']}\n"
        f"• <b>ID:</b> <code>{order_dict['customer_id']}</code>\n\n"
        f"<b>📅 TIMELINE</b>\n"
        f"• <b>Order Created:</b> {order_dict['created_at']}\n"
        f"• <b>Payment Confirmed:</b> {order_dict['payment_confirmed_at'] or 'Pending'}\n\n"
        f"<b>🔗 GROUP LINK STATUS</b>\n"
    )
    
    if order_dict['transaction_group_link']:
        text += f"✅ Set: {order_dict['transaction_group_link']}\n"
    else:
        text += f"⏳ Not yet set\n"

    keyboard = []
    
    if not order_dict['transaction_group_link']:
        keyboard.append([InlineKeyboardButton("🔗 Add Group Link", callback_data=f"add_group_link_{order_id}")])
    
    if order_dict['transaction_group_link'] and order_dict['order_status'] != 'completed':
        keyboard.append([InlineKeyboardButton("✅ Mark as Completed", callback_data=f"mark_completed_{order_id}")])
    
    # Allow deletion of pre-pending orders
    if order_dict['order_status'] == 'pending' and order_dict['payment_status'] == 'pending':
        keyboard.append([InlineKeyboardButton("🗑️ Delete This Order", callback_data=f"admin_delete_order_{order_id}")])
    
    keyboard.append([InlineKeyboardButton("📦 Back to Orders", callback_data="admin_orders_panel")])
    
    query.answer()
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return MAIN_MENU


def admin_delete_prepending_order(update, context):
    """Delete a pre-pending order from the database."""
    query = update.callback_query
    order_id = int(query.data.replace("admin_delete_order_", ""))

    conn = get_connection()
    cursor = conn.cursor()
    # Safety check: only allow deleting orders that are still pre-pending
    cursor.execute("SELECT order_number, order_status, payment_status FROM orders WHERE id = ?", (order_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        query.answer("Order not found.", show_alert=True)
        return MAIN_MENU

    order_number, order_status, payment_status = row
    if order_status != 'pending' or payment_status != 'pending':
        conn.close()
        query.answer("Only pre-pending orders can be deleted.", show_alert=True)
        return MAIN_MENU

    cursor.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()

    query.answer(f"Order {order_number} deleted.", show_alert=True)
    # Refresh the pre-pending orders list
    return admin_pre_pending_orders_panel(update, context)

def customer_my_orders(update, context):
    """Show customer their orders."""
    query = update.callback_query if update.callback_query else None
    user_id = update.effective_user.id
    
    page = 0
    if query and query.data.startswith("my_orders_page_"):
        page = int(query.data.replace("my_orders_page_", ""))
        context.user_data['my_orders_page'] = page
    else:
        page = context.user_data.get('my_orders_page', 0)
        
    PAGE_SIZE = 10
    offset = page * PAGE_SIZE
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM orders WHERE customer_id = ?", (user_id,))
    total = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT id, order_number, product_id, platform, total_price, escrow_fee,
               order_status, created_at
        FROM orders
        WHERE customer_id = ?
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """, (user_id, PAGE_SIZE, offset))
    orders = cursor.fetchall()
    conn.close()

    if not orders and total == 0:
        text = "🛒 <b>My Orders</b>\n\n📭 You haven't placed any orders yet.\n\nUse /dashboard to browse listings!"
        keyboard = [[InlineKeyboardButton("🔙 Back to Dashboard", callback_data="back_to_customer_start")]]
        
        if query:
            query.answer()
            query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        else:
            update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        return CUSTOMER_MENU

    text = f"🛒 <b>My Orders</b> (Page {page + 1})\n\n"
    keyboard = []

    for order in orders:
        order_id, order_num, product_id, platform, price, fee, status, created = order
        status_emoji = {"pending": "⏳", "group_link_set": "🔗", "completed": "✅"}.get(status, "❓")
        
        text += (
            f"{status_emoji} <b>{order_num}</b> | {platform} | ${price:,.0f}\n"
        )
        
        keyboard.append([InlineKeyboardButton(f"View {order_num}", callback_data=f"customer_order_{order_id}")])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️ Previous", callback_data=f"my_orders_page_{page-1}"))
    if offset + PAGE_SIZE < total:
        nav_row.append(InlineKeyboardButton("Next ▶️", callback_data=f"my_orders_page_{page+1}"))
    
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton("🔙 Back to Dashboard", callback_data="back_to_customer_start")])
    
    if query:
        query.answer()
        query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    else:
        update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    
    return CUSTOMER_MENU


def customer_view_order_detail(update, context):
    """Show customer their order details with COMPLETE info including group link."""
    query = update.callback_query
    order_id = int(query.data.replace("customer_order_", ""))
    user_id = update.effective_user.id
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Fetch complete order details
    cursor.execute("""
        SELECT id, order_number, product_id, platform, total_price, escrow_fee,
               order_status, payment_status, payment_confirmed_at, completed_at,
               seller_id, customer_username, created_at, transaction_group_link
        FROM orders 
        WHERE id = ? AND customer_id = ?
    """, (order_id, user_id))
    order = cursor.fetchone()
    
    if not order:
        query.answer("Order not found.", show_alert=True)
        return CUSTOMER_MENU
    
    (order_id, order_num, product_id, platform, total_price, escrow_fee,
     order_status, payment_status, payment_confirmed_at, completed_at,
     seller_id, buyer_username, created_at, group_link) = order
    
    # Fetch listing details
    cursor.execute("""
        SELECT account_type, subscribers, views, niche, monetization, seller_contact
        FROM listings
        WHERE listing_id = ?
    """, (product_id,))
    listing = cursor.fetchone()
    
    account_type = ""
    subscribers = "N/A"
    views = "N/A"
    niche = "N/A"
    monetization = "N/A"
    
    if listing:
        account_type, subs, views_num, niche, monetization, _ = listing
        subscribers = format_number(subs) if subs else "N/A"
        views = format_number(views_num) if views_num else "N/A"
    
    # Fetch seller info
    seller_username = "Unknown Seller"
    if seller_id:
        cursor.execute(
            "SELECT customer_username FROM customer_listings WHERE customer_id = ? ORDER BY created_at DESC LIMIT 1",
            (seller_id,)
        )
        seller_result = cursor.fetchone()
        if seller_result and seller_result[0]:
            seller_username = seller_result[0]
    
    conn.close()

    # Build status indicators
    status_emoji = {"pending": "⏳", "group_link_set": "🔗", "completed": "✅"}.get(order_status, "❓")
    payment_emoji = "✅" if payment_status == "confirmed" else "⏳"
    
    # Build comprehensive order details
    text = (
        f"{status_emoji} <b>ORDER {order_num}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        f"<b>📋 ACCOUNT DETAILS</b>\n"
        f"• 🆔 <b>Account ID:</b> <code>{product_id}</code>\n"
        f"• 📱 <b>Platform:</b> {platform}\n"
        f"• 👤 <b>Account Type:</b> {account_type}\n"
        f"• 🗃️ <b>Niche:</b> {niche}\n"
        f"• 👥 <b>Subscribers:</b> {subscribers}\n"
        f"• 👀 <b>Views:</b> {views}\n"
        f"• 💲 <b>Monetization:</b> {monetization}\n\n"
        
        f"<b>💰 PRICING & ESCROW</b>\n"
        f"• 💵 <b>Account Price:</b> ${total_price:,.2f}\n"
        f"• 🛡️ <b>Escrow Fee (5%):</b> ${escrow_fee:.2f}\n\n"
        
        f"<b>👥 PARTIES</b>\n"
        f"• 🛍️ <b>You (Buyer):</b> @{buyer_username}\n"
        f"• 🎯 <b>Seller:</b> @{seller_username}\n"
        f"• 👨‍⚖️ <b>Escrow Agent:</b> @smyards\n\n"
        
        f"<b>📊 ORDER STATUS</b>\n"
        f"• {payment_emoji} <b>Payment:</b> {'Confirmed ✅' if payment_status == 'confirmed' else 'Pending ⏳'}\n"
        f"• {status_emoji} <b>Order:</b> {order_status.replace('_', ' ').title()}\n\n"
        
        f"<b>📅 TIMELINE</b>\n"
        f"• 📝 <b>Created:</b> {created_at}\n"
    )
    
    if payment_confirmed_at:
        text += f"• ✅ <b>Payment Confirmed:</b> {payment_confirmed_at}\n"
    
    if completed_at:
        text += f"• 🎉 <b>Completed:</b> {completed_at}\n"
    
    text += "\n━━━━━━━━━━━━━━━━━━━━━━"
    
    keyboard = []
    
    # Add group link button if it exists
    if group_link and group_link.startswith('https://t.me/'):
        text += (
            f"\n\n🔗 <b>DEAL GROUP LINK</b>\n"
            f"Join the secure group where you, the seller, and escrow agent complete the transaction."
        )
        keyboard.append([
            InlineKeyboardButton("🔗 JOIN DEAL GROUP", url=group_link),
        ])
    elif order_status == "pending":
        text += f"\n\n⏳ <b>Waiting for admin to create the deal group...</b>"
        
    # Check if they can leave separate reviews for the platform and the other party
    if order_status == "completed":
        conn = get_connection()
        c = conn.cursor()
        c.execute(
            "SELECT id FROM user_reviews WHERE order_number = ? AND reviewer_id = ? AND target_user_id != 0",
            (order_num, user_id)
        )
        has_user_review = c.fetchone()
        c.execute(
            "SELECT id FROM platform_reviews WHERE order_number = ? AND reviewer_id = ? AND status = 'active'",
            (order_num, user_id)
        )
        has_platform_review = c.fetchone()
        conn.close()
        
        if not has_user_review:
            keyboard.append([InlineKeyboardButton("⭐ Review Other Party", callback_data=f"leave_review_user_{order_num}")])
        if not has_platform_review:
            keyboard.append([InlineKeyboardButton("⭐ Review Platform", callback_data=f"leave_review_platform_{order_num}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Back to My Orders", callback_data="customer_my_orders")])
    
    query.answer()
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CUSTOMER_MENU

def customer_leave_review_prompt(update, context):
    query = update.callback_query
    data = query.data

    if data.startswith("leave_review_platform_"):
        order_num = data.replace("leave_review_platform_", "")
        text = f"⭐ <b>Leave a Review for SMYARDS Platform</b>\n\nHow would you rate our Escrow service for order {order_num}?"
        keyboard = [[
            InlineKeyboardButton("1 ⭐", callback_data=f"rate_plat_{order_num}_1"),
            InlineKeyboardButton("2 ⭐", callback_data=f"rate_plat_{order_num}_2"),
            InlineKeyboardButton("3 ⭐", callback_data=f"rate_plat_{order_num}_3"),
            InlineKeyboardButton("4 ⭐", callback_data=f"rate_plat_{order_num}_4"),
            InlineKeyboardButton("5 ⭐", callback_data=f"rate_plat_{order_num}_5")
        ]]
    elif data.startswith("leave_review_user_"):
        order_num = data.replace("leave_review_user_", "")
        text = f"⭐ <b>Leave a Review for Order {order_num}</b>\n\nHow would you rate your experience with the other party?"
        keyboard = [[
            InlineKeyboardButton("1 ⭐", callback_data=f"rate_user_{order_num}_1"),
            InlineKeyboardButton("2 ⭐", callback_data=f"rate_user_{order_num}_2"),
            InlineKeyboardButton("3 ⭐", callback_data=f"rate_user_{order_num}_3"),
            InlineKeyboardButton("4 ⭐", callback_data=f"rate_user_{order_num}_4"),
            InlineKeyboardButton("5 ⭐", callback_data=f"rate_user_{order_num}_5")
        ]]
    else:
        order_num = data.replace("leave_review_", "")
        text = f"⭐ <b>Leave a Review for Order {order_num}</b>\n\nChoose what you want to review:"
        keyboard = [
            [InlineKeyboardButton("⭐ Review Other Party", callback_data=f"leave_review_user_{order_num}")],
            [InlineKeyboardButton("⭐ Review Platform", callback_data=f"leave_review_platform_{order_num}")]
        ]

    keyboard.append([InlineKeyboardButton("🔙 Cancel", callback_data="customer_my_orders")])
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CUSTOMER_MENU

def customer_rate_order(update, context):
    query = update.callback_query
    parts = query.data.split("_")
    order_num = parts[2]
    stars = parts[3]
    
    user_id = update.effective_user.id
    username = update.effective_user.username or str(user_id)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get order info to determine target user
    cursor.execute("SELECT customer_id, customer_username, seller_id FROM orders WHERE order_number = ?", (order_num,))
    order_data = cursor.fetchone()
    
    if not order_data:
        conn.close()
        query.answer("Order not found.", show_alert=True)
        query.edit_message_text("❌ Order not found.", reply_markup=None)
        return ConversationHandler.END
        
    buyer_id, buyer_username, seller_id = order_data
    
    # Determine who is reviewing who
    if user_id == buyer_id:
        target_id = seller_id
        cursor.execute("SELECT customer_username FROM customer_listings WHERE customer_id = ? LIMIT 1", (seller_id,))
        res = cursor.fetchone()
        target_username = res[0] if res else "Seller"
    elif user_id == seller_id:
        target_id = buyer_id
        target_username = buyer_username
    else:
        conn.close()
        query.answer("You are not part of this order.", show_alert=True)
        query.edit_message_text("❌ You are not authorized to review this order.", reply_markup=None)
        return ConversationHandler.END
        
    try:
        cursor.execute("""
            INSERT INTO user_reviews (order_number, reviewer_id, reviewer_name, target_user_id, target_username, rating, comment)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (order_num, user_id, username, target_id, target_username, int(stars), "Great transaction! (Auto-rated)"))
        conn.commit()
        query.answer("Review submitted!", show_alert=True)
        query.edit_message_text(f"✅ Thank you! You rated @{target_username} {stars} ⭐", reply_markup=None)
    except sqlite3.IntegrityError:
        query.answer("You already submitted a review for this.", show_alert=True)
        query.edit_message_text("⚠️ You have already submitted a review.", reply_markup=None)
    finally:
        conn.close()
        
    return ConversationHandler.END

def customer_rate_platform(update, context):
    query = update.callback_query
    parts = query.data.split("_")
    order_num = parts[2]
    stars = parts[3]
    
    user_id = update.effective_user.id
    username = update.effective_user.username or str(user_id)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO platform_reviews (order_number, reviewer_id, reviewer_name, rating, comment)
            VALUES (?, ?, ?, ?, ?)
        """, (order_num, user_id, username, int(stars), "Great platform! (Auto-rated)"))
        conn.commit()
        update_escrow_post_with_review(context.bot, order_num)
        query.answer("Platform review submitted!", show_alert=True)
        query.edit_message_text(f"✅ Thank you! You rated the SMYARDS Platform {stars} ⭐", reply_markup=None)
    except sqlite3.IntegrityError:
        query.answer("You already submitted a review for this.", show_alert=True)
        query.edit_message_text("⚠️ You have already submitted a platform review for this order.", reply_markup=None)
    finally:
        conn.close()
        
    return ConversationHandler.END

def user_profile_feedback(update, context):
    """User Profile & Feedback page with real data and pagination"""
    query = update.callback_query if update.callback_query else None
    user_id = update.effective_user.id
    username = update.effective_user.username or str(user_id)
    
    page = 0
    if query and query.data.startswith("profile_page_"):
        page = int(query.data.replace("profile_page_", ""))
        context.user_data['profile_page'] = page
    else:
        page = context.user_data.get('profile_page', 0)
        
    PAGE_SIZE = 10
    offset = page * PAGE_SIZE
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Calculate stats
    cursor.execute("SELECT COUNT(*), AVG(rating) FROM user_reviews WHERE target_user_id = ?", (user_id,))
    stats = cursor.fetchone()
    total_reviews = stats[0] if stats[0] else 0
    avg_rating = round(stats[1], 1) if stats[1] else 0.0
    
    cursor.execute("SELECT COUNT(*) FROM orders WHERE customer_id = ? OR seller_id = ?", (user_id, user_id))
    tx_count = cursor.fetchone()[0]
    
    # Fetch paginated reviews about this user
    cursor.execute("""
        SELECT rating, reviewer_name, comment, created_at, order_number 
        FROM user_reviews 
        WHERE target_user_id = ? 
        ORDER BY created_at DESC 
        LIMIT ? OFFSET ?
    """, (user_id, PAGE_SIZE, offset))
    reviews = cursor.fetchall()
    conn.close()
    
    text = (
        f"👤 <b>Your Profile</b>\n\n"
        f"👤 <b>Username:</b> @{username}\n"
        f"🌟 <b>Rating:</b> {avg_rating}/5.0 ({total_reviews} reviews)\n"
        f"📊 <b>Transactions:</b> {tx_count}\n\n"
    )
    
    if not reviews:
        text += "<b>Reviews:</b>\n<i>No reviews yet.</i>"
    else:
        text += f"<b>Reviews (Page {page + 1}):</b>\n"
        for rating, r_name, comment, created_at, order_num in reviews:
            stars = "⭐" * rating
            text += f"\n{stars} from @{r_name} (Order {order_num})\n💬 <i>\"{comment}\"</i>\n"
            
    keyboard = []
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️ Previous", callback_data=f"profile_page_{page-1}"))
    if offset + PAGE_SIZE < total_reviews:
        nav_row.append(InlineKeyboardButton("Next ▶️", callback_data=f"profile_page_{page+1}"))
    
    if nav_row:
        keyboard.append(nav_row)
        
    keyboard.append([InlineKeyboardButton("🔙 Back to Dashboard", callback_data="open_dashboard")])
    
    if query:
        query.answer()
        query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    else:
        update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CUSTOMER_MENU

def notify_admin_on_order_created(order_number, product_id, price, escrow_fee, buyer_username, seller_username, order_id, context):
    """Notify admin when order created - NO GROUP LINK BUTTON YET (only after payment confirmed)."""
    try:
        # NO "Add Group Link" button here - only show when payment confirmed
        text = (
            f"🛍 <b>NEW ORDER CREATED!</b>\n\n"
            f"📦 <b>Product:</b> <code>{product_id}</code>\n"
            f"🆔 <b>Order:</b> <code>{order_number}</code>\n"
            f"💰 <b>Account Price:</b> ${price:,.2f}\n"
            f"🛡️ <b>Escrow Fee:</b> ${escrow_fee:.2f}\n"
            f"👤 <b>Buyer:</b> @{buyer_username}\n"
            f"👤 <b>Seller:</b> @{seller_username}\n\n"
            f"⏳ <b>Status:</b> Waiting for buyer to complete escrow fee payment...\n\n"
            f"The 'Add Group Link' button will appear once payment is confirmed."
        )
        
        keyboard = []  # EMPTY - no buttons until payment confirmed
        context.bot.send_message(
            chat_id=OWNER_ID,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
            parse_mode=ParseMode.HTML
        )
        logger.info(f"✅ Admin notified of new order {order_number} (waiting for payment)")
    except Exception as e:
        logger.error(f"Error notifying admin of new order: {e}")


def notify_seller_on_payment(seller_id, order_number, product_id, price, escrow_fee, buyer_username, context):
    """Notify seller when buyer confirms escrow payment."""
    try:
        text = (
            f"🛍 <b>NEW ORDER ON YOUR LISTING!</b>\n\n"
            f"📦 <b>Product:</b> <code>{product_id}</code>\n"
            f"🆔 <b>Order:</b> <code>{order_number}</code>\n"
            f"💰 <b>Price:</b> ${price:,.2f}\n"
            f"🛡️ <b>Escrow Fee:</b> ${escrow_fee:.2f}\n"
            f"👤 <b>Buyer:</b> @{buyer_username}\n\n"
            f"⏳ <b>Status:</b> Waiting for admin to set up the deal group...\n\n"
            f"You'll receive the group link shortly!"
        )
        context.bot.send_message(
            chat_id=seller_id,
            text=text,
            parse_mode=ParseMode.HTML
        )
        logger.info(f"Seller {seller_id} notified for order {order_number}")
    except Exception as e:
        logger.error(f"Error notifying seller: {e}")
        
def send_enriched_deal_group_welcome(order_number, context):
    """Fetches listing data and sends the deferred enriched welcome message."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Get order info
        cursor.execute('''
            SELECT product_id, customer_username, seller_id, transaction_group_id, amount_to_pay
            FROM orders WHERE order_number = ?
        ''', (order_number,))
        order_data = cursor.fetchone()
        
        if not order_data:
            conn.close()
            return False
            
        product_id, buyer_username, seller_id, group_chat_id, amount_to_pay = order_data
        
        # Get listing info (including seller_contact and channel_link)
        cursor.execute('SELECT * FROM listings WHERE listing_id = ?', (product_id,))
        listing_row = cursor.fetchone()
        
        if not listing_row:
            conn.close()
            return False
            
        # IMPORTANT: Build dict BEFORE executing the next query, otherwise cursor.description changes
        col_names = [desc[0] for desc in cursor.description]
        listing_dict = dict(zip(col_names, listing_row))
        
        # Also try to get username from users table as fallback
        cursor.execute('SELECT username FROM users WHERE telegram_id = ?', (seller_id,))
        seller_row = cursor.fetchone()
        conn.close()
        
        platform = listing_dict.get('platform', '')
        price = listing_dict.get('price', 0)
        seller_contact = listing_dict.get('seller_contact')
        channel_link = listing_dict.get('channel_link')
        
        # Extract seller username
        seller_username = str(seller_id)
        if seller_contact:
            seller_username = seller_contact.split('/')[-1].replace('@', '')
        elif seller_row and seller_row[0]:
            seller_username = seller_row[0].replace('@', '')
        
        safe_order_number = html_escape(order_number)
        safe_product_id = html_escape(product_id)
        safe_seller_username = html_escape(safe_telegram_username(seller_username, fallback="Seller"))
        safe_buyer_username = html_escape(safe_telegram_username(buyer_username, fallback="Buyer"))

        # Construct message
        msg = "🎉 <b>TRANSACTION INITIATED!</b>\n"
        msg += "===================\n\n"
        msg += f"🇨🇧 <b>Transaction ID:</b> <code>{safe_order_number}</code>\n"
        msg += f"📦 <b>Account ID:</b> <code>{safe_product_id}</code>\n"
        msg += f"💵 <b>Price:</b> ${float(price):,.2f}\n"
        msg += f"👤 <b>Seller:</b> {safe_seller_username}\n"
        msg += f"👤 <b>Buyer:</b> {safe_buyer_username}\n"
        if channel_link and str(channel_link).lower() not in ('none', ''):
            safe_channel_link = html_escape(channel_link)
            msg += f'🔗 <b>Channel Link:</b> <a href="{safe_channel_link}">Link</a>\n'
        msg += f"______________________________________\n\n"
        
        msg += f"📋 <b>ACCOUNT INFO:</b>\n\n"
        
        full_post = get_listing_post_text(listing_dict)
        info_idx = full_post.find("📋 <b>BASIC INFO</b>")
        if info_idx != -1:
            msg += full_post[info_idx:]
        else:
            msg += "Could not parse account info properly."
            
        msg += f"\n\n______________________________________\n\n"
        
        if platform and platform.lower() == 'youtube':
            msg += f"<b>How It Works:</b>\n"
            msg += f"1️⃣ Buyer makes the payment for the account.\n"
            msg += f"2️⃣ Seller adds the Admin as \"Owner\" and the Buyer as \"Manager\"\n"
            msg += f"3️⃣ After 7 days, the Seller makes the Buyer as \"Primary Owner\" and removes himself\n"
            msg += f"4️⃣ Admin verifies the ownership transfer process\n"
            msg += f"5️⃣ Admin releases the funds to the seller and marks the deal completed.\n\n"
        else:
            msg += f"<b>How It Works:</b>\n"
            msg += f"1️⃣ Buyer makes the payment for the account.\n"
            msg += f"2️⃣ Seller provides the account credentials privately to the Admin.\n"
            msg += f"3️⃣ Admin verifies the account and secures it.\n"
            msg += f"4️⃣ Buyer receives the account credentials privately.\n"
            msg += f"5️⃣ Buyer verifies the account and confirm changing its info (changes password/email).\n"
            msg += f"6️⃣ Admin releases the funds to the seller and marks the deal completed.\n\n"
            
        msg += f"⚠️ <b>IMPORTANT:</b> Stick to the Admin instructions and don't make any step unless you're told to"
        
        context.bot.send_message(chat_id=group_chat_id, text=msg, parse_mode=ParseMode.HTML)
        logger.info(f"✅ Enriched welcome message sent to Deal Group {group_chat_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to send enriched welcome message to Deal Group: {e}")
        return False

def handle_new_group_member(update, context):
    """Tracks when buyer and seller join the deal group."""
    if not update.message or not update.message.new_chat_members:
        return
        
    chat_id = str(update.message.chat_id)
    new_members = update.message.new_chat_members
    logger.debug("New members in chat %s: %s", chat_id, [m.id for m in new_members])
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Match by both string and numeric chat_id
        cursor.execute('''
            SELECT order_number, customer_id, seller_id, buyer_joined, seller_joined, welcome_sent
            FROM orders WHERE transaction_group_id = ? OR transaction_group_id = ?
        ''', (chat_id, chat_id.lstrip('-')))
        order = cursor.fetchone()
        logger.debug("DB lookup for chat_id=%s: order_found=%s", chat_id, order is not None)
        
        if not order:
            # Check if this is a manually added group where we don't have the chat_id yet
            for member in new_members:
                cursor.execute('''

                    SELECT order_number, customer_id, seller_id 
                    FROM orders 
                    WHERE transaction_group_id IS NULL 
                    AND transaction_group_link IS NOT NULL 
                    AND (customer_id = ? OR seller_id = ?)
                    AND order_status = 'group_link_set'
                    ORDER BY id DESC LIMIT 1
                ''', (member.id, member.id))
                matched = cursor.fetchone()
                
                if matched:
                    matched_order = matched['order_number']
                    # Link the chat_id to the order!
                    cursor.execute('UPDATE orders SET transaction_group_id = ? WHERE order_number = ?', (chat_id, matched_order))
                    conn.commit()
                    logger.debug("Auto-linked manual group %s to order %s via member %s", chat_id, matched_order, member.id)
                    
                    # Attempt to rename the group now that we know its ID
                    try:
                        context.bot.set_chat_title(chat_id=chat_id, title=f"SMyards - Transaction {matched_order} Group")
                    except Exception as e:
                        logger.error(f"Error renaming manual group {chat_id}: {e}")
                        try:
                            context.bot.send_message(
                                chat_id=chat_id,
                                text=f"⚠️ **Admin Note:** I tried to automatically rename this group to `SMyards - Transaction {matched_order} Group` but I lack the 'Change Group Info' permission. Please rename it manually.",
                                parse_mode="Markdown"
                            )
                        except Exception:
                            pass
                    
                    # Refetch the order to proceed with the welcome message logic
                    cursor.execute('''
                        SELECT order_number, customer_id, seller_id, buyer_joined, seller_joined, welcome_sent
                        FROM orders WHERE order_number = ?
                    ''', (matched_order,))
                    order = cursor.fetchone()
                    break
                    
        if not order:
            # Log all known group IDs for comparison
            cursor.execute("SELECT order_number, transaction_group_id FROM orders WHERE transaction_group_id IS NOT NULL")
            known = cursor.fetchall()
            logger.debug("Known group IDs in DB: %s", known)
            return
            
        order_number, buyer_id, seller_id, buyer_joined, seller_joined, welcome_sent = order
        logger.debug(
            "Order %s: buyer_id=%s, seller_id=%s, buyer_joined=%s, seller_joined=%s, welcome_sent=%s",
            order_number, buyer_id, seller_id, buyer_joined, seller_joined, welcome_sent,
        )
        
        # Treat NULL as 0
        buyer_joined = 1 if buyer_joined else 0
        seller_joined = 1 if seller_joined else 0
        welcome_sent = 1 if welcome_sent else 0
        
        if welcome_sent:
            return
            
        updated = False
        for member in new_members:
            logger.debug("Checking member id=%s vs buyer=%s, seller=%s", member.id, buyer_id, seller_id)
            if str(member.id) == str(buyer_id):
                buyer_joined = 1
                updated = True
                cursor.execute('UPDATE orders SET buyer_joined = 1 WHERE order_number = ?', (order_number,))
                logger.info(f"Buyer joined deal group for order {order_number}")
            if str(member.id) == str(seller_id):
                seller_joined = 1
                updated = True
                cursor.execute('UPDATE orders SET seller_joined = 1 WHERE order_number = ?', (order_number,))
                logger.info(f"Seller joined deal group for order {order_number}")
                
        if updated:
            conn.commit()
            
        if buyer_joined and seller_joined and not welcome_sent:
            if send_enriched_deal_group_welcome(order_number, context):
                cursor.execute('UPDATE orders SET welcome_sent = 1 WHERE order_number = ?', (order_number,))
                conn.commit()
            
    except Exception as e:
        logger.error(f"Error handling new group member: {e}")
    finally:
        conn.close()
    



def handle_admin_edit_approval(update, context):
    """Standalone handler for admin edit approvals - fires outside ConversationHandler."""
    query = update.callback_query
    query.answer()
    data = query.data

    action = "approve" if data.startswith("admin_approve_edit_") else "reject"
    req_id = data.replace(f"admin_{action}_edit_", "")

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM edit_requests WHERE id = ?", (req_id,))
        req = cursor.fetchone()

        if not req or req['status'] != 'pending':
            query.edit_message_text("❌ Request not found or already processed.")
            return

        listing_id = req['listing_id']
        field = req['field_name']
        new_value = req['new_value']

        if action == "approve":
            allowed_fields = ['price', 'features', 'channel_age', 'region', 'subscribers', 'views', 'status', 'niche', 'monetization']
            db_field = field if field in allowed_fields else "features"
            
            cursor.execute(f"UPDATE listings SET {db_field} = ? WHERE listing_id = ?", (new_value, listing_id))
            cursor.execute("UPDATE edit_requests SET status = 'approved' WHERE id = ?", (req_id,))

            cursor.execute("SELECT * FROM listings WHERE listing_id = ?", (listing_id,))
            listing = cursor.fetchone()
            conn.commit()

            # Parse the comma-separated channel_message_id (button posts)
            raw_ids = row_get(listing, 'channel_message_id', '') if listing else ''
            button_msg_ids = [mid.strip() for mid in str(raw_ids).split(',') if mid.strip()] if raw_ids else []
            
            # Parse the comma-separated screenshot_message_id (caption/text posts)
            raw_caption_ids = row_get(listing, 'screenshot_message_id', '') if listing else ''
            caption_msg_ids = [mid.strip() for mid in str(raw_caption_ids).split(',') if mid.strip()] if raw_caption_ids else []

            if listing and button_msg_ids:
                post_text = get_listing_post_text(listing)
                reply_markup = generate_buttons(
                    listing_id=listing_id,
                    seller_contact=row_get(listing, 'seller_contact'),
                    stock_message_id=row_get(listing, 'stock_message_id'),
                    seller_id=row_get(listing, 'created_by')
                )

                # Determine which caption IDs to update
                target_caption_ids = list(caption_msg_ids)
                if not target_caption_ids:
                    # Fallback for old posts before tracking was added
                    try:
                        import json
                        screenshots_raw = row_get(listing, 'screenshots') or '[]'
                        screenshots = json.loads(screenshots_raw)
                        num_screenshots = len(screenshots) if screenshots else 0
                        offset = max(num_screenshots, 1)
                        for b_id in button_msg_ids:
                            target_caption_ids.append(str(int(b_id) - offset))
                    except Exception:
                        pass

                # 1. Update ALL caption/text posts
                for cid in target_caption_ids:
                    try:
                        context.bot.edit_message_caption(
                            chat_id=CHANNEL_ID,
                            message_id=int(cid),
                            caption=post_text,
                            parse_mode='HTML'
                        )
                    except Exception as e1:
                        # Fallback if it's a text-only message (no photo)
                        try:
                            context.bot.edit_message_text(
                                chat_id=CHANNEL_ID,
                                message_id=int(cid),
                                text=post_text,
                                parse_mode='HTML'
                            )
                        except Exception:
                            pass

                # 2. Update ONLY the buttons of the last companion post (resetting text back to short version)
                last_id = button_msg_ids[-1]
                companion_text = f"<b>🆔 Account ID:</b> <code>{listing_id}</code>"
                try:
                    context.bot.edit_message_text(
                        chat_id=CHANNEL_ID,
                        message_id=int(last_id),
                        text=companion_text,
                        parse_mode='HTML',
                        reply_markup=reply_markup
                    )
                except Exception as edit_err:
                    logger.warning(f"Edit approval channel button update failed for {listing_id}: {edit_err}")

            query.edit_message_text(
                f"✅ Edit approved.\n\n📋 Listing `{listing_id}`\n🔧 Field: {field.title()}\n✏️ Channel post updated.",
                parse_mode="Markdown"
            )
            if listing:
                try:
                    context.bot.send_message(
                        chat_id=row_get(listing, 'created_by'),
                        text=f"✅ Your edit request for listing `{listing_id}` has been approved and the post was updated!"
                    )
                except Exception:
                    pass
        else:
            cursor.execute("UPDATE edit_requests SET status = 'rejected' WHERE id = ?", (req_id,))
            cursor.execute("SELECT created_by FROM listings WHERE listing_id = ?", (listing_id,))
            lst = cursor.fetchone()
            conn.commit()
            query.edit_message_text(f"❌ Edit request rejected.\n\n📋 Listing `{listing_id}`\n🔧 Field: {field.title()}", parse_mode="Markdown")
            if lst:
                try:
                    context.bot.send_message(
                        chat_id=row_get(lst, 'created_by'),
                        text=f"❌ Your edit request for listing `{listing_id}` ({field}) was rejected by the admin."
                    )
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"handle_admin_edit_approval error: {e}")
        try:
            query.edit_message_text("❌ An error occurred processing this request.")
        except Exception:
            pass
    finally:
        conn.close()


def admin_add_group_link(update, context):
    """Admin clicked 'Add Group Link' - prompt for the invite URL"""
    query = update.callback_query
    query.answer()
    
    order_id = int(query.data.replace("add_group_link_", ""))
    
    # Store with order_id AND query to get order_number for reference
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT order_number FROM orders WHERE id = ?", (order_id,))
    order_result = cursor.fetchone()
    conn.close()
    
    if not order_result:
        query.edit_message_text("❌ Order not found in database. This is unusual - please contact support.")
        return MAIN_MENU
    
    order_number = order_result[0]
    
    # Store BOTH for reference
    context.user_data['pending_group_link_order_id'] = order_id
    context.user_data['pending_group_link_order_number'] = order_number
    
    query.edit_message_text(
        "🔗 <b>Add Group Link</b>\n\n"
        f"<b>Order:</b> <code>{order_number}</code>\n\n"
        "Send the Telegram group invite link.\n\n"
        "Format: <code>https://t.me/+abcdef123xyz</code>\n\n"
        "Type 'cancel' to abort.",
        parse_mode=ParseMode.HTML
    )
    return ADMIN_ADD_GROUP_LINK

def admin_handle_group_link_input(update, context):
    """Handle the group link text input from admin"""
    group_link = update.message.text.strip()
    
    if group_link.lower() == 'cancel':
        update.message.reply_text("❌ Group link addition cancelled.")
        context.user_data.pop('pending_group_link_order_id', None)
        context.user_data.pop('pending_group_link_order_number', None)
        return MAIN_MENU
    
    if not group_link.startswith('https://t.me/'):
        update.message.reply_text(
            "❌ Invalid format. Please provide a valid Telegram invite link.\n\n"
            "Example: https://t.me/+abcdef123xyz\n\n"
            "Send again or type 'cancel':"
        )
        return ADMIN_ADD_GROUP_LINK
    
    order_id = context.user_data.get('pending_group_link_order_id')
    order_number = context.user_data.get('pending_group_link_order_number')
    
    if not order_id or not order_number:
        update.message.reply_text("❌ Order info expired. Please click 'Add Group Link' again.")
        return MAIN_MENU
    
    try:
        # Save group link to order
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE orders SET transaction_group_link = ?, order_status = 'group_link_set' WHERE id = ?",
            (group_link, order_id)
        )
        conn.commit()
        
        # Get order details to notify parties
        cursor.execute("""
            SELECT order_number, product_id, customer_id, customer_username, seller_id
            FROM orders WHERE id = ?
        """, (order_id,))
        order = cursor.fetchone()
        conn.close()
        
        if not order:
            update.message.reply_text(f"❌ Order {order_number} not found after save. This is unusual.")
            return MAIN_MENU
        
        order_num, product_id, buyer_id, buyer_username, seller_id = order
        safe_order_num = html_escape(order_num)
        safe_product_id = html_escape(product_id)
        safe_group_link = html_escape(group_link)
        safe_buyer_username = html_escape(safe_telegram_username(buyer_username))
        
        # Notify buyer
        buyer_text = (
            f"🎉 <b>Your Deal Group is Ready!</b>\n\n"
            f"🆔 <b>Order:</b> <code>{safe_order_num}</code>\n"
            f"📦 <b>Product:</b> <code>{safe_product_id}</code>\n\n"
            f"Join the deal group:\n{safe_group_link}\n\n"
            f"The seller and admin are waiting for you!"
        )
        buyer_notified = False
        if buyer_id and int(str(buyer_id)) > 0:  # Skip fake/negative AP buyer IDs
            try:
                context.bot.send_message(chat_id=buyer_id, text=buyer_text, parse_mode=ParseMode.HTML)
                logger.info(f"✅ Buyer {buyer_id} notified of group link for order {order_num}")
                buyer_notified = True
            except Exception as e:
                logger.error(f"❌ Error notifying buyer: {e}")
                buyer_link = f"https://t.me/{buyer_username}" if buyer_username and not buyer_username.startswith('Buyer') else f"tg://user?id={buyer_id}"
                update.message.reply_text(
                    f"⚠️ <b>Could not auto-notify buyer</b>\n"
                    f"Reason: <code>{html_escape(str(e))}</code>\n\n"
                    f"👤 Buyer: <a href='{buyer_link}'>{safe_buyer_username}</a>\n"
                    f"📨 Please send them the group link manually:\n<code>{safe_group_link}</code>",
                    parse_mode=ParseMode.HTML
                )
        else:
            logger.info(f"Skipping buyer notification for AP simulation order {order_num} (fake buyer ID: {buyer_id})")
            buyer_notified = True  # Not an error, just a simulation
        
        # Notify seller
        seller_notified = False
        if seller_id and seller_id != OWNER_ID:
            seller_text = (
                f"🛍 <b>Deal Group Ready!</b>\n\n"
                f"📦 <b>Product:</b> <code>{safe_product_id}</code>\n"
                f"🆔 <b>Order:</b> <code>{safe_order_num}</code>\n"
                f"👤 <b>Buyer:</b> {safe_buyer_username}\n\n"
                f"Join the deal group here:\n{safe_group_link}\n\n"
                f"Complete the transaction there!"
            )
            try:
                context.bot.send_message(chat_id=seller_id, text=seller_text, parse_mode=ParseMode.HTML)
                logger.info(f"✅ Seller {seller_id} notified of group link for order {order_num}")
                seller_notified = True
            except Exception as e:
                logger.error(f"❌ Error notifying seller {seller_id}: {e}")
                update.message.reply_text(
                    f"⚠️ <b>Could not auto-notify seller</b>\n"
                    f"Reason: <code>{html_escape(str(e))}</code>\n\n"
                    f"📨 Please forward the group link to the seller manually:\n<code>{safe_group_link}</code>",
                    parse_mode=ParseMode.HTML
                )
        else:
            logger.warning(f"No valid seller_id for order {order_num}: {seller_id}")
        
        # Confirm to admin
        update.message.reply_text(
            f"✅ <b>Group link saved!</b>\n\n"
            f"📦 <b>Order:</b> <code>{safe_order_num}</code>\n"
            f"🔗 <b>Link:</b> {safe_group_link}\n\n"
            f"Both parties have been notified.",
            parse_mode=ParseMode.HTML
        )
        
        # Clean up context
        context.user_data.pop('pending_group_link_order_id', None)
        context.user_data.pop('pending_group_link_order_number', None)
        
        return MAIN_MENU
        
    except Exception as e:
        logger.error(f"Error saving group link: {e}", exc_info=True)
        update.message.reply_text(f"❌ Error saving group link: {str(e)[:100]}\n\nPlease try again.")
        return ADMIN_ADD_GROUP_LINK

def admin_handle_group_link_standalone(update, context):
    """Handle group link input from admin outside ConversationHandler."""
    if update.effective_user.id != OWNER_ID:
        return
    
    # Only handle if we're expecting a group link
    if 'pending_group_link_order_id' not in context.user_data:
        return
    
    group_link = update.message.text.strip()
    
    if group_link.lower() == 'cancel':
        context.user_data.pop('pending_group_link_order_id', None)
        update.message.reply_text("❌ Group link addition cancelled.")
        return
    
    if not group_link.startswith('https://t.me/'):
        update.message.reply_text(
            "❌ Invalid format. Please send a valid Telegram invite link.\n"
            "Example: https://t.me/+abcdef123xyz\n\n"
            "Type 'cancel' to abort."
        )
        return
    
    order_id = context.user_data.get('pending_group_link_order_id')
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE orders SET transaction_group_link = ?, order_status = 'group_link_set' WHERE id = ?",
            (group_link, order_id)
        )
        conn.commit()
        
        cursor.execute("""
            SELECT order_number, product_id, customer_id, customer_username, seller_id
            FROM orders WHERE id = ?
        """, (order_id,))
        order = cursor.fetchone()
        conn.close()
        
        if not order:
            update.message.reply_text("❌ Order not found.")
            return
        
        order_num, product_id, buyer_id, buyer_username, seller_id = order
        safe_order_num = html_escape(order_num)
        safe_product_id = html_escape(product_id)
        safe_group_link = html_escape(group_link)
        safe_buyer_username = html_escape(safe_telegram_username(buyer_username))
        
        # Notify buyer
        try:
            context.bot.send_message(
                chat_id=int(buyer_id),
                text=(
                    f"🎉 <b>Your Deal Group is Ready!</b>\n\n"
                    f"🆔 <b>Order:</b> <code>{safe_order_num}</code>\n"
                    f"📦 <b>Product:</b> <code>{safe_product_id}</code>\n\n"
                    f"Join the deal group here:\n{safe_group_link}\n\n"
                    f"The seller and admin are waiting for you!"
                ),
                parse_mode=ParseMode.HTML
            )
            update.message.reply_text("✅ Buyer notified.")
        except Exception as e:
            logger.error(f"Error notifying buyer: {e}")
            update.message.reply_text(f"⚠️ Could not notify buyer (buyer_id: {buyer_id}): {e}\n💡 *Note: If this is an old Auto Pilot ghost buyer or they haven't started the bot, this is expected.*", parse_mode="Markdown")
        
        # Notify seller
        if seller_id:
            try:
                context.bot.send_message(
                    chat_id=int(seller_id),
                    text=(
                        f"🛍 <b>Deal Group Ready!</b>\n\n"
                        f"📦 <b>Product:</b> <code>{safe_product_id}</code>\n"
                        f"🆔 <b>Order:</b> <code>{safe_order_num}</code>\n"
                        f"👤 <b>Buyer:</b> {safe_buyer_username}\n\n"
                        f"Join the deal group here:\n{safe_group_link}\n\n"
                        f"Complete the transaction there!"
                    ),
                    parse_mode=ParseMode.HTML
                )
                update.message.reply_text("✅ Seller notified.")
            except Exception as e:
                logger.error(f"Error notifying seller: {e}")
                update.message.reply_text(f"⚠️ Could not notify seller (seller_id: {seller_id}): {e}")
        else:
            update.message.reply_text(f"⚠️ No seller_id found for this order.")
        
        context.user_data.pop('pending_group_link_order_id', None)
        update.message.reply_text(
            f"✅ <b>Group link saved!</b>\n\n"
            f"Order: <code>{safe_order_num}</code>\n"
            f"Link: {safe_group_link}",
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        logger.error(f"Error saving group link: {e}", exc_info=True)
        update.message.reply_text(f"❌ Error saving group link: {e}")


def _obscure_name(name):
    if not name: return "Use*****"
    name = str(name).lstrip('@')
    if len(name) < 3: return name.capitalize() + "*****"
    return name[:3].capitalize() + "*****"

def post_escrow_completion(bot, order_num, product_id, platform, seller_name, buyer_name, price, txid=None, main_post_url=None, payment_method=None):
    from datetime import datetime
    date_str = datetime.now().strftime('%#d %b %Y') if os.name == 'nt' else datetime.now().strftime('%-d %b %Y')

    obs_seller = _obscure_name(seller_name)
    obs_buyer = _obscure_name(buyer_name)

    text1 = (
        f'\u2705 <b>COMPLETED VIA ESCROW</b>\n'
        f'\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n'
        f'\U0001f4f1 <b>Platform:</b> {platform}\n'
        f'\U0001f194 <b>Account ID:</b> <code>{product_id}</code>\n'
        f'\U0001f6cd <b>Order:</b> <code>{order_num}</code>\n'
        f'\U0001f464 <b>Seller:</b> {obs_seller}\n'
        f'\U0001f464 <b>Buyer:</b> {obs_buyer}\n'
        f'\U0001f4b0 <b>Price:</b> ${price:,.2f}\n'
    )
    if payment_method:
        text1 += f'\U0001f4b3 <b>Paid by {payment_method}</b>\n'
    if txid:
        text1 += f'\U0001f517 <b>TXid:</b> <a href="{html_escape(txid)}">Link</a>\n'
    text1 += f'\U0001f550 <b>Completed:</b> {date_str}\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501'

    markup1 = None
    if main_post_url:
        markup1 = InlineKeyboardMarkup([[
            InlineKeyboardButton("ℹ️ View Account Info", url=main_post_url)
        ]])

    text2 = (
        f'\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n'
        f'\u2728 Escrow Guarded Transaction Successfully Completed For ${price:,.2f} For Order {order_num}\n'
        f'\u23f3 Waiting for Platform Reviews...\n\n'
        f'\U0001f6cd <b>Order:</b> {order_num}\n'
        f'\U0001f194 <b>Account ID:</b> {product_id}\n'
        f'\U0001f550 <b>Submitted:</b> {date_str}\n'
        f'\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501'
    )

    try:
        msg1 = bot.send_message(
            chat_id=ESCROW_LOG_CHANNEL_ID,
            text=text1,
            reply_markup=markup1,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        msg2 = bot.send_message(
            chat_id=ESCROW_LOG_CHANNEL_ID,
            text=text2,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        # post1_id -> "View Transaction Proof" SOLD button
        # post2_id -> stored as escrow_message_id, edited when reviews arrive
        return msg1.message_id, msg2.message_id
    except Exception as e:
        logger.error(f"Error posting escrow completion to channel: {e}")
        return None, None

def check_and_post_milestone(bot, cursor):
    cursor.execute("SELECT COUNT(*) FROM transactions_log")
    total_deals = cursor.fetchone()[0]
    
    milestones = [10, 25, 50, 100, 250, 500, 750, 1000]
    if total_deals in milestones:
        text = (
            f"🎉 <b>MILESTONE REACHED!</b> 🎉\n\n"
            f"We have successfully completed <b>{total_deals}</b> secure escrow deals!\n\n"
            f"Thank you to our amazing community for trusting SMYARDS Escrow! 🚀"
        )
        try:
            bot.send_message(
                chat_id=ESCROW_LOG_CHANNEL_ID,
                text=text,
                parse_mode="HTML"
            )
            logger.info(f"Milestone {total_deals} posted to Escrow_Log_Channel")
        except Exception as e:
            logger.error(f"Error posting milestone to channel: {e}")

def admin_mark_order_completed(update, context):
    """Admin clicked 'Mark as Completed' on an escrow order — first ask payment method"""
    query = update.callback_query
    order_id = int(query.data.replace("mark_completed_", ""))
    context.user_data['completing_order_id'] = order_id
    
    query.answer()
    keyboard = [
        [InlineKeyboardButton("💲 Crypto (USDT)", callback_data="opm_USDT"),
         InlineKeyboardButton("💲 Crypto (USDC)", callback_data="opm_USDC")],
        [InlineKeyboardButton("💰 Crypto (BTC)", callback_data="opm_BTC"),
         InlineKeyboardButton("💰 Crypto (ETH)", callback_data="opm_ETH")],
        [InlineKeyboardButton("💸 Crypto (LTC)", callback_data="opm_LTC"),
         InlineKeyboardButton("💸 Crypto (XRP)", callback_data="opm_XRP")],
        [InlineKeyboardButton("💱 Crypto (Other)", callback_data="opm_OTHER")],
    ]
    query.edit_message_text(
        "💳 <b>Select Payment Method:</b>\n\nHow was this order paid?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )
    return ENTER_ORDER_PAYMENT_METHOD


def admin_handle_order_payment_method(update, context):
    """Admin selected payment method — now ask for TXid"""
    query = update.callback_query
    data = query.data  # e.g. opm_USDT
    method_key = data.replace('opm_', '')
    
    method_map = {
        'USDT': 'Crypto (USDT)', 'USDC': 'Crypto (USDC)',
        'BTC':  'Crypto (BTC)',  'ETH':  'Crypto (ETH)',
        'LTC':  'Crypto (LTC)',  'XRP':  'Crypto (XRP)',
    }
    
    if method_key == 'OTHER':
        query.answer()
        query.edit_message_text(
            "💱 <b>Enter Crypto Coin Name:</b>\n\nType the name of the cryptocurrency used (e.g. SOL, TRX, DOGE):",
            parse_mode=ParseMode.HTML
        )
        return ENTER_CUSTOM_CRYPTO
    
    payment_method = method_map.get(method_key, f'Crypto ({method_key})')
    context.user_data['completing_payment_method'] = payment_method
    
    query.answer()
    query.edit_message_text(
        f"✅ Payment method: <b>{payment_method}</b>\n\n"
        f"📝 <b>Enter Transaction ID (TXid):</b>\n"
        f"Paste the blockchain transaction link or ID for the payout.\n"
        f"Type 'skip' if no TXid, or 'cancel' to abort.",
        parse_mode=ParseMode.HTML
    )
    return ENTER_ORDER_TXID


def admin_handle_custom_crypto(update, context):
    """Admin typed custom crypto name — now ask for TXid"""
    coin_name = update.message.text.strip()
    payment_method = f'Crypto ({coin_name})'
    context.user_data['completing_payment_method'] = payment_method
    update.message.reply_text(
        f"✅ Payment method: <b>{payment_method}</b>\n\n"
        f"📝 <b>Enter Transaction ID (TXid):</b>\n"
        f"Paste the blockchain transaction link or ID for the payout.\n"
        f"Type 'skip' if no TXid, or 'cancel' to abort.",
        parse_mode=ParseMode.HTML
    )
    return ENTER_ORDER_TXID

def admin_handle_order_txid(update, context):
    """Admin entered TXid for a completed escrow order"""
    txid = update.message.text.strip()
    
    if txid.lower() == 'cancel':
        update.message.reply_text("❌ Marking order as completed cancelled.")
        context.user_data.pop('completing_order_id', None)
        return admin_start(update, context)
    
    if txid.lower() == 'skip':
        txid = None
        
    order_id = context.user_data.get('completing_order_id')
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Get order details
        cursor.execute("""
            SELECT order_number, customer_id, customer_username, seller_id, product_id, 
                   platform, total_price, escrow_fee, transaction_group_id
            FROM orders WHERE id = ?
        """, (order_id,))
        order = cursor.fetchone()
        
        if not order:
            update.message.reply_text("❌ Order not found.")
            return admin_start(update, context)
        
        order_num, buyer_id, buyer_username, seller_id, product_id, platform, price, fee, group_chat_id = order
        
        # Get seller name - try username from seller_contact in listing first, fall back to customer_username
        cursor.execute("SELECT seller_contact FROM listings WHERE listing_id = ?", (product_id,))
        contact_row = cursor.fetchone()
        if contact_row and contact_row[0]:
            # seller_contact is like 'https://t.me/username' or '@username'
            contact = str(contact_row[0]).strip()
            if contact.startswith('https://t.me/'):
                seller_name = contact.split('/')[-1]
            elif contact.startswith('@'):
                seller_name = contact[1:]
            else:
                seller_name = contact
        else:
            # Fall back to username lookup in users table
            cursor.execute("SELECT username FROM users WHERE telegram_id = ?", (seller_id,))
            seller_row = cursor.fetchone()
            seller_name = seller_row[0] if seller_row and seller_row[0] else f"Seller{str(seller_id)[-4:]}"
        
        buyer_name = buyer_username if buyer_username else f"Buyer{str(buyer_id)[-4:]}"
        
        # Fetch channel_message_id to construct URL
        cursor.execute("SELECT channel_message_id FROM listings WHERE listing_id = ?", (product_id,))
        listing_row = cursor.fetchone()
        channel_message_id = listing_row[0] if listing_row else None
        
        main_post_url = None
        if channel_message_id:
            # channel_message_id may be comma-separated (historical); take the first
            first_msg_id = str(channel_message_id).split(',')[0].strip()
            if first_msg_id.lower() != 'none' and first_msg_id.isdigit():
                main_post_url = helper_get_tg_url(CHANNEL_ID, first_msg_id)
        
        payment_method = context.user_data.pop('completing_payment_method', None)
        
        # Post to Escrow_Log_Channel — returns (post1_id for SOLD link, post2_id for review edits)
        escrow_post1_id, msg_id = post_escrow_completion(context.bot, order_num, product_id, platform, seller_name, buyer_name, price, txid, main_post_url, payment_method)
        
        # Edit the main channel post to show it as sold (link to Post 1 — static info)
        sold_data = {
            'listing_id': product_id,
            'channel_message_id': channel_message_id,
            'order_number': order_num,
            'price': price,
            'payment_method': 'N/A'
        }
        admin_update_main_post_as_sold(sold_data, context.bot, escrow_post1_id)
        
        # Insert into transactions_log (store post2 id as escrow_message_id for review edits)
        cursor.execute("""
            INSERT INTO transactions_log 
            (order_number, product_id, platform, seller_name, buyer_name, price, payment_method, txid, status, escrow_message_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (order_num, product_id, platform, seller_name, buyer_name, price, payment_method, txid, 'completed', msg_id))
        
        # Check milestones
        check_and_post_milestone(context.bot, cursor)
        
        # Update order status
        cursor.execute("""
            UPDATE orders 
            SET order_status = 'completed', completed_at = CURRENT_TIMESTAMP, escrow_message_id = ?
            WHERE id = ?
        """, (msg_id, order_id))
        
        # Mark listing as sold
        cursor.execute("UPDATE listings SET status_flag = 'sold' WHERE listing_id = ?", (product_id,))
        
        conn.commit()
        conn.close()
        
        # Notify the Deal Group — clean completion message, NO review buttons
        if group_chat_id:
            group_text = (
                f"🎉 *DEAL COMPLETED!*\n\n"
                f"🆔 *Order:* `{order_num}`\n"
                f"📦 *Product:* `{product_id}`\n\n"
                f"✅ *Account successfully secured by the buyer.*\n"
                f"✅ *Funds successfully released to the seller.*\n\n"
                f"Thank you for using SMYARDS Escrow! 🙌"
            )
            try:
                context.bot.send_message(
                    chat_id=group_chat_id,
                    text=group_text,
                    parse_mode="Markdown"
                )
                logger.info(f"Sent completion message to Deal Group {group_chat_id}")
            except Exception as e:
                logger.error(f"Error notifying Deal Group of completion: {e}")
        else:
            logger.warning(f"Order {order_num} has no transaction_group_id! Could not send group completion message.")

        # --- Send private DM to BUYER with review buttons ---
        buyer_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("─── Rate SMYARDS Platform ───", callback_data="noop")],
            [InlineKeyboardButton("⭐⭐⭐⭐⭐ (5)", callback_data=f"rate_plat_{order_num}_5"),
             InlineKeyboardButton("⭐⭐⭐⭐ (4)", callback_data=f"rate_plat_{order_num}_4")],
            [InlineKeyboardButton("⭐⭐⭐ (3)", callback_data=f"rate_plat_{order_num}_3"),
             InlineKeyboardButton("⭐⭐ (2)", callback_data=f"rate_plat_{order_num}_2"),
             InlineKeyboardButton("⭐ (1)", callback_data=f"rate_plat_{order_num}_1")],
            [InlineKeyboardButton("─── Rate the Seller ───", callback_data="noop")],
            [InlineKeyboardButton("⭐⭐⭐⭐⭐ (5)", callback_data=f"rate_user_{order_num}_5"),
             InlineKeyboardButton("⭐⭐⭐⭐ (4)", callback_data=f"rate_user_{order_num}_4")],
            [InlineKeyboardButton("⭐⭐⭐ (3)", callback_data=f"rate_user_{order_num}_3"),
             InlineKeyboardButton("⭐⭐ (2)", callback_data=f"rate_user_{order_num}_2"),
             InlineKeyboardButton("⭐ (1)", callback_data=f"rate_user_{order_num}_1")],
        ])
        buyer_dm_text = (
            f"🎉 <b>Your order {order_num} is complete!</b>\n\n"
            f"We'd love to hear how it went. Please tap a star rating below:\n\n"
            f"<b>📱 Rate SMYARDS Escrow</b> — How was our service?\n"
            f"<b>👤 Rate the Seller</b> — How was the other party?"
        )
        try:
            context.bot.send_message(
                chat_id=buyer_id,
                text=buyer_dm_text,
                reply_markup=buyer_keyboard,
                parse_mode=ParseMode.HTML
            )
            logger.info(f"Sent review DM to buyer {buyer_id} for order {order_num}")
        except Exception as e:
            logger.error(f"Could not send review DM to buyer {buyer_id}: {e}")

        # --- Send private DM to SELLER with review buttons ---
        seller_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("─── Rate SMYARDS Platform ───", callback_data="noop")],
            [InlineKeyboardButton("⭐⭐⭐⭐⭐ (5)", callback_data=f"rate_plat_{order_num}_5"),
             InlineKeyboardButton("⭐⭐⭐⭐ (4)", callback_data=f"rate_plat_{order_num}_4")],
            [InlineKeyboardButton("⭐⭐⭐ (3)", callback_data=f"rate_plat_{order_num}_3"),
             InlineKeyboardButton("⭐⭐ (2)", callback_data=f"rate_plat_{order_num}_2"),
             InlineKeyboardButton("⭐ (1)", callback_data=f"rate_plat_{order_num}_1")],
            [InlineKeyboardButton("─── Rate the Buyer ───", callback_data="noop")],
            [InlineKeyboardButton("⭐⭐⭐⭐⭐ (5)", callback_data=f"rate_user_{order_num}_5"),
             InlineKeyboardButton("⭐⭐⭐⭐ (4)", callback_data=f"rate_user_{order_num}_4")],
            [InlineKeyboardButton("⭐⭐⭐ (3)", callback_data=f"rate_user_{order_num}_3"),
             InlineKeyboardButton("⭐⭐ (2)", callback_data=f"rate_user_{order_num}_2"),
             InlineKeyboardButton("⭐ (1)", callback_data=f"rate_user_{order_num}_1")],
        ])
        seller_dm_text = (
            f"🎉 <b>Order {order_num} has been completed!</b>\n\n"
            f"Thank you for selling through SMYARDS Escrow. Please tap a star rating:\n\n"
            f"<b>📱 Rate SMYARDS Escrow</b> — How was our service?\n"
            f"<b>👤 Rate the Buyer</b> — How was the other party?"
        )
        try:
            context.bot.send_message(
                chat_id=seller_id,
                text=seller_dm_text,
                reply_markup=seller_keyboard,
                parse_mode=ParseMode.HTML
            )
            logger.info(f"Sent review DM to seller {seller_id} for order {order_num}")
        except Exception as e:
            logger.error(f"Could not send review DM to seller {seller_id}: {e}")


        
        update.message.reply_text(f"✅ Order <b>{order_num}</b> marked as completed and logged!", parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Error marking order completed: {e}", exc_info=True)
        update.message.reply_text(f"❌ Error completing order: {e}")
        
    finally:
        context.user_data.pop('completing_order_id', None)
        
    return admin_start(update, context)





# ===== CORE BOT FUNCTIONS =====
def start(update, context):
    """Handle /start — supports deep links: ?start=buy_<id> and ?start=sell"""
    args = context.args
    user_id = update.effective_user.id

    # Handle deep link payloads from channel post buttons
    if args:
        payload = args[0]
        if payload.startswith('buy_'):
            product_id = payload[4:]  # strip 'buy_'
            return handle_deep_link_buy(update, context, product_id)
        elif payload.startswith('seller_'):
            seller_id = payload[7:]
            return handle_deep_link_seller(update, context, seller_id)
        elif payload == 'sell':
            return handle_deep_link_sell(update, context)
        elif payload == 'help':
            # Support clicking Help Center from main channel deep links
            # We must clear data to enter the new state tree cleanly
            context.user_data.clear()
            return customer_help_center(update, context)
        elif payload == 'browse':
            # Route to the customer browse menu via a fresh message
            context.user_data.clear()
            user_first = update.effective_user.first_name or "there"
            keyboard = [[InlineKeyboardButton("\U0001f6d2 Browse Accounts Market", callback_data="browse_menu")]]
            update.message.reply_text(
                f"\U0001f44b Hi {user_first}! Tap below to browse available accounts.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return ConversationHandler.END
        elif payload == 'txlog':
            context.user_data.clear()
            return transactions_log_view(update, context)
        elif payload.startswith('review_user_'):
            order_num = payload.replace('review_user_', '')
            return handle_deep_link_review(update, context, order_num, "user")
        elif payload.startswith('review_plat_'):
            order_num = payload.replace('review_plat_', '')
            return handle_deep_link_review(update, context, order_num, "platform")

    context.user_data.clear()

    # If admin, tell them to use /admin
    if user_id == OWNER_ID or is_admin(user_id):
        update.message.reply_text(
            "👋 Welcome back, Admin!\n\n"
            "Use /admin to open your admin dashboard."
        )
        return ConversationHandler.END

    # Everyone else: just one button
    user_first = update.effective_user.first_name or "there"
    text = f"👋 Welcome, {user_first}!\n\nOpen your dashboard to get started."
    
    keyboard = [[InlineKeyboardButton("🏠 Open My Dashboard", callback_data="open_dashboard")]]
    
    update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )
    return ConversationHandler.END

def dashboard(update, context):
    """Customer dashboard entry point — /dashboard command"""
    return customer_start(update, context)


def handle_deep_link_review(update, context, order_num, review_type):
    """Handles deep link from Deal Group to leave a review"""
    context.user_data.clear()
    context.user_data['review_active'] = True
    
    if review_type == "user":
        text = f"⭐ <b>Leave a Review for Order {order_num}</b>\n\nHow would you rate your experience with the other party?"
        keyboard = [
            [
                InlineKeyboardButton("1 ⭐", callback_data=f"rate_user_{order_num}_1"),
                InlineKeyboardButton("2 ⭐", callback_data=f"rate_user_{order_num}_2"),
                InlineKeyboardButton("3 ⭐", callback_data=f"rate_user_{order_num}_3"),
                InlineKeyboardButton("4 ⭐", callback_data=f"rate_user_{order_num}_4"),
                InlineKeyboardButton("5 ⭐", callback_data=f"rate_user_{order_num}_5")
            ]
        ]
    else:
        text = f"⭐ <b>Leave a Review for SMYARDS Platform</b>\n\nHow would you rate our Escrow service for order {order_num}?"
        keyboard = [
            [
                InlineKeyboardButton("1 ⭐", callback_data=f"rate_plat_{order_num}_1"),
                InlineKeyboardButton("2 ⭐", callback_data=f"rate_plat_{order_num}_2"),
                InlineKeyboardButton("3 ⭐", callback_data=f"rate_plat_{order_num}_3"),
                InlineKeyboardButton("4 ⭐", callback_data=f"rate_plat_{order_num}_4"),
                InlineKeyboardButton("5 ⭐", callback_data=f"rate_plat_{order_num}_5")
            ]
        ]
        
    update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    user_id = update.effective_user.id
    if user_id == OWNER_ID or is_admin(user_id):
        return MAIN_MENU
    return CUSTOMER_MENU

def rebuild_escrow_post_text(order_num):
    pass

def update_escrow_post_with_review(bot, order_num):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT escrow_message_id FROM transactions_log WHERE order_number = ?", (order_num,))
    row = cursor.fetchone()
    if not row or not row[0]:
        conn.close()
        return
        
    # Safely parse message_id — guard against old tuple-string values like "(110, 111)"
    raw_id = str(row[0]).strip().strip('()')
    try:
        escrow_message_id = int(raw_id.split(',')[0].strip())
    except (ValueError, IndexError):
        logger.error(f"Invalid escrow_message_id in DB: {row[0]}")
        conn.close()
        return
    
    cursor.execute("SELECT rating, comment, reviewer_id, reviewer_name FROM platform_reviews WHERE order_number = ? AND status = 'active' ORDER BY created_at ASC", (order_num,))
    reviews = cursor.fetchall()
    
    cursor.execute("SELECT customer_id, seller_id FROM orders WHERE order_number = ?", (order_num,))
    order_data = cursor.fetchone()
    
    cursor.execute("""
        SELECT t.product_id, t.price, t.completed_at
        FROM transactions_log t
        WHERE t.order_number = ?
    """, (order_num,))
    tx = cursor.fetchone()
    conn.close()
    
    if not tx:
        return
    
    product_id, price, completed_at = tx
    
    try:
        from datetime import datetime
        if isinstance(completed_at, str):
            dt = datetime.strptime(completed_at.split('.')[0], '%Y-%m-%d %H:%M:%S')
            date_str = dt.strftime('%-d %b %Y') if os.name != 'nt' else dt.strftime('%#d %b %Y')
        else:
            date_str = completed_at.strftime('%-d %b %Y') if os.name != 'nt' else completed_at.strftime('%#d %b %Y')
    except Exception:
        date_str = str(completed_at)

    text = f'━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
    text += f'✨ Escrow Guarded Transaction Successfully Completed For <code>${price:,.2f}</code> For Order <code>{order_num}</code>\n'
    
    if reviews:
        buyer_id = order_data[0] if order_data else None
        seller_id = order_data[1] if order_data else None
        
        text += '💫 Platform Rreviews Received\n'
        text += '━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        
        for review in reviews:
            rating, comment, reviewer_id, reviewer_name = review
            stars = '⭐️' * rating
            obs_name = _obscure_name(reviewer_name) if reviewer_name else "User***"
            
            if reviewer_id == seller_id:
                label = f"👤 <b>Seller Review ({obs_name}):</b>"
            elif reviewer_id == buyer_id:
                label = f"👤 <b>Buyer Review ({obs_name}):</b>"
            else:
                label = f"👤 <b>Review ({obs_name}):</b>"
                
            text += f'\n{label}\n{stars}'
            if comment and comment.lower() != 'none':
                text += f' 💬 "{html_escape(comment)}"\n'
            else:
                text += '\n'
                
    else:
        text += '⏳ Waiting for Platform Reviews...\n'
        
    text += f'\n🛍 <b>Order:</b> <code>{order_num}</code>\n'
    text += f'🆔 <b>Account ID:</b> <code>{product_id}</code>\n'
    text += f'🕐 <b>Submitted:</b> {date_str}\n'
    text += f'━━━━━━━━━━━━━━━━━━━━━━━━━━'

    try:
        bot.edit_message_text(
            chat_id=ESCROW_LOG_CHANNEL_ID,
            message_id=escrow_message_id,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        logger.info(f"Updated Escrow_Log_Channel post {escrow_message_id} with reviews.")
    except Exception as e:
        logger.error(f"Error updating escrow post with review: {e}")

def handle_review_rating(update, context):
    """Step 1: User clicks a star rating. Show preset comment options."""
    query = update.callback_query
    data = query.data
    logger.debug("handle_review_rating: %s", data)
    
    if data.startswith('rate_plat_'):
        parts = data.replace('rate_plat_', '').rsplit('_', 1)
        order_num = parts[0]
        rating = int(parts[1])
        review_type = 'platform'
    elif data.startswith('rate_user_'):
        parts = data.replace('rate_user_', '').rsplit('_', 1)
        order_num = parts[0]
        rating = int(parts[1])
        review_type = 'user'
    else:
        return
        
    stars = '⭐' * rating
    try:
        query.answer(f"You selected {rating}/5 stars!")
    except Exception:
        pass
    
    # Use reviews.py for a varied, seeded selection of 5 preset options
    from reviews import get_preset_comments
    seed = hash((update.effective_user.id, order_num, rating))
    preset_comments = get_preset_comments(rating, review_type, seed=seed)
    
    keyboard = [[InlineKeyboardButton(c, callback_data=f"rvcmt_{review_type}_{order_num}_{rating}_{i}")] for i, c in enumerate(preset_comments)]
    keyboard.append([InlineKeyboardButton("📝 Write my own comment", callback_data=f"rv_write_{review_type}_{order_num}_{rating}")])
    keyboard.append([InlineKeyboardButton("⏭️ Skip comment", callback_data=f"rvcmt_{review_type}_{order_num}_{rating}_skip")])
    
    query.edit_message_text(
        f"{stars} <b>You rated {rating}/5</b>\n\nWould you like to add a quick comment? Pick one below or write your own:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )

def handle_review_comment_preset(update, context):
    """Step 2a: User picks a preset comment OR skips. Saves review immediately."""
    query = update.callback_query
    data = query.data  # rvcmt_{type}_{order_num}_{rating}_{idx_or_skip}
    logger.debug("handle_review_comment_preset: %s", data)
    
    parts = data[len('rvcmt_'):].split('_')
    # type, order_num parts (may contain underscores), rating, idx_or_skip
    # Format: rvcmt_platform_YT#0047_5_0 or rvcmt_user_YT#0047_3_skip
    review_type = parts[0]
    idx_or_skip = parts[-1]
    rating = int(parts[-2])
    order_num = '_'.join(parts[1:-2])  # everything between type and rating
    
    comment = None
    if idx_or_skip != 'skip':
        try:
            idx = int(idx_or_skip)
            # Re-generate the same seeded preset list so index mapping is consistent
            from reviews import get_preset_comments
            seed = hash((update.effective_user.id, order_num, rating))
            pool = get_preset_comments(rating, review_type, seed=seed)
            comment = pool[idx] if idx < len(pool) else None
        except (ValueError, IndexError):
            comment = None
    
    _save_review(update, context, review_type, order_num, rating, comment)
    try:
        query.answer()
    except Exception:
        pass
    text, markup = build_review_success_message(order_num, update.effective_user.id)
    query.edit_message_text(
        text,
        reply_markup=markup,
        parse_mode=ParseMode.HTML
    )


def handle_review_write_prompt(update, context):
    """Step 2b: User wants to write their own comment. Set pending state."""
    query = update.callback_query
    data = query.data  # rv_write_{type}_{order_num}_{rating}
    
    parts = data[len('rv_write_'):].split('_')
    review_type = parts[0]
    rating = int(parts[-1])
    order_num = '_'.join(parts[1:-1])
    
    context.user_data['pending_review'] = {
        'order_num': order_num,
        'rating': rating,
        'type': review_type
    }
    
    query.answer()
    query.edit_message_text(
        f"⭐ <b>Your rating: {rating}/5</b>\n\nPlease type your comment now:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏭️ Skip", callback_data=f"rvcmt_{review_type}_{order_num}_{rating}_skip")]]),
        parse_mode=ParseMode.HTML
    )


def handle_review_comment(update, context):
    """Step 2c: User typed a custom comment. Only fires if pending_review is set."""
    if update.message.chat.type != 'private':
        return
    if 'pending_review' not in context.user_data:
        if 'review_active' in context.user_data:
            update.message.reply_text("⚠️ Please select a Star rating from the message above before typing your comment.")
        return
        
    pending = context.user_data.pop('pending_review')
    comment = update.message.text.strip()
    if comment.lower() == '/skip':
        comment = None
    
    _save_review(update, context, pending['type'], pending['order_num'], pending['rating'], comment)
    text, markup = build_review_success_message(pending['order_num'], update.effective_user.id)
    update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)


def _save_review(update, context, r_type, order_num, rating, comment):
    """Internal helper: save a review to DB. Returns True on success, False on failure."""
    context.user_data.pop('review_active', None)
    user = update.effective_user
    # Ensure user is in database
    conn = get_connection()
    try:
        conn.execute("INSERT OR IGNORE INTO users (telegram_id, username) VALUES (?, ?)", 
                     (update.effective_user.id, update.effective_user.username))
        conn.commit()
    finally:
        conn.close()
    user_id = user.id
    user_name = user.first_name or str(user_id)
    
    logger.debug("_save_review: type=%s, order=%s, rating=%s, user=%s", r_type, order_num, rating, user_id)
    
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if r_type == 'platform':
            cursor.execute("""
                INSERT INTO platform_reviews (order_number, reviewer_id, reviewer_name, rating, comment)
                VALUES (?, ?, ?, ?, ?)
            """, (order_num, user_id, user_name, rating, comment))
            conn.commit()
            logger.debug("platform_review saved for order=%s", order_num)
            try:
                update_escrow_post_with_review(context.bot, order_num)
            except Exception as ue:
                logger.error("update_escrow_post_with_review failed: %s", ue, exc_info=True)
            return True
        else:
            # Determine who the target is
            cursor.execute("SELECT customer_id, customer_username, seller_id FROM orders WHERE order_number = ?", (order_num,))
            order_data = cursor.fetchone()
            target_id = 0
            target_username = 'Other Party'
            if order_data:
                buyer_id, buyer_username, seller_id = order_data[0], order_data[1], order_data[2]
                if user_id == buyer_id:
                    target_id = seller_id
                    cursor.execute("SELECT username FROM users WHERE telegram_id = ?", (seller_id,))
                    su = cursor.fetchone()
                    target_username = su[0] if su and su[0] else str(seller_id)
                elif user_id == seller_id:
                    target_id = buyer_id
                    target_username = buyer_username
            cursor.execute("""
                INSERT INTO user_reviews (order_number, reviewer_id, reviewer_name, target_user_id, target_username, rating, comment)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (order_num, user_id, user_name, target_id, target_username, rating, comment))
            conn.commit()
            logger.debug("user_review saved for order=%s, target=%s", order_num, target_id)
            return True
    except Exception as e:
        logger.error("Error saving review: %s", e, exc_info=True)
        return False
    finally:
        conn.close()

def build_review_success_message(order_num, user_id):
    """Show remaining review actions so users can submit both reviews independently."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM user_reviews WHERE order_number = ? AND reviewer_id = ? AND target_user_id != 0",
        (order_num, user_id)
    )
    has_user_review = cursor.fetchone() is not None
    cursor.execute(
        "SELECT id FROM platform_reviews WHERE order_number = ? AND reviewer_id = ? AND status = 'active'",
        (order_num, user_id)
    )
    has_platform_review = cursor.fetchone() is not None
    conn.close()

    buttons = []
    if not has_user_review:
        buttons.append([InlineKeyboardButton("⭐ Review Other Party", callback_data=f"leave_review_user_{order_num}")])
    if not has_platform_review:
        buttons.append([InlineKeyboardButton("⭐ Review Platform", callback_data=f"leave_review_platform_{order_num}")])

    if buttons:
        return (
            "✅ <b>Review Submitted!</b>\n\nThank you for your feedback! You can still submit the other review below.",
            InlineKeyboardMarkup(buttons)
        )

    return ("✅ <b>Both Reviews Submitted!</b>\n\nThank you for your feedback! ❤️", None)


def handle_deep_link_buy(update, context, product_id):
    """Handles deep link buy — shows account details and escrow fee, waits for confirmation before generating invoice."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM listings WHERE listing_id = ? AND status_flag = 'published'", (product_id,))
        listing = cursor.fetchone()
        conn.close()

        if not listing:
            update.message.reply_text(
                f"❌ <b>Account Not Found</b>\n\n"
                f"Product <code>{product_id}</code> is not available or has already been sold.\n\n"
                f"Use /dashboard to browse other available listings.",
                parse_mode=ParseMode.HTML
            )
            return

        price = float(listing["price"])
        escrow_fee = calculate_escrow_fee(price, row_get(listing, "created_by"))
        platform = listing["platform"]
        order_number = generate_order_number(platform)
        
        subs_fmt = format_number(listing['subscribers'])
        views_fmt = format_number(listing['views'])
        price_fmt = f"${price:,.0f}"
        fee_fmt = f"${escrow_fee:.2f}"

        # Store order info
        context.user_data['pending_order'] = {
            'listing_id': product_id,
            'platform': platform,
            'price': price,
            'escrow_fee': escrow_fee,
            'seller_id': row_get(listing, 'created_by'),
            'order_number': order_number
        }

        text = (
            f"🎯 <b>{listing['platform']} ACCOUNT</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>📋 BASIC INFO</b>\n"
            f"• 🆔 <b>Account ID:</b> <code>{product_id}</code>\n"
            f"• 👤 <b>Type:</b> {listing['account_type']}\n"
            f"• 🌍 <b>Region:</b> {listing['region'] or 'N/A'}\n\n"
            f"<b>📊 STATISTICS</b>\n"
            f"• 👥 <b>Subscribers:</b> {subs_fmt}\n"
            f"• 👀 <b>Views:</b> {views_fmt}\n"
            f"• ✅ <b>Status:</b> {listing['status'] or 'N/A'}\n\n"
            f"<b>⚙️ FEATURES</b>\n"
            f"• 🗃️ <b>Niche:</b> {listing['niche'] or 'Mixed'}\n"
            f"• 🔧 <b>Features:</b> {listing['features'] or 'N/A'}\n"
            f"• 💲 <b>Monetization:</b> {listing['monetization'] or 'N/A'}\n\n"
            f"<b>💰 PRICING & ESCROW</b>\n"
            f"• 💵 <b>Account Price:</b> {price_fmt}\n"
            f"• 🔐 <b>Escrow Fee (5%, min $5):</b> <b>{fee_fmt} USDT</b>\n\n"
            f"<b>🛡️ How Escrow Works:</b>\n"
            f"1. You pay the escrow fee\n"
            f"2. Admin creates a private group with you, seller, and themselves\n"
            f"3. Seller transfers the account to you\n"
            f"4. You confirm receipt of the account\n"
            f"5. Admin releases funds to the seller\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━"
        )

        keyboard = [
            [InlineKeyboardButton(f"💳 Pay Escrow Fee ({fee_fmt})", callback_data=f"confirm_pay_escrow_{product_id}")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_to_customer_start")]
        ]
        update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        
        return CUSTOMER_MENU

    except Exception as e:
        logger.error(f"Error in handle_deep_link_buy: {e}", exc_info=True)
        update.message.reply_text("❌ An error occurred. Please contact @smyards for assistance.")
        return CUSTOMER_MENU
		

def handle_deep_link_seller(update, context, seller_id):
    """Deep link to view a Seller's Profile — shows main profile menu."""
    try:
        seller_name = get_seller_name(seller_id)
        seller_username = get_seller_username(seller_id)
        # Store seller_id in user_data so sub-menus can access it
        context.user_data['viewing_seller_id'] = seller_id
        context.user_data['viewing_seller_name'] = seller_name

        text = (
            f"✴️ This is the Main Menu for 👤 User: <b>{seller_name}</b>"
        )
        keyboard = [
            [InlineKeyboardButton("📋 Listed Accounts", callback_data=f"sp_listings_{seller_id}")],
            [InlineKeyboardButton("⭐ Feedback Profile", callback_data=f"sp_feedback_{seller_id}")],
            [InlineKeyboardButton("💬 Message Seller", url=f"https://t.me/{seller_username}")],
            [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_customer_main")],
        ]
        update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
        return CUSTOMER_MENU
    except Exception as e:
        logger.error(f"Error in deep link seller: {str(e)}", exc_info=True)
        update.message.reply_text("❌ An error occurred loading the seller profile.")
        return CUSTOMER_MENU


def seller_profile_main_menu(update, context, seller_id=None):
    """Show the seller's main profile menu (called from callbacks)."""
    query = update.callback_query
    if seller_id is None:
        # Try to parse from callback data like sp_main_123456
        data = query.data
        seller_id = int(data.replace("sp_main_", ""))

    seller_name = get_seller_name(seller_id)
    seller_username = get_seller_username(seller_id)
    context.user_data['viewing_seller_id'] = seller_id
    context.user_data['viewing_seller_name'] = seller_name

    text = f"✴️ This is the Main Menu for 👤 User: <b>{seller_name}</b>"
    keyboard = [
        [InlineKeyboardButton("📋 Listed Accounts", callback_data=f"sp_listings_{seller_id}")],
        [InlineKeyboardButton("⭐ Feedback Profile", callback_data=f"sp_feedback_{seller_id}")],
        [InlineKeyboardButton("💬 Message Seller", url=f"https://t.me/{seller_username}")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_customer_main")],
    ]
    query.answer()
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CUSTOMER_MENU


def seller_profile_listings(update, context):
    """Show the seller's active account listings as buttons."""
    query = update.callback_query
    seller_id = int(query.data.replace("sp_listings_", ""))
    seller_name = get_seller_name(seller_id)
    seller_username = get_seller_username(seller_id)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT listing_id, platform, subscribers, views, price FROM listings "
        "WHERE seller_telegram_id = ? AND status_flag = 'published' ORDER BY created_at DESC",
        (seller_id,)
    )
    listings = cursor.fetchall()
    conn.close()

    if not listings:
        text = f"📋 <b>Listed Accounts for {seller_name}</b>\n\n⚠️ This seller has no active listings right now."
        keyboard = [[InlineKeyboardButton("🔙 Back to Profile", callback_data=f"sp_main_{seller_id}")]]
        query.answer()
        query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        return CUSTOMER_MENU

    text = f"📋 <b>Active Listings for {seller_name}</b>\n\nClick any account to view details:"
    keyboard = []
    for lst in listings:
        list_id, platform, subs, views, price = lst
        subs_fmt = f"{int(subs):,}" if subs else "N/A"
        views_fmt = f"{int(views):,}" if views else "N/A"
        price_fmt = f"${price:,.0f}" if price else "N/A"
        btn_text = f"{list_id} | {subs_fmt} Subs | {views_fmt} Views | {price_fmt}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"buyer_view_channel_{list_id}")])

    keyboard.append([InlineKeyboardButton("🔙 Back to Profile", callback_data=f"sp_main_{seller_id}")])

    query.answer()
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CUSTOMER_MENU


def seller_profile_feedback(update, context):
    """Show the seller's feedback profile with stats and reviews."""
    query = update.callback_query
    seller_id = int(query.data.replace("sp_feedback_", ""))

    conn = get_connection()
    cursor = conn.cursor()

    # Get seller name
    seller_name = get_seller_name(seller_id)
    seller_username = get_seller_username(seller_id)

    # Badge
    badge = "Regular"
    cursor.execute("SELECT badge_type, badge_expires_at FROM users WHERE telegram_id = ?", (seller_id,))
    res = cursor.fetchone()
    if res:
        badge_type, expires = res[0], res[1]
        if expires:
            from datetime import datetime as _dt
            try:
                if _dt.strptime(expires, '%Y-%m-%d %H:%M:%S') > _dt.now():
                    badge = badge_type
            except Exception:
                pass

    badge_icon = "🛡️ VIP" if badge == "VIP" else ("🔹 Pro" if badge == "Pro" else "👤 Regular")

    # Rating
    cursor.execute("SELECT AVG(rating), COUNT(*) FROM user_reviews WHERE target_user_id = ?", (seller_id,))
    res = cursor.fetchone()
    avg_rating = float(res[0]) if res and res[0] else 0.0
    review_count = res[1] if res else 0
    rating_str = f"⭐ {avg_rating:.1f}/5.0" if avg_rating > 0 else "⭐ No Reviews Yet"

    # Completed trades & worth
    cursor.execute(
        "SELECT COUNT(*), SUM(total_price) FROM orders WHERE seller_id = ? AND order_status = 'completed'",
        (seller_id,)
    )
    res = cursor.fetchone()
    trades = res[0] if res else 0
    trades_worth = res[1] if res and res[1] else 0.0

    # Reviews (last 10)
    cursor.execute("""
        SELECT ur.reviewer_name, ur.order_number, ur.rating, ur.comment, ur.created_at,
               o.product_id, o.total_price
        FROM user_reviews ur
        LEFT JOIN orders o ON o.order_number = ur.order_number
        WHERE ur.target_user_id = ?
        ORDER BY ur.created_at DESC
        LIMIT 10
    """, (seller_id,))
    reviews = cursor.fetchall()
    conn.close()

    text = (
        f"👤 <b>User:</b> {seller_name}\n"
        f"🤝 <b>Completed Trades:</b> {trades}\n"
        f"💰 <b>Trades Worth:</b> ${trades_worth:,.0f}\n"
        f"🏅 <b>Badge:</b> {badge_icon}\n"
        f"📈 <b>Rating:</b> {rating_str}\n"
    )

    if reviews:
        text += "\n📝 <b>Reviews:</b>\n"
        for rev in reviews:
            rev_name, order_num, rating, comment, created_at, product_id, tx_price = rev
            obs_name = _obscure_name(rev_name) if rev_name else "User***"
            stars = "⭐️" * rating
            price_str = f"${tx_price:,.0f}" if tx_price else "N/A"
            prod_str = product_id or "N/A"
            date_str = created_at[:19] if created_at else "N/A"
            text += (
                f"\n<b>{obs_name}</b> | <code>{order_num}</code> | {prod_str} | {price_str}\n"
                f"{stars} 💬 \"{html_escape(comment or '')}\"\n"
                f"<i>{date_str}</i>\n"
            )
    else:
        text += "\n📝 <i>No reviews yet.</i>"

    keyboard = [[InlineKeyboardButton("🔙 Back to Profile", callback_data=f"sp_main_{seller_id}")]]

    query.answer()
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CUSTOMER_MENU


def handle_deep_link_sell(update, context):
    """Deep link sell — goes straight to the sell info screen, same as clicking Sell a Channel"""
    try:
        text = (
            "💰 <b>SELL YOUR ACCOUNT NOW:</b>\n\n"
            "_____________________________________\n"
            "✅ <b>Why Sell With Our Platform?</b>\n"
            "_____________________________________\n"
            "• Reach thousands of serious buyers\n"
            "• Secure escrow protection\n"
            "• Get paid quickly &amp; safely\n"
            "• Professional listing presentation\n\n"
            "___________________\n"
            "📋 <b>How It Works:</b>\n"
            "___________________\n"
            "1. Submit your account details\n"
            "2. Our team reviews &amp; approves\n"
            "3. Your account gets listed on our platform\n"
            "4. Buyers contact you via our system\n"
            "5. We handle secure payment via escrow\n"
            "6. You get paid after successful account transfer\n\n"
            "_____________________________\n"
            "⚖️ <b>Service Terms &amp; Rules:</b>\n"
            "_____________________________\n"
            "⏰ <b>Approval Time:</b> 2-12 hours\n"
            "💰 <b>Commission:</b> 5% escrow fee (paid by buyer)\n"
            "🛡 <b>Security:</b> 100% protected transactions\n\n"
            "Ready to list your account?"
        )
        keyboard = [
            [InlineKeyboardButton("📝 List Your Account Now", callback_data="seller_list_account")],
        ]
        update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
        return SELLER_INFO
        
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Error in deep link sell: %s", e)


def error_handler(update, context):
    """Log errors cleanly without redundant try/except blocks"""
    logger.error(f"Update {update} caused error:", exc_info=context.error)
    
    try:
        if update and update.effective_message and update.effective_chat.type == "private":
            update.effective_message.reply_text("❌ An unexpected error occurred.\nPlease try again or contact @smyards for support.")
    except Exception as e:
        logger.error(f"Error notifying user in error handler: {e}")

        

def admin_simulate_payment(update, context):
    """TESTING ONLY — manually mark an order as paid to test the post-payment flow."""
    if update.effective_user.id != OWNER_ID:
        return
    
    if not context.args:
        update.message.reply_text(
            "Usage: /simulate_payment ORDER_NUMBER\n"
            "Example: /simulate_payment YT#0007"
        )
        return
    
    order_number = context.args[0]
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check if this is an upgrade order
    if order_number.startswith("sub-"):
        cursor.execute("SELECT * FROM upgrade_orders WHERE order_number = ?", (order_number,))
        upg_order = cursor.fetchone()
        
        if not upg_order:
            conn.close()
            update.message.reply_text(f"❌ Upgrade Order {order_number} not found.")
            return
            
        cursor.execute("PRAGMA table_info(upgrade_orders)")
        columns = [col[1] for col in cursor.fetchall()]
        upg_dict = dict(zip(columns, upg_order))
        
        # Update order status
        cursor.execute("""
            UPDATE upgrade_orders
            SET payment_status = 'confirmed',
                payment_confirmed_at = CURRENT_TIMESTAMP
            WHERE order_number = ?
        """, (order_number,))
        
        # Grant badge
        uid = upg_dict['customer_id']
        uname = upg_dict['customer_username']
        tier = upg_dict['upgrade_type']
        days = upg_dict['duration_days']
        
        from datetime import datetime, timedelta
        expiry = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute("""
            INSERT INTO users (telegram_id, username, badge_type, badge_expires_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                badge_type = excluded.badge_type,
                badge_expires_at = excluded.badge_expires_at
        """, (uid, uname, tier, expiry))
        conn.commit()
        conn.close()
        
        # Notify User
        try:
            context.bot.send_message(
                chat_id=uid,
                text=f"🎉 **PAYMENT CONFIRMED!**\n\nYour **{tier}** upgrade has been successfully activated for {days} days!\n\nCheck your Dashboard for your new perks.",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to notify user of upgrade: {e}")
            
        # Notify Admin
        update.message.reply_text(
            f"✅ **UPGRADE PAYMENT CONFIRMED (Simulated)**\n\n"
            f"📦 Order: `{order_number}`\n"
            f"👤 User: @{uname}\n"
            f"💎 Type: **{tier}**\n"
            f"💰 Paid: ${upg_dict['amount_to_pay']}\n\n"
            f"Badge successfully granted for {days} days.",
            parse_mode="Markdown"
        )
        return

    # Regular order flow
    cursor.execute("""
        UPDATE orders 
        SET payment_status = 'confirmed', 
            payment_confirmed_at = CURRENT_TIMESTAMP
        WHERE order_number = ?
    """, (order_number,))
    conn.commit()
    
    cursor.execute("SELECT * FROM orders WHERE order_number = ?", (order_number,))
    order = cursor.fetchone()
    cursor.execute("PRAGMA table_info(orders)")
    columns = [col[1] for col in cursor.fetchall()]
    conn.close()
    
    if not order:
        update.message.reply_text(f"❌ Order {order_number} not found.")
        return
    
    order_dict = dict(zip(columns, order))
    order_id = order_dict.get('id')
    seller_id = order_dict.get('seller_id')
    product_id = order_dict.get('product_id')
    buyer_username = order_dict.get('customer_username', 'N/A')
    price = order_dict.get('total_price', 0)
    escrow_fee = order_dict.get('escrow_fee', 0)

    group_assigned = False
    group_invite_link = None
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Auto-assign Deal Group from pool
        cursor.execute("SELECT id, chat_id, invite_link FROM available_groups WHERE status = 'available' ORDER BY created_at ASC LIMIT 1")
        available_group = cursor.fetchone()
        
        if available_group:
            group_db_id, group_chat_id, group_invite_link = available_group
            
            # Mark group in use and update order
            cursor.execute("UPDATE available_groups SET status = 'in_use', assigned_order_id = ? WHERE id = ?", (order_number, group_db_id))
            cursor.execute("UPDATE orders SET transaction_group_id = ?, transaction_group_link = ?, order_status = 'group_link_set' WHERE order_number = ?", 
                           (group_chat_id, group_invite_link, order_number))
            group_assigned = True
            
            # Attempt to rename the group
            try:
                context.bot.set_chat_title(chat_id=group_chat_id, title=f"SMyards - Transaction {order_number} Group")
            except Exception as e:
                logger.error(f"Error renaming group {group_chat_id}: {e}")
        conn.commit()
    finally:
        conn.close()

    # Notify Buyer
    buyer_id = order_dict.get('customer_id')
    if buyer_id and group_assigned and group_invite_link:
        try:
            context.bot.send_message(
                chat_id=buyer_id,
                text=(
                    f"✅ **PAYMENT CONFIRMED!**\n\n"
                    f"Your escrow payment for order `{order_number}` is secured.\n\n"
                    f"🔗 **Join the Deal Group Here:**\n{group_invite_link}\n\n"
                    f"The seller and admin are waiting for you!"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Error notifying buyer: {e}")

    # Notify Seller
    if seller_id and group_assigned and group_invite_link:
        try:
            context.bot.send_message(
                chat_id=seller_id,
                text=(
                    f"✅ **PAYMENT CONFIRMED FOR YOUR LISTING!**\n\n"
                    f"📦 **Product:** `{product_id}`\n"
                    f"🆔 **Order:** `{order_number}`\n"
                    f"👤 **Buyer:** @{buyer_username}\n\n"
                    f"The buyer's payment is fully secured in escrow!\n\n"
                    f"🔗 **Join the Deal Group Here:**\n{group_invite_link}\n\n"
                    f"Please join to proceed with transferring the account."
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Error notifying seller: {e}")

    # Send admin notification
    if group_assigned:
        update.message.reply_text(
            f"✅ <b>PAYMENT CONFIRMED (Simulated)</b>\n\n"
            f"🆔 Order: <code>{order_number}</code>\n"
            f"📦 Product: <code>{product_id}</code>\n"
            f"👤 Buyer: @{buyer_username}\n"
            f"💵 Escrow Fee: ${escrow_fee:.2f}\n\n"
            f"🤖 <b>A Deal Group was automatically assigned from the pool!</b>\n"
            f"🔗 Link: {group_invite_link}",
            parse_mode=ParseMode.HTML
        )
    else:
        keyboard = [[InlineKeyboardButton("🔗 Add Group Link", callback_data=f"add_group_link_{order_id}")]]
        update.message.reply_text(
            f"✅ <b>PAYMENT CONFIRMED (Simulated)</b>\n\n"
            f"🆔 Order: <code>{order_number}</code>\n"
            f"📦 Product: <code>{product_id}</code>\n"
            f"👤 Buyer: @{buyer_username}\n"
            f"💵 Escrow Fee: ${escrow_fee:.2f}\n\n"
            f"⚠️ <b>No Deal Groups available in pool.</b>\n"
            f"➡️ Click below to add the group link manually:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )

    # Notify seller
    if seller_id:
        try:
            if group_assigned:
                seller_text = (
                    f"🛍 <b>NEW ORDER ON YOUR LISTING!</b>\n\n"
                    f"📦 <b>Product:</b> <code>{product_id}</code>\n"
                    f"🆔 <b>Order:</b> <code>{order_number}</code>\n"
                    f"💰 <b>Price:</b> ${price:,.2f}\n"
                    f"🛡️ <b>Escrow Fee:</b> ${escrow_fee:.2f}\n"
                    f"👤 <b>Buyer:</b> @{buyer_username}\n\n"
                    f"✅ **A secure Deal Group has been created!** Join here to hand over the account:\n{group_invite_link}"
                )
            else:
                seller_text = (
                    f"🛍 <b>NEW ORDER ON YOUR LISTING!</b>\n\n"
                    f"📦 <b>Product:</b> <code>{product_id}</code>\n"
                    f"🆔 <b>Order:</b> <code>{order_number}</code>\n"
                    f"💰 <b>Price:</b> ${price:,.2f}\n"
                    f"🛡️ <b>Escrow Fee:</b> ${escrow_fee:.2f}\n"
                    f"👤 <b>Buyer:</b> @{buyer_username}\n\n"
                    f"⏳ Waiting for admin to set up the deal group...\n\n"
                    f"You'll receive the group link shortly!"
                )
            
            context.bot.send_message(
                chat_id=int(seller_id),
                text=seller_text,
                parse_mode=ParseMode.HTML
            )
            update.message.reply_text("✅ Seller also notified.")
        except Exception as e:
            update.message.reply_text(
                f"⚠️ Could not notify seller.\n"
                f"seller_id in DB: {seller_id}\n"
                f"Error: {e}"
            )
    else:
        update.message.reply_text(
            f"⚠️ No seller_id found for this order.\n"
            f"This is likely an admin-created listing.\n"
            f"seller_id in DB: {seller_id}"
        )

def admin_manage_listing(update, context):
    """Admin manage single listing with bump/delete/mark sold options."""
    query = update.callback_query
    query.answer()
    
    listing_id = int(query.data.replace("admin_manage_listing_", ""))
    context.user_data['admin_managing_listing_id'] = listing_id
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT listing_id, platform, price, status_flag FROM listings WHERE id = ?", (listing_id,))
    listing = cursor.fetchone()
    conn.close()
    
    if not listing:
        query.edit_message_text("❌ Listing not found.")
        return MAIN_MENU
    
    l_id, platform, price, status = listing
    
    text = (
        f"⚙️ <b>Manage Listing</b>\n"
        f"🆔 {l_id} | {platform} | ${price:,.0f}\n"
        f"Status: {status.upper()}\n\n"
        f"Choose action:"
    )
    
    keyboard = [
        [InlineKeyboardButton("🆙 Bump to the Top", callback_data=f"admin_bump_listing_{listing_id}")],
        [InlineKeyboardButton("💰 Mark as Sold", callback_data=f"admin_mark_sold_listing_{listing_id}")],
        [InlineKeyboardButton("🗑️ Delete Listing", callback_data=f"admin_delete_listing_{listing_id}")],
        [InlineKeyboardButton("🔙 Back to Listings", callback_data="admin_view_listings_reset")],
    ]
    
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return MAIN_MENU

# admin_delete_listing - delete with confirmation
def admin_delete_listing(update, context):
    """Delete a listing after confirmation."""
    query = update.callback_query
    query.answer()
    
    listing_id = int(query.data.replace("admin_delete_listing_", ""))
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT listing_id FROM listings WHERE id = ?", (listing_id,))
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        query.edit_message_text("❌ Listing not found.")
        return MAIN_MENU
    
    l_id = result[0]
    context.user_data['listing_to_delete'] = listing_id
    
    text = f"⚠️ <b>CONFIRM DELETE</b>\n\nPermanently delete listing <code>{l_id}</code>?\n\nThis cannot be undone!"
    keyboard = [
        [InlineKeyboardButton("✅ Yes, Delete", callback_data="confirm_delete_listing")],
        [InlineKeyboardButton("❌ Cancel", callback_data="admin_view_listings_reset")],
    ]
    
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return MAIN_MENU

# confirm_delete_listing - executes deletion
def confirm_delete_listing(update, context):
    """Execute listing deletion."""
    query = update.callback_query
    query.answer()
    
    listing_id = context.user_data.pop('listing_to_delete', None)
    
    if not listing_id:
        query.edit_message_text("❌ Error: Listing ID not found.")
        return MAIN_MENU
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT listing_id FROM listings WHERE id = ?", (listing_id,))
        result = cursor.fetchone()
        
        if result:
            l_id = result[0]
            cursor.execute("DELETE FROM listings WHERE id = ?", (listing_id,))
            conn.commit()
            query.edit_message_text(f"✅ Listing <code>{l_id}</code> deleted from database.", parse_mode=ParseMode.HTML)
        else:
            query.edit_message_text("❌ Listing not found.")
        
        conn.close()
    except Exception as e:
        logger.error(f"Error deleting listing: {e}")
        query.edit_message_text(f"❌ Error: {str(e)[:100]}")
    
    return MAIN_MENU

# admin_view_listings_reset - reset filters
def admin_view_listings_reset(update, context):
    """Reset platform filter and go back to main admin listings view."""
    query = update.callback_query
    query.answer()
    
    context.user_data.pop('admin_platform_filter', None)
    context.user_data['listings_page'] = 0
    
    return admin_view_listings(update, context)

		


		
		
def debug_check_order(update, context):
    """Admin command to check order details - /check_order ORDER_NUMBER"""
    if update.effective_user.id != OWNER_ID:
        return
    
    if not context.args:
        update.message.reply_text(
            "Usage: /check_order ORDER_NUMBER\n"
            "Example: /check_order YT#0001\n"
            "This shows order details including seller_id"
        )
        return
    
    order_number = context.args[0]
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, order_number, product_id, customer_id, customer_username, 
               seller_id, payment_status, order_status, created_at, transaction_group_link
        FROM orders WHERE order_number = ?
    """, (order_number,))
    order = cursor.fetchone()
    conn.close()
    
    if not order:
        update.message.reply_text(f"❌ Order {order_number} not found")
        return
    
    order_id, ord_num, product_id, customer_id, customer_username, seller_id, payment_status, order_status, created_at, group_link = order
    
    text = (
        f"🔍 <b>ORDER DEBUG INFO</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Order Details:</b>\n"
        f"• ID: <code>{order_id}</code>\n"
        f"• Order #: <code>{ord_num}</code>\n"
        f"• Product: <code>{product_id}</code>\n"
        f"• Payment: {payment_status}\n"
        f"• Status: {order_status}\n"
        f"• Created: {created_at}\n\n"
        f"<b>Buyer:</b>\n"
        f"• ID: <code>{customer_id}</code>\n"
        f"• Username: @{customer_username}\n\n"
        f"<b>SELLER (THIS IS KEY!):</b>\n"
        f"• seller_id: <code>{seller_id}</code> {'✅ VALID' if seller_id else '❌ NULL!'}\n"
        f"• Is Admin? {seller_id == OWNER_ID}\n\n"
        f"<b>Group Link:</b>\n"
        f"• Set: {'✅ Yes' if group_link else '❌ No'}\n"
        f"• Link: {group_link if group_link else 'None'}\n"
    )

	
    update.message.reply_text(text, parse_mode=ParseMode.HTML)

def admin_pool_group(update, context):
    """Admin command: /pool <invite_link> — adds the current group to the deal group pool."""
    if update.effective_user.id != OWNER_ID:
        return
    
    chat = update.effective_chat
    
    # Must be used in a group
    if chat.type not in ('group', 'supergroup'):
        update.message.reply_text("❌ This command must be used inside a group chat.")
        return
    
    # Get invite link from args or generate one
    if context.args:
        invite_link = context.args[0]
    else:
        try:
            invite_link = context.bot.export_chat_invite_link(chat.id)
        except Exception as e:
            update.message.reply_text(f"❌ Could not get invite link. Please provide one:\n/pool <invite_link>")
            return
    
    chat_id = str(chat.id)
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO available_groups (chat_id, invite_link, status) VALUES (?, ?, 'available')",
            (chat_id, invite_link)
        )
        if cursor.rowcount == 0:
            update.message.reply_text(f"⚠️ This group is already in the pool.")
        else:
            conn.commit()
            update.message.reply_text(
                f"✅ <b>Group Added to Deal Pool!</b>\n\n"
                f"• <b>Chat ID:</b> <code>{chat_id}</code>\n"
                f"• <b>Invite Link:</b> {invite_link}\n"
                f"• <b>Status:</b> 🟢 Available\n\n"
                f"This group will be automatically assigned to the next paid order.",
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        logger.error(f"Error adding group to pool: {e}")
        update.message.reply_text(f"❌ Error adding group: {e}")
    finally:
        conn.close()

def admin_check_seller_id(update, context):
    """Admin command to diagnose seller notification issues"""
    if update.effective_user.id != OWNER_ID:
        return
    
    if not context.args:
        update.message.reply_text(
            "Usage: /check_seller ORDER_NUMBER\n"
            "Shows if seller_id is set and what it is\n\n"
            "Example: /check_seller YT#0001"
        )
        return
    
    order_number = context.args[0]
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check orders table
    cursor.execute("""
        SELECT id, product_id, seller_id, customer_id, payment_status
        FROM orders WHERE order_number = ?
    """, (order_number,))
    order = cursor.fetchone()
    
    if not order:
        update.message.reply_text(f"❌ Order {order_number} not found")
        conn.close()
        return
    
    order_id, product_id, seller_id, buyer_id, payment_status = order
    
    # Check listing
    cursor.execute("SELECT created_by FROM listings WHERE listing_id = ?", (product_id,))
    listing = cursor.fetchone()
    listing_created_by = listing[0] if listing else None
    
    conn.close()
    
    text = (
        f"🔍 <b>SELLER DIAGNOSTIC</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Order:</b> {order_number}\n"
        f"<b>Product:</b> {product_id}\n"
        f"<b>Payment Status:</b> {payment_status}\n\n"
        f"<b>CRITICAL - Seller ID:</b>\n"
        f"• In orders table: <code>{seller_id}</code>\n"
        f"• In listings.created_by: <code>{listing_created_by}</code>\n"
        f"• Match? {'✅ YES' if seller_id == listing_created_by else '❌ NO'}\n"
        f"• Is NULL? {'❌ YES - PROBLEM!' if not seller_id else '✅ NO'}\n"
        f"• Is Admin (OWNER_ID={OWNER_ID})? {'⚠️ YES - Will skip' if seller_id == OWNER_ID else '✅ NO'}\n\n"
        f"<b>Buyer ID:</b> {buyer_id}\n\n"
    )
    
    if not seller_id:
        text += "❌ <b>PROBLEM FOUND:</b> seller_id is NULL!\n"
        text += "This is why seller is not notified.\n"
        text += "Check if listing {product_id} has created_by set."
    elif seller_id == OWNER_ID:
        text += "⚠️ <b>INFO:</b> This is admin-created listing.\n"
        text += "Seller notifications skipped for admin listings (expected)."
    else:
        text += f"✅ seller_id={seller_id} looks valid.\n"
        text += f"If seller still not notified, check:\n"
        text += f"1. Is Telegram ID {seller_id} correct?\n"
        text += f"2. Can bot message that Telegram ID?\n"
        text += f"3. Check bot logs for error messages."
    
    update.message.reply_text(text, parse_mode=ParseMode.HTML)

	
# ===== SCHEDULED JOB FUNCTIONS (For Escrow_Log Channel) =====
import datetime as _dt

def _next_sunday_10am():
    """Return a datetime for the next Sunday at 10:00 AM UTC."""
    now = _dt.datetime.utcnow()
    days_ahead = (6 - now.weekday()) % 7
    if days_ahead == 0 and now.hour >= 10:
        days_ahead = 7
    if days_ahead == 0:
        days_ahead = 7
    next_sun = now + _dt.timedelta(days=days_ahead)
    return next_sun.replace(hour=10, minute=0, second=0, microsecond=0)

def weekly_escrow_summary_job(context):
    """Post a weekly escrow summary to Escrow_Log_Channel every Sunday."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*), COALESCE(SUM(price), 0)
            FROM transactions_log
            WHERE completed_at >= datetime('now', '-7 days')
        """)
        week_count, week_volume = cursor.fetchone()
        week_volume = week_volume or 0
        cursor.execute("SELECT COUNT(*), COALESCE(SUM(price), 0) FROM transactions_log")
        total_count, total_volume = cursor.fetchone()
        total_volume = total_volume or 0
        conn.close()
        now = _dt.datetime.utcnow()
        week_start = (now - _dt.timedelta(days=6)).strftime('%d %b')
        week_end = now.strftime('%d %b %Y')
        text = (
            f"\ud83d\udcca <b>SMYARDS WEEKLY ESCROW REPORT</b>\n"
            f"Week of {week_start} \u2013 {week_end}\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"\u2705 Completed Deals: <b>{week_count}</b>\n"
            f"\ud83d\udcb0 Total Volume: <b>${week_volume:,.2f}</b>\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"\ud83d\udd22 <b>Lifetime Totals:</b>\n"
            f"   \ud83d\udea7 Total Deals: <b>{total_count}</b>\n"
            f"   \ud83d\udcb5 Total Volume: <b>${total_volume:,.2f}</b>"
        )
        context.bot.send_message(chat_id=ESCROW_LOG_CHANNEL_ID, text=text, parse_mode="HTML")
        logger.info(f"Weekly summary posted ({week_count} deals this week)")
    except Exception as e:
        logger.error(f"Error posting weekly summary: {e}", exc_info=True)

def monthly_review_highlights_job(context):
    """On first Sunday of month, post top 3 platform review highlights from previous month."""
    try:
        now = _dt.datetime.utcnow()
        if now.day > 7:
            return
        conn = get_connection()
        cursor = conn.cursor()
        first_of_this_month = now.replace(day=1)
        last_month_end = first_of_this_month - _dt.timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        cursor.execute("""
            SELECT reviewer_name, rating, comment
            FROM platform_reviews
            WHERE status = 'active'
              AND created_at >= ?
              AND created_at <= ?
              AND comment IS NOT NULL AND TRIM(comment) != ''
            ORDER BY rating DESC, created_at DESC
            LIMIT 3
        """, (last_month_start.strftime('%Y-%m-%d'), last_month_end.strftime('%Y-%m-%d 23:59:59')))
        reviews = cursor.fetchall()
        conn.close()
        if not reviews:
            logger.info("No platform reviews last month, skipping highlights.")
            return
        month_name = last_month_end.strftime('%B %Y')
        text = (
            f"\ud83c\udf1f <b>SMYARDS REVIEW HIGHLIGHTS</b>\n"
            f"\ud83d\udcc5 {month_name}\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        )
        medals = ["\ud83e\udd47", "\ud83e\udd48", "\ud83e\udd49"]
        for i, (reviewer, rating, comment) in enumerate(reviews):
            stars = "\u2b50" * rating
            short_comment = (comment[:80] + "\u2026") if len(comment) > 80 else comment
            name_display = (reviewer[0] + "\u2022\u2022\u2022") if reviewer else "User"
            text += f"{medals[i]} {name_display}\n{stars}\n\u201c{short_comment}\u201d\n\n"
        text += "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\ud83d\uded2 <b>smyards.net</b> | Trusted Escrow Marketplace"
        context.bot.send_message(chat_id=ESCROW_LOG_CHANNEL_ID, text=text, parse_mode="HTML")
        logger.info(f"Monthly highlights posted for {month_name}")
    except Exception as e:
        logger.error(f"Error posting monthly highlights: {e}", exc_info=True)


# ===== MAIN EXECUTION =====
def main():
    init_database()
    updater = Updater(BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher
    
    # 1. STANDALONE CALLBACKS
    dispatcher.add_handler(CallbackQueryHandler(approve_customer_listing, pattern='^approve_listing_'))
    dispatcher.add_handler(CallbackQueryHandler(reject_customer_listing, pattern='^reject_listing_'))
    dispatcher.add_handler(CallbackQueryHandler(verify_payment, pattern='^verify_payment_'))
    dispatcher.add_handler(CommandHandler('simulate_payment', admin_simulate_payment))
    dispatcher.add_handler(CallbackQueryHandler(admin_add_group_link, pattern='^add_group_link_'))
    dispatcher.add_handler(CallbackQueryHandler(handle_admin_edit_approval, pattern='^admin_approve_edit_|^admin_reject_edit_'))
    dispatcher.add_handler(MessageHandler(
        Filters.text & ~Filters.command & Filters.user(OWNER_ID),
        admin_handle_group_link_standalone
    ), group=1)
    dispatcher.add_handler(CommandHandler('check_order', debug_check_order))
    dispatcher.add_handler(CommandHandler('setname', admin_setname))
    dispatcher.add_handler(CommandHandler('check_seller', admin_check_seller_id))
    dispatcher.add_handler(CommandHandler('pool', admin_pool_group))
    dispatcher.add_error_handler(error_handler)

    # Review handlers (fire before ConversationHandlers in group 0)
    dispatcher.add_handler(CallbackQueryHandler(handle_review_rating, pattern='^rate_plat_'))
    dispatcher.add_handler(CallbackQueryHandler(handle_review_rating, pattern='^rate_user_'))
    dispatcher.add_handler(CallbackQueryHandler(handle_review_comment_preset, pattern='^rvcmt_'))
    dispatcher.add_handler(CallbackQueryHandler(handle_review_write_prompt, pattern='^rv_write_'))
    # Noop handler: silently dismisses separator buttons in review DMs
    dispatcher.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.answer(), pattern='^noop$'))

    admin_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('admin', admin_start),
            CallbackQueryHandler(admin_start, pattern='^admin_back_main$'),
            CallbackQueryHandler(admin_settings, pattern='^admin_settings$')
        ],
        states={
            MAIN_MENU: [CallbackQueryHandler(admin_button_callback)],
            CREATE_PLATFORM: [CallbackQueryHandler(admin_button_callback)],
            CREATE_TYPE: [
                MessageHandler(Filters.text & ~Filters.command, admin_handle_channel_age),
                CallbackQueryHandler(admin_button_callback)
            ],
            CREATE_DETAILS: [
                MessageHandler(Filters.text & ~Filters.command, admin_handle_details),
                CallbackQueryHandler(admin_button_callback)
            ],
            CREATE_PRICE: [
                MessageHandler(Filters.text & ~Filters.command, admin_handle_price),
                CallbackQueryHandler(admin_button_callback)
            ],
            CREATE_SELLER_CONTACT: [
                MessageHandler(Filters.text & ~Filters.command, admin_handle_seller_contact),
                CallbackQueryHandler(admin_button_callback)
            ],
            SCREENSHOT_ASK: [CallbackQueryHandler(admin_button_callback)],
            SCREENSHOT_UPLOAD: [
                MessageHandler(Filters.photo, admin_handle_screenshot_upload),
                MessageHandler(Filters.text & ~Filters.command, admin_handle_screenshot_upload),
                CallbackQueryHandler(admin_button_callback)
            ],
            CREATE_CONFIRM: [CallbackQueryHandler(admin_button_callback)],
            MARK_SOLD: [CallbackQueryHandler(admin_button_callback)],
            ENTER_PRODUCT_ID: [
                MessageHandler(Filters.text & ~Filters.command, admin_handle_seller_tg_id),
                CallbackQueryHandler(admin_button_callback)
            ],
            ENTER_SELLER_NAME: [
                MessageHandler(Filters.text & ~Filters.command, admin_handle_seller_display_name),
                CallbackQueryHandler(admin_button_callback)
            ],
            ENTER_TXID: [
                MessageHandler(Filters.text & ~Filters.command, admin_button_callback),
                CallbackQueryHandler(admin_button_callback)
            ],
            ENTER_PAYMENT_METHOD: [
                MessageHandler(Filters.text & ~Filters.command, admin_button_callback),
                CallbackQueryHandler(admin_button_callback)
            ],
            ENTER_ORDER_NUMBER: [
                MessageHandler(Filters.text & ~Filters.command, admin_button_callback),
                CallbackQueryHandler(admin_button_callback)
            ],
            ADMIN_RELIST_MENU: [CallbackQueryHandler(admin_button_callback)],
            ADMIN_ORDERS_PANEL: [CallbackQueryHandler(admin_button_callback)],
            ADMIN_ORDER_DETAIL: [CallbackQueryHandler(admin_button_callback)],
            ADMIN_ADD_GROUP_LINK: [
                MessageHandler(Filters.text & ~Filters.command, admin_handle_group_link_input),
                CallbackQueryHandler(admin_button_callback)
            ],
            ADMIN_MARK_SOLD: [
                MessageHandler(Filters.text & ~Filters.command, route_admin_mark_sold_flow),
                CallbackQueryHandler(admin_button_callback)
            ],
            ENTER_ORDER_TXID: [
                MessageHandler(Filters.text & ~Filters.command, admin_handle_order_txid),
                CallbackQueryHandler(admin_button_callback)
            ],
            ENTER_ORDER_PAYMENT_METHOD: [
                CallbackQueryHandler(admin_handle_order_payment_method, pattern='^opm_'),
                CallbackQueryHandler(admin_button_callback)
            ],
            ENTER_CUSTOM_CRYPTO: [
                MessageHandler(Filters.text & ~Filters.command, admin_handle_custom_crypto),
                CallbackQueryHandler(admin_button_callback)
            ],
            ADMIN_REJECT_REASON: [
                MessageHandler(Filters.text & ~Filters.command, admin_handle_reject_reason),
                CallbackQueryHandler(admin_button_callback)
            ],
            ADMIN_EDIT_REVIEW: [
                MessageHandler(Filters.text & ~Filters.command, admin_handle_edit_review),
                CallbackQueryHandler(admin_button_callback)
            ],
            ADMIN_EDIT_BUMP_TIME: [
                MessageHandler(Filters.text & ~Filters.command, admin_handle_bump_settings_edit),
                CallbackQueryHandler(admin_button_callback)
            ],
            ASSIGN_UPGRADE_USER: [
                MessageHandler(Filters.text & ~Filters.command, admin_handle_upgrade_username),
                CallbackQueryHandler(admin_button_callback)
            ],
            ASSIGN_UPGRADE_TYPE: [
                CallbackQueryHandler(admin_handle_upgrade_type, pattern='^assign_type_'),
                CallbackQueryHandler(admin_button_callback)
            ],
            ASSIGN_UPGRADE_DUR: [
                MessageHandler(Filters.text & ~Filters.command, admin_handle_upgrade_duration),
                CallbackQueryHandler(admin_button_callback)
            ],
        },
        fallbacks=[CommandHandler('start', start)],
        allow_reentry=True,
        name="admin_conversation"
    )
    dispatcher.add_handler(admin_conv_handler)
    
    # 3. CUSTOMER CONVERSATION (Uses /start and /customer)
    customer_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('customer', customer_start),
            CommandHandler('dashboard', dashboard),
            CommandHandler('start', start),
            CallbackQueryHandler(customer_start, pattern='^open_dashboard$'),
            CallbackQueryHandler(browse_menu, pattern='^browse_menu$'),
        ],
        states={
            CUSTOMER_MENU: [
                MessageHandler(Filters.text & ~Filters.command, handle_review_comment),
                CallbackQueryHandler(customer_callback)
            ],
            BUYER_ESCROW_INFO: [CallbackQueryHandler(customer_callback)],
            BUYER_ENTER_PRODUCT_ID: [
                MessageHandler(Filters.text & ~Filters.command, handle_buyer_product_id),
                CallbackQueryHandler(customer_callback)
            ],
            BUYER_PAYMENT_METHODS: [CallbackQueryHandler(customer_callback)],
            BUYER_PAYMENT_INSTRUCTIONS: [CallbackQueryHandler(customer_callback)],
            BUYER_CONFIRM_PAYMENT: [CallbackQueryHandler(customer_callback)],
            SELLER_INFO: [CallbackQueryHandler(customer_callback)],
            SELLER_PLATFORM: [CallbackQueryHandler(customer_callback)],
            SELLER_LINK: [
                MessageHandler(Filters.text & ~Filters.command, handle_customer_link),
                CallbackQueryHandler(customer_callback)
            ],
            SELLER_DETAILS: [
                MessageHandler(Filters.text & ~Filters.command, handle_customer_details),
                CallbackQueryHandler(customer_callback)
            ],
            SELLER_PRICE: [
                MessageHandler(Filters.text & ~Filters.command, handle_customer_price),
                CallbackQueryHandler(customer_callback)
            ],
            SELLER_CONTACT: [
                MessageHandler(Filters.text & ~Filters.command, handle_customer_contact),
                CallbackQueryHandler(customer_callback)
            ],
            SELLER_SCREENSHOTS: [
                MessageHandler(Filters.photo, handle_customer_screenshot_upload),
                MessageHandler(Filters.text & ~Filters.command, handle_customer_screenshot_upload),
                CallbackQueryHandler(customer_callback)
            ],
            SELLER_CONFIRM: [CallbackQueryHandler(customer_callback)],
            CUSTOMER_MANAGE_LISTINGS: [CallbackQueryHandler(customer_callback)],
            CUSTOMER_CONFIRM_SOLD: [CallbackQueryHandler(customer_callback)],
            CUSTOMER_EDIT_FIELD: [CallbackQueryHandler(customer_callback)],
            CUSTOMER_EDIT_INPUT: [MessageHandler(Filters.text & ~Filters.command, handle_customer_edit_input), CallbackQueryHandler(customer_callback)],
            BROWSE_MENU: [CallbackQueryHandler(customer_callback)],
            BROWSE_PLATFORM_LIST: [CallbackQueryHandler(customer_callback)],
            BROWSE_LISTING_DETAIL: [CallbackQueryHandler(customer_callback)],
            BROWSE_FILTER_MENU: [CallbackQueryHandler(customer_callback)],
            BROWSE_FILTER_PRICE: [
                MessageHandler(Filters.text & ~Filters.command, browse_handle_filter_input),
                CallbackQueryHandler(customer_callback)
            ],
            BROWSE_FILTER_SUBS: [
                MessageHandler(Filters.text & ~Filters.command, browse_handle_filter_input),
                CallbackQueryHandler(customer_callback)
            ],
            BROWSE_FILTER_AGE: [
                MessageHandler(Filters.text & ~Filters.command, browse_handle_filter_input),
                CallbackQueryHandler(customer_callback)
            ],
            BROWSE_SEARCH_KEYWORD: [
                MessageHandler(Filters.text & ~Filters.command, browse_handle_filter_input),
                CallbackQueryHandler(customer_callback)
            ],
        },
        fallbacks=[CommandHandler('cancel', lambda u, c: ConversationHandler.END)],
        allow_reentry=True,
        name="customer_conversation"
    )
    dispatcher.add_handler(customer_conv_handler)
    
    # Register Auto Pilot module
    import auto_pilot
    auto_pilot.register_handlers(dispatcher)
    
    # Handler for tracking new deal group members
    dispatcher.add_handler(MessageHandler(Filters.status_update.new_chat_members, handle_new_group_member))
    
    # Start Flask webhook server in background thread for Cryptomus callbacks
    global _bot_instance
    _bot_instance = updater.bot
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask webhook server started on port 8080")

    # ===== SCHEDULED JOBS (For Escrow_Log Channel) =====
    job_queue = updater.job_queue
    
    # Weekly summary - every Sunday at 10:00 AM UTC (use days=(0,) for Monday = 0, Sunday = 6)
    import datetime as dt
    job_queue.run_repeating(
        weekly_escrow_summary_job,
        interval=dt.timedelta(weeks=1),
        first=_next_sunday_10am(),
        name="weekly_summary"
    )
    # Monthly highlights - first Sunday of month at 11:00 AM UTC (check inside job)
    job_queue.run_repeating(
        monthly_review_highlights_job,
        interval=dt.timedelta(weeks=1),
        first=_next_sunday_10am(),
        name="monthly_highlights"
    )
    logger.info("✅ Scheduled weekly + monthly jobs registered")

    logger.info("SMYARDS bot started")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
