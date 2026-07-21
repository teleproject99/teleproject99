# -*- coding: utf-8 -*-
"""
reviews.py — Centralized review library for SMyards Bot.

All review text pools are stored here. Import this module wherever reviews
are needed (auto_pilot.py, bot_final_fixed.py).

Usage:
    from reviews import get_preset_comments, get_auto_review

Functions:
    get_preset_comments(rating, review_type, seed=None) -> list[str]
        Returns exactly 5 unique, randomly selected preset comments for the
        given rating and review_type ('platform' or 'user').

    get_auto_review(review_type, used=None) -> str
        Returns a single 5-star review string, avoiding recently used ones.
        Pass a mutable set as `used` to track and avoid repeats across calls.
"""

import random

# ──────────────────────────────────────────────────────────────────
#  5-STAR PLATFORM REVIEWS  (used for auto-play + high-rating preset)
# ──────────────────────────────────────────────────────────────────
PLATFORM_5_STAR = [
    "Honestly one of the smoothest deals I've had online. Everything was transparent from start to finish. 🙌",
    "The escrow system here is top-tier. Felt completely safe the whole time.",
    "Can't believe how fast this went. Listed, sold, done. No drama at all.",
    "SMyards is the real deal. This is how account trading should work.",
    "Verified escrow + fast admin response = perfect experience. Will definitely be back.",
    "Zero stress from start to finish. The process was crystal clear.",
    "I was skeptical at first but this platform delivered 100%. Highly recommend.",
    "Admin was super responsive. Any question I had got answered within minutes.",
    "Transferred ownership in under an hour. Absolutely blown away by how smooth this was.",
    "The platform takes security seriously. Felt protected the entire time.",
    "Legit, fast, and professional. Exactly what I was looking for.",
    "Been using crypto escrow on other platforms and this blows them all out of the water.",
    "3rd time using SMyards. Never had a single issue. That speaks for itself.",
    "The whole flow felt premium. Not like most sketchy marketplaces out there.",
    "Everything matched what was advertised. No surprises — love that.",
    "Loved that there was a proper escrow buffer before funds were released. Smart system.",
    "Ownership was transferred cleanly. Got full access with no issues whatsoever.",
    "For anyone hesitating — just do it. The platform is legit, the process is airtight.",
    "Admin verified everything before release. That level of care is rare.",
    "Fastest and safest account sale I've ever done. This is my go-to platform now.",
    "Phenomenal service. Couldn't ask for a better marketplace experience.",
    "The transparency here is refreshing. I knew exactly what was happening at every step.",
    "My funds were held safely throughout. Zero risk, maximum peace of mind.",
    "Didn't expect it to be this easy. Genuinely impressed. Will refer friends.",
    "Clean interface, clear instructions, fast execution. 10/10.",
    "This platform is a hidden gem. More people need to know about it.",
    "From listing to completed transfer — under 2 hours. Outstanding.",
    "The escrow process removed all doubt. Money moved only when I was happy.",
    "Professional from first message to final confirmation. Rare quality.",
    "No bots, no scams, just real trades done right. Exactly what we needed.",
    "Used three other platforms before this. None of them come close.",
    "Trustworthy marketplace with real oversight. This is the standard.",
    "Transaction was flawless. Got exactly what was promised. Stars don't lie.",
    "I was worried about losing money but the escrow system eliminated that risk entirely.",
    "Seller was vetted, process was secure, delivery was fast. Perfect trifecta.",
    "Finally a platform that prioritizes buyer safety. Truly appreciated.",
    "Every step was documented and confirmed. This is how business should be done.",
    "The admin team clearly knows what they're doing. World-class support.",
    "Smooth deal. No back-and-forth drama. Straight to the point. 💯",
    "I've recommended this to 4 friends already. That's how good it was.",
]

# ──────────────────────────────────────────────────────────────────
#  4-STAR PLATFORM REVIEWS
# ──────────────────────────────────────────────────────────────────
PLATFORM_4_STAR = [
    "Really good experience overall. A few small delays but nothing major.",
    "Solid platform. Would have been 5 stars if the process was a tiny bit quicker.",
    "Safe and reliable. Minor communication wait but resolved fine.",
    "Very trustworthy. Just wish there were more listings in my niche.",
    "Great service. The escrow system works perfectly. Took slightly longer than expected.",
    "Good experience. Would definitely use again. Just a minor wait time.",
    "Reliable and professional. Nothing to complain about really, just minor quibbles.",
    "Happy with how the trade went. Admin was helpful and responsive.",
    "Almost perfect. Small hiccup early on but the team sorted it out fast.",
    "Good platform. Solid process. Would return for future purchases.",
    "Trustworthy system. I felt safe. Would recommend to anyone buying accounts.",
    "Decent experience. A couple of things could be faster but overall positive.",
    "Pretty smooth. The escrow worked as promised. Slight delay on verification.",
    "Good deal, well managed. Wouldn't hesitate to use SMyards again.",
    "4 stars because of a minor wait, but honestly the platform itself is excellent.",
]

