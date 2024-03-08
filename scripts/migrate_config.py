# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import argparse
import yaml

config_map = {
    "auth_basic_users": "auth.basic.users",
    "auth_lp_teams": "auth.sso.teams",
    "auth_sso_location": "auth.sso.url",
    "auth_sso_public_key": "auth.sso.public-key",
    "blocklist_cache_refresh": "patch-blocklist.refresh-interval",
    "burst_limit": "server.burst-limit",
    "cloud_delay_default_delay_hours": "cloud_delay.default_delay_hours",
    "concurrency_limit": "server.concurrency-limit",
    "contract_server_password": "contracts.password",
    "contract_server_url": "contracts.url",
    "contract_server_user": "contracts.user",
    "dbconn_max_lifetime": "database.connection-lifetime-max",
    "dbconn_max": "database.connection-pool-max",
    "event_bus_brokers": "machine-reports.event-bus.brokers",
    "event_bus_ca_cert": "machine-reports.event-bus.ca-cert",
    "event_bus_client_cert": "machine-reports.event-bus.client-cert",
    "event_bus_client_key": "machine-reports.event-bus.client-key",
    "http_proxy": "patch-sync.proxy.http",
    "https_proxy": "patch-sync.proxy.https",
    "influxdb_bucket": "influx.bucket",
    "influxdb_organization": "influx.organization",
    "influxdb_token": "influx.token",
    "influxdb_url": "influx.url",
    "is_cloud_delay_enabled": "cloud_delay.enabled",
    "kpi_reports": "kpi-reports.interval",
    "log_level": "server.log-level",
    "no_proxy": "patch-sync.proxy.no-proxy",
    "patch_cache_on": "patch-cache.enabled",
    "patch_cache_size": "patch-cache.cache-size",
    "patch_cache_ttl": "patch-cache.cache-ttl",
    "patch_sync_enabled": "patch-sync.enabled",
    "patchstore": "patch-storage.type",
    "profiler_block_profile_rate": "profiler.block_profile_rate",
    "profiler_enabled": "profiler.enabled",
    "profiler_hostname": "profiler.hostname",
    "profiler_mutex_profile_fraction": "profiler.mutex_profile_fraction",
    "profiler_profile_allocations": "profiler.profile_allocations",
    "profiler_profile_blocks": "profiler.profile_blocks",
    "profiler_profile_goroutines": "profiler.profile_goroutine",
    "profiler_profile_inuse": "profiler.profile_inuse",
    "profiler_profile_mutexes": "profiler.profile_mutexes",
    "profiler_sample_rate": "profiler.sample_rate",
    "profiler_server_address": "profiler.server_address",
    "profiler_upload_rate": "profiler.upload_rate",
    "psql_dbname": "database.name",
    "psql_roles": None,
    "report_cleanup_interval": "machine-reports.database.cleanup-interval",
    "report_cleanup_row_limit": "machine-reports.database.cleanup-row-limit",
    "report_retention": "machine-reports.database.retention-days",
    "s3_access_key_id": "patch-storage.s3-access-key",
    "s3_bucket": "patch-storage.s3-bucket",
    "s3_endpoint": "patch-storage.s3-endpoint",
    "s3_region": "patch-storage.s3-region",
    "s3_secret_key": "patch-storage.s3-secret-key",
    "s3_secure": "patch-storage.s3-secure",
    "storage_path": "patch-storage.filesystem-path",
    "swift_apikey": "patch-storage.swift-api-key",
    "swift_auth_url": "patch-storage.swift-auth-url",
    "swift_container_name": "patch-storage.swift-container",
    "swift_domain_name": "patch-storage.swift-domain",
    "swift_region_name": "patch-storage.swift-region",
    "swift_tenant_name": "patch-storage.swift-tenant",
    "swift_username": "patch-storage.swift-username",
    "sync_flavors": "patch-sync.flavors",
    "sync_identity": None,
    "sync_interval": "patch-sync.interval",
    "sync_minimum_kernel_version": "patch-sync.minimum-kernel-version",
    "sync_tier": None,
    "sync_token": "patch-sync.token",
    "sync_upstream_tier": None,
    "sync_upstream": "patch-sync.upstream-url",
    "url_template": "server.url-template",
}

additional_config_dict = {
    "auth_basic_users": ("auth.basic.enabled", True),
    "auth_lp_teams": ("auth.sso.enabled", True),
    "auth_sso_location": ("auth.sso.enabled", True),
    "auth_sso_public_key": ("auth.sso.enabled", True),
    "blocklist_cache_refresh": ("patch-blocklist.enabled", True),
    "contract_server_password": ("contracts.enabled", True),
    "contract_server_user": ("contracts.enabled", True),
    "event_bus_brokers": ("machine-reports.event-bus.enabled", True),
    "event_bus_ca_cert": ("machine-reports.event-bus.enabled", True),
    "event_bus_client_cert": ("machine-reports.event-bus.enabled", True),
    "event_bus_client_key": ("machine-reports.event-bus.enabled", True),
    "filebacked": ("patch-storage.type", "filesystem"),
    "http_proxy": ("patch-sync.proxy.enabled", True),
    "https_proxy": ("patch-sync.proxy.enabled", True),
    "kpi_reports": ("kpi-reports.enabled", True),
    "no_proxy": ("patch-sync.proxy.enabled", True),
    "sync_architectures": ("patch-sync.enabled", True),
    "sync_flavors": ("patch-sync.enabled", True),
    "sync_interval": ("patch-sync.enabled", True),
    "sync_minimum_kernel_version": ("patch-sync.enabled", True),
    "sync_token": ("patch-sync.enabled", True),
    "sync_upstream": ("patch-sync.enabled", True),
}


def parse_input_file(input_file_path: str):
    with open(input_file_path, "r") as yaml_stream:
        yaml_data = yaml.load(yaml_stream, Loader=yaml.FullLoader)
        return yaml_data


def main(input_file, output_file):
    json_content = parse_input_file(input_file)
    settings = json_content.get("options", {})
    if settings == {}:
        settings = json_content.get("settings", {})
    if settings == {}:
        print("No settings found")
        exit(-1)
    converted_options = {}
    removed_keys = []
    unrecognized_keys = []
    for key, val in settings.items():
        if key in additional_config_dict:
            add_conf_key, add_conf_val = additional_config_dict[key]
            converted_options[add_conf_key] = add_conf_val
        if key in config_map:
            if config_map[key]:
                if "value" not in val:
                    raise ValueError(f"{key} doesn't have a set value for it")
                parsed_val = val.get("value")
                converted_options[config_map[key]] = parsed_val
            else:
                removed_keys.append(key)
        if key not in additional_config_dict and key not in config_map:
            unrecognized_keys.append(key)
    print(
        "These keys were present in your configuration",
        "but they are removed for the new config.\n",
        removed_keys,
    )
    print("\nUnrecognized keys: ", unrecognized_keys)
    new_config = {"options": converted_options}
    with open(f"{output_file}", "w") as f:
        yaml.dump(new_config, f)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process input and write to output file")
    parser.add_argument("-i", "--input_file", help="input file full path")
    parser.add_argument("-o", "--output_file", help="output file full path")
    args = parser.parse_args()

    main(args.input_file, args.output_file)
