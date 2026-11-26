"""Пакет маршрутів (Blueprint) застосунку LOQ Market."""
from .admin import admin_bp
from .api import api_bp
from .auth import auth_bp
from .feedback import feedback_bp
from .shop import shop_bp

__all__ = ["admin_bp", "api_bp", "auth_bp", "feedback_bp", "shop_bp"]
