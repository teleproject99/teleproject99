# -*- coding: utf-8 -*-
import os
import random
import logging
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, ParseMode
from telegram.ext import ConversationHandler, CallbackQueryHandler, MessageHandler, Filters, CommandHandler

# Import helpers from bot_final_fixed if possible, or redefine safe access patterns
import bot_final_fixed as bot_main

logger = logging.getLogger(__name__)

# Auto Pilot States
(
    AP_PLATFORM, AP_TYPE, AP_CHANNEL_LINK, AP_DETAILS, AP_PRICE, AP_SELLER_INFO, 
    AP_SELLER_TG_ID, AP_TXID, AP_SCREENSHOTS, AP_CONFIRM,
    AP_PROMO_TEXT, AP_PROMO_MEDIA,
    AP_GUIDE_TITLE, AP_GUIDE_TEXT, AP_GUIDE_MEDIA, AP_GUIDE_MEDIA_COLLECT,
    AP_PROMO_TITLE
) = range(100, 117)

# Import the review library (replaces the old GENERIC_REVIEWS list)
from reviews import get_auto_review

# Per-session used-review sets to avoid repeats within a bot session
_used_platform_reviews = set()
_used_user_reviews = set()

def ap_dashboard(update, context):
    """Entry point for Auto Pilot Dashboard."""
    query = update.callback_query
    query.answer()
    
    text = "🤖 **Auto Pilot System**\n\nManage your simulated transaction packages and content pools here."
    keyboard = [
        [InlineKeyboardButton("📦 Transactions Packages Pool", callback_data="ap_pool_plat_YouTube_page_0")],
        [InlineKeyboardButton("📣 Promotion Posts Pool", callback_data="ap_promo_pool_0")],
        [InlineKeyboardButton("📚 Guidance Posts Pool", callback_data="ap_guide_pool_0")],
        [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_back_main")]
    ]
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return ConversationHandler.END

# ================= PACKAGE CREATION WIZARD =================

def ap_add_new(update, context):
    query = update.callback_query
    query.answer()
    
    # Initialize package data
    context.user_data['ap_pkg'] = {}
    
    keyboard = [
        [InlineKeyboardButton("YouTube", callback_data="ap_plat_YouTube"),
         InlineKeyboardButton("TikTok", callback_data="ap_plat_TikTok")],
        [InlineKeyboardButton("Instagram", callback_data="ap_plat_Instagram"),
         InlineKeyboardButton("Facebook", callback_data="ap_plat_Facebook")],
        [InlineKeyboardButton("🔙 Cancel", callback_data="ap_dashboard")]
    ]
    query.edit_message_text(
        "🤖 **Auto Pilot: New Package**\n\nSelect the platform:",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )
    return AP_PLATFORM

def ap_handle_platform(update, context):
    query = update.callback_query
    query.answer()
    
    if query.data == "ap_dashboard":
        return ap_dashboard(update, context)
        
    platform = query.data.replace('ap_plat_', '')
    context.user_data['ap_pkg']['platform'] = platform
    
    keyboard = [[InlineKeyboardButton("🔙 Cancel", callback_data="ap_dashboard")]]
    
    query.edit_message_text(
        f"Platform: **{platform}**\n\n🔗 **Enter the Channel/Account Link**\n\n"
        f"Please provide a direct link to the {platform} channel or account.\n"
        f"Example: `https://youtube.com/@channelname`\n\n"
        f"Type 'skip' if not available.",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )
    return AP_CHANNEL_LINK

def ap_handle_channel_link_first(update, context):
    """Handles the channel link, then sends platform template."""
    text = update.message.text.strip()
    if text.lower() == 'cancel':
        update.message.reply_text("❌ Cancelled.")
        return ConversationHandler.END
    context.user_data['ap_pkg']['channel_link'] = text if text.lower() != 'skip' else ""
    context.user_data['ap_pkg']['account_type'] = "N/A"
    
    platform = context.user_data['ap_pkg'].get('platform', 'YouTube')
    template = bot_main.get_details_template(platform)
    
    update.message.reply_text(
        f"📱 *Platform:* {platform}\n\n{template}\n\n"
        f"Fill in your values and send it back. Type 'cancel' to abort.",
        parse_mode="Markdown"
    )
    return AP_DETAILS

def ap_handle_type(update, context):
    """Deprecated stub"""
    pass

def ap_handle_details(update, context):
    text = update.message.text
    if text.lower() == 'cancel':
        update.message.reply_text("❌ Cancelled.")
        return ConversationHandler.END
        
    platform = context.user_data['ap_pkg'].get('platform', 'YouTube')
    details = bot_main.parse_platform_details(platform, text)
    
    if not details.get('channel_age') and not details.get('subscribers'):
        update.message.reply_text(
            "⚠️ **Please fill in the template properly.**\n\n"
            "Make sure you copy the template, fill in the values, and send it back.\n"
            "Type 'cancel' to cancel.",
            parse_mode="Markdown"
        )
        return AP_DETAILS
        
    context.user_data['ap_pkg'].update(details)
        
    update.message.reply_text("💵 Enter **Price** in USD (e.g., `250`):")
    return AP_PRICE


def ap_handle_price(update, context):
    text = update.message.text
    try:
        price = float(text.replace('$', '').strip())
        context.user_data['ap_pkg']['price'] = price
    except Exception:
        update.message.reply_text("❌ Invalid price. Enter a number (e.g. `250`).")
        return AP_PRICE
        
    update.message.reply_text(
        "👤 Enter **Seller Name** and **Contact Link**.\n"
        "Format: `Name|Contact`\n"
        "Example: `JohnDoe|https://t.me/johndoe`\n\nType your answer:",
        parse_mode="Markdown"
    )
    return AP_SELLER_INFO

def ap_handle_seller_info(update, context):
    text = update.message.text
    try:
        name, contact = text.split('|')
        context.user_data['ap_pkg']['seller_name'] = name.strip()
        context.user_data['ap_pkg']['seller_contact'] = contact.strip()
    except Exception:
        update.message.reply_text("❌ Invalid format. Use `Name|Contact`.")
        return AP_SELLER_INFO
        
    update.message.reply_text(
        "🆔 Enter the **Seller's Telegram ID** (numeric ID).\n\n"
        "💡 The seller can get their ID by messaging @userinfobot on Telegram.\n\n"
        "Example: `123456789`",
        parse_mode="Markdown"
    )
    return AP_SELLER_TG_ID

def ap_handle_seller_tg_id(update, context):
    text = update.message.text.strip()
    try:
        seller_tg_id = int(text)
        if seller_tg_id <= 0:
            raise ValueError("Must be positive")
        context.user_data['ap_pkg']['seller_telegram_id'] = seller_tg_id
    except (ValueError, TypeError):
        update.message.reply_text("❌ Invalid Telegram ID. Must be a positive number (e.g. `123456789`).")
        return AP_SELLER_TG_ID
        
    update.message.reply_text(
        "🔗 Enter the **TXid Link** (Blockchain receipt link) for the escrow log:\n"
        "Or type `skip` if none.",
        parse_mode="Markdown"
    )
    return AP_TXID

def ap_handle_txid(update, context):
    text = update.message.text.strip()
    context.user_data['ap_pkg']['txid'] = text if text.lower() != 'skip' else ""
    
    context.user_data['ap_pkg']['screenshots'] = []
    
    keyboard = [[InlineKeyboardButton("✅ Done Uploading", callback_data="ap_done_screenshots")]]
    update.message.reply_text(
        "🖼️ **Upload Screenshots** (Max 10).\n"
        "Send images one by one. Click Done when finished.",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )
    return AP_SCREENSHOTS

def ap_handle_screenshots(update, context):
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        if len(context.user_data['ap_pkg']['screenshots']) < 10:
            context.user_data['ap_pkg']['screenshots'].append(file_id)
            update.message.reply_text(f"✅ Received screenshot {len(context.user_data['ap_pkg']['screenshots'])}/10")
        else:
            update.message.reply_text("⚠️ Maximum 10 screenshots reached. Click Done.")
    return AP_SCREENSHOTS

def ap_confirm_package(update, context):
    query = update.callback_query
    query.answer()
    
    pkg = context.user_data.get('ap_pkg', {})
    
    import html as _html
    def e(v): return _html.escape(str(v)) if v is not None else 'N/A'
    
    channel_link_val = pkg.get('channel_link', '') or 'None'
    
    summary = (
        f"📦 <b>Confirm Transaction Package</b>\n\n"
        f"📱 <b>Platform:</b> {e(pkg.get('platform'))}\n"
        f"🔖 <b>Type:</b> {e(pkg.get('account_type'))}\n"
        f"🔗 <b>Channel Link:</b> {e(channel_link_val)}\n"
        f"👥 <b>Subs:</b> {e(pkg.get('subscribers', 'N/A'))} | 👀 <b>Views:</b> {e(pkg.get('views', 'N/A'))}\n"
        f"🎯 <b>Niche:</b> {e(pkg.get('niche', 'N/A'))}\n"
        f"✨ <b>Features:</b> {e(pkg.get('features', 'N/A'))}\n"
        f"💵 <b>Price:</b> ${e(pkg.get('price'))}\n"
        f"👤 <b>Seller:</b> {e(pkg.get('seller_name'))} ({e(pkg.get('seller_contact'))})\n"
        f"🆔 <b>Seller TG ID:</b> <code>{e(pkg.get('seller_telegram_id'))}</code>\n"
        f"🔗 <b>TXid:</b> {e(pkg.get('txid') or 'None')}\n"
        f"🖼️ <b>Screenshots:</b> {len(pkg.get('screenshots', []))}\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Save Package", callback_data="ap_save_pkg")],
        [InlineKeyboardButton("❌ Cancel", callback_data="ap_dashboard")]
    ]
    query.edit_message_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return AP_CONFIRM

