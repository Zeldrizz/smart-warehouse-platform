from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_port: int = 8002
    kafka_brokers: str = "kafka-1:29092,kafka-2:29093"
    schema_registry_url: str = "http://schema-registry:8081"
    kafka_topic: str = "warehouse-events"
    kafka_dlq_topic: str = "warehouse-events-dlq"
    kafka_consumer_group: str = "warehouse-state-consumer"
    cassandra_contact_points: str = "cassandra-1,cassandra-2,cassandra-3"
    cassandra_port: int = 9042
    cassandra_keyspace: str = "warehouse"
    consumer_poll_timeout: float = 1.0
    lag_refresh_seconds: float = 5.0
    healthcheck_seconds: float = 10.0
    analytics_lookback_days_default: int = 14


settings = Settings()
