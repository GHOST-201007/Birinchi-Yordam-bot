"""
discount_helpers.py — SUPER PRIZ chegirmasi (24 soat, Pro -50%) testlari uchun umumiy yordamchilar.

Testlar bazaga murojaat qilmasligi uchun database.get_discount_info shu yerdagi tayyor natija bilan almashtiriladi.
Vaqt HAQIQIY hozirgi payt (database.get_uz_now) ga nisbatan olinadi: bot.format_discount_left ham shu soatdan foydalanadi.
"""
import datetime as dt

import database


def discount_info(active=True, hours=5, minutes=0):
    """database.get_discount_info natijasi: {"active", "expires_at", "seconds_left", "price", "old_price"}.
    active=True: hozirdan hours soat minutes daqiqadan keyin tugaydi; False: chegirma yo'q (muddat o'tgan ham shu ko'rinishda)."""
    if not active:
        return database._discount_view(0, None)
    now = database.get_uz_now()
    return database._discount_view(1, now + dt.timedelta(hours=hours, minutes=minutes), now)
