import asyncio
import json

from src.jawafdehi_mcp.tools.jawafdehi_cases import (
    GetJawafdehiCaseTool,
    SearchJawafdehiCasesTool,
)


async def main():
    print("Testing SearchJawafdehiCasesTool...")
    search_tool = SearchJawafdehiCasesTool()
    res = await search_tool.execute({})

    data = json.loads(res[0].text)
    print(f"Found {data['count']} cases.")

    if data["count"] > 0:
        first_case = data["results"][0]
        first_case_id = first_case["id"]
        first_case_slug = first_case.get("slug", "")
        print(
            f"\nTesting GetJawafdehiCaseTool (with sources) for case {first_case_id} (slug={first_case_slug})..."
        )
        get_tool = GetJawafdehiCaseTool()
        res_get = await get_tool.execute(
            {"slug": first_case_slug, "fetch_sources": True}
        )

        get_data = json.loads(res_get[0].text)
        print(f"Case Title: {get_data.get('title')}")
        if "_resolved_sources" in get_data:
            print(f"Resolved sources: {len(get_data['_resolved_sources'])}")
        else:
            print("No sources resolved.")
    print("-" * 40)


if __name__ == "__main__":
    asyncio.run(main())
