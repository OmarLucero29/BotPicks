import time
from pipelines.data_system_pipeline import DataSystemPipeline


class DataCollectorWorker:

    name = "data_collector_worker"

    def __init__(self):
        self.pipeline = DataSystemPipeline()

    def run(self, context):

        context["logger"].info("Data collector worker started")

        while True:

            try:

                self.pipeline.execute(context)

                context["logger"].info("Data collection cycle completed")

            except Exception as e:

                context["logger"].error(f"Data collector error {e}")

            time.sleep(60)