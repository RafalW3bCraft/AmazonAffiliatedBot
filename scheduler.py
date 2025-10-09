import asyncio
import logging
from datetime import datetime, timedelta
from config import Config

logger = logging.getLogger(__name__)


class TaskScheduler:
    
    
    def __init__(self, bot, config: Config):
        self.bot = bot
        self.config = config
        self.running = False
        self.tasks = []
        
    async def start(self):
        
        try:
            self.running = True
            logger.info("⏰ Starting task scheduler...")
            
            try:
                async with asyncio.TaskGroup() as tg:
                    deal_posting_task = tg.create_task(
                        self._schedule_deal_posting()
                    )
                    self.tasks.append(deal_posting_task)
                    
                    cleanup_task = tg.create_task(
                        self._schedule_database_cleanup()
                    )
                    self.tasks.append(cleanup_task)
                    
                    stats_task = tg.create_task(
                        self._schedule_stats_update()
                    )
                    self.tasks.append(stats_task)
                    
                    logger.info("✅ All scheduled tasks started")
                    
            except* Exception as eg:
                logger.error(f"Error in task scheduler: {eg}")
        except Exception as e:
            logger.warning("TaskGroup not available, using legacy task scheduling")
            await self._start_legacy_tasks()
        finally:
            self.running = False
    
    async def _start_legacy_tasks(self):
        
        self.running = True
        
        tasks = [
            asyncio.create_task(self._schedule_deal_posting()),
            asyncio.create_task(self._schedule_database_cleanup()),
            asyncio.create_task(self._schedule_stats_update())
        ]
        
        self.tasks.extend(tasks)
        
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.error(f"Legacy task scheduler error: {e}")
    
    async def stop(self):
        
        logger.info("🛑 Stopping task scheduler...")
        self.running = False
        
        for task in self.tasks:
            if not task.done():
                task.cancel()
        
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        
        logger.info("✅ Task scheduler stopped")
    
    async def _schedule_deal_posting(self):
        
        logger.info(f"📋 Deal posting scheduled every {self.config.POST_INTERVAL_MINUTES} minutes")
        
        await asyncio.sleep(60)
        
        while self.running:
            try:
                logger.info("🔄 Starting scheduled deal posting...")
                
                posted_count = await self.bot.post_deals()
                
                if posted_count > 0:
                    logger.info(f"✅ Scheduled posting: {posted_count} deals posted")
                else:
                    logger.info("ℹ️ Scheduled posting: No new deals to post")
                
                await asyncio.sleep(self.config.POST_INTERVAL_MINUTES * 60)
                
            except asyncio.CancelledError:
                logger.info("Deal posting task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in scheduled deal posting: {e}")
                await asyncio.sleep(300)
    
    async def _schedule_database_cleanup(self):
        
        logger.info("🧹 Database cleanup scheduled daily")
        
        await asyncio.sleep(300)
        
        while self.running:
            try:
                logger.info("🧹 Starting scheduled database cleanup...")
                
                deleted_count = await self.bot.db_manager.cleanup_old_deals(days=30)
                
                if deleted_count > 0:
                    logger.info(f"✅ Database cleanup: Removed {deleted_count} old deals")
                else:
                    logger.info("ℹ️ Database cleanup: No old deals to remove")
                
                await asyncio.sleep(24 * 3600)
                
            except asyncio.CancelledError:
                logger.info("Database cleanup task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in scheduled database cleanup: {e}")
                await asyncio.sleep(3600)
    
    async def _schedule_stats_update(self):
        
        logger.info("📊 Statistics update scheduled every hour")
        await asyncio.sleep(120)
        while self.running:
            try:
                logger.info("📊 Updating statistics...")
                stats = await self.bot.db_manager.get_deal_stats()
                if stats:
                    logger.info(f"📊 Current stats: {stats.total_deals} deals, "
                                f"{stats.total_clicks} clicks, ${stats.total_earnings:.2f} earnings")
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                logger.info("Statistics update task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in scheduled stats update: {e}")
                await asyncio.sleep(1800)
    
    async def run_immediate_task(self, task_name: str) -> bool:
        
        try:
            match task_name.lower():
                case 'post_deals':
                    logger.info("🚀 Running immediate deal posting...")
                    count = await self.bot.post_deals()
                    logger.info(f"✅ Immediate posting completed: {count} deals")
                    return True
                    
                case 'cleanup_database':
                    logger.info("🚀 Running immediate database cleanup...")
                    count = await self.bot.db_manager.cleanup_old_deals()
                    logger.info(f"✅ Immediate cleanup completed: {count} deals removed")
                    return True
                    
                case 'update_stats':
                    logger.info("🚀 Running immediate stats update...")
                    stats = await self.bot.db_manager.get_deal_stats()
                    if stats:
                        logger.info(f"✅ Stats updated: {stats.total_deals} total deals")
                    return True
                    
                case _:
                    logger.error(f"Unknown task: {task_name}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error running immediate task {task_name}: {e}")
            return False
    
    def get_task_status(self) -> dict:
        
        return {
            'running': self.running,
            'active_tasks': len([t for t in self.tasks if not t.done()]),
            'total_tasks': len(self.tasks),
            'next_deal_posting': self._get_next_run_time('deal_posting'),
            'next_cleanup': self._get_next_run_time('cleanup'),
            'next_stats_update': self._get_next_run_time('stats')
        }
    
    def _get_next_run_time(self, task_type: str) -> str:
        
        now = datetime.now()
        
        match task_type:
            case 'deal_posting':
                next_run = now + timedelta(minutes=self.config.POST_INTERVAL_MINUTES)
            case 'cleanup':
                next_run = now + timedelta(days=1)
            case 'stats':
                next_run = now + timedelta(hours=1)
            case _:
                return "Unknown"
        
        return next_run.strftime("%Y-%m-%d %H:%M:%S")


class PerformanceMonitor:
    
    
    def __init__(self):
        self.task_metrics = {}
        self.error_counts = {}
        
    def record_task_execution(self, task_name: str, duration: float, success: bool):
        
        if task_name not in self.task_metrics:
            self.task_metrics[task_name] = {
                'executions': 0,
                'total_duration': 0.0,
                'successes': 0,
                'failures': 0,
                'last_execution': None
            }
        
        metrics = self.task_metrics[task_name]
        metrics['executions'] += 1
        metrics['total_duration'] += duration
        metrics['last_execution'] = datetime.now()
        
        if success:
            metrics['successes'] += 1
        else:
            metrics['failures'] += 1
    
    def get_task_health(self, task_name: str) -> dict:
        
        if task_name not in self.task_metrics:
            return {'status': 'unknown', 'message': 'No execution data'}
        
        metrics = self.task_metrics[task_name]
        success_rate = metrics['successes'] / metrics['executions'] if metrics['executions'] > 0 else 0
        avg_duration = metrics['total_duration'] / metrics['executions'] if metrics['executions'] > 0 else 0
        
        if success_rate >= 0.9:
            status = 'healthy'
        elif success_rate >= 0.7:
            status = 'warning'
        else:
            status = 'critical'
        
        return {
            'status': status,
            'success_rate': success_rate,
            'average_duration': avg_duration,
            'total_executions': metrics['executions'],
            'last_execution': metrics['last_execution'].isoformat() if metrics['last_execution'] else None
        }
