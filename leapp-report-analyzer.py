import argparse
import glob
import json
import logging
import os
import sys
from collections import OrderedDict, defaultdict

# Check if Python version is 3.6 or higher (cgi.escape is deprecated/removed for newer versions)
if sys.version_info.major >= 3 and sys.version_info.minor >= 6:
    from html import escape
else:
    from cgi import escape

SEVERITY_ORDER = ["inhibitor", "high", "medium", "low", "info"]
HTML_TABLE_OPTIONS = "border='1' cellpadding='5' cellspacing='0'"


def _create_grouped_data_structure():
    # JSON structure: {severity: [key: {title: str, {hostnames: [], remediations: {}}]}
    return defaultdict(lambda: defaultdict(lambda: {"title": "", "hostnames": [], "remediations": []}))


def escape_html(text):
    return escape(text, quote=True)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = get_parser()
    args = parser.parse_args()

    if args.input_directory:
        input_files = glob.glob(os.path.join(args.input_directory, "*.json"))
    else:
        input_files = args.input_files

    logging.info("Processing %d input files", len(input_files))

    grouped_data_list = [parse_leapp_report(input_file) for input_file in input_files]
    merged_grouped_data = merge_grouped_data(grouped_data_list)
    ordered_merged_data = order_grouped_data(merged_grouped_data)

    logging.info("Writing JSON output to %s", args.output_json)
    write_grouped_data_to_json(ordered_merged_data, args.output_json)

    logging.info("Writing HTML output to %s", args.output_html)
    html_tables = generate_html_tables(ordered_merged_data)
    write_html_tables_to_file(html_tables, args.output_html)

    logging.info("Results written to %s and %s", args.output_json, args.output_html)


def get_parser():
    parser = argparse.ArgumentParser(description="Analyze leapp reports and group systems by severity and entries.")

    input_group = parser.add_argument_group("input", "Input options (at least one required)")
    input_group_exclusive = input_group.add_mutually_exclusive_group(required=True)
    input_group_exclusive.add_argument(
        "-f", "--input-files", nargs="+", metavar="INPUT_FILE", help="leapp report JSON files to be analyzed"
    )
    input_group_exclusive.add_argument(
        "-d", "--input-directory", help="Directory containing leapp report JSON files to be analyzed"
    )

    output_group = parser.add_argument_group("output", "Output options, both required")
    output_group.add_argument("-o", "--output-json", required=True, help="Output JSON file to store the grouped data")
    output_group.add_argument(
        "-t", "--output-html", required=True, help="Output HTML file to store the tables with grouped data"
    )

    return parser


def parse_leapp_report(report_file):
    logging.info("Processing report file: %s", report_file)
    with open(report_file, "r") as f:
        report_data = json.load(f)

    grouped_data = _create_grouped_data_structure()

    for entry in report_data["entries"]:
        severity = entry["severity"]
        title = entry["title"]
        hostname = entry["hostname"]
        entry_flags = entry.get("flags", entry.get("groups", []))
        remediations = entry.get("detail", {}).get("remediations", [])
        # NOTE: use key if exists, otherwise use title (v100 reports may not have key field)
        key = entry.get("key", title)

        if "inhibitor" in entry_flags:
            severity = "inhibitor"

        grouped_data[severity][key]["title"] = title
        grouped_data[severity][key]["hostnames"].append(hostname)
        grouped_data[severity][key]["remediations"] = remediations

    return grouped_data


def merge_grouped_data(grouped_data_list):
    """Merge grouped data from multiple reports into one."""
    merged_data = _create_grouped_data_structure()

    for grouped_data in grouped_data_list:
        for severity, entries in grouped_data.items():
            for key, entry_data in entries.items():
                merged_data[severity][key]["title"] = entry_data["title"]
                merged_data[severity][key]["hostnames"].extend(entry_data["hostnames"])
                # NOTE: remediations should be the same for the same key
                merged_data[severity][key]["remediations"] = entry_data["remediations"]

    return merged_data


def order_grouped_data(grouped_data):
    """Order the data by severity, and entries by entry title. Sort hostnames alphabetically."""
    ordered_data = OrderedDict()
    # Order the data by severity
    for severity in SEVERITY_ORDER:
        if severity in grouped_data:
            # Sort entries (by title) and hostnames alphabetically
            ordered_data[severity] = OrderedDict(
                sorted(
                    ((key, {
                        "title": entry_data["title"],
                        "hostnames": sorted(entry_data["hostnames"]),
                        "remediations": entry_data["remediations"]
                    }) for key, entry_data in grouped_data[severity].items()),
                    key=lambda x: x[1]["title"]
                )
            )
    return ordered_data


def write_grouped_data_to_json(grouped_data, output_file):
    with open(output_file, "w") as f:
        json.dump(grouped_data, f, indent=2)


def generate_html_tables(grouped_data):
    html_tables = generate_severity_legend_table()

    for severity in grouped_data:
        entries = grouped_data[severity]

        html_table = "<h2>{}</h2>\n".format(severity.capitalize())
        html_table += "<table {}>\n".format(HTML_TABLE_OPTIONS)
        html_table += "<tr><th>Entry Title</th><th>Hostnames</th><th>Remediations</th></tr>\n"
        for key, entry_data in entries.items():
            escaped_entry_title = escape_html(entry_data["title"])
            hostnames = ", ".join(entry_data["hostnames"])

            remediations = []
            for remediation in entry_data["remediations"]:
                type = remediation["type"]
                context = remediation["context"]

                if type == "hint":
                    remediations.append(escape_html(context))
                elif type == "playbook":
                    remediations.append("Path to Ansible playbook: <code>{}</code>".format(escape_html(context)))
                elif type == "command":
                    command_context = " ".join(context)
                    remediations.append("Command: <code>{}</code>".format(escape_html(command_context)))

            remediations_html = "<br>".join(remediations)

            html_table += "<tr><td>{}</td><td>{}</td><td>{}</td></tr>\n".format(
                escaped_entry_title, hostnames, remediations_html
            )
        html_table += "</table>"

        html_tables += html_table + "<br>\n"

    return html_tables


def generate_severity_legend_table():
    html_table = "<h3>Severity Levels Legend</h3>\n"
    html_table += "<table {}>\n".format(HTML_TABLE_OPTIONS)
    html_table += "<tr><th>Severity</th><th>Description</th></tr>\n"
    html_table += "<tr style='background-color: #ff6666'><td>Inhibitor</td><td>Will inhibit (hard stop) the upgrade process, otherwise the system could become unbootable, inaccessible, or dysfunctional.</td></tr>\n"
    html_table += "<tr style='background-color: #ffcc66'><td>High</td><td>Very likely to result in a deteriorated system state.</td></tr>\n"
    html_table += "<tr style='background-color: #ffff66'><td>Medium</td><td>Can impact both the system and applications.</td></tr>\n"
    html_table += "<tr style='background-color: #ccff66'><td>Low</td><td>Should not impact the system but can have an impact on applications.</td></tr>\n"
    html_table += "<tr style='background-color: #66ff66'><td>Info</td><td>Informational with no expected impact to the system or applications.</td></tr>\n"
    html_table += "</table><br>"
    return html_table


def write_html_tables_to_file(html_tables, output_file):
    html_template = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Leapp Report Analyzer</title>
    <style>table, th, td {{border: 1px solid black;}}</style>
</head>
<body>
{content}
</body>
</html>
"""
    with open(output_file, "w") as f:
        f.write(html_template.format(content=html_tables))


if __name__:
    main()
