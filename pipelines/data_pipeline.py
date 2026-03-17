from layers.data.source_intelligence.source_layer_engine import Engine as SourceLayer
from layers.data.acquisition.acquisition_layer_engine import Engine as AcquisitionLayer
from layers.data.reconstruction.reconstruction_layer_engine import Engine as ReconstructionLayer
from layers.data.normalization.normalization_layer_engine import Engine as NormalizationLayer
from layers.data.validation.validation_layer_engine import Engine as ValidationLayer


class Pipeline:

    name = "data_pipeline"

    def __init__(self):

        self.engines = [

            SourceLayer(),
            AcquisitionLayer(),
            ReconstructionLayer(),
            NormalizationLayer(),
            ValidationLayer()

        ]

    def run(self, context):

        for engine in self.engines:

            engine.initialize(context)
            engine.execute(context)