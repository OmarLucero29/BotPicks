from layers.sports_modeling.knowledge_graph.knowledge_graph_layer_engine import Engine as KG
from layers.sports_modeling.game_representation.game_representation_layer_engine import Engine as GR
from layers.sports_modeling.physics_dynamics.physics_dynamics_layer_engine import Engine as PD
from layers.sports_modeling.human_behavior.human_behavior_layer_engine import Engine as HB
from layers.sports_modeling.match_context.match_context_layer_engine import Engine as MC
from layers.sports_modeling.digital_twin.sports_digital_twin_layer_engine import Engine as DT


class Pipeline:

    name = "sports_modeling_pipeline"

    def __init__(self):

        self.engines = [

            KG(),
            GR(),
            PD(),
            HB(),
            MC(),
            DT()

        ]

    def run(self, context):

        for engine in self.engines:

            engine.initialize(context)
            engine.execute(context)