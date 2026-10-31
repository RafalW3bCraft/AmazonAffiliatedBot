import functools
import logging
import asyncio
import threading
import atexit
from datetime import datetime
from flask import Flask, render_template, request, jsonify, abort
from config import Config
from database_simple import SimpleDatabaseManager
from core.telemetry import metrics

logger = logging.getLogger(__name__)


def require_dashboard_auth(config: Config):
    """Decorator factory: protect privileged routes with DASHBOARD_TOKEN.

    Token is accepted via `Authorization: Bearer <token>` header or `?token=`
    query param (for the HTML pages). When no token is configured and the app
    is not in DEMO_MODE, privileged routes are disabled (404) rather than open.
    """
    def decorator(view):
        @functools.wraps(view)
        def wrapper(*args, **kwargs):
            token = getattr(config, 'DASHBOARD_TOKEN', '')
            demo = getattr(config, 'DEMO_MODE', False)
            if not token:
                if demo:
                    return view(*args, **kwargs)  # demo mode: open, clearly labeled in UI
                abort(404)  # fail closed: privileged route disabled
            provided = request.headers.get('Authorization', '')
            if provided.startswith('Bearer '):
                provided = provided[7:]
            else:
                provided = request.args.get('token', '')
            import hmac
            if not provided or not hmac.compare_digest(provided, token):
                return jsonify({'error': 'authentication required'}), 401
            return view(*args, **kwargs)
        return wrapper
    return decorator


class AsyncDataManager:
    
    def __init__(self, config: Config):
        self.config = config
        self.db_manager = None
        self._loop = None
        self._thread = None
        self._initialized = False
        
    def start(self):
        if self._initialized:
            return
            
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        
        import time
        timeout = 10
        start_time = time.time()
        while not self._initialized and time.time() - start_time < timeout:
            time.sleep(0.1)
        
    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        
        try:
            if hasattr(self.config, 'DATABASE_URL') and self.config.DATABASE_URL:
                try:
                    from database import DatabaseManager
                    self.db_manager = DatabaseManager(self.config.DATABASE_URL)
                    logger.info("📊 Dashboard using PostgreSQL database")
                except Exception as e:
                    logger.warning(f"PostgreSQL failed, using in-memory database: {e}")
                    self.db_manager = SimpleDatabaseManager()
            else:
                logger.info("📊 Dashboard using in-memory database")
                self.db_manager = SimpleDatabaseManager()
                
            self._loop.run_until_complete(self.db_manager.initialize())
            self._initialized = True
            
            self._loop.run_forever()
        except Exception as e:
            logger.error(f"Error in async loop: {e}")
            self._initialized = True
        
    def execute_async(self, coro):
        if not self._loop or not self._initialized:
            if hasattr(coro, "close"):
                coro.close()
            return None
            
        try:
            future = asyncio.run_coroutine_threadsafe(coro, self._loop)
            return future.result(timeout=10)
        except Exception as e:
            if hasattr(coro, "close"):
                coro.close()
            logger.error(f"Async execution error: {e}")
            return None

    def stop(self):
        if self.db_manager and self._loop and self._loop.is_running():
            try:
                close_coro = self.db_manager.close()
                asyncio.run_coroutine_threadsafe(close_coro, self._loop).result(timeout=5)
            except Exception as e:
                logger.warning(f"AsyncDataManager DB close warning: {e}")
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        logger.info("AsyncDataManager stopped")


def safe_int(value, default=0):
    if value is None:
        return default
    try:
        result = int(value)
        # Prevent negative values or extremely large values
        if result < 0:
            return default
        if result > 1000000:  # Reasonable upper limit
            return default
        return result
    except (ValueError, TypeError):
        return default

def safe_float(value, default=0.0):
    if value is None:
        return default
    try:
        result = float(value)
        # Prevent negative values or extremely large values
        if result < 0:
            return default
        if result > 10000000:  # Reasonable upper limit
            return default
        return result
    except (ValueError, TypeError):
        return default

