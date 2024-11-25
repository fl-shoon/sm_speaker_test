from sensor.sensor import SpeakerSensor

import datetime
import logging
import schedule

logging.basicConfig(level=logging.INFO)
scheduler_logger = logging.getLogger(__name__)

scheduler = schedule.Scheduler()

def run_pending():
    scheduler.run_pending()

def every(interval):
    return scheduler.every(interval)

def clear(tag=None):
    return scheduler.clear(tag)

class ScheduleManager:
    def __init__(self, server_manager, fire_client):
        self.sensor = SpeakerSensor(server_manager=server_manager, fire_client=fire_client)
        
        self.fire_client = fire_client
        self.current_schedule = {}
        self.schedule_update_interval = 3 * 60  # run schedule every 3 minutes
        self.scheduled_conversation_flag = False
        self.last_trigger_time = None

        self.initialize()

    def initialize(self):
        self.get_schedule()
        every(self.schedule_update_interval).seconds.do(self.get_schedule)
        every(self.schedule_update_interval).seconds.do(self.sensor.update_sensor_data)

    def get_schedule(self):
        try:
            new_schedule = self.fire_client.fetch_schedule()
            if new_schedule != self.current_schedule:
                self.current_schedule = new_schedule
                self.set_next_schedule_check()
            scheduler_logger.info("Schedule updated")
        except Exception as e:
            scheduler_logger.error(f"Failed to fetch schedule: {e}")

    def set_next_schedule_check(self):
        if not self.current_schedule:
            return

        now = datetime.datetime.now()
        scheduled_time = now.replace(hour=int(self.current_schedule['hour']), 
                                     minute=int(self.current_schedule['minute']), 
                                     second=0, microsecond=0)
        
        if scheduled_time <= now:
            scheduled_time += datetime.timedelta(days=1)
        
        time_diff = (scheduled_time - now).total_seconds()
        check_time = max(time_diff - 30, 30)  
        
        clear('schedule_check')
        every(check_time).seconds.do(self.trigger_scheduled_conversation).tag('schedule_check')
        scheduler_logger.info(f"Next schedule check set for {check_time} seconds from now")

    def trigger_scheduled_conversation(self):
        now = datetime.datetime.now()
        scheduled_time = now.replace(hour=int(self.current_schedule['hour']), 
                                     minute=int(self.current_schedule['minute']), 
                                     second=0, microsecond=0)
        
        time_diff = abs((now - scheduled_time).total_seconds())
        if time_diff <= 30:
            if (self.last_trigger_time is None or 
                (now - self.last_trigger_time).total_seconds() > 300):
                self.scheduled_conversation_flag = True
                self.last_trigger_time = now
                scheduler_logger.info(f"Triggering scheduled conversation at {now}")
            else:
                scheduler_logger.info(f"Skipping trigger as last trigger was too recent")
        
        self.set_next_schedule_check()

    def check_scheduled_conversation(self):
        if self.scheduled_conversation_flag:
            self.scheduled_conversation_flag = False  
            return True
        return False