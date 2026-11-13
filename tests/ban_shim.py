"""
ban_shim.py — testlar uchun ban yordamchilari.

Ban tekshiruvi endi YAGONA database.get_ban_info orqali ketadi (middleware, API, pre_checkout, fon vazifalari).
Eski testlar database.is_user_banned ni (bool, matn) ko'rinishida mock qiladi: ban_info_patch shu mock'dan get_ban_info
javobini hosil qiladi, shunda ikkalasi hamisha mos turadi.
"""
from unittest import mock

import database

FREE_INFO = {"banned": False, "mode": None, "until": None, "reason": None}


def info_from_result(result) -> dict:
    """(is_banned, matn, ...) -> get_ban_info ko'rinishi (rejim 'open', muddatsiz, sababsiz)."""
    if result and result[0]:
        return {"banned": True, "mode": "open", "until": None, "reason": None}
    return dict(FREE_INFO)


def ban_info_patch(is_banned_mock):
    """get_ban_info ni is_user_banned mock'iga bog'laydi (qo'ng'iroqlar ikkalasida ham hisoblanadi)."""
    return mock.patch.object(database, "get_ban_info", side_effect=lambda uid: info_from_result(is_banned_mock(uid)))


def not_banned_patch():
    """Hech kim banda emas (get_ban_info)."""
    return mock.patch.object(database, "get_ban_info", return_value=dict(FREE_INFO))
