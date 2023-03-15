import argparse
import collections
import json
import glob
import os
import sys
# Check if Python version is 3.6 or higher (cgi.escape is deprecated/removed for newer versions)
if sys.version_info.major >= 3 and sys.version_info.minor >= 6:
    from html import escape
else:
    from cgi import escape

SEVERITY_ORDER = ["inhibitor", "high", "medium", "low", "info"]


def main():
    parser = get_parser()
    args = parser.parse_args()

    if args.input_directory:
        input_files = glob.glob(os.path.join(args.input_directory, "*.json"))
    else:
        input_files = args.input_files

    grouped_data_list = [parse_leapp_report(input_file) for input_file in input_files]
    merged_grouped_data = merge_grouped_data(grouped_data_list)
    write_grouped_data_to_json(merged_grouped_data, args.output_json)
    html_tables = generate_html_tables(merged_grouped_data)
    write_html_tables_to_file(html_tables, args.output_html)


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
    output_group.add_argument(
        "-o", "--output-json", required=True, help="Output JSON file to store the grouped data"
    )
    output_group.add_argument(
        "-t", "--output-html", required=True, help="Output HTML file to store the tables with grouped data"
    )

    return parser


def parse_leapp_report(report_file):
    with open(report_file, "r") as f:
        report_data = json.load(f)

    grouped_data = collections.defaultdict(lambda: collections.defaultdict(set))
    for entry in report_data["entries"]:
        severity = entry["severity"]
        entry_flags = entry.get("flags", entry.get("groups", []))
        if "inhibitor" in entry_flags:
            severity = "inhibitor"
        grouped_data[severity][entry["title"]].add(entry["hostname"])

    return grouped_data


def merge_grouped_data(grouped_data_list):
    """Merge grouped data from multiple reports into one. And sort entries and hostnames alphabetically."""
    merged_data = collections.defaultdict(lambda: collections.defaultdict(set))

    for grouped_data in grouped_data_list:
        for severity, entries in grouped_data.items():
            for entry_title, hostnames in entries.items():
                merged_data[severity][entry_title].update(hostnames)

    ordered_merged_data = collections.OrderedDict()
    for severity in SEVERITY_ORDER:
        if severity in merged_data:
            # Sort entries and hostnames alphabetically
            ordered_merged_data[severity] = collections.OrderedDict(
                sorted(
                    ((entry_title, sorted(list(hostnames))) for entry_title, hostnames in merged_data[severity].items()),
                    key=lambda x: x[0]
                )
            )

    return ordered_merged_data


def write_grouped_data_to_json(grouped_data, output_file):
    with open(output_file, "w") as f:
        json.dump(grouped_data, f, indent=2)


def generate_html_tables(grouped_data):
    html_tables = ""

    for severity in grouped_data:
        entries = grouped_data[severity]

        html_table = "<h2>{}</h2>\n".format(severity.capitalize())
        html_table += "<table border='1' cellpadding='5' cellspacing='0'>\n"
        html_table += "<tr><th>Entry Title</th><th>Hostnames</th></tr>\n"
        for entry_title, hostnames in entries.items():
            escaped_entry_title = escape(entry_title, quote=True)
            html_table += "<tr><td>{}</td><td>{}</td></tr>\n".format(escaped_entry_title, ", ".join(hostnames))
        html_table += "</table>"

        html_tables += html_table + "<br>\n"

    return html_tables


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
