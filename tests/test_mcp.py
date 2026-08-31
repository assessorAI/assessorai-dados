from mcp import Client

from assessorai_dados.mcp_server import mcp


async def test_mcp_advertises_read_only_tools():
    async with Client(mcp) as client:
        result = await client.list_tools()

    names = {tool.name for tool in result.tools}
    assert names == {
        "find_related_propositions",
        "get_dataset_download",
        "get_dataset_release",
        "get_proposition",
        "list_sources",
        "read_proposition_text",
        "search_propositions",
    }
