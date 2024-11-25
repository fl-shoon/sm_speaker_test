import asyncio
import logging 

logging.basicConfig(level=logging.INFO)
sensor_logger = logging.getLogger(__name__)

class SpeakerSensor:
    def __init__(self, server_manager, fire_client):
        self.server_manager = server_manager
        self.fire_client = fire_client
        self.auth_token =  None
        self.last_sensor_data = None

    async def update_sensor_data(self):
        current_sensor_data = await self.get_current_sensor_data()
        if self.should_update_sensor_data(current_sensor_data):
            try:
                success = await self.fire_client.update_sensor_data(current_sensor_data)
                if success:
                    self.last_sensor_data = current_sensor_data
                else:
                    sensor_logger.error("Failed to update sensor data")
            except Exception as e:
                sensor_logger.error(f"Error updating sensor data: {e}")

    def should_update_sensor_data(self, current_sensor_data):
        if not self.last_sensor_data:
            return True
        
        thresholds = {
            'temperatureSensor': 0.5,  
            'irSensor': None,  
            'brightnessSensor': 5.0  
        }
        
        for key, threshold in thresholds.items():
            if key not in self.last_sensor_data:
                return True
            
            current_value = current_sensor_data.get(key)
            last_value = self.last_sensor_data.get(key)
            
            if current_value is None or last_value is None:
                return True
            
            if isinstance(current_value, bool):
                if current_value != last_value:
                    return True
            else:
                try:
                    if abs(float(current_value) - float(last_value)) >= threshold:
                        return True
                except ValueError:
                    if current_value != last_value:
                        return True
        
        return False

    async def get_current_sensor_data(self):
        try:
            sensors = await self.server.get_sensors()
            if sensors:
                return {
                    'temperatureSensor': f"{sensors.get('temperature', 0):.2f}",
                    'irSensor': sensors.get('motion', False),
                    'brightnessSensor': f"{sensors.get('lux2', 0):.2f}"  # Using lux2 (visible light + UV) for brightness
                }
            return {}
        except Exception as e:
            sensor_logger.error(f"Error getting sensor data: {e}")
            return {}