def sanitize_string(value, max_length=100, allowed_chars=None):
    """Sanitize string input to prevent XSS and injection attacks."""
    if value is None:
        return None
    
    if not isinstance(value, str):
        value = str(value)
    
    # Remove any HTML tags
    import re
    value = re.sub(r'<[^>]+>', '', value)
    
    # Remove script patterns
    value = re.sub(r'javascript:', '', value, flags=re.IGNORECASE)
    value = re.sub(r'on\w+\s*=', '', value, flags=re.IGNORECASE)
    
    # Limit length
    value = value[:max_length] if len(value) > max_length else value
    
    # If allowed_chars specified, filter to only those characters
    if allowed_chars:
        value = ''.join(c for c in value if c in allowed_chars)
    
    return value.strip()

def create_app(config: Config):
    app = Flask(__name__)
    # Config validates FLASK_SECRET_KEY at construction (fail-closed); no insecure
    # fallback is permitted here.
    app.config['SECRET_KEY'] = config.FLASK_SECRET_KEY

    # Session cookie hardening (DealPilot web layer).
    try:
        from web.auth import apply_security
        apply_security(app)
    except Exception as e:
        logger.warning(f"apply_security failed: {e}")

    data_manager = AsyncDataManager(config)
    data_manager.start()
    atexit.register(data_manager.stop)

    setattr(app, 'data_manager', data_manager)

    auth = require_dashboard_auth(config)

    # Register the commerce blueprint (DealPilot two-lane shop) when enabled.
    if getattr(config, 'ENABLE_MERCHANT_CHECKOUT', False) or getattr(config, 'ENABLE_EXTERNAL_AFFILIATE', False):
        try:
            from web.commerce_routes import create_commerce_blueprint
            commerce_bp = create_commerce_blueprint(config)
            app.register_blueprint(commerce_bp)
            logger.info("Commerce blueprint registered (/shop, /cart, /checkout, /orders, /merchant)")
        except Exception as e:
            logger.error(f"Commerce blueprint registration failed: {e}")
            if not getattr(config, 'DEMO_MODE', False):
                raise
    
    @app.route('/')
    def landing():
        if getattr(config, 'ENABLE_MERCHANT_CHECKOUT', False) or getattr(config, 'ENABLE_EXTERNAL_AFFILIATE', False):
            try:
                return render_template('landing.html')
            except Exception:
                pass
        return render_template('dashboard.html')
    
    @app.route('/deals')
    def deals_page():
        return render_template('deals.html')
    
    @app.route('/users')
    @auth
    def users_page():
        return render_template('users.html')
    
    @app.route('/api/stats')
    def api_stats():
        try:
            data_manager = getattr(app, 'data_manager', None)
            if not data_manager or not data_manager.db_manager:
                return jsonify({'error': 'Database not available'}), 503
            
            total_deals = 0
            recent_count = 0
            total_clicks = 0
            total_conversions = 0
            total_earnings = 0.0
            active_count = 0
            category_stats = {}
            source_stats = {}
            
            try:
                stats = data_manager.execute_async(data_manager.db_manager.get_deal_stats())
                if stats:
                    total_deals = safe_int(getattr(stats, 'total_deals', 0))
                    total_clicks = safe_int(getattr(stats, 'total_clicks', 0))
                    total_conversions = safe_int(getattr(stats, 'total_conversions', 0))
                    total_earnings = safe_float(getattr(stats, 'total_earnings', 0.0))
                    recent_count = safe_int(getattr(stats, 'recent_deals', 0))
                    active_count = safe_int(getattr(stats, 'active_users', 0))
                    
                    category_stats = getattr(stats, 'category_stats', {}) or {}
                    source_stats = getattr(stats, 'source_stats', {}) or {}
                    if not isinstance(category_stats, dict):
                        category_stats = {}
                    if not isinstance(source_stats, dict):
                        source_stats = {}
                    category_stats = {str(k): int(v) if v is not None else 0 for k, v in category_stats.items()}
                    source_stats = {str(k): int(v) if v is not None else 0 for k, v in source_stats.items()}
                        
            except Exception as e:
                logger.error(f"Error getting deal stats: {e}")
                import traceback
                logger.error(f"Stats traceback: {traceback.format_exc()}")
            
            if recent_count == 0:
                try:
                    recent_deals = data_manager.execute_async(
                        data_manager.db_manager.get_recent_deals(hours=24, limit=100)
                    )
                    recent_count = len(recent_deals) if recent_deals else 0
                except Exception as e:
                    logger.error(f"Error getting recent deals: {e}")
            
            if active_count == 0:
                try:
                    active_users = data_manager.execute_async(
                        data_manager.db_manager.get_active_users(days=30)
                    )
                    active_count = len(active_users) if active_users else 0
                except Exception as e:
                    logger.error(f"Error getting active users: {e}")
            
            conversion_rate = 0.0
            if total_clicks > 0:
                conversion_rate = (total_conversions / total_clicks) * 100
            
            avg_earnings_per_deal = 0.0
            avg_earnings_per_click = 0.0
            
            if total_deals > 0:
                avg_earnings_per_deal = total_earnings / total_deals
            
            if total_clicks > 0:
                avg_earnings_per_click = total_earnings / total_clicks
            
            return jsonify({
                'total_deals': total_deals,
                'recent_deals': recent_count,
                'total_clicks': total_clicks,
                'total_conversions': total_conversions,
                'total_earnings': round(total_earnings, 2),
                'active_users': active_count,
                'conversion_rate': round(conversion_rate, 2),
                'avg_earnings_per_deal': round(avg_earnings_per_deal, 2),
                'avg_earnings_per_click': round(avg_earnings_per_click, 4),
                'category_stats': category_stats,
                'source_stats': source_stats,
                'timestamp': datetime.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Stats API error: {e}")
            import traceback
            logger.error(f"Stats API traceback: {traceback.format_exc()}")
            
            return jsonify({'error': 'Statistics temporarily unavailable'}), 503
    
    @app.route('/api/deals')
    def api_deals():
        try:
            hours = safe_int(request.args.get('hours', 24), 24)
            limit = safe_int(request.args.get('limit', 50), 50)
            category_raw = request.args.get('category', None)
            # Sanitize category input - only allow alphanumeric, hyphens, underscores
            category = sanitize_string(category_raw, max_length=50, allowed_chars='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_') if category_raw else None
            
            data_manager = getattr(app, 'data_manager', None)
            if not data_manager or not data_manager.db_manager:
                return jsonify([])
            
            deals = data_manager.execute_async(
                data_manager.db_manager.get_recent_deals(
                    hours=hours, limit=limit, category=category
                )
            )
            
            if not deals:
                return jsonify([])
            
            deals_data = []
            for deal in deals:
                try:
                    deal_dict = {
                        'id': getattr(deal, 'id', None),
                        'title': str(getattr(deal, 'title', '') or ''),
                        'price': str(getattr(deal, 'price', '') or ''),
                        'discount': str(getattr(deal, 'discount', '') or ''),
                        'category': str(getattr(deal, 'category', '') or ''),
                        'source': str(getattr(deal, 'source', '') or ''),
                        'asin': str(getattr(deal, 'asin', '') or ''),
                        'clicks': safe_int(getattr(deal, 'clicks', 0)),
                        'conversions': safe_int(getattr(deal, 'conversions', 0)),
                        'earnings': safe_float(getattr(deal, 'earnings', 0.0)),
                        'posted_at': getattr(deal, 'posted_at', None).isoformat() if getattr(deal, 'posted_at', None) else None,
                        'affiliate_link': str(getattr(deal, 'affiliate_link', '') or ''),
                        'rating': safe_float(getattr(deal, 'rating', 0.0)),
                        'review_count': safe_int(getattr(deal, 'review_count', 0)),
                        'is_active': bool(getattr(deal, 'is_active', True))
                    }
                    deals_data.append(deal_dict)
                except Exception as e:
                    logger.error(f"Error processing deal: {e}")
                    continue
            
            return jsonify(deals_data)
            
        except Exception as e:
            logger.error(f"Deals API error: {e}")
            return jsonify([])
    
    @app.route('/api/users')
    @auth
    def api_users():
        """Privileged endpoint: data-minimized aggregates only, no PII."""
        try:
            days = safe_int(request.args.get('days', 30), 30)

            data_manager = getattr(app, 'data_manager', None)
            if not data_manager or not data_manager.db_manager:
                return jsonify({'error': 'Database not available'}), 503

            users = data_manager.execute_async(
                data_manager.db_manager.get_active_users(days=days)
            )

            if not users:
                return jsonify({'active_users': 0, 'regions': {}, 'categories': {}, 'window_days': days})

            regions: dict = {}
            categories: dict = {}
            for user in users:
                try:
                    region = str(getattr(user, 'region', 'US') or 'US')
                    category = str(getattr(user, 'category', 'all') or 'all')
                    regions[region] = regions.get(region, 0) + 1
                    categories[category] = categories.get(category, 0) + 1
                except Exception as e:
                    logger.error(f"Error aggregating user: {e}")
                    continue

            return jsonify({
                'active_users': len(users),
                'regions': regions,
                'categories': categories,
                'window_days': days,
            })

        except Exception as e:
            logger.error(f"Users API error: {e}")
            return jsonify({'error': 'User statistics temporarily unavailable'}), 503
    
    @app.route('/api/config')
    def api_config():
        """Public, non-sensitive configuration. No affiliate IDs, no secrets,
        no merchant credentials - masked capability flags only."""
        try:
            return jsonify({
                'supported_regions': config.get_supported_regions() if hasattr(config, 'get_supported_regions') else ['US'],
                'default_region': getattr(config, 'DEFAULT_REGION', 'US'),
                'bot_configured': bool(getattr(config, 'bot_configured', False)),
                'ai_configured': bool(getattr(config, 'ai_configured', False)),
                'database_configured': bool(getattr(config, 'database_configured', False)),
                'merchant_checkout_enabled': bool(getattr(config, 'ENABLE_MERCHANT_CHECKOUT', False)),
                'external_affiliate_enabled': bool(getattr(config, 'ENABLE_EXTERNAL_AFFILIATE', False)),
                'demo_mode': bool(getattr(config, 'DEMO_MODE', False)),
                'post_interval_hours': getattr(config, 'POST_INTERVAL_HOURS', 1),
                'version': '3.0.0-dealpilot'
            })
        except Exception as e:
            logger.error(f"Config API error: {e}")
            return jsonify({'error': 'Configuration unavailable'}), 500

    @app.route('/api/ready')
    def api_ready():
        """Readiness: fails (503) unless every enabled feature's hard dependency
        is available. Distinct from /api/health which reports liveness."""
        checks = {}
        ready = True

        data_manager = getattr(app, 'data_manager', None)
        db_ok = False
        if data_manager and getattr(data_manager, 'db_manager', None) is not None:
            try:
                db_ok = data_manager.execute_async(data_manager.db_manager.get_deal_stats()) is not None
            except Exception:
                db_ok = False
        checks['database'] = db_ok

        if getattr(config, 'ENABLE_MERCHANT_CHECKOUT', False):
            try:
                from commerce.storage import CommerceStorage
                storage = getattr(app, 'commerce_storage', None)
                checks['commerce_storage'] = bool(storage and storage.ready())
                if not checks['commerce_storage']:
                    ready = False
            except Exception:
                checks['commerce_storage'] = False
                ready = False

        checks['paypal_credentials_present'] = bool(getattr(config, 'paypal_configured', False))
        if getattr(config, 'ENABLE_MERCHANT_CHECKOUT', False) and not checks['paypal_credentials_present']:
            ready = False  # checkout enabled without credentials is not ready

        status = 200 if ready else 503
        return jsonify({
            'ready': ready,
            'checks': checks,
            'timestamp': datetime.now().isoformat()
        }), status
    
    @app.route('/api/health')
    def api_health():
        try:
            data_manager = getattr(app, 'data_manager', None)
            db_healthy = False
            
            if data_manager and hasattr(data_manager, 'db_manager') and data_manager.db_manager is not None:
                if hasattr(data_manager, 'execute_async'):
                    try:
                        test_stats = data_manager.execute_async(data_manager.db_manager.get_deal_stats())
                        db_healthy = test_stats is not None
                    except:
                        db_healthy = False
                else:
                    db_healthy = True
            
            return jsonify({
                'status': 'healthy' if db_healthy else 'degraded',
                'database': 'connected' if db_healthy else 'disconnected',
                'metrics': metrics.snapshot(),
                'timestamp': datetime.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Health check error: {e}")
            return jsonify({
                'status': 'unhealthy',
                'error': str(e),
                'metrics': metrics.snapshot(),
                'timestamp': datetime.now().isoformat()
            }), 503
    
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Endpoint not found'}), 404
    
    @app.errorhandler(500)  
    def internal_error(error):
        logger.error(f"Internal server error: {error}")
        return jsonify({'error': 'Internal server error'}), 500
    
    return app


def run_production_dashboard():
    config = Config()
    app = create_app(config)
    
    logger.info("Starting production web dashboard on http://0.0.0.0:5000")
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,
        threaded=True
    )


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    run_production_dashboard()
