{#
  By default dbt names custom schemas "<default>_<custom>" (e.g. main_silver).
  This override makes the schema exactly what we configure: silver, gold.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