# ──────────────────────────────────────────────────────────────────
#  3-STAR PLATFORM REVIEWS (Neutral)
# ──────────────────────────────────────────────────────────────────
PLATFORM_3_STAR = [
    "It was okay. Took longer than I hoped but the result was fine.",
    "Average experience. Got what I paid for eventually.",
    "Not bad, not exceptional. Decent enough for what it is.",
    "Worked fine in the end. Just expected a bit more communication.",
    "Meh. Nothing went wrong, nothing particularly impressed me either.",
    "Process is a bit slow but functional. Would maybe try again.",
    "Got there in the end. Some friction along the way but resolved.",
    "Middle of the road experience. Works as described.",
]

# ──────────────────────────────────────────────────────────────────
#  1-2 STAR PLATFORM REVIEWS (Negative)
# ──────────────────────────────────────────────────────────────────
PLATFORM_LOW = [
    "Took way too long. Expected better for the fees involved.",
    "Process was unclear. Needed more guidance throughout.",
    "Had issues that weren't resolved quickly. Disappointing.",
    "Not the experience I was hoping for. Left frustrated.",
    "Communication could be much better. Felt ignored at times.",
    "Too slow. Other platforms have done this in a fraction of the time.",
    "Not satisfied. The process felt unnecessarily complicated.",
]

# ──────────────────────────────────────────────────────────────────
#  5-STAR SELLER/USER REVIEWS
# ──────────────────────────────────────────────────────────────────
USER_5_STAR = [
    "Seller was incredibly responsive. Answered every question promptly. 🔥",
    "Super professional seller. Delivered everything exactly as described.",
    "Best transaction experience I've had. Seller made it effortless.",
    "Honest, quick, and reliable. Will 100% buy from this seller again.",
    "Seller had the channel fully ready for transfer. No delays at all.",
    "Genuinely one of the most trustworthy sellers I've dealt with online.",
    "Seller communicated perfectly throughout. Never felt left in the dark.",
    "Everything was exactly as listed. Seller didn't exaggerate a single thing.",
    "Couldn't have asked for a better seller. Smooth, professional, fast.",
    "Seller walked me through every step. Really appreciated the patience.",
    "Stats were accurate, transfer was clean. This seller is the real deal.",
    "Got the channel in better condition than expected. Great seller!",
    "Seller responded instantly. Had full access within the hour.",
    "No games, no delays. Exactly what a seller should be. Highly rated.",
    "Seller had everything prepared and made the handover seamless. 💯",
    "Top tier seller. Honest communication, clean transfer, fast delivery.",
    "This seller knew what they were talking about. Very knowledgeable too.",
    "Professional attitude, clean channel, no surprises. Perfect seller.",
    "Seller stayed in contact the whole time. Really put my mind at ease.",
    "Everything checked out. The seller was transparent about everything.",
    "Had great energy throughout the deal. Made the whole thing enjoyable.",
    "Seller was patient when I had questions. Really appreciated that.",
    "Fastest seller response I've seen on any marketplace. Impressive.",
    "Channel was in pristine condition. Seller clearly valued their reputation.",
    "Excellent communication. Delivered on every promise. Stellar seller.",
    "Seller made the verification process quick and painless.",
    "No pressure, no rush. Seller let me verify everything before proceeding.",
    "After-sale support was also great. Seller didn't just disappear.",
    "Seller was upfront about everything. Refreshing honesty in a marketplace.",
    "First-time buyer and this seller made the experience easy and stress-free.",
    "Would buy from this seller again in a heartbeat. Absolutely flawless.",
    "Seller had the best communication I've seen — clear, prompt, professional.",
    "Verified everything with the seller before paying. They were totally cooperative.",
    "A+ seller. Delivered fast, communicated well, no drama whatsoever.",
    "Channel was exactly as described. Not a single misleading detail. Love it.",
    "Seller completed the transfer well ahead of schedule. Outstanding.",
    "Best account purchasing experience of my life. This seller set the bar.",
    "Seller took the time to ensure I was comfortable before proceeding. Class act.",
    "Short, simple, and smooth. Exactly what I needed from a seller.",
    "I've bought accounts before and this was by far the cleanest transaction yet.",
]

