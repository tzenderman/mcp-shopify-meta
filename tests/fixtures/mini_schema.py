"""A small hand-rolled GraphQL introspection JSON for fast schema tests.

This mirrors the shape Shopify returns from a full introspection query
but with only a handful of types so tests stay deterministic and fast.
"""

MINI_INTROSPECTION = {
    "__schema": {
        "queryType": {"name": "QueryRoot"},
        "mutationType": {"name": "Mutation"},
        "subscriptionType": None,
        "types": [
            {
                "kind": "OBJECT",
                "name": "QueryRoot",
                "description": "The root query type.",
                "fields": [
                    {
                        "name": "shop",
                        "description": "Returns the current Shop.",
                        "args": [],
                        "type": {"kind": "NON_NULL", "name": None, "ofType": {"kind": "OBJECT", "name": "Shop", "ofType": None}},
                        "isDeprecated": False,
                        "deprecationReason": None,
                    },
                    {
                        "name": "product",
                        "description": "Look up a Product by ID.",
                        "args": [
                            {"name": "id", "description": "Product GID", "type": {"kind": "NON_NULL", "name": None, "ofType": {"kind": "SCALAR", "name": "ID", "ofType": None}}, "defaultValue": None}
                        ],
                        "type": {"kind": "OBJECT", "name": "Product", "ofType": None},
                        "isDeprecated": False,
                        "deprecationReason": None,
                    },
                    {
                        "name": "products",
                        "description": "List products on the shop.",
                        "args": [
                            {"name": "first", "description": "Page size", "type": {"kind": "SCALAR", "name": "Int", "ofType": None}, "defaultValue": None},
                            {"name": "query", "description": "Shopify search query", "type": {"kind": "SCALAR", "name": "String", "ofType": None}, "defaultValue": None},
                        ],
                        "type": {"kind": "OBJECT", "name": "ProductConnection", "ofType": None},
                        "isDeprecated": False,
                        "deprecationReason": None,
                    },
                ],
                "inputFields": None,
                "interfaces": [],
                "enumValues": None,
                "possibleTypes": None,
            },
            {
                "kind": "OBJECT",
                "name": "Mutation",
                "description": "The root mutation type.",
                "fields": [
                    {
                        "name": "productCreate",
                        "description": "Creates a product.",
                        "args": [
                            {"name": "input", "description": None, "type": {"kind": "NON_NULL", "name": None, "ofType": {"kind": "INPUT_OBJECT", "name": "ProductInput", "ofType": None}}, "defaultValue": None}
                        ],
                        "type": {"kind": "OBJECT", "name": "ProductCreatePayload", "ofType": None},
                        "isDeprecated": False,
                        "deprecationReason": None,
                    },
                    {
                        "name": "productUpdate",
                        "description": "Updates a product.",
                        "args": [
                            {"name": "input", "description": None, "type": {"kind": "NON_NULL", "name": None, "ofType": {"kind": "INPUT_OBJECT", "name": "ProductInput", "ofType": None}}, "defaultValue": None}
                        ],
                        "type": {"kind": "OBJECT", "name": "ProductUpdatePayload", "ofType": None},
                        "isDeprecated": False,
                        "deprecationReason": None,
                    },
                ],
                "inputFields": None,
                "interfaces": [],
                "enumValues": None,
                "possibleTypes": None,
            },
            {
                "kind": "OBJECT",
                "name": "Shop",
                "description": "A Shopify storefront.",
                "fields": [
                    {"name": "id", "description": "Shop GID", "args": [], "type": {"kind": "NON_NULL", "name": None, "ofType": {"kind": "SCALAR", "name": "ID", "ofType": None}}, "isDeprecated": False, "deprecationReason": None},
                    {"name": "name", "description": "Shop name", "args": [], "type": {"kind": "SCALAR", "name": "String", "ofType": None}, "isDeprecated": False, "deprecationReason": None},
                    {"name": "primaryDomain", "description": "Primary domain", "args": [], "type": {"kind": "OBJECT", "name": "Domain", "ofType": None}, "isDeprecated": False, "deprecationReason": None},
                ],
                "inputFields": None,
                "interfaces": [],
                "enumValues": None,
                "possibleTypes": None,
            },
            {
                "kind": "OBJECT",
                "name": "Product",
                "description": "A product in the shop.",
                "fields": [
                    {"name": "id", "description": None, "args": [], "type": {"kind": "NON_NULL", "name": None, "ofType": {"kind": "SCALAR", "name": "ID", "ofType": None}}, "isDeprecated": False, "deprecationReason": None},
                    {"name": "title", "description": "Product title", "args": [], "type": {"kind": "SCALAR", "name": "String", "ofType": None}, "isDeprecated": False, "deprecationReason": None},
                    {"name": "status", "description": "Product status", "args": [], "type": {"kind": "ENUM", "name": "ProductStatus", "ofType": None}, "isDeprecated": False, "deprecationReason": None},
                    {"name": "handle", "description": "URL handle", "args": [], "type": {"kind": "SCALAR", "name": "String", "ofType": None}, "isDeprecated": False, "deprecationReason": None},
                ],
                "inputFields": None,
                "interfaces": [],
                "enumValues": None,
                "possibleTypes": None,
            },
            {
                "kind": "OBJECT",
                "name": "Domain",
                "description": "A storefront domain.",
                "fields": [
                    {"name": "host", "description": None, "args": [], "type": {"kind": "SCALAR", "name": "String", "ofType": None}, "isDeprecated": False, "deprecationReason": None}
                ],
                "inputFields": None,
                "interfaces": [],
                "enumValues": None,
                "possibleTypes": None,
            },
            {
                "kind": "OBJECT",
                "name": "ProductConnection",
                "description": None,
                "fields": [
                    {"name": "edges", "description": None, "args": [], "type": {"kind": "LIST", "name": None, "ofType": {"kind": "OBJECT", "name": "ProductEdge", "ofType": None}}, "isDeprecated": False, "deprecationReason": None}
                ],
                "inputFields": None,
                "interfaces": [],
                "enumValues": None,
                "possibleTypes": None,
            },
            {
                "kind": "OBJECT",
                "name": "ProductEdge",
                "description": None,
                "fields": [
                    {"name": "node", "description": None, "args": [], "type": {"kind": "OBJECT", "name": "Product", "ofType": None}, "isDeprecated": False, "deprecationReason": None}
                ],
                "inputFields": None,
                "interfaces": [],
                "enumValues": None,
                "possibleTypes": None,
            },
            {
                "kind": "OBJECT",
                "name": "ProductCreatePayload",
                "description": None,
                "fields": [
                    {"name": "product", "description": None, "args": [], "type": {"kind": "OBJECT", "name": "Product", "ofType": None}, "isDeprecated": False, "deprecationReason": None},
                    {"name": "userErrors", "description": None, "args": [], "type": {"kind": "LIST", "name": None, "ofType": {"kind": "OBJECT", "name": "UserError", "ofType": None}}, "isDeprecated": False, "deprecationReason": None},
                ],
                "inputFields": None,
                "interfaces": [],
                "enumValues": None,
                "possibleTypes": None,
            },
            {
                "kind": "OBJECT",
                "name": "ProductUpdatePayload",
                "description": None,
                "fields": [
                    {"name": "product", "description": None, "args": [], "type": {"kind": "OBJECT", "name": "Product", "ofType": None}, "isDeprecated": False, "deprecationReason": None},
                    {"name": "userErrors", "description": None, "args": [], "type": {"kind": "LIST", "name": None, "ofType": {"kind": "OBJECT", "name": "UserError", "ofType": None}}, "isDeprecated": False, "deprecationReason": None},
                ],
                "inputFields": None,
                "interfaces": [],
                "enumValues": None,
                "possibleTypes": None,
            },
            {
                "kind": "OBJECT",
                "name": "UserError",
                "description": "A user-friendly error message.",
                "fields": [
                    {"name": "field", "description": None, "args": [], "type": {"kind": "LIST", "name": None, "ofType": {"kind": "SCALAR", "name": "String", "ofType": None}}, "isDeprecated": False, "deprecationReason": None},
                    {"name": "message", "description": None, "args": [], "type": {"kind": "NON_NULL", "name": None, "ofType": {"kind": "SCALAR", "name": "String", "ofType": None}}, "isDeprecated": False, "deprecationReason": None},
                ],
                "inputFields": None,
                "interfaces": [],
                "enumValues": None,
                "possibleTypes": None,
            },
            {
                "kind": "INPUT_OBJECT",
                "name": "ProductInput",
                "description": "Input for product mutations.",
                "fields": None,
                "inputFields": [
                    {"name": "title", "description": "Product title", "type": {"kind": "SCALAR", "name": "String", "ofType": None}, "defaultValue": None},
                    {"name": "status", "description": "Product status", "type": {"kind": "ENUM", "name": "ProductStatus", "ofType": None}, "defaultValue": None},
                ],
                "interfaces": None,
                "enumValues": None,
                "possibleTypes": None,
            },
            {
                "kind": "ENUM",
                "name": "ProductStatus",
                "description": "Lifecycle of a product.",
                "fields": None,
                "inputFields": None,
                "interfaces": None,
                "enumValues": [
                    {"name": "ACTIVE", "description": "Live", "isDeprecated": False, "deprecationReason": None},
                    {"name": "ARCHIVED", "description": "Archived", "isDeprecated": False, "deprecationReason": None},
                    {"name": "DRAFT", "description": "Not yet live", "isDeprecated": False, "deprecationReason": None},
                ],
                "possibleTypes": None,
            },
            {"kind": "SCALAR", "name": "ID", "description": "Global identifier.", "fields": None, "inputFields": None, "interfaces": None, "enumValues": None, "possibleTypes": None},
            {"kind": "SCALAR", "name": "String", "description": None, "fields": None, "inputFields": None, "interfaces": None, "enumValues": None, "possibleTypes": None},
            {"kind": "SCALAR", "name": "Int", "description": None, "fields": None, "inputFields": None, "interfaces": None, "enumValues": None, "possibleTypes": None},
            {"kind": "SCALAR", "name": "Boolean", "description": None, "fields": None, "inputFields": None, "interfaces": None, "enumValues": None, "possibleTypes": None},
        ],
        "directives": [],
    }
}
