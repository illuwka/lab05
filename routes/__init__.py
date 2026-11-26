"""Пакет маршрутів (Blueprint) застосунку LOQ Market."""
from .admin import admin_bp
from .api import api_bp, api_v1_bp
from .api_v2 import api_v2_bp
from .auth import auth_bp
from .feedback import feedback_bp
from .shop import shop_bp

__all__ = ["admin_bp", "api_bp", "api_v1_bp", "api_v2_bp", "auth_bp", "feedback_bp", "shop_bp"]
