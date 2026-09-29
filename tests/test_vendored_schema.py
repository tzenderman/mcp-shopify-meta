"""The vendored Shopify Admin schema must validate a query under the installed graphql-core.

The other validator tests use a mini fixture schema, which is why graphql-core
3.3.0 broke every execute_graphql call without a single test failing: the new
rule only trips on the real Shopify schema. Raising the graphql-core bound must
keep this test green.
"""

from shopify_meta.utils.schema_loader import get_graphql_schema
from shopify_meta.utils.validator import validate_query


def test_vendored_schema_validates_trivial_query():
    result = validate_query(get_graphql_schema(), "{ shop { name } }")
    assert result["valid"] is True, result["errors"]
