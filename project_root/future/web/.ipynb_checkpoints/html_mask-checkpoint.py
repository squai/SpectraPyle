from spectraPyle.schema.schema import StackingConfig
import json

def generate_html_mask():

    schema = StackingConfig.model_json_schema()

    html = "<form>\n"

    for name, prop in schema["properties"].items():

        title = prop.get("title", name)
        typ = prop.get("type", "string")

        html += f"<label>{title}</label>"

        if typ == "string":
            html += f'<input name="{name}" type="text"/><br>'

        elif typ == "number":
            html += f'<input name="{name}" type="number"/><br>'

        elif typ == "boolean":
            html += f'<input name="{name}" type="checkbox"/><br>'

        html += "<br>"

    html += "</form>"

    return html