# ──────────────────────────────────────────────────────────────────
#  4-STAR SELLER/USER REVIEWS
# ──────────────────────────────────────────────────────────────────
USER_4_STAR = [
    "Great seller overall. A little slow to respond at first but made up for it.",
    "Good transaction. Seller was helpful. Minor confusion early but sorted quickly.",
    "Reliable seller. Everything was as described. Would buy from again.",
    "Solid seller. Slight delay on transfer but communicated throughout.",
    "Positive experience. Seller was professional and the deal was clean.",
    "Trustworthy. Stats matched. Just a small wait during verification.",
    "Good seller. Delivered what was promised. Minor communication gaps.",
    "Happy with the purchase. Seller was honest and the channel was clean.",
    "Almost perfect seller. Small delay but handled it well.",
    "Would recommend this seller. Reliable and honest throughout.",
    "Decent seller. Knew their product well. Slight response delay initially.",
    "Good experience. Seller was cooperative and the transfer went fine.",
    "Reliable person to deal with. Would return for another purchase.",
    "Seller was professional. Just expected slightly faster delivery.",
    "Good seller. Clean channel. Will keep in mind for future purchases.",
]

# ──────────────────────────────────────────────────────────────────
#  3-STAR SELLER/USER REVIEWS (Neutral)
# ──────────────────────────────────────────────────────────────────
USER_3_STAR = [
    "Average seller. Got the job done eventually.",
    "Channel was okay. Some details weren't quite as described.",
    "Transaction worked out fine. Seller could communicate better.",
    "Seller delivered but took longer than expected.",
    "Nothing exceptional but the deal was completed.",
    "Decent enough. Wouldn't rush to buy from again but won't avoid either.",
    "Channel matched description mostly. Minor inaccuracies.",
    "Seller was fine. Just average speed and communication.",
]

# ──────────────────────────────────────────────────────────────────
#  1-2 STAR SELLER/USER REVIEWS (Negative)
# ──────────────────────────────────────────────────────────────────
USER_LOW = [
    "Seller was slow to respond. Took much longer than expected.",
    "Channel wasn't exactly as described. Disappointed.",
    "Communication was lacking. Had to follow up multiple times.",
    "Seller took too long on the transfer. Frustrating experience.",
    "Not great. Seller seemed unorganized and delayed things unnecessarily.",
    "Wouldn't buy from this seller again. Too many issues.",
    "Below expectations. Channel had issues that weren't disclosed.",
]

# ──────────────────────────────────────────────────────────────────
#  SHORT QUICK-SELECT BUTTON COMMENTS  (for the preset buttons UI)
#  These are SHORT enough to fit as button text (~50 chars max)
# ──────────────────────────────────────────────────────────────────
QUICK_PLATFORM_5 = [
    "Smooth & professional! 🙌",
    "Great experience, highly recommend! 👍",
    "Fast and secure ⚡ — love it!",
    "Legit platform, zero issues 💯",
    "Super safe escrow, will use again 🔒",
    "Trustworthy & fast! Really impressed 🔥",
    "Flawless transaction from start to finish ✅",
    "Clean process, no drama whatsoever 🎯",
    "Best marketplace I've used! ⭐",
    "Funds were safe throughout. Excellent! 💎",
    "Admin team is top-notch 🙏",
    "Transparent process — exactly what I needed",
    "Zero stress. Would 100% recommend 🚀",
    "Fast, legit, and professional 💪",
    "Perfect escrow system. No worries at all",
    "Used 3 platforms before — this is #1 🏆",
    "Everything went like clockwork ⏱️",
    "Would recommend to any account buyer",
    "Safest trade I've ever made 🛡️",
    "Solid platform, honest team, clean process",
]

QUICK_PLATFORM_4 = [
    "Good experience overall 👌",
    "Reliable platform, minor wait time",
    "Solid service. Would use again 👍",
    "Good process, small delays but fine",
    "Trustworthy. Just a tiny bit slow",
    "Happy with the result overall",
    "Good trade. Minor hiccup but resolved",
    "Would recommend. Just slightly slow",
    "Decent experience. Safe platform",
    "Reliable. Would return for future deals",
]

QUICK_PLATFORM_3 = [
    "It was okay. Could be faster",
    "Average experience. Got what I paid for",
    "Not bad, not great. Works fine",
    "Process could be smoother",
    "Functional but needs improvement",
    "Expected more but it worked out",
]

QUICK_PLATFORM_LOW = [
    "Took way too long 👎",
    "Not satisfied with the process",
    "Could be much better 😕",
    "Communication was lacking",
    "Expected faster service",
    "Process felt unclear and slow",
]

