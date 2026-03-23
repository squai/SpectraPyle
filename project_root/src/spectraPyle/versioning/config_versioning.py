# CONFIG VERSIONING

LATEST_VERSION = "1.0.0"

MIGRATIONS = {
    "0.9.0": "migrate_090_to_100",
}

def migrate_090_to_100(cfg_dict):
    # example
    if "normalization_type" in cfg_dict:
        cfg_dict["norm"] = {"normalization": cfg_dict.pop("normalization_type")}
    return cfg_dict

def load_config_with_migration(data):

    version = data.get("config_version", "0.9.0")

    while version != LATEST_VERSION:
        migrate_fn = MIGRATION_FUNCS[version]
        data = migrate_fn(data)
        version = next_version(version)

    return data
