"""
导出 OpenAPI Schema 命令

使用方式:
    python manage.py export_schema
    python manage.py export_schema --format openapi-json
    python manage.py export_schema --output api_schema.json
"""

from typing import Any

from django.core.management.base import BaseCommand
from drf_spectacular.generators import SchemaGenerator


class Command(BaseCommand):
    help = "导出 OpenAPI Schema"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--format",
            type=str,
            default="openapi-json",
            choices=["openapi-json", "openapi-yaml"],
            help="输出格式 (默认: openapi-json)",
        )
        parser.add_argument(
            "--output", type=str, default="api_schema.json", help="输出文件路径 (默认: api_schema.json)"
        )

    def handle(self, *args: Any, **options: Any) -> None:
        generator = SchemaGenerator()
        schema = generator.get_schema()

        format_type = options["format"]
        output_file = options["output"]

        if format_type == "openapi-json":
            import json

            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(schema, f, ensure_ascii=False, indent=2)
        elif format_type == "openapi-yaml":
            try:
                import yaml

                with open(output_file, "w", encoding="utf-8") as f:
                    yaml.dump(schema, f, allow_unicode=True, default_flow_style=False)
            except ImportError:
                self.stdout.write(self.style.ERROR("需要安装 PyYAML: pip install PyYAML"))
                return

        self.stdout.write(self.style.SUCCESS(f"Schema 已导出到 {output_file}"))
