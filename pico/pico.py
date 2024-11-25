import logging
import pvporcupine 

logging.basicConfig(level=logging.INFO)
pico_logger = logging.getLogger(__name__)

class PicoVoiceTrigger:
    def __init__(self, args):
        self.porcupine = self._create_porcupine(args.access_key, args.model_path, args.keyword_paths, args.sensitivities)
        self.frame_length = self.porcupine.frame_length

    def _create_porcupine(self,access_key, model_path, keyword_paths, sensitivities):
        try:
            return pvporcupine.create(
                access_key=access_key,
                model_path=model_path,
                keyword_paths=keyword_paths,
                sensitivities=sensitivities)
        except pvporcupine.PorcupineInvalidArgumentError as e:
            pico_logger.error("One or more arguments provided to Porcupine is invalid: ", e)
            raise e
        except pvporcupine.PorcupineActivationError as e:
            pico_logger.error("AccessKey activation error")
            raise e
        except pvporcupine.PorcupineActivationLimitError as e:
            pico_logger.error("AccessKey '%s' has reached its temporary device limit" % access_key)
            raise e
        except pvporcupine.PorcupineActivationRefusedError as e:
            pico_logger.error("AccessKey '%s' refused" % access_key)
            raise e
        except pvporcupine.PorcupineActivationThrottledError as e:
            pico_logger.error("AccessKey '%s' has been throttled" % access_key)
            raise e
        except pvporcupine.PorcupineError as e:
            pico_logger.error(f"Failed to initialize Porcupine: {e}")
            raise e
    
    def process(self, audio_frame):
        return self.porcupine.process(audio_frame)
    
    