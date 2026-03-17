from layers.market_modeling.market_microstructure.market_microstructure_layer_engine import Engine as MM
from layers.market_modeling.odds_formation.odds_formation_layer_engine import Engine as OF
from layers.market_modeling.sharp_money.sharp_money_layer_engine import Engine as SM
from layers.market_modeling.liquidity_depth.liquidity_depth_layer_engine import Engine as LD
from layers.market_modeling.bookmaker_behavior.bookmaker_behavior_layer_engine import Engine as BB
from layers.market_modeling.market_sentiment.market_sentiment_layer_engine import Engine as MS
from layers.market_modeling.market_regime.market_regime_layer_engine import Engine as MR
from layers.market_modeling.market_ecology.market_ecology_layer_engine import Engine as ME


class Pipeline:

    name = "market_modeling_pipeline"

    def __init__(self):

        self.engines = [

            MM(),
            OF(),
            SM(),
            LD(),
            BB(),
            MS(),
            MR(),
            ME()

        ]

    def run(self, context):

        for engine in self.engines:

            engine.initialize(context)
            engine.execute(context)