def ap_save_package(update, context):
    query = update.callback_query
    query.answer()
    
    if query.data == "ap_dashboard":
        return ap_dashboard(update, context)
        
    pkg = context.user_data['ap_pkg']
    
    screenshots_str = ",".join(pkg.get('screenshots', []))
    channel_link = pkg.get('channel_link', '')
    
    conn = bot_main.get_connection()
    cursor = conn.cursor()
    # Add channel_link column if missing
    try:
        cursor.execute("ALTER TABLE auto_pilot_packages ADD COLUMN channel_link TEXT")
        conn.commit()
    except Exception:
        pass
    cursor.execute("""
        INSERT INTO auto_pilot_packages 
        (platform, account_type, channel_age, subscribers, views, niche, features, monetization, growth, region, status, price, seller_name, seller_contact, seller_telegram_id, txid, screenshots, channel_link, likes, extra_monetization)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        pkg.get('platform'), pkg.get('account_type'), pkg.get('channel_age', 'N/A'), pkg.get('subscribers'), pkg.get('views'),
        pkg.get('niche'), pkg.get('features'), pkg.get('monetization'), pkg.get('growth'), pkg.get('region'), pkg.get('status'),
        pkg.get('price'), pkg.get('seller_name'), pkg.get('seller_contact'), pkg.get('seller_telegram_id'), pkg.get('txid'), screenshots_str,
        channel_link, pkg.get('likes', 0), pkg.get('extra_monetization', '{}')
    ))
    conn.commit()
    conn.close()
    
    query.edit_message_text("✅ Package saved successfully to the pool!", reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Back to Dashboard", callback_data="ap_dashboard")
    ]]))
    return ConversationHandler.END


# ================= PACKAGE POOL & MANAGEMENT =================

def ap_pool_list(update, context):
    """Paginated list of packages in the pool, filtered by platform."""
    query = update.callback_query
    query.answer()
    
    # Parse callback data: e.g. "ap_pool_plat_YouTube_page_0" or "ap_pool_page_0" (legacy fallback)
    data = query.data
    platform_filter = "YouTube" # default
    if "plat_" in data:
        parts = data.split('_page_')
        platform_filter = parts[0].replace('ap_pool_plat_', '')
        page = int(parts[1])
    else:
        page = int(data.replace('ap_pool_page_', ''))
        
    PAGE_SIZE = 5
    offset = page * PAGE_SIZE
    
    conn = bot_main.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM auto_pilot_packages WHERE platform = ?", (platform_filter,))
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT id, platform, price, seller_name FROM auto_pilot_packages WHERE platform = ? ORDER BY id DESC LIMIT ? OFFSET ?", (platform_filter, PAGE_SIZE, offset))
    packages = cursor.fetchall()
    conn.close()
    
    # Platform Tabs
    tabs = [
        InlineKeyboardButton("YouTube" + (" ✅" if platform_filter == "YouTube" else ""), callback_data="ap_pool_plat_YouTube_page_0"),
        InlineKeyboardButton("TikTok" + (" ✅" if platform_filter == "TikTok" else ""), callback_data="ap_pool_plat_TikTok_page_0")
    ]
    tabs2 = [
        InlineKeyboardButton("Instagram" + (" ✅" if platform_filter == "Instagram" else ""), callback_data="ap_pool_plat_Instagram_page_0"),
        InlineKeyboardButton("Facebook" + (" ✅" if platform_filter == "Facebook" else ""), callback_data="ap_pool_plat_Facebook_page_0")
    ]
    
    keyboard = [
        [InlineKeyboardButton("➕ Add New Package", callback_data="ap_add_new")],
        tabs, 
        tabs2
    ]
    
    if not packages:
        keyboard.append([InlineKeyboardButton("🔙 Back to Dashboard", callback_data="ap_dashboard")])
        query.edit_message_text(
            f"📦 **Package Pool ({platform_filter})**\n\nThe pool is empty for this platform.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return
        
    for pkg in packages:
        pkg_id, platform, price, seller = pkg
        keyboard.append([InlineKeyboardButton(f"ID:{pkg_id} | ${price} | {seller}", callback_data=f"ap_view_pkg_{pkg_id}")])
        
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"ap_pool_plat_{platform_filter}_page_{page-1}"))
    if offset + PAGE_SIZE < total:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"ap_pool_plat_{platform_filter}_page_{page+1}"))
    if nav:
        keyboard.append(nav)
        
    keyboard.append([InlineKeyboardButton("🔙 Back to Dashboard", callback_data="ap_dashboard")])
    
    query.edit_message_text(
        f"📦 **Package Pool ({platform_filter})** ({total} total)\nSelect a package to view options:",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )

def ap_view_package(update, context):
    query = update.callback_query
    query.answer()
    
    pkg_id = int(query.data.replace('ap_view_pkg_', ''))
    
    conn = bot_main.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM auto_pilot_packages WHERE id = ?", (pkg_id,))
    pkg = cursor.fetchone()
    conn.close()
    
    if not pkg:
        query.edit_message_text("❌ Package not found.")
        return
        
    pkg = dict(pkg)
    
    text = (
        f"📦 **Package ID:** {pkg['id']}\n\n"
        f"📱 **Platform:** {pkg['platform']}\n"
        f"🔖 **Type:** {pkg['account_type']}\n"
        f"👥 **Subs:** {pkg.get('subscribers', 'N/A')} | 👀 **Views:** {pkg.get('views', 'N/A')}\n"
        f"🎯 **Niche:** {pkg.get('niche', 'N/A')}\n"
        f"💵 **Price:** ${pkg['price']}\n"
        f"👤 **Seller:** {pkg['seller_name']} ({pkg['seller_contact']})\n"
        f"🔗 **TXid:** {pkg['txid'] or 'None'}\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("▶️ Play First Part (Main Post)", callback_data=f"ap_play1_{pkg_id}")],
        [InlineKeyboardButton("✅ Play Second Part (Escrow/Reviews)", callback_data=f"ap_play2_{pkg_id}")],
        [InlineKeyboardButton("🗑️ Remove", callback_data=f"ap_del_{pkg_id}"),
         InlineKeyboardButton("🔙 Back to Pool", callback_data="ap_pool_page_0")]
    ]
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

def ap_delete_package(update, context):
    query = update.callback_query
    query.answer("Package deleted!", show_alert=True)
    
    pkg_id = int(query.data.replace('ap_del_', ''))
    conn = bot_main.get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM auto_pilot_packages WHERE id = ?", (pkg_id,))
    conn.commit()
    conn.close()
    
    query.data = "ap_pool_page_0"
    return ap_pool_list(update, context)


# ================= EXECUTION LOGIC =================

def ensure_seller_profile(seller_telegram_id, seller_name, seller_contact):
    """Ensures the seller exists in the users table using their REAL Telegram ID."""
    conn = bot_main.get_connection()
    cursor = conn.cursor()
    
    # Extract real username from contact link if possible
    real_username = seller_name
    if seller_contact:
        contact_str = seller_contact.strip()
        if contact_str.startswith('https://t.me/'):
            real_username = contact_str.split('t.me/')[-1].strip('/')
        elif contact_str.startswith('@'):
            real_username = contact_str.lstrip('@')
    
    # Try to find existing profile by Telegram ID
    cursor.execute("SELECT telegram_id FROM users WHERE telegram_id = ?", (seller_telegram_id,))
    row = cursor.fetchone()
    if row:
        # Update their username in case it changed
        cursor.execute("UPDATE users SET username = ? WHERE telegram_id = ?", (real_username, seller_telegram_id))
        conn.commit()
        conn.close()
        return seller_telegram_id
        
    # Create a real profile for this seller
    cursor.execute("""
        INSERT INTO users (telegram_id, username, badge_type) 
        VALUES (?, ?, 'Regular')
    """, (seller_telegram_id, real_username))
    conn.commit()
    conn.close()
    logger.info(f"✅ Created real seller profile for {real_username} (ID: {seller_telegram_id})")
    return seller_telegram_id

def ap_play_part_1(update, context):
    """Play Part 1: Generate Listing and post to Main Channel."""
    query = update.callback_query
    pkg_id = int(query.data.replace('ap_play1_', ''))
    
    query.answer() # Answer early to prevent timeout
    
    try:
        conn = bot_main.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM auto_pilot_packages WHERE id = ?", (pkg_id,))
        pkg = cursor.fetchone()
        
        if not pkg:
            conn.close()
            query.edit_message_text("Package not found!")
            return
            
        pkg = dict(pkg)
        
        # 1. Setup Real Seller Profile
        seller_tg_id = pkg.get('seller_telegram_id') or 0
        seller_id = ensure_seller_profile(seller_tg_id, pkg['seller_name'], pkg['seller_contact'])
        
        # 2. Generate Product ID robustly — check BOTH tables to avoid collisions
        platform_code = {'YouTube': 'YT', 'TikTok': 'TT', 'Instagram': 'IG', 'Facebook': 'FB'}.get(pkg['platform'], 'ACC')
        cursor.execute("SELECT listing_id FROM listings WHERE listing_id LIKE ?", (f"{platform_code}-%",))
        existing_main = [r[0] for r in cursor.fetchall()]
        cursor.execute("SELECT listing_id FROM customer_listings WHERE listing_id LIKE ?", (f"{platform_code}-%",))
        existing_customer = [r[0] for r in cursor.fetchall()]
        max_num = 0
        for eid in existing_main + existing_customer:
            parts = eid.split('-')
            if len(parts) == 2 and parts[1].isdigit():
                max_num = max(max_num, int(parts[1]))
        product_id = f"{platform_code}-{max_num + 1:03d}"
        
        # 3. Insert into Listings
        cursor.execute("""
            INSERT INTO listings (
                listing_id, platform, account_type, channel_age, subscribers, views, likes, growth, extra_monetization, niche, features, monetization, region, status, price, 
                screenshots, seller_contact, status_flag, created_by, seller_telegram_id, published_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'published', ?, ?, CURRENT_TIMESTAMP)
        """, (
            product_id, pkg['platform'], pkg.get('account_type', 'N/A'), pkg.get('channel_age', 'N/A'),
            pkg['subscribers'], pkg['views'], pkg.get('likes', 0), pkg.get('growth', 'N/A'), pkg.get('extra_monetization', '{}'),
            pkg.get('niche', 'N/A'), pkg.get('features', 'N/A'), pkg.get('monetization', 'Enabled'), 
            pkg.get('region', 'N/A'), pkg.get('status', 'No Strikes'), pkg['price'],
            pkg['screenshots'], pkg['seller_contact'], seller_id, seller_id
        ))
        conn.commit()
    except Exception as e:
        logger.error(f"Error in AP Part 1 DB operation: {e}", exc_info=True)
        query.edit_message_text("Error preparing Part 1. Please check logs.")
        return
    finally:
        if 'conn' in locals() and conn:
            conn.close()
    
    # 4. Generate & Send Main Channel Post (Using official bot_main format)
    try:
        # Construct mock listing dict for publish_to_main_channel
        mock_listing = {
            'listing_id': product_id,
            'platform': pkg['platform'],
            'account_type': pkg.get('account_type', 'N/A'),
            'channel_age': pkg.get('channel_age', 'N/A'),
            'subscribers': pkg.get('subscribers', 'N/A'),
            'views': pkg.get('views', 'N/A'),
            'niche': pkg.get('niche', 'N/A'),
            'features': pkg.get('features', 'N/A'),
            'monetization': pkg.get('monetization', 'Enabled'),
            'region': pkg.get('region', 'N/A'),
            'status': pkg.get('status', 'No Strikes'),
            'price': pkg['price'],
            'created_by': seller_id,
            'seller_contact': pkg['seller_contact'],
            'channel_link': pkg.get('channel_link', ''),
            'growth': pkg.get('growth', ''),
            'likes': pkg.get('likes', 0),
            'extra_monetization': pkg.get('extra_monetization', '{}')
        }
        screenshots_list = pkg['screenshots'].split(',') if pkg.get('screenshots') else []
        
        main_msg_id = bot_main.publish_to_main_channel(mock_listing, screenshots_list, context.bot)
        
        # Save message ID and channel_link
        if main_msg_id:
            if isinstance(main_msg_id, tuple):
                msg_id_str = ",".join(str(i) for i in main_msg_id if i is not None)
            else:
                msg_id_str = str(main_msg_id)
                
            try:
                conn2 = bot_main.get_connection()
                cursor2 = conn2.cursor()
                cursor2.execute(
                    "UPDATE listings SET stock_message_id = ?, channel_message_id = ?, channel_link = ? WHERE listing_id = ?",
                    (msg_id_str, msg_id_str, pkg.get('channel_link', ''), product_id)
                )
                conn2.commit()
            except Exception as e:
                logger.error(f"Error updating message IDs: {e}")
            finally:
                if 'conn2' in locals() and conn2:
                    conn2.close()
        
        # Save the generated product ID to both memory and DB for robust recovery across bot restarts
        context.user_data[f'ap_last_product_id_{pkg_id}'] = product_id
        try:
            conn3 = bot_main.get_connection()
            cursor3 = conn3.cursor()
            cursor3.execute("UPDATE auto_pilot_packages SET last_generated_listing_id = ? WHERE id = ?", (product_id, pkg_id))
            conn3.commit()
        except Exception as e:
            logger.error(f"Error saving last_generated_listing_id: {e}")
        finally:
            if 'conn3' in locals() and conn3:
                conn3.close()
        
        query.edit_message_text(f"✅ Part 1 complete. New listing `{product_id}` posted to the Main Channel.")
    except Exception as e:
        logger.error(f"Error in AP Part 1 Telegram operation: {e}", exc_info=True)
        query.edit_message_text("Error executing Part 1. Please check logs.")
    return ConversationHandler.END


def ap_play_part_2(update, context):
    """Play Part 2: Simulate Sale, Escrow Post, and Reviews."""
    query = update.callback_query
    query.answer() # Answer early to prevent timeout
    pkg_id = int(query.data.replace('ap_play2_', ''))
    
    try:
        conn = bot_main.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM auto_pilot_packages WHERE id = ?", (pkg_id,))
        pkg = cursor.fetchone()
        
        if not pkg:
            conn.close()
            query.answer("Package not found!")
            return
            
        pkg = dict(pkg)
        
        # Try to get the product ID from context or DB, otherwise look up the most recent matching one
        product_id = context.user_data.get(f'ap_last_product_id_{pkg_id}') or pkg.get('last_generated_listing_id')
        if not product_id:
            cursor.execute("SELECT listing_id, stock_message_id, channel_message_id, seller_telegram_id FROM listings WHERE platform = ? AND price = ? AND status_flag = 'published' ORDER BY id DESC LIMIT 1", (pkg['platform'], pkg['price']))
            row = cursor.fetchone()
            if not row:
                conn.close()
                query.edit_message_text("No matching active listing found. Play Part 1 first!")
                return
            product_id, stock_message_id, channel_message_id, seller_id = row
        else:
            cursor.execute("SELECT stock_message_id, channel_message_id, seller_telegram_id FROM listings WHERE listing_id = ?", (product_id,))
            row = cursor.fetchone()
            stock_message_id, channel_message_id, seller_id = row if row else (None, None, None)
        
        # 1. Update Listing to Sold
        cursor.execute("UPDATE listings SET status = 'sold', status_flag = 'sold' WHERE listing_id = ?", (product_id,))
        
        # 2. Simulate Order
        order_num = bot_main.generate_order_number(pkg['platform'])
        fake_buyer_names = ["Alex****", "CryptoKing", "TradePro", "User7721", "Mike_S", "EliteBuyer"]
        buyer_name = random.choice(fake_buyer_names)
        buyer_id = random.randint(-900000, -800000) # Fake buyer ID for the simulated order
        
        cursor.execute("""
            INSERT INTO orders (order_number, product_id, customer_id, customer_username, platform, total_price, escrow_fee, amount_to_pay, payment_method, payment_address, payment_status, seller_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'confirmed', ?)
        """, (order_num, product_id, buyer_id, buyer_name, pkg['platform'], pkg['price'], bot_main.calculate_escrow_fee(pkg['price']), pkg['price'], 'Crypto', 'FakeAddr', seller_id))
        
        cursor.execute("""
            INSERT INTO transactions_log (order_number, product_id, platform, seller_name, buyer_name, price, payment_method, txid, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'completed')
        """, (order_num, product_id, pkg['platform'], pkg['seller_name'], buyer_name, pkg['price'], 'Crypto', pkg['txid']))
        
        # 3. Generate Fake Reviews — pulled from reviews.py for variety
        plat_review_1 = get_auto_review('platform', _used_platform_reviews)
        plat_review_2 = get_auto_review('platform', _used_platform_reviews)
        user_review   = get_auto_review('user', _used_user_reviews)

        cursor.execute("INSERT INTO platform_reviews (order_number, reviewer_id, reviewer_name, rating, comment) VALUES (?, ?, ?, ?, ?)",
                       (order_num, buyer_id, buyer_name, 5, plat_review_1))
        cursor.execute("INSERT INTO platform_reviews (order_number, reviewer_id, reviewer_name, rating, comment) VALUES (?, ?, ?, ?, ?)",
                       (order_num, seller_id, pkg['seller_name'], 5, plat_review_2))
        cursor.execute("INSERT INTO user_reviews (order_number, reviewer_id, reviewer_name, target_user_id, target_username, rating, comment) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (order_num, buyer_id, buyer_name, seller_id, pkg['seller_name'], 5, user_review))
        
        conn.commit()
    except Exception as e:
        logger.error(f"Error in AP Part 2 DB operation: {e}", exc_info=True)
        query.answer("Error executing Part 2", show_alert=True)
        return
    finally:
        if 'conn' in locals() and conn:
            conn.close()
            
    # 4. Build main_post_url for the "View Account Info" button on Post 1
    main_post_url = None
    if stock_message_id:
        first_id = str(stock_message_id).split(',')[0].strip()
        if first_id.isdigit():
            main_post_url = bot_main.helper_get_tg_url(bot_main.CHANNEL_ID, first_id)

    # 5. Post to Escrow Log Channel — returns (post1_id, post2_id)
    escrow_post1_id, escrow_post2_id = bot_main.post_escrow_completion(
        context.bot, order_num, product_id, pkg['platform'], 
        pkg['seller_name'], buyer_name, pkg['price'], txid=pkg['txid'],
        main_post_url=main_post_url, payment_method="Crypto"
    )
    
    if escrow_post2_id:
        try:
            conn2 = bot_main.get_connection()
            cursor2 = conn2.cursor()
            # Store post2_id as escrow_message_id so update_escrow_post_with_review can edit it
            cursor2.execute("UPDATE orders SET escrow_message_id = ? WHERE order_number = ?", (escrow_post2_id, order_num))
            cursor2.execute("UPDATE transactions_log SET escrow_message_id = ? WHERE order_number = ?", (escrow_post2_id, order_num))
            conn2.commit()
        except Exception as e:
            logger.error(f"Error updating escrow message IDs: {e}")
        finally:
            if 'conn2' in locals() and conn2:
                conn2.close()
        
        # Attach the reviews visually to Post 2
        bot_main.update_escrow_post_with_review(context.bot, order_num)
        
        # Edit the main channel post using the exact standard SOLD format
        # Pass post1_id so the SOLD button links to the static info post
        sold_data = {
            'listing_id': product_id,
            'channel_message_id': channel_message_id,
            'order_number': order_num
        }
        bot_main.admin_update_main_post_as_sold(sold_data, context.bot, escrow_post1_id or 0)
        
    query.answer("Part 2 Executed!", show_alert=True)
    query.edit_message_text(f"✅ Part 2 complete. Order `{order_num}` generated, reviews injected, and escrow post updated.")
    return ConversationHandler.END
    # End of ap_play_part_2
# ================= CONTENT POOLS (PROMO & GUIDANCE) =================

def ap_content_pool_list(update, context):
    query = update.callback_query
    query.answer()
    
    data = query.data
    pool_type = 'promo' if 'promo' in data else 'guide'
    table_name = 'ap_promo_posts' if pool_type == 'promo' else 'ap_guidance_posts'
    title = 'Promotion Posts' if pool_type == 'promo' else 'Guidance Posts'
    
    page = int(data.split('_')[-1])
    PAGE_SIZE = 5
    offset = page * PAGE_SIZE
    
    conn = bot_main.get_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT count(*) FROM {table_name}")
    total = cursor.fetchone()[0]
    
    cursor.execute(f"SELECT id, title FROM {table_name} ORDER BY id DESC LIMIT ? OFFSET ?", (PAGE_SIZE, offset))
    posts = cursor.fetchall()
    conn.close()
    
    keyboard = [
        [InlineKeyboardButton("➕ Add New Post", callback_data=f"ap_add_{pool_type}")]
    ]
    
    if not posts:
        keyboard.append([InlineKeyboardButton("🔙 Back to Dashboard", callback_data="ap_dashboard")])
        query.edit_message_text(f"📚 **{title} Pool**\n\nThe pool is empty.", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return
        
    for post in posts:
        post_id, post_title = post
        keyboard.append([InlineKeyboardButton(f"ID:{post_id} | {post_title}", callback_data=f"ap_view_{pool_type}_{post_id}")])
        
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"ap_{pool_type}_pool_{page-1}"))
    if offset + PAGE_SIZE < total:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"ap_{pool_type}_pool_{page+1}"))
    if nav:
        keyboard.append(nav)
        
    keyboard.append([InlineKeyboardButton("🔙 Back to Dashboard", callback_data="ap_dashboard")])
    
    query.edit_message_text(f"📚 **{title} Pool** ({total} total)\nSelect a post to view options:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

def ap_view_content(update, context):
    query = update.callback_query
    query.answer()
    
    data = query.data
    pool_type = 'promo' if 'promo' in data else 'guide'
    table_name = 'ap_promo_posts' if pool_type == 'promo' else 'ap_guidance_posts'
    post_id = int(data.split('_')[-1])
    
    conn = bot_main.get_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {table_name} WHERE id = ?", (post_id,))
    post = cursor.fetchone()
    conn.close()
    
    if not post:
        query.edit_message_text("❌ Post not found.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"ap_{pool_type}_pool_0")]]))
        return
        
    post = dict(post)
    
    # Fetch media count from new media table (fallback to legacy column)
    media_table = 'ap_promo_media' if pool_type == 'promo' else 'ap_guidance_media'
    conn2 = bot_main.get_connection()
    cursor2 = conn2.cursor()
    try:
        cursor2.execute(f"SELECT COUNT(*) FROM {media_table} WHERE post_id = ?", (post_id,))
        media_count = cursor2.fetchone()[0]
    except Exception:
        media_count = 1 if post.get('media_file_id') else 0
    finally:
        conn2.close()

    text = f"\U0001f4c4 **Post Title:** {post['title']}\n\n**Content:**\n{post['content_text'][:500]}"
    if media_count:
        text += f"\n\n\U0001f5bc\ufe0f *Has media attached ({media_count} file(s))*"
    elif post.get('media_file_id'):
        text += f"\n\n\U0001f5bc\ufe0f *Has media attached ({post['media_type']})*"
        
    keyboard = [
        [InlineKeyboardButton("\U0001f680 Publish to Main Channel", callback_data=f"ap_publish_{pool_type}_{post_id}")],
        [InlineKeyboardButton("\U0001f5d1\ufe0f Delete Post", callback_data=f"ap_del_{pool_type}_{post_id}")],
        [InlineKeyboardButton("\U0001f519 Back to Pool", callback_data=f"ap_{pool_type}_pool_0")]
    ]
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

def ap_delete_content(update, context):
    query = update.callback_query
    data = query.data
    pool_type = 'promo' if 'promo' in data else 'guide'
    table_name = 'ap_promo_posts' if pool_type == 'promo' else 'ap_guidance_posts'
    post_id = int(data.split('_')[-1])

    # Answer the query FIRST to prevent Telegram timeout/conflict
    query.answer("🗑️ Post deleted!", show_alert=False)

    conn = bot_main.get_connection()
    cursor = conn.cursor()
    # Manually delete media rows first (in case FK cascade is not active)
    if pool_type == 'guide':
        cursor.execute("DELETE FROM ap_guidance_media WHERE post_id = ?", (post_id,))
    elif pool_type == 'promo':
        try:
            cursor.execute("DELETE FROM ap_promo_media WHERE post_id = ?", (post_id,))
        except Exception:
            pass
    cursor.execute(f"DELETE FROM {table_name} WHERE id = ?", (post_id,))
    conn.commit()
    conn.close()

    # Redirect to the pool list using a mock object (query.data is read-only)
    query_mock = type('obj', (object,), {
        'data': f"ap_{pool_type}_pool_0", 
        'answer': lambda *a, **k: None, 
        'message': query.message,
        'edit_message_text': query.edit_message_text,
        'edit_message_caption': getattr(query, 'edit_message_caption', None)
    })
    update_mock = type('obj', (object,), {
        'callback_query': query_mock, 
        'effective_user': update.effective_user,
        'message': update.message
    })
    return ap_content_pool_list(update_mock, context)

def ap_publish_content(update, context):
    query = update.callback_query
    data = query.data
    pool_type = 'promo' if 'promo' in data else 'guide'
    table_name = 'ap_promo_posts' if pool_type == 'promo' else 'ap_guidance_posts'
    media_table = 'ap_promo_media' if pool_type == 'promo' else 'ap_guidance_media'
    post_id = int(data.split('_')[-1])
    
    conn = bot_main.get_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {table_name} WHERE id = ?", (post_id,))
    post = cursor.fetchone()
    # Fetch multi-media
    try:
        cursor.execute(f"SELECT file_id, media_type FROM {media_table} WHERE post_id = ? ORDER BY sort_order ASC", (post_id,))
        media_rows = cursor.fetchall()
    except Exception:
        media_rows = []
    conn.close()
    
    if not post:
        query.answer("Post not found!")
        return
        
    post = dict(post)
    content_text = post.get('content_text', '')
    
    # Fallback: legacy single media columns
    if not media_rows and post.get('media_file_id'):
        media_rows = [(post['media_file_id'], post.get('media_type', 'photo'))]

    photos = [(fid, mt) for fid, mt in media_rows if mt == 'photo']
    videos = [(fid, mt) for fid, mt in media_rows if mt == 'video']

    try:
        if len(photos) > 1:
            # Send album
            media_group = []
            for idx, (fid, _) in enumerate(photos):
                if idx == len(photos) - 1:
                    media_group.append(InputMediaPhoto(fid, caption=content_text))
                else:
                    media_group.append(InputMediaPhoto(fid))
            context.bot.send_media_group(chat_id=bot_main.CHANNEL_ID, media=media_group)
        elif len(photos) == 1:
            context.bot.send_photo(chat_id=bot_main.CHANNEL_ID, photo=photos[0][0], caption=content_text)
        elif videos:
            context.bot.send_video(chat_id=bot_main.CHANNEL_ID, video=videos[0][0], caption=content_text)
        else:
            context.bot.send_message(chat_id=bot_main.CHANNEL_ID, text=content_text)
        query.answer("✅ Published to Main Channel!", show_alert=True)
    except Exception as e:
        logger.error(f"Error publishing content post: {e}")
        query.answer(f"Failed to publish: {e}", show_alert=True)

# Add Wizards
def ap_add_content(update, context):
    query = update.callback_query
    query.answer()
    pool_type = 'promo' if 'promo' in query.data else 'guide'
    context.user_data['ap_content_type'] = pool_type

    if pool_type == 'guide':
        query.edit_message_text(
            "📚 *New Guidance Post*\n\n"
            "Step 1/3: Send the *title* for this guide post:\n"
            "_Example: How to Purchase an Account_\n\n"
            "Type 'cancel' to abort.",
            parse_mode="Markdown"
        )
        return AP_GUIDE_TITLE
    else:
        query.edit_message_text(
            "📣 *New Promotion Post*\n\n"
            "Step 1/3: Send the *title* for this promotion post:\n"
            "_Example: Big Sale This Week!_\n\n"
            "Type 'cancel' to abort.",
            parse_mode="Markdown"
        )
        return AP_PROMO_TITLE


def ap_handle_promo_title(update, context):
    """Handles the title step for promotion posts."""
    text = update.message.text
    if text and text.lower() == 'cancel':
        update.message.reply_text("❌ Cancelled.")
        return ConversationHandler.END
    context.user_data['ap_guide_title'] = text.strip()  # reuse same key
    update.message.reply_text(
        "Step 2/3: Send the *content/body text* for this promotion post.\n"
        "This is the full text shown when the post is displayed.\n\n"
        "Type 'cancel' to abort.",
        parse_mode="Markdown"
    )
    return AP_PROMO_TEXT


def ap_handle_guide_title(update, context):
    """Handles the title step for guidance posts."""
    text = update.message.text
    if text and text.lower() == 'cancel':
        update.message.reply_text("❌ Cancelled.")
        return ConversationHandler.END
    context.user_data['ap_guide_title'] = text.strip()
    update.message.reply_text(
        "Step 2/3: Send the *content/body text* for this guide post.\n"
        "This is the full explanatory text shown to users.\n\n"
        "Type 'cancel' to abort.",
        parse_mode="Markdown"
    )
    return AP_GUIDE_TEXT


def ap_handle_content_text(update, context):
    text = update.message.text
    if text and text.lower() == 'cancel':
        update.message.reply_text("❌ Cancelled.")
        return ConversationHandler.END

    pool_type = context.user_data['ap_content_type']
    context.user_data['ap_content_text'] = text

    # Both promo and guide now share the same multi-media collect flow
    context.user_data['ap_guide_media'] = []  # reset media list
    keyboard = [[InlineKeyboardButton("✅ No media, save now", callback_data="ap_guide_media_done")]]
    update.message.reply_text(
        "Step 3/3: Send *photos or a video* to attach to this post.\n"
        "You can send *multiple photos* one by one.\n"
        "When done, press the button below or type 'done'.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return AP_GUIDE_MEDIA_COLLECT


def ap_handle_guide_media_collect(update, context):
    """Collects multiple media files for a guidance post."""
    msg = update.message

    if msg.text and msg.text.lower() in ('cancel',):
        msg.reply_text("❌ Cancelled.")
        return ConversationHandler.END

    if msg.text and msg.text.lower() in ('done', 'skip'):
        return ap_save_guidance_post(update, context)

    media_list = context.user_data.get('ap_guide_media', [])

    if msg.photo:
        media_list.append(('photo', msg.photo[-1].file_id))
        context.user_data['ap_guide_media'] = media_list
        keyboard = [[InlineKeyboardButton("✅ Done, save post", callback_data="ap_guide_media_done")]]
        msg.reply_text(
            f"📷 Photo added ({len(media_list)} so far). Send another or press Done.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return AP_GUIDE_MEDIA_COLLECT
    elif msg.video:
        media_list.append(('video', msg.video.file_id))
        context.user_data['ap_guide_media'] = media_list
        msg.reply_text("🎥 Video added. Press Done to save.")
        return ap_save_guidance_post(update, context)  # videos: one is enough
    else:
        keyboard = [[InlineKeyboardButton("✅ Done, save post", callback_data="ap_guide_media_done")]]
        msg.reply_text(
            "⚠️ Please send a photo or video, or press Done to save without media.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return AP_GUIDE_MEDIA_COLLECT


def ap_guide_media_done_callback(update, context):
    """Handles the 'Done' button press when collecting guidance post media."""
    query = update.callback_query
    query.answer()
    return ap_save_guidance_post(update, context)


def ap_save_guidance_post(update, context):
    """Saves either a guidance post or a promo post with multi-media support."""
    pool_type = context.user_data.get('ap_content_type', 'guide')
    title = context.user_data.get('ap_guide_title', '')
    content_text = context.user_data.get('ap_content_text', '')
    media_list = context.user_data.get('ap_guide_media', [])

    conn = bot_main.get_connection()
    cursor = conn.cursor()

    if pool_type == 'promo':
        cursor.execute(
            "INSERT INTO ap_promo_posts (title, content_text) VALUES (?, ?)",
            (title, content_text)
        )
        post_id = cursor.lastrowid
        for order, (media_type, file_id) in enumerate(media_list):
            cursor.execute(
                "INSERT INTO ap_promo_media (post_id, file_id, media_type, sort_order) VALUES (?, ?, ?, ?)",
                (post_id, file_id, media_type, order)
            )
        back_cb = "ap_promo_pool_0"
        label = "Promotion"
    else:
        cursor.execute(
            "INSERT INTO ap_guidance_posts (title, content_text) VALUES (?, ?)",
            (title, content_text)
        )
        post_id = cursor.lastrowid
        for order, (media_type, file_id) in enumerate(media_list):
            cursor.execute(
                "INSERT INTO ap_guidance_media (post_id, file_id, media_type, sort_order) VALUES (?, ?, ?, ?)",
                (post_id, file_id, media_type, order)
            )
        back_cb = "ap_guide_pool_0"
        label = "Guidance"

    conn.commit()
    conn.close()

    done_kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"🔙 Back to {label} Pool", callback_data=back_cb)]])
    reply_fn = update.callback_query.edit_message_text if update.callback_query else update.message.reply_text
    try:
        reply_fn(
            f"✅ {label} post saved!\n\n"
            f"*Title:* {title}\n"
            f"*Media attached:* {len(media_list)} file(s)",
            reply_markup=done_kb,
            parse_mode="Markdown"
        )
    except Exception:
        pass
    return ConversationHandler.END


# ap_handle_content_media is no longer used for promo (promo now uses the guide media collect flow)
# Kept as a no-op fallback to avoid any stale state issues
def ap_handle_content_media(update, context):
    """Legacy handler — promo posts now use ap_handle_guide_media_collect."""
    return ap_handle_guide_media_collect(update, context)

# ================= ROUTING EXPORT =================

def register_handlers(dispatcher):
    """Register all Auto Pilot handlers with the main dispatcher."""
    
    # Standalone callbacks
    dispatcher.add_handler(CallbackQueryHandler(ap_dashboard, pattern='^ap_dashboard$'))
    dispatcher.add_handler(CallbackQueryHandler(ap_pool_list, pattern='^ap_pool_page_|^ap_pool_plat_'))
    dispatcher.add_handler(CallbackQueryHandler(ap_view_package, pattern='^ap_view_pkg_'))
    dispatcher.add_handler(CallbackQueryHandler(ap_delete_package, pattern=r'^ap_del_\d+$'))
    dispatcher.add_handler(CallbackQueryHandler(ap_play_part_1, pattern='^ap_play1_'))
    dispatcher.add_handler(CallbackQueryHandler(ap_play_part_2, pattern='^ap_play2_'))
    
    # Content Pools
    dispatcher.add_handler(CallbackQueryHandler(ap_content_pool_list, pattern='^ap_promo_pool_|^ap_guide_pool_'))
    dispatcher.add_handler(CallbackQueryHandler(ap_view_content, pattern='^ap_view_promo_|^ap_view_guide_'))
    dispatcher.add_handler(CallbackQueryHandler(ap_delete_content, pattern='^ap_del_promo_|^ap_del_guide_'))
    dispatcher.add_handler(CallbackQueryHandler(ap_publish_content, pattern='^ap_publish_promo_|^ap_publish_guide_'))
    
    # Conversation Wizard
    ap_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(ap_add_new, pattern='^ap_add_new$'),
            CallbackQueryHandler(ap_add_content, pattern='^ap_add_promo$|^ap_add_guide$')
        ],
        states={
            AP_PLATFORM: [CallbackQueryHandler(ap_handle_platform, pattern='^ap_plat_|ap_dashboard$')],
            AP_TYPE: [
                MessageHandler(Filters.text & ~Filters.command, ap_handle_type),
                CallbackQueryHandler(ap_dashboard, pattern='^ap_dashboard$')
            ],
            AP_CHANNEL_LINK: [MessageHandler(Filters.text & ~Filters.command, ap_handle_channel_link_first)],
            AP_DETAILS: [MessageHandler(Filters.text & ~Filters.command, ap_handle_details)],
            AP_PRICE: [MessageHandler(Filters.text & ~Filters.command, ap_handle_price)],
            AP_SELLER_INFO: [MessageHandler(Filters.text & ~Filters.command, ap_handle_seller_info)],
            AP_SELLER_TG_ID: [MessageHandler(Filters.text & ~Filters.command, ap_handle_seller_tg_id)],
            AP_TXID: [MessageHandler(Filters.text & ~Filters.command, ap_handle_txid)],
            AP_SCREENSHOTS: [
                MessageHandler(Filters.photo, ap_handle_screenshots),
                CallbackQueryHandler(ap_confirm_package, pattern='^ap_done_screenshots$')
            ],
            AP_CONFIRM: [
                CallbackQueryHandler(ap_save_package, pattern='^ap_save_pkg$'),
                CallbackQueryHandler(ap_dashboard, pattern='^ap_dashboard$')
            ],
            AP_PROMO_TITLE: [MessageHandler(Filters.text & ~Filters.command, ap_handle_promo_title)],
            AP_PROMO_TEXT: [MessageHandler(Filters.text & ~Filters.command, ap_handle_content_text)],
            AP_PROMO_MEDIA: [MessageHandler(Filters.photo | Filters.video | Filters.text, ap_handle_content_media)],
            AP_GUIDE_TITLE: [MessageHandler(Filters.text & ~Filters.command, ap_handle_guide_title)],
            AP_GUIDE_TEXT: [MessageHandler(Filters.text & ~Filters.command, ap_handle_content_text)],
            AP_GUIDE_MEDIA_COLLECT: [
                MessageHandler(Filters.photo | Filters.video | Filters.text, ap_handle_guide_media_collect),
                CallbackQueryHandler(ap_guide_media_done_callback, pattern='^ap_guide_media_done$')
            ],
        },
        fallbacks=[CommandHandler('cancel', ap_dashboard)],
        allow_reentry=True,
        name="auto_pilot_conversation"
    )
    dispatcher.add_handler(ap_conv_handler)
    logger.info("✅ Auto Pilot module registered.")
