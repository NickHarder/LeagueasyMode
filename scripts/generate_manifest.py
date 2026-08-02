import os
import re
from datetime import datetime

import yaml


def generate_manifest() -> None:
    base_dir = os.path.dirname(os.path.dirname(__file__))
    config_path = os.path.join(base_dir, "rules_config.yaml")
    rules_dir = os.path.join(base_dir, "rules")
    output_path = os.path.join(base_dir, "RULES_MANIFEST.md")

    try:
        with open(config_path) as f:
            config_data = yaml.safe_load(f) or {}
            config_rules = config_data.get("rules", {})
    except Exception as e:
        print(f"[ERROR] Could not read config: {e}")
        return

    # Scan the Codebase (Extract actual Rule Names from the Python code)
    discovered_rules = {}
    if os.path.exists(rules_dir):
        for filename in os.listdir(rules_dir):
            if filename.endswith(".py") and filename != "__init__.py":
                filepath = os.path.join(rules_dir, filename)
                with open(filepath, encoding="utf-8") as rf:
                    content = rf.read()

                    # Search the python file for: name="Something" or name='Something'
                    match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
                    if match:
                        rule_name = match.group(1)
                        discovered_rules[rule_name] = filename
                    else:
                        # Fallback if regex fails to find a name string
                        discovered_rules[filename.replace(".py", "")] = filename

    # Consolidate all known rules (Union of Configured + Discovered)
    configured_keys = set(config_rules.keys())
    discovered_keys = set(discovered_rules.keys())
    all_rules = sorted(configured_keys.union(discovered_keys), key=lambda x: x.lower())

    # Build the Unified Markdown Table with Visual Column
    md_content = [
        "# LeagueasyMode: Tactical Rules Manifest\n",
        f"> **Last Auto-Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
        "This manifest tracks the state, priority, and file locations of all macro coaching rules in the engine.\n",
        "| | Rule Name | Status | Priority | Source File |",
        "|---|---|---|---|---|",
    ]

    for rule in all_rules:
        # Scenario A: Rule is in both Config and Code
        if rule in configured_keys and rule in discovered_keys:
            settings = config_rules[rule]
            is_enabled = settings.get("enabled", False)
            priority = settings.get("priority", "Default")

            icon = "🟢" if is_enabled else "🔴"
            status = "Active" if is_enabled else "Disabled"
            filename = f"`{discovered_rules[rule]}`"

        # Scenario B: Rule is in Config, but missing from Code (Ghost)
        elif rule in configured_keys:
            settings = config_rules[rule]
            priority = settings.get("priority", "Default")

            icon = "👻"
            status = "Ghost (Missing File)"
            filename = "N/A"

        # Scenario C: Rule is in Code, but missing from Config (Orphaned)
        else:
            priority = "N/A"
            icon = "🟡"
            status = "Orphaned (Not Configured)"
            filename = f"`{discovered_rules[rule]}`"

        md_content.append(f"| {icon} | **{rule}** | {status} | {priority} | {filename} |")

    with open(output_path, "w") as f:
        f.write("\n".join(md_content))

    print(f"[SUCCESS] Generated rule documentation at {output_path}")


if __name__ == "__main__":
    generate_manifest()
