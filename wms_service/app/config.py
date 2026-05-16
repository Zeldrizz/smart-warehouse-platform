from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    kafka_brokers: str = "kafka-1:29092,kafka-2:29093"
    schema_registry_url: str = "http://schema-registry:8081"
    kafka_topic: str = "warehouse-events"
    service_port: int = 8001
    generator_enabled: bool = False
    generator_seed: int = 42
    generator_live_events_per_minute: int = 180
    generator_product_count: int = 320
    generator_supplier_count: int = 32


settings = Settings()
