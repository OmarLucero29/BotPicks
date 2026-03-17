class DataSystemPipeline:

    name = "data_system_pipeline"

    DATA_PIPELINE_ORDER = [

        "source_discovery_engine",
        "provider_evaluator_engine",
        "source_registry_engine",
        "source_test_engine",
        "source_layer_engine",

        "api_ingestion_engine",
        "scraper_ingestion_engine",
        "historical_ingestion_engine",
        "rate_limit_engine",
        "data_storage_engine",
        "acquisition_layer_engine",

        "stream_connection_engine",
        "stream_buffer_engine",
        "stream_parser_engine",
        "stream_feature_engine",
        "stream_layer_engine",

        "event_reconstruction_engine",
        "market_reconstruction_engine",
        "odds_reconstruction_engine",
        "statistics_reconstruction_engine",
        "dataset_builder_engine",

        "source_alignment_engine",
        "entity_merge_engine",
        "conflict_resolution_engine",
        "consensus_builder_engine",
        "data_unification_engine",

        "sport_normalization_engine",
        "league_normalization_engine",
        "team_normalization_engine",
        "player_normalization_engine",
        "entity_resolution_engine",
        "ontology_builder_engine",

        "schema_validation_engine",
        "odds_validation_engine",
        "probability_validation_engine",
        "outlier_detection_engine",
        "data_quality_scoring_engine",

        "feature_extraction_engine",
        "feature_transformation_engine",
        "feature_storage_engine",
        "feature_serving_engine",

        "dataset_definition_engine",
        "dataset_builder_engine",
        "dataset_split_engine",
        "dataset_storage_engine"

    ]

    def execute(self, context):

        engines = context.get("engine_registry", {})

        for engine_name in self.DATA_PIPELINE_ORDER:

            engine = engines.get(engine_name)

            if not engine:
                continue

            try:

                engine.execute(context)

            except Exception as e:

                context["logger"].error(f"Pipeline error {engine_name} {e}")

        context["logger"].info("DATA PIPELINE COMPLETED")