QUICK_USER_5 = [
    "Amazing seller! Super fast 🔥",
    "Honest & professional seller 💯",
    "Best seller I've dealt with ⭐",
    "Incredibly responsive seller 🙌",
    "Transfer was instant & clean ✅",
    "Seller delivered exactly as promised",
    "Trusted seller — no issues at all",
    "10/10 seller. Would buy again 🏆",
    "Channel was exactly as described 💎",
    "Smooth handover. Great seller 👍",
    "Seller made everything easy 🚀",
    "Top-tier communication. Excellent seller",
    "Fast, honest & reliable seller 💪",
    "Perfect transaction. Great seller 🎯",
    "Seller was transparent throughout 🔒",
    "Highly recommend this seller!",
    "Flawless seller. Zero complaints ✨",
    "Quick responses, clean delivery",
    "Would definitely buy from again!",
    "One of the best sellers out there 🥇",
]

QUICK_USER_4 = [
    "Good seller overall 👌",
    "Reliable. Minor delay but fine",
    "Honest seller. Would buy again",
    "Good communication, slight wait",
    "Solid seller. Delivered as promised",
    "Trustworthy. Minor hiccup resolved",
    "Good transaction. Happy overall",
    "Would recommend this seller",
    "Decent seller. No major issues",
    "Reliable person to deal with",
]

QUICK_USER_3 = [
    "Okay seller. Could communicate more",
    "Got what I paid for eventually",
    "Average. Nothing special",
    "Seller was fine. Just slow",
    "Delivered but took too long",
    "Expected more but it worked out",
]

QUICK_USER_LOW = [
    "Seller was too slow 👎",
    "Could be better 😕",
    "Not impressed with this seller",
    "Communication was poor",
    "Took way too long",
    "Didn't meet expectations",
]

# ──────────────────────────────────────────────────────────────────
#  PUBLIC API
# ──────────────────────────────────────────────────────────────────

def _get_quick_pool(rating: int, review_type: str) -> list:
    """Return the correct quick-select pool for the given rating and type."""
    if review_type == 'platform':
        if rating >= 5:
            return QUICK_PLATFORM_5
        elif rating == 4:
            return QUICK_PLATFORM_4
        elif rating == 3:
            return QUICK_PLATFORM_3
        else:
            return QUICK_PLATFORM_LOW
    else:  # 'user' / seller
        if rating >= 5:
            return QUICK_USER_5
        elif rating == 4:
            return QUICK_USER_4
        elif rating == 3:
            return QUICK_USER_3
        else:
            return QUICK_USER_LOW


def get_preset_comments(rating: int, review_type: str, seed=None) -> list:
    """
    Return exactly 5 unique preset comment strings for the rating buttons.

    Args:
        rating: 1-5 integer star rating.
        review_type: 'platform' or 'user'.
        seed: Optional seed for reproducible selection (e.g. hash of user_id+order_num).

    Returns:
        A list of exactly 5 strings (or fewer if pool is smaller than 5).
    """
    pool = _get_quick_pool(rating, review_type)
    rng = random.Random(seed) if seed is not None else random.Random()
    count = min(5, len(pool))
    return rng.sample(pool, count)


def _get_auto_pool(review_type: str) -> list:
    """Return the long-form 5-star auto-review pool for auto-play transactions."""
    if review_type == 'platform':
        return PLATFORM_5_STAR
    else:
        return USER_5_STAR


def get_auto_review(review_type: str, used: set = None) -> str:
    """
    Return a single 5-star review string for auto-play, avoiding recent repeats.

    Args:
        review_type: 'platform' or 'user'.
        used: Optional mutable set of already-used review strings. Will be
              updated with the chosen review. When pool is exhausted, resets.

    Returns:
        A review string.
    """
    pool = _get_auto_pool(review_type)
    if used is None:
        used = set()

    available = [r for r in pool if r not in used]
    # If we've exhausted the pool, reset
    if not available:
        used.clear()
        available = pool[:]

    choice = random.choice(available)
    used.add(choice)
    return choice


def get_review_by_rating(rating: int, review_type: str) -> str:
    """
    Return a single appropriate review for any rating (used for auto-play
    when you want a rating-appropriate comment, not always 5-star).
    """
    if review_type == 'platform':
        if rating >= 5:
            pool = PLATFORM_5_STAR
        elif rating == 4:
            pool = PLATFORM_4_STAR
        elif rating == 3:
            pool = PLATFORM_3_STAR
        else:
            pool = PLATFORM_LOW
    else:
        if rating >= 5:
            pool = USER_5_STAR
        elif rating == 4:
            pool = USER_4_STAR
        elif rating == 3:
            pool = USER_3_STAR
        else:
            pool = USER_LOW

    return random.choice(pool)
